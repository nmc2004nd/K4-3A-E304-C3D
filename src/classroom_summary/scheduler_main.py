import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from classroom_summary.config import get_settings
from classroom_summary.runtime import Runtime
from classroom_summary.storage.channels import list_enabled_channels

logger = logging.getLogger(__name__)


async def run_all(runtime: Runtime) -> None:
    async with runtime.database.sessions() as session:
        channels = await list_enabled_channels(session)
    results = await asyncio.gather(
        *(runtime.cron.run_channel(config) for config in channels), return_exceptions=True
    )
    for config, result in zip(channels, results, strict=True):
        if isinstance(result, Exception):
            logger.error(
                "cron_channel_failed",
                extra={"channel_id": config.channel_id},
                exc_info=(type(result), result, result.__traceback__),
            )


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    runtime = Runtime.build(settings)
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        run_all,
        "cron",
        hour="9,14,21",
        minute=0,
        args=[runtime],
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await runtime.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
