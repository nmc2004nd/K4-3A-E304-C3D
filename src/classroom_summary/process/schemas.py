from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ItemKind = Literal["topic", "faq", "task", "deadline", "open_question"]


class SummaryItem(BaseModel):
    kind: ItemKind
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=2_000)
    source_message_ids: list[int] = Field(default_factory=list)
    due_at: datetime | None = None


class SummaryOutput(BaseModel):
    overview: str = Field(min_length=1, max_length=4_000)
    items: list[SummaryItem] = Field(default_factory=list, max_length=100)
