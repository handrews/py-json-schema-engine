# Lowering IR-shape tests (M6 Step 2) for the object applicators
# (`patternProperties`, `additionalProperties`, `propertyNames`) and the
# `unevaluated*` static-coverage consumers. `properties`'s lowering is
# already covered as the EXEMPLAR elsewhere; these tests focus on what is
# new here: a swept binding, the sibling-derived `additionalProperties`
# cover expression, the `propertyNames` key cursor, and the
# `StaticCoverage`-driven `unevaluated*` sweeps (including the
# planner-bug `RuntimeError` when a consumer lowers without coverage).

import pytest

from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords.applicator_object import (
    ADDITIONAL_PROPERTIES,
    PATTERN_PROPERTIES,
    PROPERTY_NAMES,
)
from json_schema_engine.core.keywords.unevaluated import (
    UNEVALUATED_ITEMS,
    UNEVALUATED_PROPERTIES,
)
from json_schema_engine.core.lowering import (
    HERE,
    INSTANCE,
    Binding,
    ForEachIndex,
    ForEachKey,
    StaticCoverage,
    apply,
    child,
    in_consts,
    key,
    not_,
    or_,
    regex_test,
    type_is,
    when,
)

from .lowering_helpers import lower

# --- patternProperties -------------------------------------------------------


def test_pattern_properties_sweeps_matching_keys_per_pattern() -> None:
    value: JsonValue = {"^a": True, "^b": True}
    stmts = lower(PATTERN_PROPERTIES, value)
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            regex_test("^a", Binding(0)),
                            (apply(("^a",), child(HERE, Binding(0))),),
                        ),
                        when(
                            regex_test("^b", Binding(0)),
                            (apply(("^b",), child(HERE, Binding(0))),),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_pattern_properties_of_a_non_object_value_lowers_to_nothing() -> None:
    assert lower(PATTERN_PROPERTIES, "not-an-object") == ()


# --- additionalProperties ----------------------------------------------------


def test_additional_properties_with_no_sibling_covers_nothing() -> None:
    stmts = lower(ADDITIONAL_PROPERTIES, False, schema={})
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (when(not_(or_()), (apply((), child(HERE, Binding(0))),)),),
                ),
            ),
        ),
    )


def test_additional_properties_reads_sibling_names() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES, False, schema={"properties": {"a": True, "b": True}}
    )
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            not_(or_(in_consts(Binding(0), ("a", "b")))),
                            (apply((), child(HERE, Binding(0))),),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_additional_properties_reads_sibling_patterns() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES, False, schema={"patternProperties": {"^x": True}}
    )
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            not_(or_(regex_test("^x", Binding(0)))),
                            (apply((), child(HERE, Binding(0))),),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_additional_properties_combines_names_and_patterns() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES,
        False,
        schema={
            "properties": {"a": True},
            "patternProperties": {"^x": True},
        },
    )
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            not_(
                                or_(
                                    in_consts(Binding(0), ("a",)),
                                    regex_test("^x", Binding(0)),
                                )
                            ),
                            (apply((), child(HERE, Binding(0))),),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_additional_properties_ignores_non_object_siblings() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES,
        False,
        schema={"properties": ["not", "an", "object"], "patternProperties": True},
    )
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (when(not_(or_()), (apply((), child(HERE, Binding(0))),)),),
                ),
            ),
        ),
    )


# --- propertyNames ------------------------------------------------------------


def test_property_names_sweeps_with_the_key_as_the_cursor() -> None:
    stmts = lower(PROPERTY_NAMES, True)
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (ForEachKey(INSTANCE, 0, (apply((), key(0)),)),),
        ),
    )


# --- unevaluatedProperties ----------------------------------------------------

TOTAL_NAME_COVERAGE = StaticCoverage(
    names=frozenset(),
    patterns=(),
    covers_all_names=True,
    prefix_count=0,
    covers_all_indexes=False,
)

PARTIAL_NAME_COVERAGE = StaticCoverage(
    names=frozenset({"b", "a"}),
    patterns=("^x",),
    covers_all_names=False,
    prefix_count=0,
    covers_all_indexes=False,
)


def test_unevaluated_properties_with_total_coverage_lowers_to_nothing() -> None:
    stmts = lower(UNEVALUATED_PROPERTIES, False, coverage=TOTAL_NAME_COVERAGE)
    assert stmts == ()


def test_unevaluated_properties_sweeps_the_uncovered_names_and_patterns() -> None:
    stmts = lower(UNEVALUATED_PROPERTIES, False, coverage=PARTIAL_NAME_COVERAGE)
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            not_(
                                or_(
                                    in_consts(Binding(0), ("a", "b")),
                                    regex_test("^x", Binding(0)),
                                )
                            ),
                            (apply((), child(HERE, Binding(0))),),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_unevaluated_properties_without_names_or_patterns_still_sweeps() -> None:
    empty_coverage = StaticCoverage(
        names=frozenset(),
        patterns=(),
        covers_all_names=False,
        prefix_count=0,
        covers_all_indexes=False,
    )
    stmts = lower(UNEVALUATED_PROPERTIES, False, coverage=empty_coverage)
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                ForEachKey(
                    INSTANCE,
                    0,
                    (when(not_(or_()), (apply((), child(HERE, Binding(0))),)),),
                ),
            ),
        ),
    )


def test_unevaluated_properties_without_coverage_is_a_planner_bug() -> None:
    with pytest.raises(RuntimeError):
        lower(UNEVALUATED_PROPERTIES, False, coverage=None)


# --- unevaluatedItems ---------------------------------------------------------


def test_unevaluated_items_with_total_coverage_lowers_to_nothing() -> None:
    total = StaticCoverage(
        names=frozenset(),
        patterns=(),
        covers_all_names=False,
        prefix_count=0,
        covers_all_indexes=True,
    )
    assert lower(UNEVALUATED_ITEMS, False, coverage=total) == ()


def test_unevaluated_items_sweeps_from_the_covered_prefix() -> None:
    cov = StaticCoverage(
        names=frozenset(),
        patterns=(),
        covers_all_names=False,
        prefix_count=2,
        covers_all_indexes=False,
    )
    stmts = lower(UNEVALUATED_ITEMS, False, coverage=cov)
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE,
                    0,
                    (apply((), child(HERE, Binding(0))),),
                    start=2,
                ),
            ),
        ),
    )


def test_unevaluated_items_without_coverage_is_a_planner_bug() -> None:
    with pytest.raises(RuntimeError):
        lower(UNEVALUATED_ITEMS, False, coverage=None)
