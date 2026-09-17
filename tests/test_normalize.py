from datetime import UTC, datetime

from classroom_summary.ingest.events import EventType, MessageEvent
from classroom_summary.process.normalize import normalize_events


def event(kind: EventType, message_id: int, content: str | None = None) -> MessageEvent:
    return MessageEvent(
        event_type=kind,
        channel_id=10,
        message_id=message_id,
        author_id=20 if kind == EventType.CREATE else None,
        content=content,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_normalize_keeps_latest_edit_and_order() -> None:
    messages = normalize_events(
        [
            event(EventType.CREATE, 2, "before"),
            event(EventType.CREATE, 1, "first"),
            event(EventType.UPDATE, 2, "after"),
        ]
    )

    assert [message.message_id for message in messages] == [1, 2]
    assert messages[1].content == "after"
    assert messages[1].author_id == 20


def test_normalize_removes_deleted_message_and_ignores_late_edit() -> None:
    messages = normalize_events(
        [
            event(EventType.CREATE, 1, "keep"),
            event(EventType.CREATE, 2, "remove"),
            event(EventType.DELETE, 2),
            event(EventType.UPDATE, 2, "late update"),
        ]
    )

    assert [message.message_id for message in messages] == [1]
