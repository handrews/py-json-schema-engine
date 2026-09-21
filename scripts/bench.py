"""Bench CLI for json-schema-engine (M6 Step 5, M8 Step 4).

Prints the report table; writes JSON to `--out` when given (never to the
committed `packages/bench/results/results.json` unless `--out` names it
explicitly — this script has no default output path).

Run with: `uv run python scripts/bench.py [--budget-ms 250] [--filter REGEX]
[--out PATH]`

`--compare BEFORE AFTER` instead loads two previously written results JSON
files and prints a before/after ops-per-second comparison; it is mutually
exclusive with `--budget-ms`/`--filter`/`--out` (there is nothing to run).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from json_schema_engine.bench import compare, format_table, run
from json_schema_engine.core import JsonValue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--budget-ms",
        type=int,
        default=None,
        help="time budget per task, in milliseconds (default: 250)",
    )
    parser.add_argument(
        "--filter",
        dest="filter_regex",
        default=None,
        help="regex restricting which corpus/subject pairs run",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the results as JSON to this path",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        type=Path,
        default=None,
        help=(
            "compare two results JSON files instead of running the bench; "
            "mutually exclusive with --budget-ms/--filter/--out"
        ),
    )
    args = parser.parse_args(argv)

    if args.compare is not None:
        run_only_args_given = (
            args.budget_ms is not None
            or args.filter_regex is not None
            or args.out is not None
        )
        if run_only_args_given:
            parser.error(
                "--compare cannot be combined with --budget-ms, --filter, or --out"
            )
        before_path, after_path = args.compare
        before: dict[str, JsonValue] = json.loads(before_path.read_text())
        after: dict[str, JsonValue] = json.loads(after_path.read_text())
        sys.stdout.write(compare(before, after))
        return 0

    budget_ms = 250 if args.budget_ms is None else args.budget_ms
    results = run(budget_ms=budget_ms, filter_regex=args.filter_regex)
    sys.stdout.write(format_table(results))
    if args.out is not None:
        args.out.write_text(json.dumps(results.to_dict(), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
