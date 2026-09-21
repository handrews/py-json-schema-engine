# Bench results comparison (M8 Step 4), ported in intent from the TS
# reference engine's `bench/compare.ts`. Pure data in, text out — no file
# I/O here, so it is directly testable; `scripts/bench.py --compare`
# handles reading the two JSON files and printing this module's output.

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, cast

from json_schema_engine.core import JsonValue


class _Row(TypedDict):
    task: str
    ops_per_sec: float


def _ops_by_task(results: Mapping[str, JsonValue]) -> dict[str, float]:
    raw_rows = results.get("results")
    rows = cast("list[_Row]", raw_rows) if isinstance(raw_rows, list) else []
    return {row["task"]: row["ops_per_sec"] for row in rows}


def _fmt_ops(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _fmt_ratio(before: float | None, after: float | None) -> str:
    if before is None or after is None or before == 0:
        return "n/a"
    return f"{after / before:.2f}"


def compare(before: Mapping[str, JsonValue], after: Mapping[str, JsonValue]) -> str:
    """A `task | before ops/s | after ops/s | after/before` table joined
    by task name, plus the tasks present on only one side. A missing side
    (a task excluded, or not run, in one file) prints `n/a` rather than
    a fabricated ratio."""
    before_ops = _ops_by_task(before)
    after_ops = _ops_by_task(after)
    tasks = sorted(set(before_ops) | set(after_ops))

    header = ["task", "before ops/s", "after ops/s", "after/before"]
    rows = [header]
    for task in tasks:
        b = before_ops.get(task)
        a = after_ops.get(task)
        rows.append([task, _fmt_ops(b), _fmt_ops(a), _fmt_ratio(b, a)])
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = [
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True))
        for row in rows
    ]

    only_before = sorted(set(before_ops) - set(after_ops))
    only_after = sorted(set(after_ops) - set(before_ops))
    if only_before:
        lines.append("")
        lines.append("only in before:")
        lines.extend(f"  {task}" for task in only_before)
    if only_after:
        lines.append("")
        lines.append("only in after:")
        lines.extend(f"  {task}" for task in only_after)

    return "\n".join(lines).rstrip() + "\n"
