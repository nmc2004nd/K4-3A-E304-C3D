import asyncio
import logging

from classroom_summary.config import get_settings
from classroom_summary.gateway.bot import ClassroomBot
from classroom_summary.runtime import Runtime


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    runtime = Runtime.build(settings)
    bot = ClassroomBot(runtime)
    try:
        await bot.start(settings.discord_token)
    finally:
        await bot.close()
        await runtime.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
