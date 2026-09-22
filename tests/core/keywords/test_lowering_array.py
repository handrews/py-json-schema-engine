# M6 Step 2 lowering-IR tests for the array applicator keywords: `prefixItems`,
# `items`, `contains` (`applicator_array.py`), and the 2019-09/draft-07/06
# `items`/`additionalItems`/`dependencies` (`legacy.py`). Each test asserts
# the exact IR `lower()` emits, using the shared `RecordingContext` helper
# (`lowering_helpers.lower`) rather than running the compiler end to end —
# that differential lives in `tests/compiler/test_parity_array.py`.

from json_schema_engine.core.keywords.applicator_array import (
    CONTAINS,
    ITEMS,
    PREFIX_ITEMS,
    contains_behavior,
)
from json_schema_engine.core.keywords.legacy import (
    ADDITIONAL_ITEMS,
    DEPENDENCIES,
    ITEMS_LEGACY,
)
from json_schema_engine.core.lowering import (
    HERE,
    INSTANCE,
    Binding,
    Const,
    CountRange,
    ForEachIndex,
    Stmt,
    apply,
    apply_expr,
    child,
    cmp,
    cond,
    const,
    fail,
    has_key,
    helper,
    not_,
    produce,
    type_is,
    when,
)

from .lowering_helpers import lower

# --- prefixItems -------------------------------------------------------------

_LENGTH = helper("length_of", INSTANCE)


def _prefix_produce(count: int) -> Stmt:
    """`True` when every element was covered, else the largest applied
    index; guarded by a non-empty array (M9 dependency data)."""
    return when(
        cmp(">", _LENGTH, const(0)),
        (
            produce(
                cond(cmp("<=", _LENGTH, const(count)), const(True), const(count - 1))
            ),
        ),
    )


def _produce_true_past(start: int) -> Stmt:
    return when(cmp(">", _LENGTH, const(start)), (produce(const(True)),))


def test_prefix_items_guards_each_entry_by_length() -> None:
    stmts = lower(PREFIX_ITEMS, [{}, {}])
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                when(cmp(">", _LENGTH, const(0)), (apply((0,), child(HERE, 0)),)),
                when(cmp(">", _LENGTH, const(1)), (apply((1,), child(HERE, 1)),)),
                _prefix_produce(2),
            ),
        ),
    )


def test_prefix_items_empty_value_still_guards_the_type_only() -> None:
    assert lower(PREFIX_ITEMS, []) == (when(type_is(INSTANCE, "array"), ()),)


def test_prefix_items_non_list_value_emits_nothing() -> None:
    assert lower(PREFIX_ITEMS, False) == ()


# --- items (2020-12) ---------------------------------------------------------


def _items_sweep(start: int) -> tuple[Stmt, ...]:
    return (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=start
                ),
                _produce_true_past(start),
            ),
        ),
    )


def test_items_starts_after_prefix_items_sibling() -> None:
    assert lower(ITEMS, True, schema={"prefixItems": [{}, {}]}) == _items_sweep(2)


def test_items_starts_at_zero_without_a_prefix_items_sibling() -> None:
    assert lower(ITEMS, True) == _items_sweep(0)


def test_items_ignores_a_non_list_prefix_items_sibling() -> None:
    assert lower(ITEMS, True, schema={"prefixItems": False}) == _items_sweep(0)


# --- contains ------------------------------------------------------------

_MATCHED = helper("length_of", Binding(1))
_CONTAINS_PRODUCE = when(
    cmp(">", _MATCHED, const(0)),
    (produce(cond(cmp("==", _MATCHED, _LENGTH), const(True), Binding(1))),),
)


def _contains_shape(
    minimum: int | float,
    maximum: int | float | None,
    message: tuple[object, ...],
    params: dict[str, object],
) -> tuple[Stmt, ...]:
    # Bindings: 0 the swept index, 1 the matched indexes, 2 the match count
    # (named by the message and params, as `evaluate` reports them).
    return (
        when(
            type_is(INSTANCE, "array"),
            (
                CountRange(
                    INSTANCE,
                    0,
                    apply_expr((), child(HERE, Binding(0)), "discard"),
                    int(minimum),
                    int(maximum) if maximum is not None else None,
                    message=message,  # type: ignore[arg-type]
                    params=params,  # type: ignore[arg-type]
                    matched=1,
                    count=2,
                ),
                _CONTAINS_PRODUCE,
            ),
        ),
    )


def test_contains_default_bounds_minimum_one_unbounded_maximum() -> None:
    assert lower(CONTAINS, {}) == _contains_shape(
        1,
        None,
        (Binding(2), " item(s) match the contains subschema, expected at least 1"),
        {"count": Binding(2), "minContains": Const(1)},
    )


def test_contains_reads_sibling_min_and_max_contains() -> None:
    stmts = lower(CONTAINS, {}, schema={"minContains": 2, "maxContains": 3})
    assert stmts == _contains_shape(
        2,
        3,
        (Binding(2), " item(s) match the contains subschema, expected 2-3"),
        {"count": Binding(2), "minContains": Const(2), "maxContains": Const(3)},
    )


def test_contains_min_contains_zero_still_emits_a_count_range() -> None:
    # `CountRange` with `minimum=0` renders no lower-bound check
    # (`body.py`'s `_count_range`): an empty array is valid.
    assert lower(CONTAINS, {}, schema={"minContains": 0}) == _contains_shape(
        0,
        None,
        (Binding(2), " item(s) match the contains subschema, expected at least 0"),
        {"count": Binding(2), "minContains": Const(0)},
    )


def test_contains_whole_number_float_bounds_are_treated_as_integers() -> None:
    # The range check truncates; the message and params carry the raw
    # values, as `evaluate` does.
    stmts = lower(CONTAINS, {}, schema={"minContains": 2.0, "maxContains": 3.0})
    assert stmts == _contains_shape(
        2.0,
        3.0,
        (Binding(2), " item(s) match the contains subschema, expected 2.0-3.0"),
        {"count": Binding(2), "minContains": Const(2.0), "maxContains": Const(3.0)},
    )


def test_contains_without_sibling_bounds_uses_a_fixed_range_and_message() -> None:
    # draft-07/06: `minContains`/`maxContains` are ordinary unknown keywords,
    # never consulted; the requirement is always "at least one".
    behavior = contains_behavior("urn:test:contains-no-siblings", sibling_bounds=False)
    stmts = lower(behavior, {}, schema={"minContains": 5})
    assert stmts == _contains_shape(
        1,
        None,
        ("no item matches the contains subschema",),
        {"count": Binding(2), "minContains": Const(1)},
    )


# --- legacy items (2019-09: prefixItems + items folded into one keyword) ----


def test_items_legacy_tuple_form_guards_each_entry_by_length() -> None:
    stmts = lower(ITEMS_LEGACY, [{}, {}])
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                when(cmp(">", _LENGTH, const(0)), (apply((0,), child(HERE, 0)),)),
                when(cmp(">", _LENGTH, const(1)), (apply((1,), child(HERE, 1)),)),
                _prefix_produce(2),
            ),
        ),
    )


def test_items_legacy_schema_form_sweeps_every_index_from_zero() -> None:
    assert lower(ITEMS_LEGACY, {"type": "string"}) == _items_sweep(0)


def test_items_legacy_boolean_value_is_a_schema_form() -> None:
    assert lower(ITEMS_LEGACY, False) == _items_sweep(0)


def test_items_legacy_non_schema_non_list_value_emits_nothing() -> None:
    assert lower(ITEMS_LEGACY, 5) == ()


# --- additionalItems (2019-09) ----------------------------------------------


def test_additional_items_lowers_only_with_a_list_items_sibling() -> None:
    assert lower(ADDITIONAL_ITEMS, False, schema={"items": [{}, {}]}) == _items_sweep(2)


def test_additional_items_emits_nothing_without_a_list_items_sibling() -> None:
    assert lower(ADDITIONAL_ITEMS, False) == ()
    assert lower(ADDITIONAL_ITEMS, False, schema={"items": {}}) == ()


# --- dependencies (draft-07/06) ----------------------------------------------


def test_dependencies_array_member_lowers_to_the_dependent_required_shape() -> None:
    stmts = lower(DEPENDENCIES, {"a": ["b", "c"]})
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                when(
                    has_key(INSTANCE, "a"),
                    (
                        when(
                            not_(has_key(INSTANCE, "b")),
                            (
                                fail(
                                    ("'a' requires 'b' to be present",),
                                    {
                                        "property": Const("a"),
                                        "missingProperty": Const("b"),
                                    },
                                ),
                            ),
                        ),
                        when(
                            not_(has_key(INSTANCE, "c")),
                            (
                                fail(
                                    ("'a' requires 'c' to be present",),
                                    {
                                        "property": Const("a"),
                                        "missingProperty": Const("c"),
                                    },
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_dependencies_schema_member_lowers_to_a_guarded_in_place_apply() -> None:
    stmts = lower(DEPENDENCIES, {"a": {"type": "string"}})
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (when(has_key(INSTANCE, "a"), (apply(("a",), HERE),)),),
        ),
    )


def test_dependencies_mixed_array_and_schema_members() -> None:
    stmts = lower(DEPENDENCIES, {"a": ["b"], "c": {}})
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                when(
                    has_key(INSTANCE, "a"),
                    (
                        when(
                            not_(has_key(INSTANCE, "b")),
                            (
                                fail(
                                    ("'a' requires 'b' to be present",),
                                    {
                                        "property": Const("a"),
                                        "missingProperty": Const("b"),
                                    },
                                ),
                            ),
                        ),
                    ),
                ),
                when(has_key(INSTANCE, "c"), (apply(("c",), HERE),)),
            ),
        ),
    )


def test_dependencies_non_object_value_emits_nothing() -> None:
    assert lower(DEPENDENCIES, False) == ()
