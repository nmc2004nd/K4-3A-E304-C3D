"""Initial persistent model."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_config",
        sa.Column("channel_id", sa.BigInteger(), primary_key=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_messages", sa.Integer(), nullable=False),
        sa.Column("activated_after_message_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("min_messages > 0", name="ck_channel_min_messages_positive"),
    )
    op.create_table(
        "cursors",
        sa.Column("channel_id", sa.BigInteger(), primary_key=True),
        sa.Column("last_message_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "summaries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("cursor_from", sa.BigInteger(), nullable=False),
        sa.Column("cursor_to", sa.BigInteger(), nullable=False),
        sa.Column("trigger", sa.String(24), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("discord_message_id", sa.BigInteger(), nullable=True),
        sa.Column("discord_thread_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("channel_id", "cursor_from", "cursor_to", name="uq_summary_range"),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "summary_id",
            sa.Uuid(),
            sa.ForeignKey("summaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.UniqueConstraint("summary_id", "position", name="uq_item_position"),
    )


def downgrade() -> None:
    op.drop_table("items")
    op.drop_table("summaries")
    op.drop_table("cursors")
    op.drop_table("channel_config")
