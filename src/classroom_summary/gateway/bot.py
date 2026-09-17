from __future__ import annotations

import logging

import discord
from discord import app_commands
from sqlalchemy.ext.asyncio import AsyncSession

from classroom_summary.deliver.discord_api import summary_text
from classroom_summary.ingest.events import EventType, MessageEvent
from classroom_summary.process.ondemand import NoMessagesError, RateLimitedError
from classroom_summary.runtime import Runtime
from classroom_summary.storage.channels import disable_channel, enable_channel, get_channel_config

logger = logging.getLogger(__name__)


class SummaryCommands(app_commands.Group):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__(name="summary", description="Classroom summaries")
        self.runtime = runtime

    @app_commands.command(name="now", description="Generate a private summary of new messages")
    async def now(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Lệnh này chỉ dùng trong channel.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            output = await self.runtime.ondemand.run(interaction.channel_id, interaction.user.id)
            await interaction.followup.send(summary_text(output), ephemeral=True)
        except PermissionError:
            await interaction.followup.send("Channel chưa được bật Summary.", ephemeral=True)
        except RateLimitedError:
            await interaction.followup.send(
                "Bạn vừa yêu cầu Summary. Hãy thử lại sau.", ephemeral=True
            )
        except NoMessagesError:
            await interaction.followup.send("Chưa có tin nhắn mới để tổng hợp.", ephemeral=True)
        except Exception:
            logger.exception("ondemand_failed", extra={"channel_id": interaction.channel_id})
            await interaction.followup.send("Không thể tạo Summary lúc này.", ephemeral=True)

    @app_commands.command(name="enable", description="Enable summaries for this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def enable(
        self, interaction: discord.Interaction, min_messages: app_commands.Range[int, 1]
    ) -> None:
        if interaction.guild_id is None or interaction.channel_id is None:
            await interaction.response.send_message(
                "Lệnh này chỉ dùng trong server.", ephemeral=True
            )
            return
        channel = interaction.channel
        activated_after = int(getattr(channel, "last_message_id", None) or 0)
        async with self.runtime.database.sessions.begin() as session:
            await enable_channel(
                session,
                channel_id=interaction.channel_id,
                guild_id=interaction.guild_id,
                min_messages=min_messages,
                activated_after_message_id=activated_after,
            )
        await interaction.response.send_message(
            f"Đã bật Summary; ngưỡng cron là {min_messages} tin nhắn.", ephemeral=True
        )

    @app_commands.command(name="disable", description="Disable summaries for this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Lệnh này chỉ dùng trong channel.", ephemeral=True
            )
            return
        async with self.runtime.database.sessions.begin() as session:
            disabled = await disable_channel(session, interaction.channel_id)
        message = "Đã tắt Summary." if disabled else "Channel chưa được cấu hình."
        await interaction.response.send_message(message, ephemeral=True)


class ClassroomBot(discord.Client):
    def __init__(self, runtime: Runtime) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.reactions = True
        super().__init__(intents=intents)
        self.runtime = runtime
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(SummaryCommands(runtime))
        self._synced = False

    async def setup_hook(self) -> None:
        if not self._synced:
            await self.tree.sync()
            self._synced = True

    async def _enabled(self, session: AsyncSession, channel_id: int) -> bool:
        config = await get_channel_config(session, channel_id)
        return bool(config and config.enabled)

    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or len(message.content.strip()) < 3:
            return
        async with self.runtime.database.sessions() as session:
            if not await self._enabled(session, message.channel.id):
                return
        await self.runtime.stream.append(
            MessageEvent(
                event_type=EventType.CREATE,
                channel_id=message.channel.id,
                message_id=message.id,
                author_id=message.author.id,
                content=message.content,
                created_at=message.created_at,
                reply_to_id=message.reference.message_id if message.reference else None,
            )
        )

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        async with self.runtime.database.sessions() as session:
            if not await self._enabled(session, payload.channel_id):
                return
        data = payload.data
        author = data.get("author") or {}
        if author.get("bot"):
            return
        await self.runtime.stream.append(
            MessageEvent(
                event_type=EventType.UPDATE,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                author_id=int(author["id"]) if author.get("id") else None,
                content=data.get("content"),
            )
        )

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        async with self.runtime.database.sessions() as session:
            if not await self._enabled(session, payload.channel_id):
                return
        await self.runtime.stream.append(
            MessageEvent(
                event_type=EventType.DELETE,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )
        )

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction(payload, 1)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction(payload, -1)

    async def _reaction(self, payload: discord.RawReactionActionEvent, delta: int) -> None:
        async with self.runtime.database.sessions() as session:
            if not await self._enabled(session, payload.channel_id):
                return
        await self.runtime.stream.update_reaction(payload.message_id, str(payload.emoji), delta)
