from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class AIResponse:
    data: dict[str, Any]
    token_usage: int
    model: str


class AIProvider(Protocol):
    async def generate_json(
        self, *, system: str, user: str, json_schema: dict[str, Any]
    ) -> AIResponse: ...


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.model = model
        self.client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=90,
        )

    async def generate_json(
        self, *, system: str, user: str, json_schema: dict[str, Any]
    ) -> AIResponse:
        schema_instruction = (
            "Return exactly one valid JSON object matching this JSON Schema. "
            "Do not include Markdown or explanatory text.\n"
            f"JSON Schema:\n{json.dumps(json_schema, ensure_ascii=False)}"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": f"{system}\n\n{schema_instruction}"},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response: httpx.Response | None = None
        for attempt in range(4):
            response = await self.client.post("chat/completions", json=payload)
            if response.status_code == 429:
                await asyncio.sleep(float(response.headers.get("retry-after", 2**attempt)))
                continue
            if response.status_code >= 500 and attempt < 3:
                await asyncio.sleep(2**attempt)
                continue
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return AIResponse(
                data=json.loads(content),
                token_usage=int(body.get("usage", {}).get("total_tokens", 0)),
                model=str(body.get("model", self.model)),
            )
        assert response is not None
        response.raise_for_status()
        raise RuntimeError("AI request failed")

    async def close(self) -> None:
        await self.client.aclose()

    async def healthcheck(self) -> None:
        response = await self.client.get("models")
        response.raise_for_status()
