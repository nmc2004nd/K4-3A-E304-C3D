from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Protocol, cast

from redis.asyncio import Redis

from classroom_summary.ingest.events import EventType, NormalizedMessage
from classroom_summary.ingest.stream import EventStream
from classroom_summary.process.normalize import normalize_events


class HistoryFetcher(Protocol):
    async def fetch_after(
        self, channel_id: int, message_id: int, limit: int
    ) -> list[NormalizedMessage]: ...


class MessageSource:
    def __init__(self, stream: EventStream, redis: Redis, history: HistoryFetcher) -> None:
        self.stream = stream
        self.redis = redis
        self.history = history

    async def load(
        self, channel_id: int, cursor: int, cap: int
    ) -> tuple[list[NormalizedMessage], bool]:
        events = await self.stream.read_all(channel_id)
        cursor_is_present = cursor == 0 or any(
            event.message_id == cursor and event.event_type in {EventType.CREATE, EventType.UPDATE}
            for event in events
        )
        fallback_used = bool(events) and cursor > 0 and not cursor_is_present
        if fallback_used:
            messages = await self.history.fetch_after(channel_id, cursor, cap)
        else:
            relevant = [event for event in events if event.message_id > cursor]
            message_ids = {event.message_id for event in relevant}
            reactions: dict[int, dict[str, int]] = {}
            for message_id in message_ids:
                raw = await cast(
                    Awaitable[dict[Any, Any]], self.redis.hgetall(f"react:{message_id}")
                )
                reactions[message_id] = {
                    key.decode() if isinstance(key, bytes) else str(key): int(value)
                    for key, value in raw.items()
                }
            messages = normalize_events(relevant, reactions)
        return messages[:cap], fallback_used
