"""YOUKO KEY BOT V3 - Telegram group/private links + optional Discord relay.

Render: Telegram webhook. Local: Telegram long polling.
Discord relay does NOT guarantee that another Discord bot will answer bot posts.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import sys
import time

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import ConfigError, Settings, load_settings
from providers import SERVICE_DOMAINS, Status, build_provider, url_fingerprint, validate_url

log = logging.getLogger('youko')
URL_RE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

class RateLimiter:
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        self.last: dict[int, float] = {}

    def remaining(self, user_id: int) -> int:
        now = time.monotonic()
        if len(self.last) > 5000:
            self.last = {k: v for k, v in self.last.items() if now - v < self.seconds}
        return max(0, int(self.seconds - (now - self.last.get(user_id, -1e10)) + .999))

    def hit(self, user_id: int) -> None:
        self.last[user_id] = time.monotonic()


def allowed_chat(update: Update, settings: Settings) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    return chat.type == ChatType.PRIVATE or (chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and chat.id == settings.telegram_group_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data['settings']
    if not allowed_chat(update, settings):
        return
    await update.effective_message.reply_text(
        '🔑 YOUKO KEY BOT V3\n\nSend a supported HTTPS link. '
        'In the configured Telegram group, links can be relayed to Discord.\n'
        'Commands: /help /status /supported /chatid'
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update, context.bot_data['settings']):
        return
    await update.effective_message.reply_text(
        'Commands:\n/start - welcome\n/help - help\n/status - integration status\n'
        '/supported - allowed link domains\n/chatid - this Telegram chat ID\n\n'
        'Send one HTTPS link per message. Group links are processed only in TELEGRAM_GROUP_ID.\n'
        'Discord result relay requires a DIRECT REPLY from the configured result bot to the forwarded Discord message.'
    )


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat:
        await update.effective_message.reply_text(f'Telegram Chat ID: {chat.id}')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data['settings']
    if not allowed_chat(update, settings):
        return
    bridge = context.bot_data.get('discord_bridge')
    discord_status = ('ready ✅' if bridge and bridge.is_ready() else 'not ready ⚠️') if settings.discord_configured else 'not configured'
    await update.effective_message.reply_text(
        f'YOUKO KEY BOT V3\nTelegram: online ✅\n'
        f'Mode: {"webhook" if settings.use_webhook else "polling"}\n'
        f'Telegram group: {"configured" if settings.telegram_group_id else "not configured"}\n'
        f'Discord relay: {discord_status}\n'
        f'Authorized provider API: {"configured" if settings.provider_configured else "not configured"}\n'
        f'Cooldown: {settings.rate_limit_seconds}s per user'
    )


async def supported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update, context.bot_data['settings']):
        return
    lines = ['<b>Supported URL services</b>']
    for name, domains in SERVICE_DOMAINS.items():
        lines.append(f'• {html.escape(name)}: ' + ', '.join(map(html.escape, domains)))
    await update.effective_message.reply_text('\n'.join(lines), parse_mode=ParseMode.HTML)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    settings: Settings = context.bot_data['settings']
    if not message or not user or not message.text or not allowed_chat(update, settings):
        return
    match = URL_RE.search(message.text)
    if not match:
        # Avoid spamming groups on regular conversation.
        if update.effective_chat.type == ChatType.PRIVATE:
            await message.reply_text('Send a supported HTTPS link. Use /supported for the list.')
        return
    url = match.group(0).rstrip('.,;:!?)]}')
    check = validate_url(url)
    if not check.ok:
        await message.reply_text(f'❌ {check.error}')
        return

    limiter: RateLimiter = context.bot_data['limiter']
    in_flight: set[int] = context.bot_data['in_flight']
    if user.id in in_flight:
        await message.reply_text('⏳ Your previous request is still processing.')
        return
    wait = limiter.remaining(user.id)
    if wait:
        await message.reply_text(f'⏱ Wait {wait}s before another request.')
        return
    limiter.hit(user.id)
    in_flight.add(user.id)
    log.info('Request service=%s fingerprint=%s', check.service, url_fingerprint(url))
    try:
        bridge = context.bot_data.get('discord_bridge')
        if settings.discord_configured:
            if not bridge or not await bridge.forward(url, message.chat_id, message.message_id):
                await message.reply_text('⚠️ Discord message could not be confirmed. Check Render logs for channel, send or deletion details.')
            else:
                await message.reply_text(
                    '📨 Discord accepted the link. Check Render logs for the message URL. Waiting for a response.\n'
                    '⚠️ The other Discord bot may ignore bot-authored links. '
                    'Only a direct reply from the configured result bot can be returned here.'
                )
            return

        provider = context.bot_data['provider']
        if not provider.configured:
            await message.reply_text(
                f'✅ Valid {check.service} link recognized.\n\n'
                '⚠️ Neither Discord relay nor an authorized provider API is configured. No key can be retrieved.'
            )
            return
        progress = await message.reply_text(f'⏳ Processing {check.service} through the authorized API...')
        result = await provider.fetch_key(check.service, url)
        if result.status is Status.COMPLETED and result.key:
            response = f'🔑 <b>Key Ready</b>\n<code>{html.escape(result.key)}</code>'
        else:
            response = f'❌ No key available.\nReason: {html.escape(result.reason)}'
        await progress.edit_text(response, parse_mode=ParseMode.HTML)
    except Exception as exc:
        log.error('Request error: %s', type(exc).__name__)
        await message.reply_text('❌ Unexpected error. Check the bot logs.')
    finally:
        in_flight.discard(user.id)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error('Unhandled error: %s', type(context.error).__name__)


async def post_init(app: Application) -> None:
    settings: Settings = app.bot_data['settings']
    if not settings.discord_configured:
        return
    from discord_bridge import DiscordBridge

    async def return_result(chat_id: int, message_id: int, result: str) -> None:
        await app.bot.send_message(
            chat_id=chat_id, text='📩 Discord result:\n\n' + result,
            reply_to_message_id=message_id, allow_sending_without_reply=True,
            disable_web_page_preview=True,
        )

    bridge = DiscordBridge(
        settings.discord_channel_id, settings.discord_result_bot_id,
        settings.discord_result_timeout, return_result,
    )
    app.bot_data['discord_bridge'] = bridge
    task = asyncio.create_task(bridge.start(settings.discord_bot_token), name='discord-relay')
    app.bot_data['discord_task'] = task
    task.add_done_callback(lambda t: log.error('Discord relay exited: %s', type(t.exception()).__name__ if not t.cancelled() and t.exception() else 'stopped'))


async def post_shutdown(app: Application) -> None:
    bridge = app.bot_data.get('discord_bridge')
    if bridge:
        await bridge.close()
    task = app.bot_data.get('discord_task')
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s: %(message)s', level=getattr(logging, settings.log_level, logging.INFO))
    for noisy in ('httpx', 'httpcore', 'telegram', 'discord.gateway'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    app = Application.builder().token(settings.bot_token).post_init(post_init).post_shutdown(post_shutdown).build()
    app.bot_data.update(settings=settings, provider=build_provider(settings), limiter=RateLimiter(settings.rate_limit_seconds), in_flight=set())
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CommandHandler('supported', supported))
    app.add_handler(CommandHandler('chatid', chatid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)
    if settings.use_webhook:
        log.info('Starting Telegram webhook on port %s', settings.port)
        app.run_webhook(listen='0.0.0.0', port=settings.port, url_path='telegram',
                        webhook_url=f'{settings.webhook_base_url}/telegram',
                        secret_token=settings.webhook_secret,
                        allowed_updates=[Update.MESSAGE], drop_pending_updates=True)
    else:
        log.info('Starting Telegram polling')
        app.run_polling(allowed_updates=[Update.MESSAGE], drop_pending_updates=True)


if __name__ == '__main__':
    main()
