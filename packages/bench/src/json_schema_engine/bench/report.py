# Bench report formatting (M6 Step 5). Report-only: this module prints a
# human-readable table from a `harness.Results`; it enforces no thresholds
# and gates nothing.

from __future__ import annotations

from json_schema_engine.bench.harness import Results

_PARTITIONS = ("compile", "hot", "valid", "invalid")


def _ops_by(results: Results) -> dict[str, dict[str, dict[str, float]]]:
    """`{corpus: {subject: {partition: ops_per_sec}}}`."""
    table: dict[str, dict[str, dict[str, float]]] = {}
    for row in results.results:
        by_subject = table.setdefault(row.corpus, {})
        by_partition = by_subject.setdefault(row.subject, {})
        by_partition[row.partition] = row.ops_per_sec
    return table


def _fmt_ops(value: float | None) -> str:
    return "-" if value is None else f"{value:,.0f}"


def _fmt_ratio(numerator: float | None, denominator: float | None) -> str:
    if numerator is None or denominator is None or denominator == 0:
        return "n/a"
    return f"{numerator / denominator:.2f}x"


def format_table(results: Results) -> str:
    """A per-corpus table of subjects x partitions (ops/s), plus two
    compiled-vs-reference ratio lines per corpus. No thresholds — this is
    reporting, not a gate."""
    lines: list[str] = [
        f"jse bench — {results.generated_at} — python {results.python} — "
        f"budget {results.budget_ms}ms",
        "",
    ]
    ops_by = _ops_by(results)
    corpus_names = [meta.name for meta in results.corpora if meta.name in ops_by]

    for corpus_name in corpus_names:
        by_subject = ops_by[corpus_name]
        lines.append(f"=== {corpus_name} ===")
        header = ["subject", *_PARTITIONS]
        rows = [header]
        for subject_name, by_partition in by_subject.items():
            rows.append(
                [subject_name, *(_fmt_ops(by_partition.get(p)) for p in _PARTITIONS)]
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
        for row in rows:
            lines.append(
                "  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True))
            )

        compiled = by_subject.get("jse compiled flag", {})
        interpreter = by_subject.get("jse interpreter flag", {})
        fastjsonschema_ = by_subject.get("fastjsonschema", {})
        lines.append(
            "  compiled/interpreter (hot): "
            + _fmt_ratio(compiled.get("hot"), interpreter.get("hot"))
        )
        lines.append(
            "  compiled/fastjsonschema (hot): "
            + _fmt_ratio(compiled.get("hot"), fastjsonschema_.get("hot"))
        )
        lines.append("")

    if results.exclusions:
        lines.append("=== exclusions ===")
        for exclusion in results.exclusions:
            lines.append(
                f"  {exclusion.corpus} | {exclusion.subject}: {exclusion.reason}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
