from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from classroom_summary.ingest.events import NormalizedMessage
from classroom_summary.process.schemas import SummaryOutput


class DiscordAPI:
    def __init__(self, token: str) -> None:
        self.client = httpx.AsyncClient(
            base_url="https://discord.com/api/v10/",
            headers={"Authorization": f"Bot {token}"},
            timeout=30,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(5):
            response = await self.client.request(method, path.lstrip("/"), **kwargs)
            if response.status_code == 429:
                retry_after = float(response.json().get("retry_after", 1))
                await asyncio.sleep(retry_after)
                continue
            if response.status_code >= 500 and attempt < 4:
                await asyncio.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response
        assert response is not None
        response.raise_for_status()
        raise RuntimeError("Discord request failed")

    async def fetch_after(
        self, channel_id: int, message_id: int, limit: int
    ) -> list[NormalizedMessage]:
        messages: list[NormalizedMessage] = []
        after = message_id
        cutoff = datetime.now(UTC) - timedelta(days=7)
        page_count = 0
        while len(messages) < limit and page_count < 100:
            page_count += 1
            page_size = min(100, limit - len(messages))
            response = await self._request(
                "GET",
                f"/channels/{channel_id}/messages",
                params={"after": after, "limit": page_size},
            )
            page = response.json()
            if not page:
                break
            page.sort(key=lambda item: int(item["id"]))
            for item in page:
                created_at = datetime.fromisoformat(item["timestamp"])
                if created_at < cutoff:
                    continue
                if item.get("author", {}).get("bot") or len(item.get("content", "").strip()) < 3:
                    continue
                messages.append(
                    NormalizedMessage(
                        message_id=int(item["id"]),
                        author_id=int(item["author"]["id"]),
                        content=item["content"],
                        created_at=created_at,
                        reply_to_id=(
                            int(item["message_reference"]["message_id"])
                            if item.get("message_reference", {}).get("message_id")
                            else None
                        ),
                        reactions={
                            reaction["emoji"].get("name", "unknown"): int(reaction["count"])
                            for reaction in item.get("reactions", [])
                        },
                    )
                )
            next_after = int(page[-1]["id"])
            if next_after <= after or len(page) < page_size:
                break
            after = next_after
        return messages[:limit]

    async def post_milestone(self, channel_id: int, output: SummaryOutput) -> int:
        response = await self._request(
            "POST",
            f"/channels/{channel_id}/messages",
            json={"embeds": [summary_embed(output)]},
        )
        return int(response.json()["id"])

    async def create_thread(self, channel_id: int, message_id: int) -> int:
        response = await self._request(
            "POST",
            f"/channels/{channel_id}/messages/{message_id}/threads",
            json={"name": f"Summary {message_id}", "auto_archive_duration": 1440},
        )
        return int(response.json()["id"])

    async def close(self) -> None:
        await self.client.aclose()

    async def healthcheck(self) -> None:
        await self._request("GET", "/users/@me")


def summary_embed(output: SummaryOutput) -> dict[str, Any]:
    description = output.overview[:4000]
    remaining = 5800 - len(description)
    fields: list[dict[str, Any]] = []
    for item in output.items[:20]:
        name = f"{item.kind}: {item.title}"[:256]
        value = item.detail[: min(1024, max(1, remaining - len(name)))]
        if remaining <= len(name) + 1:
            break
        fields.append({"name": name, "value": value, "inline": False})
        remaining -= len(name) + len(value)
    return {
        "title": "Classroom Summary",
        "description": description,
        "fields": fields,
        "color": 0x5865F2,
    }


def summary_text(output: SummaryOutput) -> str:
    lines = [output.overview]
    lines.extend(f"• **{item.title}** — {item.detail}" for item in output.items)
    text = "\n".join(lines)
    return text[:1900] + ("…" if len(text) > 1900 else "")
