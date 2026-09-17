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

SUMMARY_PROMPT_VERSION = "vi-v2"

CLASSROOM_SYSTEM_PROMPT = (
    "You are a classroom message summarizer for an educational Discord server. "
    "Your job is to extract academically relevant information and filter out pure noise.\n\n"
    "## CRITICAL RULES:\n"
    "1. **IGNORE pure social noise**: greetings (hello, chào), emoji spam (🚀🚀), "
    "game invitations (csgo, lol), food/lunch plans, sports commentary, and "
    "purely social conversations. These produce ZERO items.\n"
    "2. **KEEP academic content even in informal language**: Students often discuss "
    "homework, assignments, code errors, exams, deadlines, and project tasks using "
    "slang, teencode, or mixed Vietnamese-English. This is STILL academic content. "
    "Examples: 'btap hnay ntn' (bài tập hôm nay như thế nào) = academic, "
    "'push code lên master' = academic, 'cái này lỗi rồi' = academic.\n"
    "3. **GROUP related Q&A into ONE item**: When a question and its answer discuss "
    "the same topic, merge into ONE item. Do NOT create separate items for a question "
    "and its reply.\n"
    "4. **Skip truly meaningless fragments**: 'Làm sao?' or 'Nhanh lên' with zero "
    "academic context should be IGNORED.\n"
    "5. **Merge by topic**: If multiple messages discuss the same subject, combine into "
    "a single item.\n"
    "6. **Skip courtesy-only messages**: 'Cảm ơn thầy' alone is NOT a separate item. "
    "But if it accompanies academic content (like exam scores), only extract the academic part.\n"
    "7. **Be balanced**: Extract all genuine academic info, but avoid splitting one topic "
    "into multiple items.\n\n"
    "## NOISE (0 items):\n"
    "- Pure greetings, emoji spam, gaming, food, sports\n"
    "- Context-less fragments ('Làm sao?', 'Ok chốt')\n\n"
    "## ACADEMIC (extract as items):\n"
    "- Homework questions/answers, assignment deadlines\n"
    "- Code errors, technical Q&A, debugging help\n"
    "- Exam schedules, course announcements\n"
    "- Project progress updates, task assignments\n"
    "- Bug reports, sprint reviews, code reviews (even in informal language)\n"
    "- Score/grade announcements\n\n"
    "If all messages are noise, return {\"overview\": \"Không có thông tin học tập liên quan.\", \"items\": []}"
)

VIETNAMESE_OUTPUT_INSTRUCTION = (
    "Write every human-readable output field in Vietnamese, including overview, title, "
    "and detail. Keep proper nouns, technical terms, code, URLs, and quoted source text "
    "unchanged when appropriate."
)


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
            {
                "prompt_version": SUMMARY_PROMPT_VERSION,
                "messages": [message.model_dump(mode="json") for message in messages],
            },
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
                CLASSROOM_SYSTEM_PROMPT,
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
                system=f"{system}\n\n{VIETNAMESE_OUTPUT_INSTRUCTION}",
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
