import json

import httpx
import pytest

from classroom_summary.process.ai import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_provider_uses_deepseek_compatible_json_mode() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": '{"overview":"ok","items":[]}'}}],
                "usage": {"total_tokens": 7},
            },
        )

    provider = OpenAICompatibleProvider("https://api.deepseek.com", "secret", "deepseek-flash")
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        base_url="https://api.deepseek.com/",
        transport=httpx.MockTransport(handler),
    )

    response = await provider.generate_json(
        system="Summarize messages.",
        user="Messages",
        json_schema={"type": "object", "required": ["overview", "items"]},
    )

    assert captured["response_format"] == {"type": "json_object"}
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert "JSON Schema" in messages[0]["content"]
    assert response.data["overview"] == "ok"
    assert response.token_usage == 7
    await provider.close()
