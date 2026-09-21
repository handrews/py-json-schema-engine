"""Tests for json_schema_engine.test_kit.suite (DESIGN.md D12)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from json_schema_engine.test_kit.suite import (
    Json,
    SuiteCase,
    collect_suite_params,
    count_params,
    load_suite_file,
    unsupported_in,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mini-suite"
SUITE_ROOT = (
    Path(__file__).resolve().parents[3] / "test-suite" / "tests" / "draft2020-12"
)
UNSUPPORTED = frozenset({"unevaluatedProperties"})


def test_load_suite_file_flattens_groups_into_cases() -> None:
    cases = load_suite_file(FIXTURES / "alpha.json")

    assert len(cases) == 5
    assert all(case.file == "alpha" for case in cases)
    assert [c.description for c in cases[:2]] == ["case-a", "case-a"]
    assert cases[0].valid is True
    assert cases[1].valid is False
    assert cases[0].skip_reason is None


def test_unsupported_in_finds_top_level_keyword() -> None:
    schema: Json = {"unevaluatedProperties": False}
    assert unsupported_in(schema, UNSUPPORTED) == {"unevaluatedProperties"}


def test_unsupported_in_ignores_enum_data() -> None:
    schema: Json = {"enum": [{"unevaluatedProperties": False}]}
    assert unsupported_in(schema, UNSUPPORTED) == set()


def test_unsupported_in_descends_properties_allof() -> None:
    schema: Json = {
        "properties": {"x": {"allOf": [{"unevaluatedProperties": False}]}},
    }
    assert unsupported_in(schema, UNSUPPORTED) == {"unevaluatedProperties"}


def test_unsupported_in_boolean_schema_has_no_hits() -> None:
    assert unsupported_in(True, UNSUPPORTED) == set()
    assert unsupported_in(False, UNSUPPORTED) == set()


def test_collect_suite_params_skips_only_the_unsupported_group() -> None:
    params = collect_suite_params(FIXTURES, ["alpha", "beta"], UNSUPPORTED)
    by_id = {p.id: p for p in params}

    # group-one: plain, not skipped, and its duplicate description gets a
    # unique suffix.
    assert "alpha/group-one/case-a" in by_id
    assert "alpha/group-one/case-a#2" in by_id
    assert len(by_id["alpha/group-one/case-a"].marks) == 0
    assert len(by_id["alpha/group-one/case-a#2"].marks) == 0

    # group-two-unsupported: top-level unsupported keyword, skipped.
    two = by_id["alpha/group-two-unsupported/case-a"]
    two_marks = list(two.marks)
    assert len(two_marks) == 1
    assert two_marks[0].name == "skip"
    assert two_marks[0].kwargs["reason"] == "uses unevaluatedProperties"
    two_case = cast(SuiteCase, two.values[0])
    assert two_case.skip_reason == "uses unevaluatedProperties"

    # group-three-enum-only: keyword name only appears as enum data, not
    # skipped.
    for suffix in ("matches enum member", "does not match enum member"):
        case_id = f"alpha/group-three-enum-only/{suffix}"
        assert len(by_id[case_id].marks) == 0

    # beta: unsupported keyword nested under properties/x/allOf/0, skipped.
    nested = by_id["beta/nested-in-allOf/case-a"]
    nested_marks = list(nested.marks)
    assert len(nested_marks) == 1
    assert nested_marks[0].name == "skip"


def test_collect_suite_params_ids_are_unique() -> None:
    params = collect_suite_params(FIXTURES, ["alpha", "beta"], UNSUPPORTED)
    ids = [p.id for p in params]
    assert len(ids) == len(set(ids))


def test_count_params_splits_run_and_skipped() -> None:
    params = collect_suite_params(FIXTURES, ["alpha", "beta"], UNSUPPORTED)
    run, skipped = count_params(params)

    # alpha: 2 (group-one) run + 1 (group-two) skipped + 2 (group-three) run
    # beta: 1 (nested-in-allOf) skipped
    assert skipped == 2
    assert run == 4
    assert run + skipped == len(params)


def test_count_params_with_no_unsupported_keywords() -> None:
    params = collect_suite_params(FIXTURES, ["alpha", "beta"], frozenset())
    run, skipped = count_params(params)
    assert skipped == 0
    assert run == len(params)


def test_load_suite_file_rejects_nan() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        load_suite_file(FIXTURES / "nan.json")


def test_load_suite_file_parses_every_draft2020_12_file_without_error() -> None:
    files = sorted(SUITE_ROOT.glob("*.json"))
    assert len(files) > 20  # sanity: the real submodule tree, not a stub

    total_cases = 0
    for file in files:
        cases = load_suite_file(file)
        total_cases += len(cases)

    assert total_cases > 1000
