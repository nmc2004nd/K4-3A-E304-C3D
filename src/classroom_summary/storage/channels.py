from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classroom_summary.storage.models import ChannelConfig


async def get_channel_config(session: AsyncSession, channel_id: int) -> ChannelConfig | None:
    return await session.get(ChannelConfig, channel_id)


async def list_enabled_channels(session: AsyncSession) -> list[ChannelConfig]:
    result = await session.scalars(select(ChannelConfig).where(ChannelConfig.enabled.is_(True)))
    return list(result)


async def enable_channel(
    session: AsyncSession,
    *,
    channel_id: int,
    guild_id: int,
    min_messages: int,
    activated_after_message_id: int,
) -> ChannelConfig:
    if min_messages <= 0:
        raise ValueError("min_messages must be positive")
    config = await session.get(ChannelConfig, channel_id)
    if config is None:
        config = ChannelConfig(
            channel_id=channel_id,
            guild_id=guild_id,
            min_messages=min_messages,
            activated_after_message_id=activated_after_message_id,
        )
        session.add(config)
    else:
        config.enabled = True
        config.guild_id = guild_id
        config.min_messages = min_messages
    return config


async def disable_channel(session: AsyncSession, channel_id: int) -> bool:
    config = await session.get(ChannelConfig, channel_id)
    if config is None:
        return False
    config.enabled = False
    return True
