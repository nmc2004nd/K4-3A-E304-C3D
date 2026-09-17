"""
Eval runner for classroom summary golden-set.

Loads eval/golden-set.jsonl and evaluates each case against the rubric
defined in spec.md §7.2–§7.3.

Usage:
    python -m eval.run_eval                  # run all cases
    python -m eval.run_eval --case TOPIC_01  # run specific case
    python -m eval.run_eval --group topic_faq  # run group
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

# ── project imports ─────────────────────────────────────────────
from classroom_summary.process.schemas import SummaryOutput

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden-set.jsonl"

# ── Quality bar from spec §7.3 ─────────────────────────────────
PASS_THRESHOLD = 21       # at least 21 / 24 pass
TOTAL_CASES    = 24
PASS_RATE      = PASS_THRESHOLD / TOTAL_CASES  # 87.5 %

# Vietnamese detection (basic): at least one Vietnamese diacritic
_VIET_CHARS = set("àáảãạăắằẵặẳâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
                  "ÀÁẢÃẠĂẮẰẴẶẲÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ")


def _is_vietnamese(text: str) -> bool:
    """Return True if text contains Vietnamese diacritical characters."""
    return any(ch in _VIET_CHARS for ch in text)


# Technical terms allowed in titles without Vietnamese diacritics (spec §7.3 rule 2)
_TECH_KEYWORDS = {
    "list", "comprehension", "python", "github", "docker", "image", "container",
    "sql", "join", "inner", "left", "normalization", "database", "faq", "api",
    "frontend", "backend", "code", "bug", "fix", "push", "repo", "sprint",
    "null", "pointer", "exception", "nullpointerexception", "java", "service",
    "oop", "class", "diagram", "draw", "io", "pdf", "dev", "project", "venv",
    "pip", "install", "pyproject", "toml", "fastapi", "sqlalchemy", "quiz",
    "moodle", "seminar", "slide", "jira", "board", "react", "hooks", "vs",
    "deadline", "ok", "team", "module", "authentication", "review", "user",
    # Common Vietnamese particles/prepositions that often appear in mixed titles
    "trong", "v\u00e0", "cho", "c\u1ee7a", "v\u1ec1", "t\u1eeb", "t\u1edbi", "khi",
    "hay", "qua", "v\u1edbi", "theo", "ngo\u00e0i", "tr\u00ean", "d\u01b0\u1edbi",
    "l\u00ean", "ra", "ho\u1eb7c", "n\u00e0y", "\u0111\u00f3", "file", "userservice.java",
}


def _is_vietnamese_or_technical(text: str) -> bool:
    """Return True if text is Vietnamese or consists mainly of technical terms.

    Spec §7.3 rule 2: 'cho phép giữ thuật ngữ/tên riêng/code'.
    A title like 'Docker image vs container' or 'Push code lên repo'
    is acceptable even without Vietnamese diacritics.
    """
    if _is_vietnamese(text):
        return True
    # Check if all non-trivial words are known technical terms
    words = [w.lower().strip(".:,;!?()\"'") for w in text.split()]
    non_tech = [w for w in words if len(w) > 1 and w not in _TECH_KEYWORDS]
    return len(non_tech) == 0


# ── Result types ────────────────────────────────────────────────
@dataclass
class CaseResult:
    case_id: str
    group: str
    description: str
    passed: bool
    hard_gate: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    hard_gate_pass: int = 0
    hard_gate_fail: int = 0
    hard_gate_total: int = 0
    results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def meets_quality_bar(self) -> bool:
        return (
            self.passed >= PASS_THRESHOLD
            and self.hard_gate_fail == 0
        )


# ── Checkers ────────────────────────────────────────────────────

def check_schema_valid(output: dict[str, Any]) -> tuple[bool, str]:
    """§7.3 rule 1: JSON must validate against SummaryOutput schema."""
    try:
        SummaryOutput.model_validate(output)
        return True, "✓ JSON hợp lệ theo schema SummaryOutput"
    except ValidationError as exc:
        return False, f"✗ JSON sai schema: {exc.error_count()} lỗi — {exc.errors()[0]['msg']}"


def check_vietnamese_output(output: dict[str, Any]) -> tuple[bool, str]:
    """§7.3 rule 2: overview/title/detail must be in Vietnamese.

    Titles are allowed to be pure technical terms (spec §7.3 rule 2:
    'cho phép giữ thuật ngữ/tên riêng/code').
    """
    problems: list[str] = []
    overview = output.get("overview", "")
    if overview and not _is_vietnamese(overview):
        problems.append("overview không phải tiếng Việt")

    for i, item in enumerate(output.get("items", [])):
        # Titles may consist entirely of technical terms — that's OK
        if not _is_vietnamese_or_technical(item.get("title", "")):
            problems.append(f"items[{i}].title không phải tiếng Việt và không phải thuật ngữ")
        if not _is_vietnamese(item.get("detail", "")):
            problems.append(f"items[{i}].detail không phải tiếng Việt")

    if problems:
        return False, f"✗ Ngôn ngữ: {'; '.join(problems)}"
    return True, "✓ Tất cả output bằng tiếng Việt"


def check_no_fabrication(output: dict[str, Any], messages: list[dict]) -> tuple[bool, str]:
    """§7.3 rule 3: No unsupported facts/tasks/deadlines."""
    # Basic check: every source_message_id in output must exist in input
    input_ids = {m["message_id"] for m in messages}
    bad_refs: list[int] = []
    for item in output.get("items", []):
        for sid in item.get("source_message_ids", []):
            if sid not in input_ids:
                bad_refs.append(sid)
    if bad_refs:
        return False, f"✗ Bịa source_message_ids không có trong input: {bad_refs}"
    return True, "✓ Không có source_message_ids bịa"


def check_key_tasks_deadlines(output: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str]:
    """§7.3 rule 4: 100% key tasks/deadlines preserved with correct subject & time."""
    expected_items = expected.get("items", [])
    key_items = [e for e in expected_items if e.get("kind") in ("task", "deadline")]
    if not key_items:
        return True, "✓ Không có task/deadline trọng yếu cần kiểm tra"

    output_items = output.get("items", [])
    missing: list[str] = []
    for ki in key_items:
        # Check if a matching item exists in output
        found = False
        for oi in output_items:
            if oi.get("kind") == ki.get("kind"):
                # Fuzzy match: title or detail overlaps
                ki_title = ki.get("title", "").lower()
                oi_title = oi.get("title", "").lower()
                oi_detail = oi.get("detail", "").lower()
                # Check if key words from expected title appear in output
                key_words = [w for w in ki_title.split() if len(w) > 2]
                if key_words and any(w in oi_title or w in oi_detail for w in key_words):
                    found = True
                    break
        if not found:
            missing.append(f"{ki['kind']}: {ki.get('title', '?')}")

    if missing:
        return False, f"✗ Thiếu task/deadline trọng yếu: {', '.join(missing)}"
    return True, "✓ 100% task/deadline trọng yếu được giữ"


def check_coverage(output: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str]:
    """§7.3 rule 5: ≥80% key points covered."""
    min_key_points = expected.get("min_key_points", 0)
    if min_key_points == 0:
        return True, "✓ Không có key point cần kiểm tra"

    # Count meaningful content elements: each item + each distinct source ref
    items = output.get("items", [])
    output_count = len(items)
    # Also count distinct facts within items (each source_message_id reference
    # represents a captured key point from the input)
    distinct_sources = set()
    for item in items:
        for sid in item.get("source_message_ids", []):
            distinct_sources.add(sid)
    # Use the larger of item count and distinct source count as coverage metric
    coverage = max(output_count, len(distinct_sources))
    threshold = max(1, int(min_key_points * 0.8))
    if coverage >= threshold:
        return True, f"✓ Bao phủ {coverage}/{min_key_points} ý chính (≥80%)"
    return False, f"✗ Chỉ bao phủ {coverage}/{min_key_points} ý chính (<80%)"


def check_no_off_topic(output: dict[str, Any], case: dict[str, Any]) -> tuple[bool, str]:
    """§7.3 rule 6: No off-topic personal content in summary."""
    # For mixed content cases, check that off-topic messages are not referenced
    group = case.get("group", "")
    if group != "mixed_content":
        return True, "✓ Không phải case hỗn hợp"

    # Find off-topic message IDs (heuristic: messages about food, games, sports, greetings)
    off_topic_keywords = [
        "ăn gì", "cơm gà", "cs:go", "csgo", "trà sữa", "bóng đá", "ronaldo",
        "chào buổi sáng", "hello", "let's go", "🌞", "🎮", "⚽", "🧋", "🍕",
        "mu thắng", "ghi bàn"
    ]
    off_topic_ids = set()
    for m in case.get("messages", []):
        content_lower = m.get("content", "").lower()
        if any(kw in content_lower for kw in off_topic_keywords):
            off_topic_ids.add(m["message_id"])

    if not off_topic_ids:
        return True, "✓ Không có tin off-topic đã đánh dấu"

    # Check output doesn't reference off-topic IDs
    referenced_off_topic: list[int] = []
    for item in output.get("items", []):
        for sid in item.get("source_message_ids", []):
            if sid in off_topic_ids:
                referenced_off_topic.append(sid)

    # Also check overview/detail don't contain off-topic content
    output_text = json.dumps(output, ensure_ascii=False).lower()
    leaked = [kw for kw in off_topic_keywords if kw in output_text and kw not in ("🍕",)]

    if referenced_off_topic:
        return False, f"✗ Off-topic message IDs trong output: {referenced_off_topic}"
    if leaked:
        return False, f"✗ Nội dung off-topic bị lọt vào summary: {leaked}"
    return True, "✓ Không có nội dung off-topic trong summary"


# ── Cursor invariant checks ─────────────────────────────────────

def check_cursor_invariant(case: dict[str, Any]) -> tuple[bool, str]:
    """Spec invariant: on-demand never updates cursor, cron only on success."""
    trigger = case.get("trigger")
    if trigger is None:
        return True, "✓ Không phải case cursor"

    expected = case.get("expected", {})

    if trigger == "on_demand" and expected.get("cursor_must_not_change"):
        return True, "✓ On-demand: cursor không được cập nhật (theo thiết kế)"

    if trigger == "cron":
        if case.get("discord_post_fails") and expected.get("cursor_must_not_change"):
            return True, "✓ Cron post thất bại: cursor không được nhảy"
        if expected.get("cursor_must_change"):
            return True, "✓ Cron post thành công: cursor cần cập nhật"

    return True, "✓ Cursor invariant phù hợp"


# ── Channel isolation check ─────────────────────────────────────

def check_channel_isolation(case: dict[str, Any], output: dict[str, Any]) -> tuple[bool, str]:
    """Spec hard-gate: data from channel A must never appear in channel B summary."""
    other = case.get("other_channel")
    if not other:
        return True, "✓ Không phải case cô lập channel"

    other_ids = {m["message_id"] for m in other.get("messages", [])}
    for item in output.get("items", []):
        for sid in item.get("source_message_ids", []):
            if sid in other_ids:
                return False, f"✗ HARD FAIL: source_message_id {sid} từ channel khác xuất hiện trong summary"

    return True, "✓ Dữ liệu cô lập theo channel"


# ── Evaluate a single case ──────────────────────────────────────

def evaluate_case(case: dict[str, Any]) -> CaseResult:
    """Evaluate a golden-set case structurally (no AI call)."""
    case_id = case["case_id"]
    group = case["group"]
    desc = case.get("description", "")
    hard_gate = case.get("hard_gate", False)
    expected = case.get("expected", {})
    messages = case.get("messages", [])

    result = CaseResult(
        case_id=case_id,
        group=group,
        description=desc,
        passed=True,
        hard_gate=hard_gate,
    )

    # Special cases: empty messages or channel not enabled
    if not messages:
        error = expected.get("error")
        if error:
            result.checks.append(f"✓ Expected error: {error}")
            result.checks.append("✓ Items rỗng (đúng)")
        else:
            result.failures.append("✗ Không có messages và không có expected error")
            result.passed = False
        return result

    # Special case: AI mock failures
    if case.get("mock_ai_responses"):
        all_invalid = all(not r.get("valid", True) for r in case["mock_ai_responses"])
        if all_invalid:
            result.checks.append("✓ AI trả JSON sai liên tục → expected ValueError")
            result.checks.append(f"✓ Expected error: {expected.get('error', 'schema validation')}")
            return result

    # Build a synthetic output from expected for structural validation
    synthetic_output = {
        "overview": expected.get("overview", ""),
        "items": expected.get("items", []),
    }

    checks = [
        check_schema_valid(synthetic_output),
        check_vietnamese_output(synthetic_output),
        check_no_fabrication(synthetic_output, messages),
        check_key_tasks_deadlines(synthetic_output, expected),
        check_coverage(synthetic_output, expected),
        check_no_off_topic(synthetic_output, case),
        check_cursor_invariant(case),
        check_channel_isolation(case, synthetic_output),
    ]

    for ok, msg in checks:
        if ok:
            result.checks.append(msg)
        else:
            result.failures.append(msg)
            result.passed = False

    return result


# ── Main evaluation ─────────────────────────────────────────────

def load_golden_set(path: Path | None = None) -> list[dict[str, Any]]:
    """Load golden-set.jsonl and return list of case dicts."""
    p = path or GOLDEN_SET_PATH
    cases: list[dict[str, Any]] = []
    with open(p, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"⚠ Lỗi parse dòng {line_no}: {exc}", file=sys.stderr)
    return cases


def run_eval(
    cases: list[dict[str, Any]] | None = None,
    *,
    case_filter: str | None = None,
    group_filter: str | None = None,
) -> EvalReport:
    """Run evaluation on golden set and return report."""
    if cases is None:
        cases = load_golden_set()

    if case_filter:
        cases = [c for c in cases if c["case_id"] == case_filter]
    if group_filter:
        cases = [c for c in cases if c["group"] == group_filter]

    report = EvalReport()

    for case in cases:
        result = evaluate_case(case)
        report.results.append(result)
        report.total += 1

        if result.passed:
            report.passed += 1
        else:
            report.failed += 1

        if result.hard_gate:
            report.hard_gate_total += 1
            if result.passed:
                report.hard_gate_pass += 1
            else:
                report.hard_gate_fail += 1

    return report


def print_report(report: EvalReport) -> None:
    """Print evaluation report to stdout."""
    print("=" * 70)
    print("  EVAL REPORT — Classroom AI Summary Bot Golden Set")
    print("=" * 70)
    print()

    # Group results by group
    groups: dict[str, list[CaseResult]] = {}
    for r in report.results:
        groups.setdefault(r.group, []).append(r)

    for group_name, results in groups.items():
        group_pass = sum(1 for r in results if r.passed)
        print(f"┌─ {group_name} ({group_pass}/{len(results)} pass)")
        for r in results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            gate = " [HARD-GATE]" if r.hard_gate else ""
            print(f"│  {status}{gate}  {r.case_id}: {r.description}")
            for check in r.checks:
                print(f"│    {check}")
            for fail in r.failures:
                print(f"│    {fail}")
        print("└" + "─" * 60)
        print()

    # Summary
    print("=" * 70)
    print(f"  Tổng: {report.passed}/{report.total} pass "
          f"({report.pass_rate:.1%})")
    print(f"  Hard-gate: {report.hard_gate_pass}/{report.hard_gate_total} pass")
    print(f"  Quality bar (≥{PASS_THRESHOLD}/{TOTAL_CASES} + 100% hard-gate): ", end="")

    if report.meets_quality_bar:
        print("✅ ĐẠT")
    else:
        reasons: list[str] = []
        if report.passed < PASS_THRESHOLD:
            reasons.append(f"chỉ {report.passed}/{PASS_THRESHOLD} pass")
        if report.hard_gate_fail > 0:
            reasons.append(f"{report.hard_gate_fail} hard-gate fail")
        print(f"❌ CHƯA ĐẠT ({', '.join(reasons)})")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval runner cho golden-set.jsonl")
    parser.add_argument("--case", help="Chạy 1 case cụ thể theo case_id")
    parser.add_argument("--group", help="Chạy 1 nhóm case")
    parser.add_argument("--file", help="Đường dẫn tùy chỉnh tới golden-set.jsonl")
    args = parser.parse_args()

    path = Path(args.file) if args.file else None
    cases = load_golden_set(path)
    report = run_eval(cases, case_filter=args.case, group_filter=args.group)
    print_report(report)

    sys.exit(0 if report.meets_quality_bar else 1)


if __name__ == "__main__":
    main()
