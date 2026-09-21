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
    apply,
    apply_expr,
    child,
    cmp,
    const,
    fail,
    has_key,
    helper,
    not_,
    type_is,
    when,
)

from .lowering_helpers import lower

# --- prefixItems -------------------------------------------------------------


def test_prefix_items_guards_each_entry_by_length() -> None:
    stmts = lower(PREFIX_ITEMS, [{}, {}])
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                when(
                    cmp(">", helper("length_of", INSTANCE), const(0)),
                    (apply((0,), child(HERE, 0)),),
                ),
                when(
                    cmp(">", helper("length_of", INSTANCE), const(1)),
                    (apply((1,), child(HERE, 1)),),
                ),
            ),
        ),
    )


def test_prefix_items_empty_value_still_guards_the_type_only() -> None:
    assert lower(PREFIX_ITEMS, []) == (when(type_is(INSTANCE, "array"), ()),)


def test_prefix_items_non_list_value_emits_nothing() -> None:
    assert lower(PREFIX_ITEMS, False) == ()


# --- items (2020-12) ---------------------------------------------------------


def test_items_starts_after_prefix_items_sibling() -> None:
    stmts = lower(ITEMS, True, schema={"prefixItems": [{}, {}]})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=2
                ),
            ),
        ),
    )


def test_items_starts_at_zero_without_a_prefix_items_sibling() -> None:
    stmts = lower(ITEMS, True)
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=0
                ),
            ),
        ),
    )


def test_items_ignores_a_non_list_prefix_items_sibling() -> None:
    stmts = lower(ITEMS, True, schema={"prefixItems": False})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=0
                ),
            ),
        ),
    )


# --- contains ------------------------------------------------------------


def test_contains_default_bounds_minimum_one_unbounded_maximum() -> None:
    stmts = lower(CONTAINS, {})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                CountRange(
                    INSTANCE,
                    0,
                    apply_expr((), child(HERE, Binding(0)), "discard"),
                    1,
                    None,
                    message=(
                        "expected at least 1 item(s) matching the contains subschema",
                    ),
                    params={"minContains": Const(1)},
                ),
            ),
        ),
    )


def test_contains_reads_sibling_min_and_max_contains() -> None:
    stmts = lower(CONTAINS, {}, schema={"minContains": 2, "maxContains": 3})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                CountRange(
                    INSTANCE,
                    0,
                    apply_expr((), child(HERE, Binding(0)), "discard"),
                    2,
                    3,
                    message=("expected 2-3 item(s) matching the contains subschema",),
                    params={"minContains": Const(2), "maxContains": Const(3)},
                ),
            ),
        ),
    )


def test_contains_min_contains_zero_still_emits_a_count_range() -> None:
    # `CountRange` with `minimum=0` renders no lower-bound check
    # (`body.py`'s `_count_range`): an empty array is valid.
    stmts = lower(CONTAINS, {}, schema={"minContains": 0})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                CountRange(
                    INSTANCE,
                    0,
                    apply_expr((), child(HERE, Binding(0)), "discard"),
                    0,
                    None,
                    message=(
                        "expected at least 0 item(s) matching the contains subschema",
                    ),
                    params={"minContains": Const(0)},
                ),
            ),
        ),
    )


def test_contains_whole_number_float_bounds_are_treated_as_integers() -> None:
    stmts = lower(CONTAINS, {}, schema={"minContains": 2.0, "maxContains": 3.0})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                CountRange(
                    INSTANCE,
                    0,
                    apply_expr((), child(HERE, Binding(0)), "discard"),
                    2,
                    3,
                    message=("expected 2-3 item(s) matching the contains subschema",),
                    params={"minContains": Const(2), "maxContains": Const(3)},
                ),
            ),
        ),
    )


def test_contains_without_sibling_bounds_uses_a_fixed_range_and_message() -> None:
    # draft-07/06: `minContains`/`maxContains` are ordinary unknown keywords,
    # never consulted; the requirement is always "at least one".
    behavior = contains_behavior("urn:test:contains-no-siblings", sibling_bounds=False)
    stmts = lower(behavior, {}, schema={"minContains": 5})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                CountRange(
                    INSTANCE,
                    0,
                    apply_expr((), child(HERE, Binding(0)), "discard"),
                    1,
                    None,
                    message=("no item matches the contains subschema",),
                    params={"minContains": Const(1)},
                ),
            ),
        ),
    )


# --- legacy items (2019-09: prefixItems + items folded into one keyword) ----


def test_items_legacy_tuple_form_guards_each_entry_by_length() -> None:
    stmts = lower(ITEMS_LEGACY, [{}, {}])
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                when(
                    cmp(">", helper("length_of", INSTANCE), const(0)),
                    (apply((0,), child(HERE, 0)),),
                ),
                when(
                    cmp(">", helper("length_of", INSTANCE), const(1)),
                    (apply((1,), child(HERE, 1)),),
                ),
            ),
        ),
    )


def test_items_legacy_schema_form_sweeps_every_index_from_zero() -> None:
    stmts = lower(ITEMS_LEGACY, {"type": "string"})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=0
                ),
            ),
        ),
    )


def test_items_legacy_boolean_value_is_a_schema_form() -> None:
    stmts = lower(ITEMS_LEGACY, False)
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=0
                ),
            ),
        ),
    )


def test_items_legacy_non_schema_non_list_value_emits_nothing() -> None:
    assert lower(ITEMS_LEGACY, 5) == ()


# --- additionalItems (2019-09) ----------------------------------------------


def test_additional_items_lowers_only_with_a_list_items_sibling() -> None:
    stmts = lower(ADDITIONAL_ITEMS, False, schema={"items": [{}, {}]})
    assert stmts == (
        when(
            type_is(INSTANCE, "array"),
            (
                ForEachIndex(
                    INSTANCE, 0, (apply((), child(HERE, Binding(0))),), start=2
                ),
            ),
        ),
    )


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
