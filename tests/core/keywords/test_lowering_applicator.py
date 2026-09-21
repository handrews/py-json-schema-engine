# IR-shape tests (M6 Step 2) for the applicator keywords' `lower()` and
# `applications` facts: `oneOf`, `not`, `if`/`then`/`else`, and
# `dependentSchemas`. `allOf`/`anyOf` are covered as exemplars elsewhere;
# these tests exercise only what this module adds.

from json_schema_engine.core.dialect import AnalyzeContext, SubschemaApplication
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords.applicator import (
    DEPENDENT_SCHEMAS,
    ELSE,
    IF,
    NOT,
    ONE_OF,
    THEN,
)
from json_schema_engine.core.lowering import (
    HERE,
    Apply,
    ApplyExpr,
    CombineCheck,
    HasKey,
    If,
    Instance,
    LowerApply,
    TypeIs,
)

from .lowering_helpers import lower

# --- oneOf -------------------------------------------------------------


def test_one_of_applications_are_conditional_and_assert() -> None:
    facts = ONE_OF.facts([True, False, True], {"oneOf": [True, False, True]})
    assert facts.applications == (
        SubschemaApplication((0,), "in_place", conditional=True, asserts=True),
        SubschemaApplication((1,), "in_place", conditional=True, asserts=True),
        SubschemaApplication((2,), "in_place", conditional=True, asserts=True),
    )


def test_one_of_lowers_to_an_exactly_one_run_closed_by_a_combine_check() -> None:
    stmts = lower(ONE_OF, [True, False])
    assert stmts == (
        Apply(LowerApply((0,), HERE, "exactly_one")),
        Apply(LowerApply((1,), HERE, "exactly_one")),
        CombineCheck(("expected exactly 1",)),
    )


# --- not -----------------------------------------------------------------


def test_not_application_is_inverted_and_unconditional() -> None:
    facts = NOT.facts(True, {"not": True})
    assert facts.applications == (
        SubschemaApplication(
            (), "in_place", conditional=False, asserts=True, inverted=True
        ),
    )


def test_not_lowers_to_a_negate_fold_with_its_own_message() -> None:
    stmts = lower(NOT, True)
    assert stmts == (
        Apply(
            LowerApply((), HERE, "negate", message=("must not match the subschema",))
        ),
    )


# --- if / then / else ------------------------------------------------------


def test_if_applications_include_only_present_siblings() -> None:
    condition_only = AnalyzeContext({"if": True})
    assert IF.facts(True, condition_only.schema).applications == (
        SubschemaApplication((), "in_place", conditional=False, asserts=False),
    )

    with_then = AnalyzeContext({"if": True, "then": True})
    assert IF.facts(True, with_then.schema).applications == (
        SubschemaApplication((), "in_place", conditional=False, asserts=False),
        SubschemaApplication(
            (), "in_place", conditional=True, asserts=True, sibling="then"
        ),
    )

    with_both = AnalyzeContext({"if": True, "then": True, "else": True})
    assert IF.facts(True, with_both.schema).applications == (
        SubschemaApplication((), "in_place", conditional=False, asserts=False),
        SubschemaApplication(
            (), "in_place", conditional=True, asserts=True, sibling="then"
        ),
        SubschemaApplication(
            (), "in_place", conditional=True, asserts=True, sibling="else"
        ),
    )


def test_if_lowers_to_a_when_selecting_the_present_siblings() -> None:
    stmts = lower(IF, True, schema={"if": True, "then": True, "else": True})
    assert stmts == (
        If(
            ApplyExpr(LowerApply((), HERE, "discard")),
            (Apply(LowerApply((), HERE, "all_must_pass", sibling="then")),),
            (Apply(LowerApply((), HERE, "all_must_pass", sibling="else")),),
        ),
    )


def test_if_then_only_omits_the_else_branch() -> None:
    stmts = lower(IF, True, schema={"if": True, "then": True})
    assert stmts == (
        If(
            ApplyExpr(LowerApply((), HERE, "discard")),
            (Apply(LowerApply((), HERE, "all_must_pass", sibling="then")),),
            (),
        ),
    )


def test_if_else_only_omits_the_then_branch() -> None:
    stmts = lower(IF, True, schema={"if": True, "else": True})
    assert stmts == (
        If(
            ApplyExpr(LowerApply((), HERE, "discard")),
            (),
            (Apply(LowerApply((), HERE, "all_must_pass", sibling="else")),),
        ),
    )


def test_if_with_neither_sibling_still_applies_the_condition() -> None:
    # No `then`/`else` consumes the outcome, but the interpreter still calls
    # `ctx.apply` unconditionally, so the lowered form must too (depth/cycle
    # bookkeeping parity) even though the verdict is discarded.
    stmts = lower(IF, True, schema={"if": True})
    assert stmts == (Apply(LowerApply((), HERE, "discard")),)


def test_then_and_else_lower_nothing_and_declare_no_edges() -> None:
    assert THEN.lower is not None
    assert ELSE.lower is not None
    assert lower(THEN, True) == ()
    assert lower(ELSE, True) == ()
    assert THEN.facts(True, {"then": True}).applications == ()
    assert ELSE.facts(True, {"else": True}).applications == ()


# --- dependentSchemas ------------------------------------------------------


def test_dependent_schemas_applications_are_conditional_and_assert() -> None:
    value: JsonValue = {"a": True, "b": False}
    facts = DEPENDENT_SCHEMAS.facts(value, {"dependentSchemas": value})
    assert facts.applications == (
        SubschemaApplication(("a",), "in_place", conditional=True, asserts=True),
        SubschemaApplication(("b",), "in_place", conditional=True, asserts=True),
    )


def test_dependent_schemas_lowers_to_a_guarded_has_key_check_per_name() -> None:
    stmts = lower(DEPENDENT_SCHEMAS, {"a": True, "b": False})
    assert stmts == (
        If(
            TypeIs(Instance(), ("object",)),
            (
                If(
                    HasKey(Instance(), "a"),
                    (Apply(LowerApply(("a",), HERE, "all_must_pass")),),
                ),
                If(
                    HasKey(Instance(), "b"),
                    (Apply(LowerApply(("b",), HERE, "all_must_pass")),),
                ),
            ),
        ),
    )


def test_dependent_schemas_lowers_to_nothing_for_a_non_object_value() -> None:
    assert lower(DEPENDENT_SCHEMAS, "not an object") == ()
