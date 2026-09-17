from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis

from classroom_summary.ingest.events import EventType, MessageEvent


class EventStream:
    def __init__(self, redis: Redis, maxlen: int) -> None:
        self.redis = redis
        self.maxlen = maxlen

    @staticmethod
    def key(channel_id: int) -> str:
        return f"stream:{channel_id}"

    async def append(self, event: MessageEvent) -> None:
        fields: dict[Any, Any] = {
            "event_type": event.event_type.value,
            "channel_id": str(event.channel_id),
            "message_id": str(event.message_id),
            "author_id": "" if event.author_id is None else str(event.author_id),
            "content": event.content or "",
            "created_at": event.created_at.isoformat(),
            "reply_to_id": "" if event.reply_to_id is None else str(event.reply_to_id),
        }
        await self.redis.xadd(
            self.key(event.channel_id), fields, maxlen=self.maxlen, approximate=True
        )

    async def update_reaction(self, message_id: int, emoji: str, delta: int) -> None:
        key = f"react:{message_id}"
        count = await cast(Awaitable[int], self.redis.hincrby(key, emoji, delta))
        if count <= 0:
            await cast(Awaitable[int], self.redis.hdel(key, emoji))

    async def read_all(self, channel_id: int) -> list[MessageEvent]:
        records = await self.redis.xrange(self.key(channel_id))
        events: list[MessageEvent] = []
        for _, raw in records:
            fields = {
                (key.decode() if isinstance(key, bytes) else key): (
                    value.decode() if isinstance(value, bytes) else value
                )
                for key, value in raw.items()
            }
            events.append(
                MessageEvent(
                    event_type=EventType(fields["event_type"]),
                    channel_id=int(fields["channel_id"]),
                    message_id=int(fields["message_id"]),
                    author_id=int(fields["author_id"]) if fields["author_id"] else None,
                    content=fields["content"],
                    created_at=fields["created_at"],
                    reply_to_id=int(fields["reply_to_id"]) if fields["reply_to_id"] else None,
                )
            )
        return events
