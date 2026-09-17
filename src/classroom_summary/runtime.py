from dataclasses import dataclass

from redis.asyncio import Redis

from classroom_summary.config import Settings
from classroom_summary.deliver.discord_api import DiscordAPI
from classroom_summary.ingest.stream import EventStream
from classroom_summary.process.ai import OpenAICompatibleProvider
from classroom_summary.process.cron import CronRunner
from classroom_summary.process.ondemand import OnDemandRunner
from classroom_summary.process.pipeline import SummaryPipeline
from classroom_summary.process.source import MessageSource
from classroom_summary.storage.database import Database


@dataclass
class Runtime:
    settings: Settings
    database: Database
    redis: Redis
    discord_api: DiscordAPI
    ai: OpenAICompatibleProvider
    stream: EventStream
    ondemand: OnDemandRunner
    cron: CronRunner

    @classmethod
    def build(cls, settings: Settings) -> "Runtime":
        database = Database(settings)
        redis = Redis.from_url(settings.redis_url)
        discord_api = DiscordAPI(settings.discord_token)
        ai = OpenAICompatibleProvider(settings.ai_base_url, settings.ai_api_key, settings.ai_model)
        stream = EventStream(redis, settings.stream_maxlen)
        source = MessageSource(stream, redis, discord_api)
        pipeline = SummaryPipeline(ai)
        return cls(
            settings=settings,
            database=database,
            redis=redis,
            discord_api=discord_api,
            ai=ai,
            stream=stream,
            ondemand=OnDemandRunner(settings, database, redis, source, pipeline),
            cron=CronRunner(settings, database, redis, source, pipeline, discord_api),
        )

    async def close(self) -> None:
        await self.ai.close()
        await self.discord_api.close()
        await self.redis.aclose()
        await self.database.close()
