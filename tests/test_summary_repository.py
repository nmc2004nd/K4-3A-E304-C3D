import uuid
from typing import Any

import pytest

from classroom_summary.process.schemas import SummaryItem, SummaryOutput
from classroom_summary.storage.models import Item, Summary
from classroom_summary.storage.summaries import save_summary


class Session:
    def __init__(self, summary: Summary) -> None:
        self.summary = summary
        self.added: list[Item] = []

    async def execute(self, statement: object) -> None:
        return None

    async def scalar(self, statement: object) -> Summary:
        return self.summary

    def add_all(self, instances: Any) -> None:
        self.added.extend(instances)


@pytest.mark.asyncio
async def test_items_are_linked_to_their_summary() -> None:
    summary = Summary(
        id=uuid.uuid4(),
        channel_id=1,
        cursor_from=10,
        cursor_to=20,
        trigger="on-demand",
        input_hash="old",
        status="processing",
    )
    session = Session(summary)
    output = SummaryOutput(
        overview="Overview",
        items=[SummaryItem(kind="topic", title="Title", detail="Detail")],
    )

    saved = await save_summary(  # type: ignore[arg-type]
        session,
        channel_id=1,
        cursor_from=10,
        cursor_to=20,
        trigger="on-demand",
        input_hash="new",
        output=output,
        token_usage=10,
        model="deepseek-flash",
    )

    assert saved is summary
    assert len(session.added) == 1
    assert session.added[0].summary_id == summary.id
