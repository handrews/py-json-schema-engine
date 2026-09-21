"""Bench CLI for json-schema-engine (M6 Step 5).

Prints the report table; writes JSON to `--out` when given (never to the
committed `packages/bench/results/results.json` unless `--out` names it
explicitly — this script has no default output path).

Run with: `uv run python scripts/bench.py [--budget-ms 250] [--filter REGEX]
[--out PATH]`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from json_schema_engine.bench import format_table, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--budget-ms",
        type=int,
        default=250,
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
    args = parser.parse_args(argv)

    results = run(budget_ms=args.budget_ms, filter_regex=args.filter_regex)
    sys.stdout.write(format_table(results))
    if args.out is not None:
        args.out.write_text(json.dumps(results.to_dict(), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
