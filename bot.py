"""YOUKO AUTO KEY BOT V2 - Telegram bot entry point.

Local (Windows):  long polling   (no WEBHOOK_BASE_URL set)
Render:           webhook        (RENDER_EXTERNAL_URL is set by Render)
"""
from __future__ import annotations

import html
import logging
import re
import sys
import time

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import ConfigError, Settings, load_settings
from providers import SERVICE_DOMAINS, Status, build_provider, url_fingerprint, validate_url

log = logging.getLogger("youko")

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

START_TEXT = (
    "🔑 <b>YOUKO KEY BOT</b>\n\n"
    "Welcome! Send me a supported HTTPS link in this private chat and I will "
    "check it and process it through an authorized provider API, if one is "
    "configured.\n\n"
    "Commands:\n"
    "/help - show commands\n"
    "/status - bot and API status\n"
    "/supported - supported services"
)

HELP_TEXT = (
    "<b>Commands</b>\n"
    "/start - welcome message\n"
    "/help - this help\n"
    "/status - bot and API status\n"
    "/supported - supported URL services\n\n"
    "<b>Usage</b>\n"
    "Send one HTTPS link per message, in a private chat with me."
)


class RateLimiter:
    """Simple per-user cooldown."""

    def __init__(self, seconds: int) -> None:
        self._seconds = seconds
        self._last: dict[int, float] = {}

    def remaining(self, user_id: int) -> int:
        now = time.monotonic()
        if len(self._last) > 5000:  # keep memory bounded
            self._last = {u: t for u, t in self._last.items() if now - t < self._seconds}
        last = self._last.get(user_id)
        if last is None:
            return 0
        return max(0, int(self._seconds - (now - last) + 0.999))

    def hit(self, user_id: int) -> None:
        self._last[user_id] = time.monotonic()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(START_TEXT, parse_mode=ParseMode.HTML)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    provider = context.bot_data["provider"]
    mode = "webhook" if settings.use_webhook else "long polling"
    api = "configured ✅" if provider.configured else "not configured ⚠️"
    text = (
        "<b>YOUKO KEY BOT status</b>\n"
        "Bot: online ✅\n"
        f"Mode: {mode}\n"
        f"Authorized key API: {api}\n"
        f"Rate limit: 1 request / {settings.rate_limit_seconds}s per user"
    )
    if not provider.configured:
        text += "\n\nLink validation works. Automatic key retrieval is unavailable until an authorized API is configured."
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def supported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["<b>Supported URL services</b>"]
    for service, domains in SERVICE_DOMAINS.items():
        lines.append(f"• {html.escape(service)}: " + ", ".join(html.escape(d) for d in domains))
    lines.append("\nLinks must start with https://")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None or not message.text:
        return

    match = URL_RE.search(message.text)

    # Privacy: only handle links in private chats so results are never public.
    if chat.type != ChatType.PRIVATE:
        if match:
            await message.reply_text("For your privacy, please send links to me in a private chat.")
        return

    if not match:
        await message.reply_text("Please send a link that starts with https://\nUse /help for commands.")
        return

    url = match.group(0).rstrip(".,;:!?)]}")
    check = validate_url(url)
    if not check.ok:
        await message.reply_text(f"❌ {check.error}")
        return

    provider = context.bot_data["provider"]
    if not provider.configured:
        await message.reply_text(
            f"✅ Valid {check.service} link recognized.\n\n"
            "ℹ️ Automatic key retrieval is unavailable because no authorized "
            "provider API is configured."
        )
        return

    in_flight: set[int] = context.bot_data["in_flight"]
    if user.id in in_flight:
        await message.reply_text("⏳ Your previous request is still processing. Please wait.")
        return

    limiter: RateLimiter = context.bot_data["limiter"]
    wait = limiter.remaining(user.id)
    if wait:
        await message.reply_text(f"⏱ Please wait {wait}s before sending another link.")
        return

    in_flight.add(user.id)
    limiter.hit(user.id)
    log.info("Request user=%s service=%s link=%s", user.id, check.service, url_fingerprint(url))
    try:
        progress = await message.reply_text(f"⏳ Processing your {check.service} link...")
        result = await provider.fetch_key(check.service, url)

        if result.status is Status.COMPLETED and result.key:
            text = (
                "🔑 <b>YOUKO KEY BOT</b>\n\n"
                "✅ <b>Key Ready!</b>\n\n"
                f"<code>{html.escape(result.key)}</code>"
            )
        else:
            text = f"❌ Unable to retrieve a key.\n\nReason: {html.escape(result.reason)}"
        await progress.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as exc:  # noqa: BLE001 - never leak details to users
        log.error("Handler error %s", type(exc).__name__)
        await message.reply_text("❌ Unable to retrieve a key.\n\nReason: Unexpected error. Please try again later.")
    finally:
        in_flight.discard(user.id)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Log only the exception type: messages can contain URLs/tokens.
    log.error("Unhandled error: %s", type(context.error).__name__)


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=getattr(logging, settings.log_level, logging.INFO),
    )
    # httpx logs full request URLs (which contain the bot token) at INFO.
    for noisy in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["provider"] = build_provider(settings)
    app.bot_data["limiter"] = RateLimiter(settings.rate_limit_seconds)
    app.bot_data["in_flight"] = set()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("supported", supported))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)

    if settings.use_webhook:
        log.info("Starting in webhook mode on port %s", settings.port)
        app.run_webhook(
            listen="0.0.0.0",
            port=settings.port,
            url_path="telegram",
            webhook_url=f"{settings.webhook_base_url}/telegram",
            secret_token=settings.webhook_secret,
            allowed_updates=[Update.MESSAGE],
            drop_pending_updates=True,
        )
    else:
        log.info("Starting in long-polling mode")
        app.run_polling(allowed_updates=[Update.MESSAGE], drop_pending_updates=True)


if __name__ == "__main__":
    main()
