from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_cursor_write_has_single_implementation() -> None:
    sources = list((ROOT / "src").rglob("*.py"))
    definitions = [
        path for path in sources if "async def commit_cursor(" in path.read_text(encoding="utf-8")
    ]
    assert definitions == [ROOT / "src/classroom_summary/storage/cursor.py"]


def test_only_cron_delivery_calls_commit_cursor() -> None:
    cron = (ROOT / "src/classroom_summary/process/cron.py").read_text(encoding="utf-8")
    ondemand = (ROOT / "src/classroom_summary/process/ondemand.py").read_text(encoding="utf-8")
    assert "await commit_cursor(" in cron
    assert "commit_cursor" not in ondemand
    assert cron.index("post_milestone") < cron.index("await commit_cursor(")
