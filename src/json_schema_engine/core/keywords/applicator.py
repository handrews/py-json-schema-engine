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

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
)
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id

ANY_OF_ID = keyword_id(VOCAB_APPLICATOR, "anyOf")
ALL_OF_ID = keyword_id(VOCAB_APPLICATOR, "allOf")


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


APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {
    "anyOf": ANY_OF,
    "allOf": ALL_OF,
}
