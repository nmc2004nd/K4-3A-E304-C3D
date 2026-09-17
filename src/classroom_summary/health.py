import asyncio

from sqlalchemy import text

from classroom_summary.config import get_settings
from classroom_summary.runtime import Runtime


async def check() -> None:
    settings = get_settings()
    runtime = Runtime.build(settings)
    try:
        async with runtime.database.sessions() as session:
            await session.execute(text("SELECT 1"))
        if not await runtime.redis.ping():
            raise RuntimeError("Redis ping failed")
        await runtime.discord_api.healthcheck()
        await runtime.ai.healthcheck()
    finally:
        await runtime.close()


def main() -> None:
    asyncio.run(check())
