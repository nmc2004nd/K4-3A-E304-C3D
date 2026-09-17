from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from classroom_summary.ingest.events import EventType, MessageEvent, NormalizedMessage
from classroom_summary.process.source import MessageSource


class Redis:
    async def hgetall(self, key: str) -> dict[str, str]:
        return {}


def raw(message_id: int) -> MessageEvent:
    return MessageEvent(
        event_type=EventType.CREATE,
        channel_id=1,
        message_id=message_id,
        author_id=2,
        content="message",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def normalized(message_id: int) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=message_id,
        author_id=2,
        content="fallback",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_uses_rest_when_cursor_event_was_trimmed() -> None:
    stream = AsyncMock()
    stream.read_all.return_value = [raw(30)]
    history = AsyncMock()
    history.fetch_after.return_value = [normalized(20), normalized(30)]
    source = MessageSource(stream, Redis(), history)  # type: ignore[arg-type]

    messages, fallback = await source.load(channel_id=1, cursor=10, cap=100)

    assert fallback is True
    assert [item.message_id for item in messages] == [20, 30]
    history.fetch_after.assert_awaited_once_with(1, 10, 100)


@pytest.mark.asyncio
async def test_uses_stream_when_cursor_event_is_present() -> None:
    stream = AsyncMock()
    stream.read_all.return_value = [raw(10), raw(20)]
    history = AsyncMock()
    source = MessageSource(stream, Redis(), history)  # type: ignore[arg-type]

    messages, fallback = await source.load(channel_id=1, cursor=10, cap=100)

    assert fallback is False
    assert [item.message_id for item in messages] == [20]
    history.fetch_after.assert_not_awaited()
