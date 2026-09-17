from datetime import UTC, datetime
from typing import Any

import pytest

from classroom_summary.ingest.events import NormalizedMessage
from classroom_summary.process.ai import AIResponse
from classroom_summary.process.pipeline import SummaryPipeline
from classroom_summary.storage.models import Summary


class Provider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(
        self, *, system: str, user: str, json_schema: dict[str, Any]
    ) -> AIResponse:
        self.calls += 1
        return AIResponse({"overview": f"result-{self.calls}", "items": []}, 2, "fake")


def message(content: str) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=20,
        author_id=2,
        content=content,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def memory_repository(monkeypatch: pytest.MonkeyPatch) -> dict[str, Summary | None]:
    state: dict[str, Summary | None] = {"summary": None}

    async def get_summary(*args: Any, **kwargs: Any) -> Summary | None:
        return state["summary"]

    async def save_summary(*args: Any, **kwargs: Any) -> Summary:
        output = kwargs["output"]
        current = state["summary"]
        if current is None:
            current = Summary(
                channel_id=kwargs["channel_id"],
                cursor_from=kwargs["cursor_from"],
                cursor_to=kwargs["cursor_to"],
                trigger=kwargs["trigger"],
                input_hash=kwargs["input_hash"],
                status="ready",
            )
            state["summary"] = current
        current.input_hash = kwargs["input_hash"]
        current.result = output.model_dump(mode="json")
        current.token_usage = kwargs["token_usage"]
        current.model = kwargs["model"]
        return current

    monkeypatch.setattr("classroom_summary.process.pipeline.get_summary_for_range", get_summary)
    monkeypatch.setattr("classroom_summary.process.pipeline.save_summary", save_summary)
    return state


@pytest.mark.asyncio
async def test_same_range_and_input_reuses_persisted_summary(
    memory_repository: dict[str, Summary | None],
) -> None:
    provider = Provider()
    pipeline = SummaryPipeline(provider)
    session = object()

    first = await pipeline.run(  # type: ignore[arg-type]
        session,
        channel_id=1,
        cursor_from=10,
        messages=[message("hello")],
        trigger="on-demand",
    )
    second = await pipeline.run(  # type: ignore[arg-type]
        session,
        channel_id=1,
        cursor_from=10,
        messages=[message("hello")],
        trigger="cron",
    )

    assert first.summary is second.summary
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_edit_refreshes_existing_range_without_duplicate(
    memory_repository: dict[str, Summary | None],
) -> None:
    provider = Provider()
    pipeline = SummaryPipeline(provider)
    session = object()

    first = await pipeline.run(  # type: ignore[arg-type]
        session,
        channel_id=1,
        cursor_from=10,
        messages=[message("before edit")],
        trigger="on-demand",
    )
    refreshed = await pipeline.run(  # type: ignore[arg-type]
        session,
        channel_id=1,
        cursor_from=10,
        messages=[message("after edit")],
        trigger="cron",
    )

    assert first.summary is refreshed.summary
    assert provider.calls == 4
