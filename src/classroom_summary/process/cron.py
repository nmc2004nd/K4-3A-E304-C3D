from __future__ import annotations

import logging

from pydantic import ValidationError
from redis.asyncio import Redis

from classroom_summary.config import Settings
from classroom_summary.deliver.discord_api import DiscordAPI
from classroom_summary.jobs.lock import RedisLock
from classroom_summary.process.pipeline import SummaryPipeline
from classroom_summary.process.schemas import SummaryOutput
from classroom_summary.process.source import MessageSource
from classroom_summary.storage.cursor import commit_cursor, get_cursor
from classroom_summary.storage.database import Database
from classroom_summary.storage.models import ChannelConfig
from classroom_summary.storage.summaries import latest_published_summary

logger = logging.getLogger(__name__)


class CronRunner:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        redis: Redis,
        source: MessageSource,
        pipeline: SummaryPipeline,
        discord: DiscordAPI,
    ) -> None:
        self.settings = settings
        self.database = database
        self.redis = redis
        self.source = source
        self.pipeline = pipeline
        self.discord = discord

    async def run_channel(self, config: ChannelConfig) -> bool:
        lock = RedisLock(
            self.redis,
            f"lock:cron:{config.channel_id}",
            self.settings.cron_lock_ttl_seconds,
        )
        if not await lock.acquire():
            logger.info("cron_skipped_locked", extra={"channel_id": config.channel_id})
            return False
        try:
            async with self.database.sessions() as session:
                stored_cursor = await get_cursor(session, config.channel_id)
                cursor_before = stored_cursor or config.activated_after_message_id
                messages, fallback_used = await self.source.load(
                    config.channel_id, cursor_before, self.settings.process_message_cap
                )
                if len(messages) < config.min_messages:
                    return False
                previous = await latest_published_summary(session, config.channel_id)
                rolling: SummaryOutput | None = None
                if previous and previous.result:
                    try:
                        rolling = SummaryOutput.model_validate(previous.result)
                    except ValidationError:
                        logger.warning(
                            "invalid_rolling_summary", extra={"channel_id": config.channel_id}
                        )
                result = await self.pipeline.run(
                    session,
                    channel_id=config.channel_id,
                    cursor_from=cursor_before,
                    messages=messages,
                    trigger="cron",
                    rolling_summary=rolling,
                )
                await session.commit()

            message_id = await self.discord.post_milestone(config.channel_id, result.output)
            thread_id: int | None = None
            try:
                thread_id = await self.discord.create_thread(config.channel_id, message_id)
            except Exception:
                logger.exception("thread_create_failed", extra={"channel_id": config.channel_id})

            async with self.database.sessions.begin() as session:
                persisted = await session.get(
                    type(result.summary), result.summary.id, with_for_update=True
                )
                if persisted is None:
                    raise RuntimeError("summary disappeared before delivery commit")
                persisted.status = "published"
                persisted.discord_message_id = message_id
                persisted.discord_thread_id = thread_id
                await commit_cursor(session, config.channel_id, result.last_message_id)
            logger.info(
                "cron_published",
                extra={
                    "channel_id": config.channel_id,
                    "cursor_before": cursor_before,
                    "cursor_after": result.last_message_id,
                    "message_count": result.message_count,
                    "token_used": result.summary.token_usage,
                    "fallback_used": fallback_used,
                },
            )
            return True
        finally:
            await lock.release()
