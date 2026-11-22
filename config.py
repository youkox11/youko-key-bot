"""Configuration loading and startup validation for YOUKO AUTO KEY BOT V2.

Secrets are read only from environment variables (or a local .env file).
Validation errors name the variables involved but never print their values.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    webhook_base_url: str | None
    webhook_secret: str | None
    port: int
    rate_limit_seconds: int
    request_timeout: float
    job_timeout: float
    poll_interval: float
    api_url: str | None
    api_token: str | None
    log_level: str

    @property
    def use_webhook(self) -> bool:
        return self.webhook_base_url is not None

    @property
    def provider_configured(self) -> bool:
        return self.api_url is not None and self.api_token is not None


def _get(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip().strip('"').strip("'").strip()
    return value or None


def _number(name: str, default: float, minimum: float, problems: list[str], cast=float):
    raw = _get(name)
    if raw is None:
        return cast(default)
    try:
        value = cast(raw)
    except ValueError:
        problems.append(f"{name} must be a number.")
        return cast(default)
    if value < minimum:
        problems.append(f"{name} must be at least {minimum}.")
        return cast(default)
    return value


def load_settings() -> Settings:
    missing: list[str] = []
    problems: list[str] = []

    token = _get("TELEGRAM_BOT_TOKEN")
    if token is None:
        missing.append("TELEGRAM_BOT_TOKEN")
    elif not _TOKEN_RE.match(token):
        problems.append(
            "TELEGRAM_BOT_TOKEN is set but its format looks wrong. "
            "Copy it again from @BotFather (no quotes, no spaces)."
        )

    # Webhook mode is used when a public HTTPS base URL is available
    # (Render sets RENDER_EXTERNAL_URL automatically). Otherwise: long polling.
    base_url = _get("WEBHOOK_BASE_URL") or _get("RENDER_EXTERNAL_URL")
    secret = _get("WEBHOOK_SECRET")
    if base_url:
        base_url = base_url.rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            problems.append("WEBHOOK_BASE_URL must be a public https:// URL.")
        if secret is None:
            missing.append("WEBHOOK_SECRET (required in webhook mode)")
        elif not _SECRET_RE.match(secret):
            problems.append(
                "WEBHOOK_SECRET must be 16-256 characters using only "
                "letters, digits, '_' and '-'."
            )

    api_url = _get("AUTHORIZED_API_URL")
    api_token = _get("AUTHORIZED_API_TOKEN")
    if bool(api_url) != bool(api_token):
        problems.append(
            "AUTHORIZED_API_URL and AUTHORIZED_API_TOKEN must be set together "
            "(or both left empty)."
        )
    if api_url:
        parsed_api = urlparse(api_url)
        if parsed_api.scheme != "https" or not parsed_api.hostname:
            problems.append("AUTHORIZED_API_URL must be an https:// URL.")

    port = _number("PORT", 10000, 1, problems, int)
    rate_limit = _number("RATE_LIMIT_SECONDS", 30, 1, problems, int)
    request_timeout = _number("REQUEST_TIMEOUT_SECONDS", 15, 1, problems, float)
    job_timeout = _number("JOB_TIMEOUT_SECONDS", 90, 5, problems, float)
    poll_interval = _number("POLL_INTERVAL_SECONDS", 3, 1, problems, float)
    log_level = (_get("LOG_LEVEL") or "INFO").upper()

    if missing or problems:
        lines = ["Startup check failed."]
        if missing:
            lines.append("Missing environment variables:")
            lines += [f"  - {name}" for name in missing]
        if problems:
            lines.append("Problems found:")
            lines += [f"  - {text}" for text in problems]
        if not ENV_FILE.exists():
            lines.append(
                f"No .env file found at: {ENV_FILE}\n"
                "Create it with: copy .env.example .env  (then edit it), "
                "or set the variables in your shell / Render dashboard."
            )
            if (BASE_DIR / ".env.txt").exists():
                lines.append("Found '.env.txt' - rename it to '.env' (Notepad adds .txt).")
        raise ConfigError("\n".join(lines))

    return Settings(
        bot_token=token,  # type: ignore[arg-type]
        webhook_base_url=base_url,
        webhook_secret=secret,
        port=port,
        rate_limit_seconds=rate_limit,
        request_timeout=request_timeout,
        job_timeout=job_timeout,
        poll_interval=poll_interval,
        api_url=api_url.rstrip("/") if api_url else None,
        api_token=api_token,
        log_level=log_level,
    )
