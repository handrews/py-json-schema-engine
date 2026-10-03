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
from json_schema_engine.core.keywords._rejects import is_false, names_rejected
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    Const,
    Expr,
    LoweringContext,
    LowerMessage,
    LowerParams,
    Stmt,
    apply,
    apply_expr,
    collect,
    combine_check,
    fail,
    has_key,
    helper,
    lower_nothing,
    reject,
    reject_check,
    type_is,
    when,
)
from json_schema_engine.core.messages import index_ranges, realize

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


def _any_of_message(count: int) -> str:
    # Which branches failed would say nothing new: all of them did, and
    # each reported why.
    if count == 1:
        return "does not match the anyOf branch"
    return f"does not match any of the {count} anyOf branches"


def _any_of_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    # Every branch is an `any_may_pass` apply; the combine check closes the
    # run with the keyword's own message. The emitter may short-circuit only
    # where the plan proves the region verdict-only (§4 rule 7).
    lctx.emit(
        *(apply((index,), HERE, "any_may_pass") for index in range(len(value))),
        combine_check((_any_of_message(len(value)),)),
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
        ctx.error(_any_of_message(len(value)))
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


def _all_of_rejected(failed: list[int]) -> tuple[LowerMessage, LowerParams]:
    if len(failed) == 1:
        text = f"allOf branch {failed[0]} is false"
    else:
        text = f"allOf branches {index_ranges(failed)} are false"
    return (text,), {"failed": Const(list(failed))}


def _false_branches(value: list[JsonValue]) -> list[int]:
    return [index for index, schema in enumerate(value) if is_false(schema)]


def _all_of_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    failed = _false_branches(value)
    lctx.emit(
        *(
            apply((index,), HERE)
            for index, schema in enumerate(value)
            if not is_false(schema)
        ),
        *((fail(*_all_of_rejected(failed)),) if failed else ()),
    )


def _all_of_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, list)
    ok = True
    for index, schema in enumerate(value):
        if not is_false(schema) and not ctx.apply(("allOf", index), cursor):
            ok = False
    # No message of its own for a failing branch: it already reported why,
    # and that error stays relevant because `allOf` rejects too (§4 rule
    # 6). A `false` branch explains nothing, so `allOf` names it instead.
    failed = _false_branches(value)
    if failed:
        ctx.error(*realize(*_all_of_rejected(failed), cursor.value))
        ok = False
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


def _one_of_describe(count: int, passing: Expr) -> tuple[LowerMessage, LowerParams]:
    return (
        (
            "matched ",
            helper("counted_indexes", passing, Const("branch"), Const("branches")),
            f", expected exactly 1 of {count}",
        ),
        {"passing": passing},
    )


def _one_of_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    if not value:
        # No branch can match, and the combine run has no apply to bind
        # its passing list from: the failure is a constant.
        lctx.emit(fail(*_one_of_describe(0, Const([]))))
        return
    # Every branch is an `exactly_one` apply; the combine check closes the
    # run and names, through its bindings, the passing indexes `evaluate`
    # reports (D1: one message).
    count = lctx.binding()
    passing = lctx.binding()
    lctx.emit(
        *(apply((index,), HERE, "exactly_one") for index in range(len(value))),
        combine_check(
            *_one_of_describe(len(value), Binding(passing)),
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
        ctx.error(*realize(*_one_of_describe(len(value), Const(passing)), cursor.value))
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


def dependents_rejected(keyword: str, names: Expr) -> tuple[LowerMessage, LowerParams]:
    """`property "a" present, which dependentSchemas forbids`: shared with
    draft-07's `dependencies`."""
    return names_rejected("", f" present, which {keyword} forbids", names)


def _dependent_schemas_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not is_object(value):
        return
    instance = lctx.instance
    r = lctx.binding()
    forbidden = any(is_false(schema) for schema in value.values())

    def step(name: str) -> Stmt:
        if is_false(value[name]):
            return reject(r, Const(name))
        return apply((name,), HERE)

    lctx.emit(
        when(
            type_is(instance, "object"),
            (
                *((collect(r, errors=True),) if forbidden else ()),
                *(when(has_key(instance, name), (step(name),)) for name in value),
                *(
                    (
                        reject_check(
                            r, *dependents_rejected("dependentSchemas", Binding(r))
                        ),
                    )
                    if forbidden
                    else ()
                ),
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
    rejected: list[JsonValue] = []
    for name in value:
        if name not in instance:
            continue
        if is_false(value[name]):
            rejected.append(name)
        elif not ctx.apply(("dependentSchemas", name), cursor):
            ok = False
    # No message of its own for a failing named subschema: it already
    # reported why. A `false` one explains nothing, so it is named here.
    if rejected:
        described = dependents_rejected("dependentSchemas", Const(rejected))
        ctx.error(*realize(*described, instance))
        ok = False
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
