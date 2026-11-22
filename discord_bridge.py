"""Optional Discord relay.

Sends links as the configured Discord bot. Can relay a response ONLY when the
configured result bot replies directly to that message. Other bots may ignore
bot-authored messages, so this cannot guarantee a Linkhive response.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import discord

log = logging.getLogger('youko.discord')

@dataclass
class Pending:
    telegram_chat_id: int
    telegram_message_id: int
    expires_at: float

class DiscordBridge(discord.Client):
    def __init__(self, channel_id: int, result_bot_id: int, timeout_seconds: int,
                 on_result: Callable[[int, int, str], Awaitable[None]]) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.result_bot_id = result_bot_id
        self.timeout_seconds = timeout_seconds
        self.on_result = on_result
        self.pending: dict[int, Pending] = {}

    async def on_ready(self) -> None:
        log.info('Discord relay ready (bot ID=%s)', self.user.id if self.user else 'unknown')

    async def forward(self, url: str, chat_id: int, message_id: int) -> bool:
        if not self.is_ready():
            return False
        channel = self.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.warning('Discord channel unavailable or not a text channel')
            return False
        try:
            sent = await channel.send(url, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            log.warning('Could not send message to Discord channel')
            return False
        self._prune()
        self.pending[sent.id] = Pending(chat_id, message_id, time.monotonic() + self.timeout_seconds)
        return True

    def _prune(self) -> None:
        now = time.monotonic()
        self.pending = {k: v for k, v in self.pending.items() if v.expires_at > now}
        if len(self.pending) > 1000:
            self.pending = dict(list(self.pending.items())[-1000:])

    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id != self.channel_id or message.author.id != self.result_bot_id:
            return
        if not message.reference or not message.reference.message_id:
            return
        self._prune()
        pending = self.pending.pop(message.reference.message_id, None)
        if pending is None:
            return
        pieces = [message.content.strip()] if message.content.strip() else []
        for embed in message.embeds[:2]:
            if embed.title:
                pieces.append(embed.title)
            if embed.description:
                pieces.append(embed.description)
            for field in embed.fields[:5]:
                pieces.append(f'{field.name}: {field.value}')
        result = '\n'.join(pieces).strip()
        if not result:
            result = 'Discord replied, but no readable text was provided.'
        # Discord responses are untrusted: forward as plain text, not Markdown/HTML.
        try:
            await self.on_result(pending.telegram_chat_id, pending.telegram_message_id, result[:3500])
        except Exception as exc:
            log.error('Telegram relay failed: %s', type(exc).__name__)
