from collections.abc import Iterable, Mapping

from classroom_summary.ingest.events import EventType, MessageEvent, NormalizedMessage


def normalize_events(
    events: Iterable[MessageEvent], reactions: Mapping[int, dict[str, int]] | None = None
) -> list[NormalizedMessage]:
    state: dict[int, NormalizedMessage] = {}
    deleted: set[int] = set()
    for event in events:
        if event.event_type == EventType.DELETE:
            state.pop(event.message_id, None)
            deleted.add(event.message_id)
            continue
        if event.event_type not in {EventType.CREATE, EventType.UPDATE}:
            continue
        if event.message_id in deleted and event.event_type == EventType.UPDATE:
            continue
        current = state.get(event.message_id)
        author_id = (
            event.author_id
            if event.author_id is not None
            else (current.author_id if current else None)
        )
        content = (
            event.content if event.content is not None else (current.content if current else None)
        )
        if author_id is None or content is None:
            continue
        state[event.message_id] = NormalizedMessage(
            message_id=event.message_id,
            author_id=author_id,
            content=content,
            created_at=event.created_at,
            reply_to_id=event.reply_to_id
            if event.reply_to_id is not None
            else (current.reply_to_id if current else None),
            reactions=(reactions or {}).get(event.message_id, {}),
        )
        deleted.discard(event.message_id)
    return sorted(state.values(), key=lambda message: message.message_id)
