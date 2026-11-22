"""URL validation and authorized key-provider integration.

This module does NOT bypass, skip, or automate any ad, CAPTCHA, anti-bot, or
key-authorization system. It only:

1. validates that a user-supplied link is a well-formed HTTPS link on a
   recognised service domain, and
2. forwards it to ONE operator-configured API that you are authorized to use,
   then reads the result that API legitimately returns.

If no such API is configured, no key is ever produced.
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

# Recognised link domains (edit as needed). A host matches if it equals a
# domain or is a subdomain of it.
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


# --------------------------------------------------------------------------
# URL validation
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    service: str | None = None
    error: str | None = None


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def validate_url(raw: str) -> ValidationResult:
    """Validate a user-supplied URL. Never fetches it."""
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
        if any(_host_matches(host, d) for d in domains):
            return ValidationResult(True, service=service)
    return ValidationResult(False, error="Unsupported service. Use /supported to see the list.")


def url_fingerprint(url: str) -> str:
    """Short hash used in logs instead of the private URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:10]


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
class NoProvider:
    """Used when no authorized API is configured. Never returns a key."""

    name = "none"
    configured = False

    async def fetch_key(self, service: str, url: str) -> KeyResult:
        return KeyResult(
            Status.UNAVAILABLE,
            reason="Automatic key retrieval is not configured.",
        )


@dataclass
class _Outcome:
    pending: bool = False
    job_id: str | None = None
    result: KeyResult | None = None


class AuthorizedApiProvider:
    """Client for ONE operator-configured, authorized HTTPS API.

    Expected API contract (see README):
      POST {api_url}            body: {"service": "...", "url": "..."}
      GET  {api_url}/{job_id}   (only if the POST answered "pending")
    Response JSON: {"status": "pending|completed|failed",
                    "job_id": "...", "key": "..."}

    Outgoing requests are restricted to the configured host; redirects are
    never followed, so the bot cannot be steered to another host (no SSRF).
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
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != self._host:
            raise ValueError("Outgoing request blocked: host is not approved.")

    def _interpret(self, resp: httpx.Response) -> _Outcome:
        if resp.status_code == 429:
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider is rate limiting requests. Try again later."))
        if resp.status_code not in (200, 201, 202):
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider returned an error."))
        try:
            data = resp.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider returned an unexpected response."))

        status = str(data.get("status", "")).lower()
        job_id = data.get("job_id")
        job_id = job_id if isinstance(job_id, str) and _JOB_ID_RE.match(job_id) else None

        if status in ("pending", "processing", "queued"):
            return _Outcome(pending=True, job_id=job_id)
        if status == "completed":
            key = data.get("key")
            if isinstance(key, str) and _KEY_RE.match(key):
                return _Outcome(result=KeyResult(Status.COMPLETED, key=key))
            return _Outcome(result=KeyResult(Status.FAILED, reason="Provider did not return a valid key."))
        return _Outcome(result=KeyResult(Status.FAILED, reason="Provider could not complete this request."))

    async def fetch_key(self, service: str, url: str) -> KeyResult:
        fp = url_fingerprint(url)
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        try:
            async with asyncio.timeout(self._job_timeout):
                async with httpx.AsyncClient(
                    timeout=self._request_timeout, follow_redirects=False, headers=headers
                ) as client:
                    self._assert_allowed(self._api_url)
                    resp = await client.post(self._api_url, json={"service": service, "url": url})
                    outcome = self._interpret(resp)
                    job_id = outcome.job_id

                    while outcome.pending:
                        if not job_id:
                            return KeyResult(Status.FAILED, reason="Provider did not return a job reference.")
                        await asyncio.sleep(self._poll_interval)
                        poll_url = f"{self._api_url}/{job_id}"
                        self._assert_allowed(poll_url)
                        outcome = self._interpret(await client.get(poll_url))
                        job_id = outcome.job_id or job_id

                    return outcome.result or KeyResult(Status.FAILED)
        except (TimeoutError, httpx.TimeoutException):
            log.warning("Provider timeout (link=%s)", fp)
            return KeyResult(Status.TIMEOUT, reason="The provider took too long to respond.")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Provider error %s (link=%s)", type(exc).__name__, fp)
            return KeyResult(Status.FAILED)


def build_provider(settings) -> NoProvider | AuthorizedApiProvider:
    if settings.provider_configured:
        return AuthorizedApiProvider(
            settings.api_url, settings.api_token, settings.request_timeout,
            settings.job_timeout, settings.poll_interval,
        )
    return NoProvider()
