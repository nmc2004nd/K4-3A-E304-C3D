from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from classroom_summary.process.cron import CronRunner
from classroom_summary.process.pipeline import PipelineResult
from classroom_summary.process.schemas import SummaryOutput


class Context:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


class Session:
    def __init__(self, summary: object) -> None:
        self.summary = summary

    async def commit(self) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> object:
        return self.summary


class Sessions:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __call__(self) -> Context:
        return Context(self.session)

    def begin(self) -> Context:
        return Context(self.session)


class Lock:
    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


class BusyLock(Lock):
    async def acquire(self) -> bool:
        return False


def runner(discord: object, summary: object) -> CronRunner:
    settings = SimpleNamespace(cron_lock_ttl_seconds=60, process_message_cap=100)
    database = SimpleNamespace(sessions=Sessions(Session(summary)))
    source = SimpleNamespace(load=AsyncMock(return_value=([SimpleNamespace(message_id=20)], False)))
    pipeline = SimpleNamespace(
        run=AsyncMock(
            return_value=PipelineResult(
                summary=summary,
                output=SummaryOutput(overview="Result", items=[]),
                message_count=1,
                last_message_id=20,
            )
        )
    )
    return CronRunner(settings, database, object(), source, pipeline, discord)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_overlapping_cron_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = SimpleNamespace(id="id", token_usage=1)
    discord = SimpleNamespace(post_milestone=AsyncMock())
    instance = runner(discord, summary)
    monkeypatch.setattr("classroom_summary.process.cron.RedisLock", lambda *args: BusyLock())

    assert not await instance.run_channel(
        SimpleNamespace(channel_id=1, activated_after_message_id=0, min_messages=1)
    )
    instance.source.load.assert_not_awaited()
    discord.post_milestone.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_post_never_commits_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = SimpleNamespace(id="id", token_usage=1)
    discord = SimpleNamespace(post_milestone=AsyncMock(side_effect=RuntimeError("Discord down")))
    commit = AsyncMock()
    monkeypatch.setattr("classroom_summary.process.cron.RedisLock", lambda *args: Lock())
    monkeypatch.setattr("classroom_summary.process.cron.get_cursor", AsyncMock(return_value=10))
    monkeypatch.setattr(
        "classroom_summary.process.cron.latest_published_summary", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("classroom_summary.process.cron.commit_cursor", commit)

    with pytest.raises(RuntimeError, match="Discord down"):
        await runner(discord, summary).run_channel(
            SimpleNamespace(channel_id=1, activated_after_message_id=0, min_messages=1)
        )

    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_post_commits_last_processed_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = SimpleNamespace(id="id", token_usage=1)
    discord = SimpleNamespace(
        post_milestone=AsyncMock(return_value=100),
        create_thread=AsyncMock(return_value=101),
    )
    commit = AsyncMock()
    monkeypatch.setattr("classroom_summary.process.cron.RedisLock", lambda *args: Lock())
    monkeypatch.setattr("classroom_summary.process.cron.get_cursor", AsyncMock(return_value=10))
    monkeypatch.setattr(
        "classroom_summary.process.cron.latest_published_summary", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("classroom_summary.process.cron.commit_cursor", commit)

    assert await runner(discord, summary).run_channel(
        SimpleNamespace(channel_id=1, activated_after_message_id=0, min_messages=1)
    )
    commit.assert_awaited_once()
    assert commit.await_args.args[1:] == (1, 20)
