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
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id

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
    return StaticFacts(subschemas=tuple((index,) for index in range(count)))


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
    id=ANY_OF_ID, evaluate=_any_of_evaluate, analyze=_any_of_analyze
)


# --- allOf (in-place applicator, no dependency data of its own) -----------


def _all_of_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(subschemas=tuple((index,) for index in range(count)))


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
    id=ALL_OF_ID, evaluate=_all_of_evaluate, analyze=_all_of_analyze
)


# --- oneOf (in-place applicator; exactly one branch must match) -----------


def _one_of_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(subschemas=tuple((index,) for index in range(count)))


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
    id=ONE_OF_ID, evaluate=_one_of_evaluate, analyze=_one_of_analyze
)


# --- not (in-place applicator; the subschema must not match) --------------


def _not_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(subschemas=((),))


def _not_evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    if ctx.apply(("not",), cursor):
        ctx.error("must not match the subschema")
        return False
    return True


NOT = KeywordBehavior(id=NOT_ID, evaluate=_not_evaluate, analyze=_not_analyze)


# --- if / then / else -----------------------------------------------------


def _if_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(subschemas=((),), produces=(IF_ID,))


def _if_evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    # `if` always accepts (§4 rule 6): its subschema's own verdict becomes
    # dependency data for `then`/`else` rather than an assertion of its own,
    # so a rejecting condition's errors become irrelevant.
    outcome = ctx.apply(("if",), cursor)
    ctx.produce(outcome)
    return True


IF = KeywordBehavior(id=IF_ID, evaluate=_if_evaluate, analyze=_if_analyze)


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
)
ELSE = KeywordBehavior(
    id=ELSE_ID,
    evaluate=_make_conditional_branch_evaluate("else", False),
    analyze=_conditional_branch_analyze,
)


# --- dependentSchemas (in-place applicator, keyed by member name) ---------


def _dependent_schemas_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    names = tuple(value) if is_object(value) else ()
    return StaticFacts(subschemas=tuple((name,) for name in names))


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
