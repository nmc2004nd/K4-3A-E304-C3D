from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classroom_summary.ingest.events import NormalizedMessage
from classroom_summary.process.ai import AIProvider
from classroom_summary.process.schemas import SummaryOutput
from classroom_summary.storage.models import Summary
from classroom_summary.storage.summaries import get_summary_for_range, save_summary


@dataclass(frozen=True)
class PipelineResult:
    summary: Summary
    output: SummaryOutput
    message_count: int
    last_message_id: int


class SummaryPipeline:
    def __init__(self, provider: AIProvider, chunk_size: int = 400) -> None:
        self.provider = provider
        self.chunk_size = chunk_size

    async def run(
        self,
        session: AsyncSession,
        *,
        channel_id: int,
        cursor_from: int,
        messages: list[NormalizedMessage],
        trigger: str,
        rolling_summary: SummaryOutput | None = None,
    ) -> PipelineResult:
        if not messages:
            raise ValueError("cannot summarize an empty message range")
        cursor_to = messages[-1].message_id
        canonical = json.dumps(
            [message.model_dump(mode="json") for message in messages],
            sort_keys=True,
            separators=(",", ":"),
        )
        input_hash = hashlib.sha256(canonical.encode()).hexdigest()
        existing = await get_summary_for_range(session, channel_id, cursor_from, cursor_to)
        if existing and existing.input_hash == input_hash and existing.result:
            return PipelineResult(
                summary=existing,
                output=SummaryOutput.model_validate(existing.result),
                message_count=len(messages),
                last_message_id=cursor_to,
            )

        total_tokens = 0
        model = "unknown"
        mapped: list[SummaryOutput] = []
        for start in range(0, len(messages), self.chunk_size):
            chunk = messages[start : start + self.chunk_size]
            output, tokens, model = await self._generate(
                "Summarize only the supplied classroom messages. Never invent rules or facts.",
                json.dumps([item.model_dump(mode="json") for item in chunk], ensure_ascii=False),
            )
            total_tokens += tokens
            mapped.append(output)

        reduce_input = {
            "previous_summary": rolling_summary.model_dump(mode="json")
            if rolling_summary
            else None,
            "chunk_summaries": [item.model_dump(mode="json") for item in mapped],
        }
        output, tokens, model = await self._generate(
            "Merge the supplied summaries without adding unsupported facts. "
            "Preserve source message IDs.",
            json.dumps(reduce_input, ensure_ascii=False),
        )
        total_tokens += tokens
        summary = await save_summary(
            session,
            channel_id=channel_id,
            cursor_from=cursor_from,
            cursor_to=cursor_to,
            trigger=trigger,
            input_hash=input_hash,
            output=output,
            token_usage=total_tokens,
            model=model,
        )
        return PipelineResult(summary, output, len(messages), cursor_to)

    async def _generate(self, system: str, user: str) -> tuple[SummaryOutput, int, str]:
        prompt = user
        last_error: ValidationError | None = None
        for _ in range(3):
            response = await self.provider.generate_json(
                system=system,
                user=prompt,
                json_schema=SummaryOutput.model_json_schema(),
            )
            try:
                return (
                    SummaryOutput.model_validate(response.data),
                    response.token_usage,
                    response.model,
                )
            except ValidationError as error:
                last_error = error
                prompt = (
                    f"The previous JSON failed validation: {error}. "
                    f"Return corrected JSON only.\n{user}"
                )
        raise ValueError("AI output failed schema validation") from last_error
