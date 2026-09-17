from __future__ import annotations

import asyncio
import json
import logging

from redis.asyncio import Redis

from classroom_summary.config import Settings
from classroom_summary.jobs.lock import RedisLock
from classroom_summary.process.pipeline import SUMMARY_PROMPT_VERSION, SummaryPipeline
from classroom_summary.process.schemas import SummaryOutput
from classroom_summary.process.source import MessageSource
from classroom_summary.storage.channels import get_channel_config
from classroom_summary.storage.cursor import get_cursor
from classroom_summary.storage.database import Database

logger = logging.getLogger(__name__)


class RateLimitedError(Exception):
    pass


class NoMessagesError(Exception):
    pass


class OnDemandRunner:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        redis: Redis,
        source: MessageSource,
        pipeline: SummaryPipeline,
    ) -> None:
        self.settings = settings
        self.database = database
        self.redis = redis
        self.source = source
        self.pipeline = pipeline

    async def run(self, channel_id: int, user_id: int) -> SummaryOutput:
        rate_key = f"rate:ondemand:{channel_id}:{user_id}"
        allowed = await self.redis.set(
            rate_key, "1", ex=self.settings.ondemand_rate_limit_seconds, nx=True
        )
        if not allowed:
            raise RateLimitedError

        async with self.database.sessions() as session:
            config = await get_channel_config(session, channel_id)
            if config is None or not config.enabled:
                raise PermissionError("channel is not opted in")
            stored_cursor = await get_cursor(session, channel_id)
            cursor = stored_cursor or config.activated_after_message_id

        cache_key = f"cache:ondemand:{SUMMARY_PROMPT_VERSION}:{channel_id}:{cursor}"
        cached = await self.redis.get(cache_key)
        if cached:
            return SummaryOutput.model_validate_json(cached)

        lock = RedisLock(self.redis, f"lock:ondemand:{channel_id}:{cursor}", 120)
        if not await lock.acquire():
            for _ in range(40):
                await asyncio.sleep(0.25)
                cached = await self.redis.get(cache_key)
                if cached:
                    return SummaryOutput.model_validate_json(cached)
            raise RuntimeError("another summary request is still running")

        try:
            messages, _ = await self.source.load(
                channel_id, cursor, self.settings.process_message_cap
            )
            if not messages:
                raise NoMessagesError
            async with self.database.sessions() as session:
                result = await self.pipeline.run(
                    session,
                    channel_id=channel_id,
                    cursor_from=cursor,
                    messages=messages,
                    trigger="on-demand",
                )
                await session.commit()
            await self.redis.set(
                cache_key,
                json.dumps(result.output.model_dump(mode="json"), ensure_ascii=False),
                ex=self.settings.ondemand_cache_ttl_seconds,
            )
            logger.info(
                "ondemand_completed",
                extra={
                    "trigger": "on-demand",
                    "channel_id": channel_id,
                    "cursor_before": cursor,
                    "cursor_after": cursor,
                    "message_count": result.message_count,
                    "token_used": result.summary.token_usage,
                },
            )
            return result.output
        finally:
            await lock.release()
