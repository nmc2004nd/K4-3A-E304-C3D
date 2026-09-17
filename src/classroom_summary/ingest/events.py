from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EventType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    REACTION_ADD = "reaction_add"
    REACTION_REMOVE = "reaction_remove"


class MessageEvent(BaseModel):
    event_type: EventType
    channel_id: int
    message_id: int
    author_id: int | None = None
    content: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reply_to_id: int | None = None


class NormalizedMessage(BaseModel):
    message_id: int
    author_id: int
    content: str
    created_at: datetime
    reply_to_id: int | None = None
    reactions: dict[str, int] = Field(default_factory=dict)
