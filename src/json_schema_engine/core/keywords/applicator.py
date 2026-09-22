# In-place applicators (DESIGN.md D2, §3): keywords that apply subschemas
# to the instance at the same cursor. EXEMPLAR promoted to production form
# here: `anyOf` (every branch runs at the same cursor, §4 rule 7; a rejecting
# branch's records are discarded by rule 3, not by any short-circuit).
# `allOf` is the plain case with no dependency data of its own. M2 adds
# `oneOf`, `not`, `if`/`then`/`else`, and `dependentSchemas`. Child
# applicators live in `applicator_object.py` and `applicator_array.py`.
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and
# `_ids`. The evaluator drives these through `KeywordContext`; this module
# never imports the evaluator or the registry.

from collections.abc import Callable

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
    SubschemaApplication,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    LoweringContext,
    apply,
    apply_expr,
    combine_check,
    has_key,
    lower_nothing,
    type_is,
    when,
)

ANY_OF_ID = keyword_id(VOCAB_APPLICATOR, "anyOf")
ALL_OF_ID = keyword_id(VOCAB_APPLICATOR, "allOf")
ONE_OF_ID = keyword_id(VOCAB_APPLICATOR, "oneOf")
NOT_ID = keyword_id(VOCAB_APPLICATOR, "not")
IF_ID = keyword_id(VOCAB_APPLICATOR, "if")
THEN_ID = keyword_id(VOCAB_APPLICATOR, "then")
ELSE_ID = keyword_id(VOCAB_APPLICATOR, "else")
DEPENDENT_SCHEMAS_ID = keyword_id(VOCAB_APPLICATOR, "dependentSchemas")


# --- anyOf (EXEMPLAR: in-place applicator) --------------------------------


def _any_of_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(
        subschemas=tuple((index,) for index in range(count)),
        applications=tuple(
            SubschemaApplication((index,), "in_place", conditional=True, asserts=True)
            for index in range(count)
        ),
    )


def _any_of_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    # Every branch is an `any_may_pass` apply; the combine check closes the
    # run with the keyword's own message. The emitter may short-circuit only
    # where the plan proves the region verdict-only (§4 rule 7).
    lctx.emit(
        *(apply((index,), HERE, "any_may_pass") for index in range(len(value))),
        combine_check(("does not match any anyOf branch",)),
    )


def _any_of_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, list)
    # §4 rule 7: the interpreter never short-circuits, so every branch runs
    # even after one has already matched.
    ok = False
    for index in range(len(value)):
        if ctx.apply(("anyOf", index), cursor):
            ok = True
    if not ok:
        ctx.error("does not match any anyOf branch")
    return ok


ANY_OF = KeywordBehavior(
    id=ANY_OF_ID,
    evaluate=_any_of_evaluate,
    analyze=_any_of_analyze,
    lower=_any_of_lower,
)


# --- allOf (in-place applicator, no dependency data of its own) -----------


def _all_of_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(
        subschemas=tuple((index,) for index in range(count)),
        applications=tuple(
            SubschemaApplication((index,), "in_place", conditional=False, asserts=True)
            for index in range(count)
        ),
    )


def _all_of_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    lctx.emit(*(apply((index,), HERE) for index in range(len(value))))


def _all_of_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, list)
    ok = True
    for index in range(len(value)):
        if not ctx.apply(("allOf", index), cursor):
            ok = False
    # No message of its own: a failing branch already reported why, and that
    # error stays relevant because `allOf` rejects too (§4 rule 6).
    return ok


ALL_OF = KeywordBehavior(
    id=ALL_OF_ID,
    evaluate=_all_of_evaluate,
    analyze=_all_of_analyze,
    lower=_all_of_lower,
)


# --- oneOf (in-place applicator; exactly one branch must match) -----------


def _one_of_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(
        subschemas=tuple((index,) for index in range(count)),
        applications=tuple(
            SubschemaApplication((index,), "in_place", conditional=True, asserts=True)
            for index in range(count)
        ),
    )


def _one_of_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    # Every branch is an `exactly_one` apply; the combine check closes the
    # run and names, through its bindings, the passing count and indexes
    # `evaluate` reports (D1: one message).
    count = lctx.binding()
    passing = lctx.binding()
    lctx.emit(
        *(apply((index,), HERE, "exactly_one") for index in range(len(value))),
        combine_check(
            ("matched ", Binding(count), " branches, expected exactly 1"),
            {"passing": Binding(passing)},
            count=count,
            passing=passing,
        ),
    )


def _one_of_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, list)
    # §4 rule 7: every branch runs regardless of how many have already
    # matched, so the reported count is exact.
    passing: list[JsonValue] = []
    for index in range(len(value)):
        if ctx.apply(("oneOf", index), cursor):
            passing.append(index)
    if len(passing) != 1:
        ctx.error(
            f"matched {len(passing)} branches, expected exactly 1",
            {"passing": passing},
        )
    return len(passing) == 1


ONE_OF = KeywordBehavior(
    id=ONE_OF_ID,
    evaluate=_one_of_evaluate,
    analyze=_one_of_analyze,
    lower=_one_of_lower,
)


# --- not (in-place applicator; the subschema must not match) --------------


def _not_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        applications=(
            SubschemaApplication(
                (), "in_place", conditional=False, asserts=True, inverted=True
            ),
        ),
    )


def _not_lower(_value: JsonValue, lctx: LoweringContext) -> None:
    lctx.emit(apply((), HERE, "negate", message=("must not match the subschema",)))


def _not_evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    if ctx.apply(("not",), cursor):
        ctx.error("must not match the subschema")
        return False
    return True


NOT = KeywordBehavior(
    id=NOT_ID, evaluate=_not_evaluate, analyze=_not_analyze, lower=_not_lower
)


# --- if / then / else -----------------------------------------------------


def _if_analyze(_value: JsonValue, ctx: AnalyzeContext) -> StaticFacts:
    applications = [
        SubschemaApplication((), "in_place", conditional=False, asserts=False)
    ]
    for branch in ("then", "else"):
        if branch in ctx.schema:
            applications.append(
                SubschemaApplication(
                    (), "in_place", conditional=True, asserts=True, sibling=branch
                )
            )
    return StaticFacts(
        subschemas=((),), produces=(IF_ID,), applications=tuple(applications)
    )


def _if_lower(_value: JsonValue, lctx: LoweringContext) -> None:
    has_then = "then" in lctx.schema
    has_else = "else" in lctx.schema
    if not has_then and not has_else:
        # No sibling consumes the outcome, but the interpreter still applies
        # the condition unconditionally (depth/cycle bookkeeping must match)
        # even though its verdict and any errors are irrelevant here.
        lctx.emit(apply((), HERE, "discard"))
        return
    lctx.emit(
        when(
            apply_expr((), HERE, "discard"),
            (apply((), HERE, sibling="then"),) if has_then else (),
            (apply((), HERE, sibling="else"),) if has_else else (),
        )
    )


def _if_evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    # `if` always accepts (§4 rule 6): its subschema's own verdict becomes
    # dependency data for `then`/`else` rather than an assertion of its own,
    # so a rejecting condition's errors become irrelevant.
    outcome = ctx.apply(("if",), cursor)
    ctx.produce(outcome)
    return True


IF = KeywordBehavior(
    id=IF_ID, evaluate=_if_evaluate, analyze=_if_analyze, lower=_if_lower
)


def _conditional_branch_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(subschemas=((),), consumes=(IF_ID,))


def _make_conditional_branch_evaluate(
    name: str, when: bool
) -> Callable[[JsonValue, Cursor, KeywordContext], bool]:
    def evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        # `if`'s outcome is a same-scope dependency (draft-03 §12.3): visible
        # only adjacently, never through an in-place child's channel merge.
        views = ctx.visible((IF_ID,), "adjacent")
        if not views or views[0].data is not when:
            return True
        return ctx.apply((name,), cursor)

    return evaluate


THEN = KeywordBehavior(
    id=THEN_ID,
    evaluate=_make_conditional_branch_evaluate("then", True),
    analyze=_conditional_branch_analyze,
    lower=lower_nothing,
)
ELSE = KeywordBehavior(
    id=ELSE_ID,
    evaluate=_make_conditional_branch_evaluate("else", False),
    analyze=_conditional_branch_analyze,
    lower=lower_nothing,
)


# --- dependentSchemas (in-place applicator, keyed by member name) ---------


def _dependent_schemas_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    names = tuple(value) if is_object(value) else ()
    return StaticFacts(
        subschemas=tuple((name,) for name in names),
        applications=tuple(
            SubschemaApplication((name,), "in_place", conditional=True, asserts=True)
            for name in names
        ),
    )


def _dependent_schemas_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not is_object(value):
        return
    instance = lctx.instance
    lctx.emit(
        when(
            type_is(instance, "object"),
            tuple(
                when(has_key(instance, name), (apply((name,), HERE),)) for name in value
            ),
        )
    )


def _dependent_schemas_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    for name in value:
        if name in instance and not ctx.apply(("dependentSchemas", name), cursor):
            ok = False
    # No message of its own: a failing named subschema already reported why.
    return ok


DEPENDENT_SCHEMAS = KeywordBehavior(
    id=DEPENDENT_SCHEMAS_ID,
    evaluate=_dependent_schemas_evaluate,
    analyze=_dependent_schemas_analyze,
    lower=_dependent_schemas_lower,
)


APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {
    "anyOf": ANY_OF,
    "allOf": ALL_OF,
    "oneOf": ONE_OF,
    "not": NOT,
    "if": IF,
    "then": THEN,
    "else": ELSE,
    "dependentSchemas": DEPENDENT_SCHEMAS,
}
