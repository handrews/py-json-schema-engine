"""Fast smoke test for the bench harness (M6 Step 5, M8 Step 6).

Runs the real harness at a tiny budget, filtered to one corpus at a time,
so it stays well under a few seconds. It checks the harness's own
contract — every subject either produces timed results or a recorded
exclusion with a reason — not any performance threshold (the harness is
report-only).
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from json_schema_engine.bench import compare, format_table
from json_schema_engine.bench.harness import CorpusMeta, Results, TaskResult, run
from json_schema_engine.bench.subjects import SUBJECTS
from json_schema_engine.core import JsonValue, create_engine

# `corpora/api_payload.py` is loaded the same way `corpora.py` loads it
# (see that module's header): the `corpora/` directory is shadowed by the
# sibling `corpora.py` module, so it cannot be reached as a submodule, and
# its generator function is private to that loading trick either way —
# loading it directly here (rather than reaching into `corpora.py`'s
# private `_api_payload` attribute) keeps this test off of internals
# `reportPrivateUsage` would otherwise flag.
_CORPORA_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "json_schema_engine"
    / "bench"
    / "corpora"
)


def _load_api_payload_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_bench._api_payload_gen", _CORPORA_DIR / "api_payload.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load api_payload generator for testing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Subjects whose disagreement with the oracle would mean an engine or
# compiler bug, not a legitimate competitor divergence — these must never
# appear in `exclusions` for the `user` corpus (its schema has no feature
# `jse standalone` would refuse to emit, so it must not appear either).
_MUST_NOT_BE_EXCLUDED = {
    "jse interpreter flag",
    "jse compiled flag",
    "jse standalone",
}


def test_user_corpus_smoke() -> None:
    results = run(budget_ms=5, filter_regex="user")

    assert results.results, "expected at least one timed task"
    assert all(row.corpus == "user" for row in results.results)
    assert all(exclusion.corpus == "user" for exclusion in results.exclusions)

    timed_subjects = {row.subject for row in results.results}
    excluded_subjects = {exclusion.subject for exclusion in results.exclusions}
    all_subject_names = {subject.name for subject in SUBJECTS}

    # Every subject is accounted for: either it produced at least one
    # timed row, or it was excluded (with a reason) — never silently
    # missing.
    assert timed_subjects | excluded_subjects >= all_subject_names

    for exclusion in results.exclusions:
        assert exclusion.reason, "exclusion must record a reason"
        assert exclusion.subject not in _MUST_NOT_BE_EXCLUDED, (
            f"unexpected exclusion for {exclusion.subject}: {exclusion.reason}"
        )


def test_oas_document_corpus() -> None:
    """Every jse tier must survive oracle-checking and get timed: since M9
    the schema's `$dynamicRef` sites resolve at plan time and its root's
    `anyOf` + `unevaluatedProperties` consumer is tracked at runtime, so
    the plan has no interpreted unit and `jse standalone` emits it."""
    results = run(budget_ms=5, filter_regex="oas-document")

    assert results.results, "expected at least one timed task"
    assert all(row.corpus == "oas-document" for row in results.results)

    timed_subjects = {row.subject for row in results.results}
    assert {"jse interpreter flag", "jse compiled flag", "jse standalone"} <= (
        timed_subjects
    )
    assert not [e for e in results.exclusions if e.subject.startswith("jse")]


def test_api_payload_corpus_smoke() -> None:
    results = run(budget_ms=5, filter_regex="api-payload")

    assert results.results, "expected at least one timed task"
    assert all(row.corpus == "api-payload" for row in results.results)

    for exclusion in results.exclusions:
        assert exclusion.reason, "exclusion must record a reason"
        assert exclusion.subject not in _MUST_NOT_BE_EXCLUDED, (
            f"unexpected exclusion for {exclusion.subject}: {exclusion.reason}"
        )


def test_api_payload_generator_agrees_with_oracle() -> None:
    """The generator's own valid/invalid bookkeeping (each planted defect
    is supposed to make the schema reject the instance) must agree with
    the interpreter oracle on every instance — otherwise a defect that the
    schema does not actually reject would silently mislabel a corpus
    instance instead of failing loudly here."""
    generator = _load_api_payload_generator()
    instances, by_construction = generator.build_api_payloads()
    schema: JsonValue = json.loads(
        (_CORPORA_DIR / "api-payload-schema.json").read_text()
    )
    engine = create_engine()
    uri = engine.register_schema(schema, "https://bench.example/test-oracle")
    oracle = [engine.evaluate(uri, instance).valid for instance in instances]
    assert by_construction == oracle


def test_results_metadata() -> None:
    results = run(budget_ms=5, filter_regex="user")

    assert isinstance(results.machine, str)
    assert results.machine  # never empty: falls back to "unknown"
    assert results.commit is None or isinstance(results.commit, str)
    assert set(results.subjects) == {
        "json-schema-engine",
        "ecma-regex",
        "fastjsonschema",
        "jsonschema",
    }
    assert all(isinstance(version, str) for version in results.subjects.values())


def test_compare_ratio_and_missing_sides() -> None:
    before: dict[str, JsonValue] = {
        "results": [
            {"task": "a", "ops_per_sec": 100.0},
            {"task": "b", "ops_per_sec": 50.0},
        ]
    }
    after: dict[str, JsonValue] = {
        "results": [
            {"task": "a", "ops_per_sec": 150.0},
            {"task": "c", "ops_per_sec": 10.0},
        ]
    }

    table = compare(before, after)

    assert "1.50" in table  # a: 150/100
    assert "only in before:" in table
    assert "  b" in table
    assert "only in after:" in table
    assert "  c" in table


def test_compare_says_which_way_is_faster() -> None:
    table = compare(
        {"results": [{"task": "a", "ops_per_sec": 100.0}]},
        {"results": [{"task": "a", "ops_per_sec": 150.0}]},
    )
    assert table.startswith("Ops/s: higher is faster.")


def _row(corpus: str, subject: str, ops: float) -> TaskResult:
    return TaskResult(
        f"{corpus} | hot | {subject}", corpus, "hot", subject, ops, 0.0, 1
    )


def test_the_report_reads_each_ratio_out_in_words() -> None:
    results = Results(
        generated_at="t",
        python="3",
        platform="p",
        machine="m",
        commit=None,
        subjects={},
        budget_ms=1,
        corpora=[CorpusMeta("user", 1, 0)],
        exclusions=[],
        results=[
            _row("user", "jse compiled flag", 3400.0),
            _row("user", "jse interpreter flag", 33.0),
            _row("user", "jsonschema", 100.0),
        ],
    )
    report = format_table(results)
    assert "Numbers are operations per second: higher is faster" in report
    assert "compiled/jsonschema (hot): 34.00x (compiled faster)" in report
    assert "interpreter/jsonschema (hot): 0.33x (interpreter slower)" in report
    # A missing side still prints `n/a`, with nothing to read out.
    assert "compiled/fastjsonschema (hot): n/a\n" in report
