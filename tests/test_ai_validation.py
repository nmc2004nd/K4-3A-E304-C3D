from typing import Any

import pytest

from classroom_summary.process.ai import AIResponse
from classroom_summary.process.pipeline import SummaryPipeline


class FakeProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls = 0
        self.system_prompts: list[str] = []

    async def generate_json(
        self, *, system: str, user: str, json_schema: dict[str, Any]
    ) -> AIResponse:
        self.system_prompts.append(system)
        response = self.responses[self.calls]
        self.calls += 1
        return AIResponse(response, 5, "fake")


@pytest.mark.asyncio
async def test_pipeline_retries_invalid_ai_schema() -> None:
    provider = FakeProvider(
        [
            {"items": []},
            {"overview": "Valid result", "items": []},
        ]
    )

    output, tokens, model = await SummaryPipeline(provider)._generate("system", "messages")

    assert output.overview == "Valid result"
    assert tokens == 5
    assert model == "fake"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_pipeline_always_requests_vietnamese_output() -> None:
    provider = FakeProvider([{"overview": "Kết quả hợp lệ", "items": []}])

    await SummaryPipeline(provider)._generate("Summarize messages.", "messages")

    assert "every human-readable output field in Vietnamese" in provider.system_prompts[0]
    assert "overview, title, and detail" in provider.system_prompts[0]


@pytest.mark.asyncio
async def test_pipeline_stops_after_bounded_schema_retries() -> None:
    provider = FakeProvider([{}, {}, {}])

    with pytest.raises(ValueError, match="schema validation"):
        await SummaryPipeline(provider)._generate("system", "messages")

    assert provider.calls == 3
