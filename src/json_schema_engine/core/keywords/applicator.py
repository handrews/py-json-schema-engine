# The applicator vocabulary (DESIGN.md D2, §3): keywords that apply
# subschemas to the instance, in place or to children. EXEMPLARS promoted to
# production form here: `anyOf` (in-place applicator class — every branch
# runs at the same cursor, §4 rule 7; a rejecting branch's records are
# discarded by rule 3, not by any short-circuit) and `properties` (child
# applicator class — matched members get their own cursor and the matched
# names become dependency data, produced only on success per §4 rule 6).
# `allOf` is the plain in-place case with no dependency data of its own.
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and
# `_ids`. The evaluator drives these through `KeywordContext`; this module
# never imports the evaluator or the registry.

from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    NamesCoverage,
    StaticFacts,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id

PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "properties")
ANY_OF_ID = keyword_id(VOCAB_APPLICATOR, "anyOf")
ALL_OF_ID = keyword_id(VOCAB_APPLICATOR, "allOf")


# --- properties (EXEMPLAR: child applicator) ------------------------------


def _properties_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    names = tuple(value) if is_object(value) else ()
    return StaticFacts(
        subschemas=tuple((name,) for name in names),
        produces=(PROPERTIES_ID,),
        evaluates_names=NamesCoverage(names),
    )


def _properties_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    matched: list[str] = []
    for name in value:
        if name in instance:
            matched.append(name)
            if not ctx.apply(
                ("properties", name), child_cursor(cursor, name, instance[name])
            ):
                ok = False
    # Dependency data comes only from an accepting keyword (§4 rule 6,
    # draft-03 Appendix D): a rejecting `properties` communicates nothing.
    if ok:
        ctx.produce(matched)
    return ok


PROPERTIES = KeywordBehavior(
    id=PROPERTIES_ID, evaluate=_properties_evaluate, analyze=_properties_analyze
)


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
    "properties": PROPERTIES,
    "anyOf": ANY_OF,
    "allOf": ALL_OF,
}
