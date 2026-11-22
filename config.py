"""Validated settings for Telegram + optional Discord relay / authorized API."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / '.env'
load_dotenv(ENV_FILE)
TOKEN_RE = re.compile(r'^\d{5,}:[A-Za-z0-9_-]{30,}$')
SECRET_RE = re.compile(r'^[A-Za-z0-9_-]{16,256}$')

class ConfigError(RuntimeError):
    pass

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
    telegram_group_id: int | None
    discord_bot_token: str | None
    discord_channel_id: int | None
    discord_result_bot_id: int | None
    discord_result_timeout: int

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_base_url)

    @property
    def provider_configured(self) -> bool:
        return bool(self.api_url and self.api_token)

    @property
    def discord_configured(self) -> bool:
        return bool(self.discord_bot_token and self.discord_channel_id and self.discord_result_bot_id)


def _get(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip().strip('"').strip("'").strip() or None if v is not None else None


def _num(name: str, default: float, min_value: float, errors: list[str], cast=float):
    raw = _get(name)
    if raw is None:
        return cast(default)
    try:
        val = cast(raw)
        if val < min_value:
            raise ValueError()
        return val
    except ValueError:
        errors.append(f'{name} must be a number >= {min_value}.')
        return cast(default)


def _optional_id(name: str, errors: list[str], negative=False) -> int | None:
    value = _get(name)
    if not value:
        return None
    try:
        result = int(value)
        if (negative and result >= 0) or (not negative and result <= 0):
            raise ValueError()
        return result
    except ValueError:
        errors.append(f'{name} must be a valid {"negative Telegram group" if negative else "positive Discord"} ID.')
        return None


def load_settings() -> Settings:
    errors: list[str] = []
    token = _get('TELEGRAM_BOT_TOKEN')
    if not token or not TOKEN_RE.fullmatch(token):
        errors.append('TELEGRAM_BOT_TOKEN is missing or invalid (get it from @BotFather).')

    base_url = _get('WEBHOOK_BASE_URL') or _get('RENDER_EXTERNAL_URL')
    secret = _get('WEBHOOK_SECRET')
    if base_url:
        base_url = base_url.rstrip('/')
        parsed = urlparse(base_url)
        if parsed.scheme != 'https' or not parsed.hostname:
            errors.append('WEBHOOK_BASE_URL must be a public HTTPS URL.')
        if not secret or not SECRET_RE.fullmatch(secret):
            errors.append('WEBHOOK_SECRET must be 16-256 characters (letters/digits/_/-).')

    api_url = _get('AUTHORIZED_API_URL')
    api_token = _get('AUTHORIZED_API_TOKEN')
    if bool(api_url) != bool(api_token):
        errors.append('AUTHORIZED_API_URL and AUTHORIZED_API_TOKEN must both be set, or both empty.')
    if api_url:
        parsed = urlparse(api_url)
        if parsed.scheme != 'https' or not parsed.hostname:
            errors.append('AUTHORIZED_API_URL must be an HTTPS URL.')

    group_id = _optional_id('TELEGRAM_GROUP_ID', errors, negative=True)
    discord_token = _get('DISCORD_BOT_TOKEN')
    discord_channel = _optional_id('DISCORD_CHANNEL_ID', errors)
    discord_result_bot = _optional_id('DISCORD_RESULT_BOT_ID', errors)
    if any((discord_token, discord_channel, discord_result_bot)) and not all((discord_token, discord_channel, discord_result_bot)):
        errors.append('Discord relay requires DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, and DISCORD_RESULT_BOT_ID.')

    port = _num('PORT', 10000, 1, errors, int)
    rate_limit = _num('RATE_LIMIT_SECONDS', 30, 1, errors, int)
    req_timeout = _num('REQUEST_TIMEOUT_SECONDS', 15, 1, errors)
    job_timeout = _num('JOB_TIMEOUT_SECONDS', 90, 5, errors)
    poll_interval = _num('POLL_INTERVAL_SECONDS', 3, 1, errors)
    result_timeout = _num('DISCORD_RESULT_TIMEOUT_SECONDS', 180, 10, errors, int)
    log_level = (_get('LOG_LEVEL') or 'INFO').upper()
    if errors:
        raise ConfigError('Startup check failed:\n - ' + '\n - '.join(errors))

    return Settings(
        bot_token=token, webhook_base_url=base_url, webhook_secret=secret,
        port=port, rate_limit_seconds=rate_limit, request_timeout=req_timeout,
        job_timeout=job_timeout, poll_interval=poll_interval,
        api_url=api_url.rstrip('/') if api_url else None, api_token=api_token,
        log_level=log_level, telegram_group_id=group_id,
        discord_bot_token=discord_token, discord_channel_id=discord_channel,
        discord_result_bot_id=discord_result_bot, discord_result_timeout=result_timeout,
    )
