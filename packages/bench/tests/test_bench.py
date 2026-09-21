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

from json_schema_engine.bench import compare
from json_schema_engine.bench.harness import run
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
    """The interpreter and compiled tiers must survive oracle-checking and
    get timed; `jse standalone` is the one legitimate jse exclusion.

    Verified directly against `build_plan` (not asserted here, since it is
    an implementation detail rather than part of the harness's contract):
    the root unit's `anyOf` + `unevaluatedProperties` combination makes its
    evaluated-property coverage statically unknowable (D9a consumer
    licensing — an `anyOf` branch is conditional, so it never contributes
    a static half), and planning reports that generic "unlowerable"
    fallback for the root before it ever descends far enough to see the
    schema's `$dynamicRef` sites. So the recorded reason names the
    generic interpreter fallback, not `$dynamicRef` by keyword — this
    assertion checks the reason the harness actually gives.
    """
    results = run(budget_ms=5, filter_regex="oas-document")

    assert results.results, "expected at least one timed task"
    assert all(row.corpus == "oas-document" for row in results.results)

    timed_subjects = {row.subject for row in results.results}
    assert "jse interpreter flag" in timed_subjects
    assert "jse compiled flag" in timed_subjects

    jse_exclusions = [
        exclusion
        for exclusion in results.exclusions
        if exclusion.subject.startswith("jse")
    ]
    assert [e.subject for e in jse_exclusions] == ["jse standalone"]
    assert "needs the interpreter at evaluation time" in jse_exclusions[0].reason


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
