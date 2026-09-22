# Lowering IR-shape tests (M6 Step 2, M9) for the object applicators
# (`properties`, `patternProperties`, `additionalProperties`,
# `propertyNames`) and the `unevaluated*` consumers in both postures:
# static coverage and runtime tracking. Producers collect the names they
# apply and `Produce` them (M9); the emitter elides the productions
# outside a tracked region, so the IR is the same in both.

import pytest

from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords.applicator_array import (
    CONTAINS_ID,
    PREFIX_ITEMS_ID,
)
from json_schema_engine.core.keywords.applicator_object import (
    ADDITIONAL_PROPERTIES,
    PATTERN_PROPERTIES,
    PROPERTIES,
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
    Const,
    Expr,
    ForEachIndex,
    ForEachKey,
    StaticCoverage,
    Stmt,
    append,
    apply,
    child,
    cmp,
    collect,
    const,
    coverage_fold,
    covers,
    has_key,
    helper,
    in_consts,
    key,
    not_,
    or_,
    produce,
    regex_test,
    type_is,
    when,
)

from .lowering_helpers import lower

# --- properties ---------------------------------------------------------------


def test_properties_applies_present_members_and_produces_their_names() -> None:
    stmts = lower(PROPERTIES, {"a": True, "b": True})
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                collect(0),
                when(
                    has_key(INSTANCE, "a"),
                    (append(0, Const("a")), apply(("a",), child(HERE, "a"))),
                ),
                when(
                    has_key(INSTANCE, "b"),
                    (append(0, Const("b")), apply(("b",), child(HERE, "b"))),
                ),
                produce(Binding(0)),
            ),
        ),
    )


# --- patternProperties -------------------------------------------------------


def test_pattern_properties_sweeps_the_keys_once_per_pattern() -> None:
    # Pattern-outermost, as `evaluate` sweeps, so error order matches.
    value: JsonValue = {"^a": True, "^b": True}
    stmts = lower(PATTERN_PROPERTIES, value)
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                collect(1),
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            regex_test("^a", Binding(0)),
                            (
                                append(1, Binding(0), unique=True),
                                apply(("^a",), child(HERE, Binding(0))),
                            ),
                        ),
                    ),
                ),
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            regex_test("^b", Binding(0)),
                            (
                                append(1, Binding(0), unique=True),
                                apply(("^b",), child(HERE, Binding(0))),
                            ),
                        ),
                    ),
                ),
                produce(Binding(1)),
            ),
        ),
    )


def test_pattern_properties_of_a_non_object_value_lowers_to_nothing() -> None:
    assert lower(PATTERN_PROPERTIES, "not-an-object") == ()


# --- additionalProperties ----------------------------------------------------


def _additional_sweep(covered: Expr) -> tuple[Stmt, ...]:
    return (
        when(
            type_is(INSTANCE, "object"),
            (
                collect(1),
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            not_(covered),
                            (
                                append(1, Binding(0)),
                                apply((), child(HERE, Binding(0))),
                            ),
                        ),
                    ),
                ),
                produce(Binding(1)),
            ),
        ),
    )


def test_additional_properties_with_no_sibling_covers_nothing() -> None:
    assert lower(ADDITIONAL_PROPERTIES, False, schema={}) == _additional_sweep(or_())


def test_additional_properties_reads_sibling_names() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES, False, schema={"properties": {"a": True, "b": True}}
    )
    assert stmts == _additional_sweep(or_(in_consts(Binding(0), ("a", "b"))))


def test_additional_properties_reads_sibling_patterns() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES, False, schema={"patternProperties": {"^x": True}}
    )
    assert stmts == _additional_sweep(or_(regex_test("^x", Binding(0))))


def test_additional_properties_combines_names_and_patterns() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES,
        False,
        schema={"properties": {"a": True}, "patternProperties": {"^x": True}},
    )
    assert stmts == _additional_sweep(
        or_(in_consts(Binding(0), ("a",)), regex_test("^x", Binding(0)))
    )


def test_additional_properties_ignores_non_object_siblings() -> None:
    stmts = lower(
        ADDITIONAL_PROPERTIES,
        False,
        schema={"properties": ["not", "an", "object"], "patternProperties": True},
    )
    assert stmts == _additional_sweep(or_())


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

NAME_CONSUMES = (
    "https://json-schema.org/draft/2020-12/vocab/applicator#properties",
    "https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties",
    "https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties",
    "https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties",
)


def _uncovered_names_sweep(uncovered: Expr, *head: Stmt) -> tuple[Stmt, ...]:
    return (
        when(
            type_is(INSTANCE, "object"),
            (
                *head,
                collect(1),
                ForEachKey(
                    INSTANCE,
                    0,
                    (
                        when(
                            uncovered,
                            (
                                append(1, Binding(0)),
                                apply((), child(HERE, Binding(0))),
                            ),
                        ),
                    ),
                ),
                produce(Binding(1)),
            ),
        ),
    )


def test_unevaluated_properties_with_total_coverage_lowers_to_nothing() -> None:
    stmts = lower(UNEVALUATED_PROPERTIES, False, coverage=TOTAL_NAME_COVERAGE)
    assert stmts == ()


def test_unevaluated_properties_sweeps_the_uncovered_names_and_patterns() -> None:
    stmts = lower(UNEVALUATED_PROPERTIES, False, coverage=PARTIAL_NAME_COVERAGE)
    assert stmts == _uncovered_names_sweep(
        not_(or_(in_consts(Binding(0), ("a", "b")), regex_test("^x", Binding(0))))
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
    assert stmts == _uncovered_names_sweep(not_(or_()))


def test_unevaluated_properties_tracked_folds_the_channel_then_sweeps() -> None:
    # M9: the planner tracks the consumer; the fold binds after the loop
    # binding and the accumulator, and the sweep tests membership in it.
    stmts = lower(UNEVALUATED_PROPERTIES, False, tracked=True)
    assert stmts == _uncovered_names_sweep(
        not_(covers(2, Binding(0))), coverage_fold(2, "names", NAME_CONSUMES)
    )


def test_unevaluated_properties_without_coverage_is_a_planner_bug() -> None:
    with pytest.raises(RuntimeError):
        lower(UNEVALUATED_PROPERTIES, False, coverage=None)


# --- unevaluatedItems ---------------------------------------------------------

INDEX_CONSUMES = (
    PREFIX_ITEMS_ID,
    "https://json-schema.org/draft/2020-12/vocab/applicator#items",
    CONTAINS_ID,
    "https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedItems",
)

_PRODUCE_IF_APPLIED = when(
    cmp(">", helper("length_of", Binding(1)), const(0)), (produce(const(True)),)
)


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
                collect(1),
                ForEachIndex(
                    INSTANCE,
                    0,
                    (append(1, Binding(0)), apply((), child(HERE, Binding(0)))),
                    start=2,
                ),
                _PRODUCE_IF_APPLIED,
            ),
        ),
    )


def test_unevaluated_items_tracked_folds_the_channel_then_sweeps() -> None:
    stmts = lower(UNEVALUATED_ITEMS, False, tracked=True)
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                coverage_fold(
                    2,
                    "indexes",
                    INDEX_CONSUMES,
                    contains_id=CONTAINS_ID,
                    prefix_id=PREFIX_ITEMS_ID,
                ),
                collect(1),
                ForEachIndex(
                    INSTANCE,
                    0,
                    (
                        when(
                            not_(covers(2, Binding(0))),
                            (
                                append(1, Binding(0)),
                                apply((), child(HERE, Binding(0))),
                            ),
                        ),
                    ),
                ),
                _PRODUCE_IF_APPLIED,
            ),
        ),
    )


def test_unevaluated_items_without_coverage_is_a_planner_bug() -> None:
    with pytest.raises(RuntimeError):
        lower(UNEVALUATED_ITEMS, False, coverage=None)
