"""YOUKO KEY BOT V3 - optional Discord relay.

Forwards links using a Discord bot account and returns responses from a
configured result bot only when they explicitly reply to a forwarded message.
This does NOT bypass Discord's bot-to-bot restrictions or invoke slash commands.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import discord

log = logging.getLogger("youko.discord")


@dataclass
class Pending:
    telegram_chat_id: int
    telegram_message_id: int
    expires_at: float
    last_result: str = ""


class DiscordBridge(discord.Client):
    def __init__(
        self,
        channel_id: int,
        result_bot_id: int,
        timeout_seconds: int,
        on_result: Callable[[int, int, str], Awaitable[None]],
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = int(channel_id)
        self.result_bot_id = int(result_bot_id)
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.on_result = on_result
        self.pending: dict[int, Pending] = {}
        # Tracks result messages, including those later edited by the result bot.
        self.result_to_request: dict[int, int] = {}

    async def on_ready(self) -> None:
        log.info("Discord relay ready (bot ID=%s)", self.user.id if self.user else "unknown")

    async def forward(self, url: str, chat_id: int, message_id: int) -> bool:
        if not self.is_ready():
            log.warning("Discord relay is not ready")
            return False
        channel = self.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                log.warning("Discord channel cannot be fetched")
                return False
        if not isinstance(channel, discord.TextChannel):
            log.warning("Configured Discord channel is not a text channel")
            return False
        try:
            sent = await channel.send(
                url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            log.warning("Discord message send failed")
            return False
        self._prune()
        self.pending[sent.id] = Pending(
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            expires_at=time.monotonic() + self.timeout_seconds,
        )
        log.info("Forwarded request to Discord (message ID=%s)", sent.id)
        return True

    def _prune(self) -> None:
        now = time.monotonic()
        self.pending = {k: v for k, v in self.pending.items() if v.expires_at > now}
        self.result_to_request = {
            result_id: request_id
            for result_id, request_id in self.result_to_request.items()
            if request_id in self.pending
        }
        if len(self.pending) > 1000:
            self.pending = dict(list(self.pending.items())[-1000:])
            self.result_to_request = {
                result_id: request_id
                for result_id, request_id in self.result_to_request.items()
                if request_id in self.pending
            }

    @staticmethod
    def _extract_result(message: discord.Message) -> str:
        pieces: list[str] = []
        if message.content.strip():
            pieces.append(message.content.strip())
        for embed in message.embeds[:5]:
            if embed.title:
                pieces.append(embed.title)
            if embed.description:
                pieces.append(embed.description)
            if embed.url:
                pieces.append(embed.url)
            for field in embed.fields[:10]:
                pieces.append(f"{field.name}: {field.value}")
            if embed.footer and embed.footer.text:
                pieces.append(embed.footer.text)
        # discord.py 2.x exposes action-row buttons in message.components.
        for row in message.components:
            for component in getattr(row, "children", []):
                link = getattr(component, "url", None)
                if link and isinstance(link, str) and link.startswith("https://"):
                    label = getattr(component, "label", None) or "Result link"
                    pieces.append(f"{label}: {link}")
        return "\n".join(pieces).strip()[:3500]

    async def _handle_result(self, message: discord.Message) -> None:
        if message.channel.id != self.channel_id:
            return
        if message.author.id != self.result_bot_id:
            return
        self._prune()
        request_id = self.result_to_request.get(message.id)
        if request_id is None and message.reference is not None:
            request_id = message.reference.message_id
        if request_id is None or request_id not in self.pending:
            log.debug("Unmatched result bot message (ID=%s)", message.id)
            return
        pending = self.pending[request_id]
        self.result_to_request[message.id] = request_id
        result = self._extract_result(message)
        if not result or result == pending.last_result:
            return
        # Ignore progress-only messages; keep pending until a later edit/reply.
        lower = result.lower()
        if any(word in lower for word in ("processing", "please wait", "working on it", "bypassing...", "queued", "in progress")) and not any(word in lower for word in ("success", "completed", "failed", "error")):
            log.info("Discord result still processing (message ID=%s)", message.id)
            return
        try:
            await self.on_result(
                pending.telegram_chat_id,
                pending.telegram_message_id,
                result,
            )
        except Exception as exc:
            log.error("Telegram result delivery failed: %s", type(exc).__name__)
            return
        pending.last_result = result
        # Once a terminal response has been delivered, stop tracking the request.
        self.pending.pop(request_id, None)
        self.result_to_request.pop(message.id, None)
        log.info("Discord result delivered for request ID=%s", request_id)

    async def on_message(self, message: discord.Message) -> None:
        await self._handle_result(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        await self._handle_result(after)
