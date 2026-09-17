from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classroom_summary.storage.models import Cursor


async def commit_cursor(session: AsyncSession, channel_id: int, message_id: int) -> None:
    """The only allowed cursor write path; caller owns the transaction."""
    statement = insert(Cursor).values(channel_id=channel_id, last_message_id=message_id)
    statement = statement.on_conflict_do_update(
        index_elements=[Cursor.channel_id],
        set_={
            "last_message_id": message_id,
            "version": Cursor.version + 1,
        },
        where=Cursor.last_message_id < message_id,
    )
    await session.execute(statement)


async def get_cursor(session: AsyncSession, channel_id: int) -> int | None:
    cursor = await session.get(Cursor, channel_id)
    return cursor.last_message_id if cursor else None
