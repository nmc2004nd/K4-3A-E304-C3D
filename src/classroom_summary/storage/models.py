from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ChannelConfig(Base):
    __tablename__ = "channel_config"
    __table_args__ = (CheckConstraint("min_messages > 0", name="ck_channel_min_messages_positive"),)

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_messages: Mapped[int] = mapped_column(Integer, nullable=False)
    activated_after_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Cursor(Base):
    __tablename__ = "cursors"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (
        UniqueConstraint("channel_id", "cursor_from", "cursor_to", name="uq_summary_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cursor_from: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cursor_to: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trigger: Mapped[str] = mapped_column(String(24), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    discord_message_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_thread_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    items: Mapped[list[Item]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("summary_id", "position", name="uq_item_position"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("summaries.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
