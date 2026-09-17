from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis


class RedisLock:
    def __init__(self, redis: Redis, key: str, ttl_seconds: int) -> None:
        self.redis = redis
        self.key = key
        self.ttl_seconds = ttl_seconds
        self.token = secrets.token_urlsafe(24)
        self._renew_task: asyncio.Task[None] | None = None

    async def acquire(self) -> bool:
        acquired = bool(await self.redis.set(self.key, self.token, ex=self.ttl_seconds, nx=True))
        if acquired:
            self._renew_task = asyncio.create_task(self._renew())
        return acquired

    async def _renew(self) -> None:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
          return redis.call('expire', KEYS[1], ARGV[2])
        end
        return 0
        """
        while True:
            await asyncio.sleep(max(1, self.ttl_seconds // 3))
            renewed = await cast(
                Awaitable[Any],
                self.redis.eval(script, 1, self.key, self.token, str(self.ttl_seconds)),
            )
            if not renewed:
                return

    async def release(self) -> None:
        if self._renew_task:
            self._renew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renew_task
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
          return redis.call('del', KEYS[1])
        end
        return 0
        """
        await cast(Awaitable[Any], self.redis.eval(script, 1, self.key, self.token))
