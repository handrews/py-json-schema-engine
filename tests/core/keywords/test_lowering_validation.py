# IR-shape tests (M6 Step 2) for the validation vocabulary's `lower()`:
# `enum`, `const`, `multipleOf`, the numeric/string/array/object "guard,
# then compare" bounds, `uniqueItems`, `dependentRequired`, and the inert
# `minContains`/`maxContains` siblings. `type`, `required`, and `pattern`
# are covered by the module's own docstring as the M1/M2 exemplars and are
# not repeated here.
#
# Every keyword with a keyword-value-only message gets one test asserting
# the lowered `Fail`'s message text is byte-identical to the message
# `evaluate` reports for the same failing case (via `run_evaluation`), so
# the two can never quietly drift apart.

from typing import NoReturn

from json_schema_engine.core.dialect import DialectRegistry
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import VOCAB_VALIDATION
from json_schema_engine.core.keywords.validation import VALIDATION_VOCABULARY
from json_schema_engine.core.lowering import (
    INSTANCE,
    Const,
    Fail,
    If,
    Item,
    Stmt,
    and_,
    cmp,
    fail,
    has_key,
    helper,
    in_consts,
    not_,
    type_is,
    when,
)
from json_schema_engine.core.registry import SchemaRegistry

from .lowering_helpers import lower

# --- shared evaluation harness (mirrors test_validation.py's `run()`) -------


def make_registry() -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_VALIDATION, VALIDATION_VOCABULARY)
    dialects.register_dialect("urn:test:lowering-validation", [VOCAB_VALIDATION])
    return SchemaRegistry(dialects, "urn:test:lowering-validation")


def _no_regex(_expr: str) -> NoReturn:  # pragma: no cover - no `pattern` case here
    raise AssertionError("this suite never compiles a pattern")


def run(schema: JsonValue, instance: JsonValue) -> tuple[bool, EvalState]:
    reg = make_registry()
    uri = reg.register(schema, "https://lowering-validation.example/schema")
    return run_evaluation(reg, uri, instance, compile_regex=_no_regex)


def _single_fail(stmts: tuple[Stmt, ...]) -> Fail:
    """Unwrap a chain of single-branch `If` guards down to the lone `Fail`."""
    assert len(stmts) == 1
    stmt = stmts[0]
    while isinstance(stmt, If):
        assert len(stmt.then) == 1
        stmt = stmt.then[0]
    assert isinstance(stmt, Fail)
    return stmt


def assert_message_matches_evaluate(
    keyword: str, value: JsonValue, instance: JsonValue
) -> None:
    """The lowered `Fail`'s message equals `evaluate`'s message for the same
    (keyword value, failing instance) pair."""
    behavior = VALIDATION_VOCABULARY[keyword]
    node = _single_fail(lower(behavior, value))
    valid, state = run({keyword: value}, instance)
    assert not valid
    assert node.message == (state.errors[0].message,)


# --- enum --------------------------------------------------------------


def test_enum_lowers_to_an_in_consts_membership_test() -> None:
    behavior = VALIDATION_VOCABULARY["enum"]
    stmts = lower(behavior, [1, "a", None])
    assert stmts == (
        when(
            not_(in_consts(INSTANCE, (1, "a", None))),
            (
                fail(
                    ("not one of the allowed values",),
                    {"allowedValues": Const([1, "a", None])},
                ),
            ),
        ),
    )


def test_enum_non_list_value_always_fails_unconditionally() -> None:
    behavior = VALIDATION_VOCABULARY["enum"]
    stmts = lower(behavior, "not-a-list")
    assert stmts == (
        fail(
            ("not one of the allowed values",),
            {"allowedValues": Const("not-a-list")},
        ),
    )


def test_enum_empty_list_also_always_fails_unconditionally() -> None:
    behavior = VALIDATION_VOCABULARY["enum"]
    stmts = lower(behavior, [])
    assert stmts == (
        fail(("not one of the allowed values",), {"allowedValues": Const([])}),
    )


def test_enum_message_matches_evaluate() -> None:
    assert_message_matches_evaluate("enum", [1, 2, 3], 5)


# --- const ---------------------------------------------------------------


def test_const_lowers_to_a_json_equal_test() -> None:
    behavior = VALIDATION_VOCABULARY["const"]
    stmts = lower(behavior, {"a": 1})
    assert stmts == (
        when(
            not_(helper("json_equal", INSTANCE, Const({"a": 1}))),
            (
                fail(
                    ("does not equal the required constant",),
                    {"allowedValue": Const({"a": 1})},
                ),
            ),
        ),
    )


def test_const_message_matches_evaluate() -> None:
    assert_message_matches_evaluate("const", {"a": 1}, {"a": 2})


# --- multipleOf ------------------------------------------------------------


def test_multiple_of_lowers_to_a_numeric_guard_and_helper_call() -> None:
    behavior = VALIDATION_VOCABULARY["multipleOf"]
    stmts = lower(behavior, 2)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "number"),
                not_(helper("is_multiple_of", INSTANCE, Const(2))),
            ),
            (fail(("must be a multiple of 2",), {"multipleOf": Const(2)}),),
        ),
    )


def test_multiple_of_non_numeric_value_emits_nothing() -> None:
    behavior = VALIDATION_VOCABULARY["multipleOf"]
    assert lower(behavior, "2") == ()


def test_multiple_of_message_matches_evaluate() -> None:
    assert_message_matches_evaluate("multipleOf", 2, 3)


# --- numeric bounds ----------------------------------------------------


def test_maximum_lowers_to_a_numeric_guard_and_cmp() -> None:
    behavior = VALIDATION_VOCABULARY["maximum"]
    stmts = lower(behavior, 10)
    assert stmts == (
        when(
            and_(type_is(INSTANCE, "number"), not_(cmp("<=", INSTANCE, Const(10)))),
            (fail(("must be <= 10",), {"limit": Const(10)}),),
        ),
    )


def test_exclusive_maximum_uses_strict_less_than() -> None:
    behavior = VALIDATION_VOCABULARY["exclusiveMaximum"]
    stmts = lower(behavior, 10)
    assert stmts == (
        when(
            and_(type_is(INSTANCE, "number"), not_(cmp("<", INSTANCE, Const(10)))),
            (fail(("must be < 10",), {"limit": Const(10)}),),
        ),
    )


def test_minimum_uses_greater_or_equal() -> None:
    behavior = VALIDATION_VOCABULARY["minimum"]
    stmts = lower(behavior, 1)
    assert stmts == (
        when(
            and_(type_is(INSTANCE, "number"), not_(cmp(">=", INSTANCE, Const(1)))),
            (fail(("must be >= 1",), {"limit": Const(1)}),),
        ),
    )


def test_exclusive_minimum_uses_strict_greater_than() -> None:
    behavior = VALIDATION_VOCABULARY["exclusiveMinimum"]
    stmts = lower(behavior, 1)
    assert stmts == (
        when(
            and_(type_is(INSTANCE, "number"), not_(cmp(">", INSTANCE, Const(1)))),
            (fail(("must be > 1",), {"limit": Const(1)}),),
        ),
    )


def test_numeric_bound_non_numeric_value_emits_nothing() -> None:
    for name in ("maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum"):
        assert lower(VALIDATION_VOCABULARY[name], "10") == ()


def test_numeric_bound_messages_match_evaluate() -> None:
    assert_message_matches_evaluate("maximum", 10, 11)
    assert_message_matches_evaluate("exclusiveMaximum", 10, 10)
    assert_message_matches_evaluate("minimum", 1, 0)
    assert_message_matches_evaluate("exclusiveMinimum", 1, 1)


# --- string length -----------------------------------------------------


def test_max_length_lowers_to_a_string_guard_and_code_point_length_cmp() -> None:
    behavior = VALIDATION_VOCABULARY["maxLength"]
    stmts = lower(behavior, 3)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "string"),
                not_(cmp("<=", helper("code_point_length", INSTANCE), Const(3))),
            ),
            (fail(("must be at most 3 characters",), {"limit": Const(3)}),),
        ),
    )


def test_min_length_uses_greater_or_equal() -> None:
    behavior = VALIDATION_VOCABULARY["minLength"]
    stmts = lower(behavior, 2)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "string"),
                not_(cmp(">=", helper("code_point_length", INSTANCE), Const(2))),
            ),
            (fail(("must be at least 2 characters",), {"limit": Const(2)}),),
        ),
    )


def test_max_length_non_integer_float_value_is_truncated_like_evaluate() -> None:
    # `evaluate` casts the keyword value with `int(value)`, so `2.0` behaves
    # exactly like `2` — but the reported `limit` param still carries the
    # raw `2.0` (mirroring `_limit_params`, which never truncates).
    behavior = VALIDATION_VOCABULARY["maxLength"]
    stmts = lower(behavior, 2.0)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "string"),
                not_(cmp("<=", helper("code_point_length", INSTANCE), Const(2))),
            ),
            (fail(("must be at most 2.0 characters",), {"limit": Const(2.0)}),),
        ),
    )


def test_string_bound_non_numeric_value_emits_nothing() -> None:
    assert lower(VALIDATION_VOCABULARY["maxLength"], "3") == ()
    assert lower(VALIDATION_VOCABULARY["minLength"], "3") == ()


def test_string_bound_messages_match_evaluate() -> None:
    assert_message_matches_evaluate("maxLength", 2, "abc")
    assert_message_matches_evaluate("minLength", 2, "a")
    assert_message_matches_evaluate("maxLength", 2.0, "abc")


# --- array size --------------------------------------------------------


def test_max_items_lowers_to_an_array_guard_and_length_of_cmp() -> None:
    behavior = VALIDATION_VOCABULARY["maxItems"]
    stmts = lower(behavior, 2)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "array"),
                not_(cmp("<=", helper("length_of", INSTANCE), Const(2))),
            ),
            (fail(("must have at most 2 items",), {"limit": Const(2)}),),
        ),
    )


def test_min_items_uses_greater_or_equal() -> None:
    behavior = VALIDATION_VOCABULARY["minItems"]
    stmts = lower(behavior, 1)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "array"),
                not_(cmp(">=", helper("length_of", INSTANCE), Const(1))),
            ),
            (fail(("must have at least 1 items",), {"limit": Const(1)}),),
        ),
    )


def test_array_bound_non_numeric_value_emits_nothing() -> None:
    assert lower(VALIDATION_VOCABULARY["maxItems"], "2") == ()


def test_array_bound_messages_match_evaluate() -> None:
    assert_message_matches_evaluate("maxItems", 1, [1, 2])
    assert_message_matches_evaluate("minItems", 2, [1])


# --- object size -------------------------------------------------------


def test_max_properties_lowers_to_an_object_guard_and_length_of_cmp() -> None:
    behavior = VALIDATION_VOCABULARY["maxProperties"]
    stmts = lower(behavior, 2)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "object"),
                not_(cmp("<=", helper("length_of", INSTANCE), Const(2))),
            ),
            (fail(("must have at most 2 properties",), {"limit": Const(2)}),),
        ),
    )


def test_min_properties_uses_greater_or_equal() -> None:
    behavior = VALIDATION_VOCABULARY["minProperties"]
    stmts = lower(behavior, 1)
    assert stmts == (
        when(
            and_(
                type_is(INSTANCE, "object"),
                not_(cmp(">=", helper("length_of", INSTANCE), Const(1))),
            ),
            (fail(("must have at least 1 properties",), {"limit": Const(1)}),),
        ),
    )


def test_object_bound_non_numeric_value_emits_nothing() -> None:
    assert lower(VALIDATION_VOCABULARY["maxProperties"], "2") == ()


def test_object_bound_messages_match_evaluate() -> None:
    assert_message_matches_evaluate("maxProperties", 1, {"a": 1, "b": 2})
    assert_message_matches_evaluate("minProperties", 2, {"a": 1})


# --- uniqueItems -------------------------------------------------------


def test_unique_items_true_lowers_to_an_array_guard_and_duplicate_check() -> None:
    behavior = VALIDATION_VOCABULARY["uniqueItems"]
    stmts = lower(behavior, True)
    # The message and params name the colliding pair through the helper
    # `evaluate` uses (M9), computed only on the failure path.
    pair = helper("first_duplicate_pair", INSTANCE)
    assert stmts == (
        when(
            and_(type_is(INSTANCE, "array"), helper("has_duplicate_items", INSTANCE)),
            (
                fail(
                    (
                        "items at ",
                        Item(pair, Const(0)),
                        " and ",
                        Item(pair, Const(1)),
                        " are not unique",
                    ),
                    {"duplicates": pair},
                ),
            ),
        ),
    )


def test_unique_items_false_emits_nothing() -> None:
    assert lower(VALIDATION_VOCABULARY["uniqueItems"], False) == ()


def test_unique_items_non_boolean_value_emits_nothing() -> None:
    # `value is True` (identity), not truthiness: `1` must not turn this on.
    assert lower(VALIDATION_VOCABULARY["uniqueItems"], 1) == ()


# --- dependentRequired -------------------------------------------------


def test_dependent_required_lowers_to_nested_object_and_key_guards() -> None:
    behavior = VALIDATION_VOCABULARY["dependentRequired"]
    stmts = lower(behavior, {"a": ["b", "c"]})
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


def test_dependent_required_non_object_value_emits_nothing() -> None:
    assert lower(VALIDATION_VOCABULARY["dependentRequired"], ["a"]) == ()


def test_dependent_required_skips_malformed_dependency_lists() -> None:
    # `evaluate` skips a name whose dependency list isn't a list, and skips
    # any individual dependency name that isn't a string; a name left with
    # no valid dependencies contributes no `when` at all.
    behavior = VALIDATION_VOCABULARY["dependentRequired"]
    stmts = lower(behavior, {"a": "not-a-list", "b": [1, "c"]})
    assert stmts == (
        when(
            type_is(INSTANCE, "object"),
            (
                when(
                    has_key(INSTANCE, "b"),
                    (
                        when(
                            not_(has_key(INSTANCE, "c")),
                            (
                                fail(
                                    ("'b' requires 'c' to be present",),
                                    {
                                        "property": Const("b"),
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


def test_dependent_required_all_malformed_emits_nothing() -> None:
    behavior = VALIDATION_VOCABULARY["dependentRequired"]
    assert lower(behavior, {"a": "not-a-list"}) == ()


def test_dependent_required_message_matches_evaluate() -> None:
    assert_message_matches_evaluate("dependentRequired", {"a": ["b"]}, {"a": 1})


# --- minContains / maxContains (inert siblings) -----------------------


def test_min_max_contains_lower_to_nothing() -> None:
    assert lower(VALIDATION_VOCABULARY["minContains"], 2) == ()
    assert lower(VALIDATION_VOCABULARY["maxContains"], 2) == ()
