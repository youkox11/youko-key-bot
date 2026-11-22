"""YOUKO KEY BOT V3: Discord relay with delivery diagnostics.

Uses a normal Discord bot account. A third-party bot may ignore bot-authored
messages; this relay does not invoke slash commands or impersonate users.
"""
from __future__ import annotations

import asyncio
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
        self.result_to_request: dict[int, int] = {}

    async def on_ready(self) -> None:
        log.info(
            "Discord relay ready: bot_id=%s target_channel_id=%s result_bot_id=%s",
            self.user.id if self.user else "unknown",
            self.channel_id,
            self.result_bot_id,
        )

    async def forward(self, url: str, chat_id: int, message_id: int) -> bool:
        if not self.is_ready():
            log.warning("Discord relay not ready")
            return False

        channel = self.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
                log.warning("Cannot fetch Discord channel: %s", type(exc).__name__)
                return False
        if not isinstance(channel, discord.TextChannel):
            log.warning("Target is not a standard Discord text channel: type=%s", type(channel).__name__)
            return False

        try:
            sent = await channel.send(url, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning("Discord send failed: %s", type(exc).__name__)
            return False

        self._prune()
        self.pending[sent.id] = Pending(
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            expires_at=time.monotonic() + self.timeout_seconds,
        )
        log.info(
            "Discord API accepted message: guild_id=%s channel_id=%s channel_name=%s "
            "message_id=%s jump_url=%s",
            channel.guild.id, channel.id, channel.name, sent.id, sent.jump_url,
        )

        # Confirm that the message still exists after a short delay. An AutoMod
        # rule or another bot can remove it after Discord initially accepts it.
        await asyncio.sleep(2)
        try:
            confirmed = await channel.fetch_message(sent.id)
        except discord.NotFound:
            log.warning(
                "DISCORD MESSAGE MISSING/DELETED after send: channel_id=%s message_id=%s "
                "jump_url=%s. Check Discord AutoMod, moderation bots and audit logs.",
                channel.id, sent.id, sent.jump_url,
            )
            self.pending.pop(sent.id, None)
            return False
        except (discord.Forbidden, discord.HTTPException) as exc:
            # The send succeeded, but we cannot establish that it remains visible.
            log.warning(
                "Discord message visibility could not be verified: message_id=%s reason=%s "
                "(Read Message History permission or API availability may be involved)",
                sent.id, type(exc).__name__,
            )
            return True

        log.info(
            "Discord message confirmed present: channel_id=%s message_id=%s jump_url=%s",
            confirmed.channel.id, confirmed.id, confirmed.jump_url,
        )
        return True

    def _prune(self) -> None:
        now = time.monotonic()
        self.pending = {k: v for k, v in self.pending.items() if v.expires_at > now}
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
        for row in message.components:
            for component in getattr(row, "children", []):
                link = getattr(component, "url", None)
                if isinstance(link, str) and link.startswith("https://"):
                    label = getattr(component, "label", None) or "Result link"
                    pieces.append(f"{label}: {link}")
        return "\n".join(pieces).strip()[:3500]

    async def _handle_result(self, message: discord.Message) -> None:
        if message.channel.id != self.channel_id or message.author.id != self.result_bot_id:
            return
        self._prune()
        request_id = self.result_to_request.get(message.id)
        if request_id is None and message.reference is not None:
            request_id = message.reference.message_id
        log.info(
            "Result bot message observed: result_message_id=%s reply_to_id=%s matched=%s",
            message.id,
            message.reference.message_id if message.reference else None,
            request_id in self.pending if request_id is not None else False,
        )
        if request_id is None or request_id not in self.pending:
            # Never guess which Telegram user should receive an unrelated result.
            return
        pending = self.pending[request_id]
        self.result_to_request[message.id] = request_id
        result = self._extract_result(message)
        if not result or result == pending.last_result:
            return
        lower = result.lower()
        if any(word in lower for word in (
            "processing", "please wait", "working on it", "bypassing...", "queued", "in progress",
        )) and not any(word in lower for word in ("success", "completed", "failed", "error")):
            log.info("Result bot is still processing: message_id=%s", message.id)
            return
        try:
            await self.on_result(pending.telegram_chat_id, pending.telegram_message_id, result)
        except Exception as exc:
            log.error("Telegram result delivery failed: %s", type(exc).__name__)
            return
        pending.last_result = result
        self.pending.pop(request_id, None)
        self.result_to_request.pop(message.id, None)
        log.info("Discord result delivered: request_message_id=%s", request_id)

    async def on_message(self, message: discord.Message) -> None:
        await self._handle_result(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        await self._handle_result(after)

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.channel_id != self.channel_id or payload.message_id not in self.result_to_request:
            return
        channel = self.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            updated = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        await self._handle_result(updated)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.channel_id != self.channel_id:
            return
        if payload.message_id in self.pending:
            log.warning(
                "Forwarded Discord message DELETED: channel_id=%s message_id=%s",
                payload.channel_id, payload.message_id,
            )
            # Keep pending briefly in case the result bot has already responded.
        if payload.message_id in self.result_to_request:
            log.info("Result bot message deleted: message_id=%s", payload.message_id)

    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.channel_id != self.channel_id:
            return
        affected = set(self.pending).intersection(payload.message_ids)
        if affected:
            log.warning(
                "Forwarded Discord messages BULK DELETED: channel_id=%s count=%s ids=%s",
                payload.channel_id, len(affected), sorted(affected),
            )
