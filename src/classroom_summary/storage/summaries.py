import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classroom_summary.process.schemas import SummaryOutput
from classroom_summary.storage.models import Item, Summary


async def get_summary_for_range(
    session: AsyncSession, channel_id: int, cursor_from: int, cursor_to: int
) -> Summary | None:
    return cast(
        Summary | None,
        await session.scalar(
            select(Summary).where(
                Summary.channel_id == channel_id,
                Summary.cursor_from == cursor_from,
                Summary.cursor_to == cursor_to,
            )
        ),
    )


async def save_summary(
    session: AsyncSession,
    *,
    channel_id: int,
    cursor_from: int,
    cursor_to: int,
    trigger: str,
    input_hash: str,
    output: SummaryOutput,
    token_usage: int,
    model: str,
) -> Summary:
    summary_id = uuid.uuid4()
    statement = (
        insert(Summary)
        .values(
            id=summary_id,
            channel_id=channel_id,
            cursor_from=cursor_from,
            cursor_to=cursor_to,
            trigger=trigger,
            input_hash=input_hash,
            status="processing",
            token_usage=0,
        )
        .on_conflict_do_nothing(
            index_elements=[Summary.channel_id, Summary.cursor_from, Summary.cursor_to]
        )
    )
    await session.execute(statement)
    summary = await session.scalar(
        select(Summary)
        .where(
            Summary.channel_id == channel_id,
            Summary.cursor_from == cursor_from,
            Summary.cursor_to == cursor_to,
        )
        .with_for_update()
    )
    if summary is None:
        raise RuntimeError("failed to create or load summary range")
    if summary.status == "published":
        return summary
    if summary.input_hash == input_hash and summary.status == "ready":
        return summary

    await session.execute(delete(Item).where(Item.summary_id == summary.id))
    summary.trigger = trigger
    summary.input_hash = input_hash
    summary.status = "ready"
    summary.result = output.model_dump(mode="json")
    summary.token_usage = token_usage
    summary.model = model
    session.add_all(
        Item(
            summary_id=summary.id,
            kind=item.kind,
            position=index,
            content=item.model_dump(mode="json"),
        )
        for index, item in enumerate(output.items)
    )
    return summary


async def latest_published_summary(session: AsyncSession, channel_id: int) -> Summary | None:
    return cast(
        Summary | None,
        await session.scalar(
            select(Summary)
            .where(Summary.channel_id == channel_id, Summary.status == "published")
            .order_by(Summary.cursor_to.desc())
            .limit(1)
        ),
    )
