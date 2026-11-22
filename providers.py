"""URL validation and integration with an operator-authorized HTTPS API.

The provider must be used only for requests permitted by its terms. It does
not solve CAPTCHAs, simulate authorization, or invent keys. The provider API
must return an actual key for this module to report success.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

SERVICE_DOMAINS: dict[str, tuple[str, ...]] = {
    "LootLabs": (
        "lootlabs.gg", "loot-link.com", "loot-links.com",
        "lootdest.com", "lootdest.org", "lootdest.info",
    ),
    "Platoboost": ("platoboost.com", "platoboost.net"),
    "Linkvertise": (
        "linkvertise.com", "link-to.net", "direct-link.net",
        "up-to-down.net", "link-center.net", "link-hub.net",
    ),
}
MAX_URL_LENGTH = 2048
_KEY_RE = re.compile(r"^[A-Za-z0-9_\-.:=+/]{4,256}$")
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    service: str | None = None
    error: str | None = None


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def validate_url(raw: str) -> ValidationResult:
    if len(raw) > MAX_URL_LENGTH:
        return ValidationResult(False, error="That link is too long.")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        return ValidationResult(False, error="That link is not valid.")
    if parsed.scheme != "https":
        return ValidationResult(False, error="Only HTTPS links are accepted.")
    if parsed.username or parsed.password:
        return ValidationResult(False, error="Links with credentials are not accepted.")
    if port not in (None, 443):
        return ValidationResult(False, error="Custom ports are not accepted.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return ValidationResult(False, error="That link has no host name.")
    try:
        ipaddress.ip_address(host)
        return ValidationResult(False, error="IP-address links are not accepted.")
    except ValueError:
        pass
    for service, domains in SERVICE_DOMAINS.items():
        if any(_host_matches(host, domain) for domain in domains):
            return ValidationResult(True, service=service)
    return ValidationResult(False, error="Unsupported service. Use /supported to see the list.")


def url_fingerprint(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:10]


class Status(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class KeyResult:
    status: Status
    key: str | None = None
    reason: str = "Provider unavailable or unsupported."


class NoProvider:
    name = "none"
    configured = False

    async def fetch_key(self, service: str, url: str) -> KeyResult:
        return KeyResult(Status.UNAVAILABLE, reason="Automatic key retrieval is not configured.")


@dataclass
class _Outcome:
    pending: bool = False
    job_id: str | None = None
    result: KeyResult | None = None


class AuthorizedApiProvider:
    """Provider client compatible with the existing bot.py/config.py interface.

    Sends POST {api_url} with x-api-key and {"url": ...}, based on the
    example supplied by the user. The API response schema has NOT been
    verified; only an explicit, valid `key` field is accepted as a key.
    Pending-job polling is supported only if the API supplies a job_id and
    implements GET {api_url}/{job_id}.
    """

    name = "authorized-api"
    configured = True

    def __init__(self, api_url: str, api_token: str, request_timeout: float,
                 job_timeout: float, poll_interval: float) -> None:
        self._api_url = api_url.rstrip("/")
        self._host = (urlparse(self._api_url).hostname or "").lower()
        self._token = api_token
        self._request_timeout = request_timeout
        self._job_timeout = job_timeout
        self._poll_interval = poll_interval

    def _assert_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or
                (parsed.hostname or "").lower() != self._host or
                parsed.username or parsed.password or
                parsed.port not in (None, 443)):
            raise ValueError("Outgoing request blocked: host is not approved.")

    def _interpret(self, resp: httpx.Response) -> _Outcome:
        code = resp.status_code
        if code == 429:
            log.warning("Provider rate limit: HTTP 429")
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider rate limit (HTTP 429). Try later."))
        if code not in (200, 201, 202):
            log.warning("Provider request rejected: HTTP %s", code)
            if code in (401, 403):
                reason = f"Provider authentication/permission error (HTTP {code})."
            elif code in (400, 422):
                reason = f"Provider rejected request format or URL (HTTP {code})."
            elif code >= 500:
                reason = f"Provider server error (HTTP {code})."
            else:
                reason = f"Provider HTTP {code}."
            return _Outcome(result=KeyResult(Status.FAILED, reason=reason))

        try:
            data = resp.json()
        except ValueError:
            log.warning("Provider returned non-JSON response (HTTP %s)", code)
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider returned non-JSON data."))
        if not isinstance(data, dict):
            return _Outcome(result=KeyResult(Status.FAILED, reason="Unexpected provider response format."))

        status = str(data.get("status", "")).lower()
        job_id = data.get("job_id")
        job_id = job_id if isinstance(job_id, str) and _JOB_ID_RE.fullmatch(job_id) else None
        if status in ("pending", "processing", "queued"):
            return _Outcome(pending=True, job_id=job_id)
        if status in ("failed", "error") or data.get("success") is False:
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider reported failure."))

        # Do not confuse a resolved destination URL with an actual key.
        key = data.get("key")
        if status in ("completed", "success", "ok") and isinstance(key, str) and _KEY_RE.fullmatch(key):
            return _Outcome(result=KeyResult(Status.COMPLETED, key=key))
        if isinstance(data.get("url"), str) or isinstance(data.get("destination"), str):
            return _Outcome(result=KeyResult(
                Status.FAILED,
                reason="Provider returned a destination URL, not a key. Check its API response schema.",
            ))
        log.warning("Provider JSON schema differs from expected fields; HTTP %s", code)
        return _Outcome(result=KeyResult(
            Status.FAILED,
            reason="Provider response schema is not supported; check API documentation.",
        ))

    async def fetch_key(self, service: str, url: str) -> KeyResult:
        validation = validate_url(url)
        if not validation.ok or validation.service != service:
            return KeyResult(Status.FAILED, reason=validation.error or "Link service mismatch.")
        fp = url_fingerprint(url)
        headers = {
            "x-api-key": self._token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            async with asyncio.timeout(self._job_timeout):
                async with httpx.AsyncClient(
                    timeout=self._request_timeout,
                    follow_redirects=False,
                    headers=headers,
                ) as client:
                    self._assert_allowed(self._api_url)
                    response = await client.post(self._api_url, json={"url": url})
                    outcome = self._interpret(response)
                    job_id = outcome.job_id
                    while outcome.pending:
                        if not job_id:
                            return KeyResult(Status.FAILED, reason="Provider returned pending without a job reference.")
                        await asyncio.sleep(self._poll_interval)
                        poll_url = f"{self._api_url}/{job_id}"
                        self._assert_allowed(poll_url)
                        outcome = self._interpret(await client.get(poll_url))
                        job_id = outcome.job_id or job_id
                    return outcome.result or KeyResult(Status.FAILED)
        except (TimeoutError, httpx.TimeoutException):
            log.warning("Provider timeout (link=%s)", fp)
            return KeyResult(Status.TIMEOUT, reason="Provider timed out.")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Provider network/config error %s (link=%s)", type(exc).__name__, fp)
            return KeyResult(Status.FAILED, reason="Provider network or configuration error.")


def build_provider(settings) -> NoProvider | AuthorizedApiProvider:
    if settings.provider_configured:
        return AuthorizedApiProvider(
            settings.api_url, settings.api_token, settings.request_timeout,
            settings.job_timeout, settings.poll_interval,
        )
    return NoProvider()
