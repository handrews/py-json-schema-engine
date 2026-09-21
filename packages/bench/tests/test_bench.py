"""Fast smoke test for the bench harness (M6 Step 5).

Runs the real harness at a tiny budget, filtered to the `user` corpus, so
it stays well under a few seconds. It checks the harness's own contract —
every subject either produces timed results or a recorded exclusion with
a reason — not any performance threshold (the harness is report-only).
"""

from json_schema_engine.bench.harness import run
from json_schema_engine.bench.subjects import SUBJECTS

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
