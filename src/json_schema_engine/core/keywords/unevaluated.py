# The unevaluated vocabulary (DESIGN.md D2, §3, §4 rule 4): the channel
# consumer keyword class. EXEMPLAR: `unevaluatedProperties` runs in
# `Phase.UNEVALUATED`, after every phase-0 keyword of its schema object has
# merged, reads the dependency data those keywords produced through
# `ctx.visible()`, and applies its own subschema to whatever member no
# visible producer covered.
#
# In M1 only `properties` and `unevaluatedProperties` itself produce name
# coverage; `patternProperties`/`additionalProperties` arrive in M2 and will
# be added to `consumes` then.
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, `_ids`,
# and this package's `applicator_object` module (for `PROPERTIES_ID`). Never the
# evaluator or the registry.

from typing import cast

from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AllNames,
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    Phase,
    StaticFacts,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import VOCAB_UNEVALUATED, keyword_id
from json_schema_engine.core.keywords.applicator_object import PROPERTIES_ID

UNEVALUATED_PROPERTIES_ID = keyword_id(VOCAB_UNEVALUATED, "unevaluatedProperties")


def _unevaluated_properties_analyze(
    _value: JsonValue, _ctx: AnalyzeContext
) -> StaticFacts:
    # The keyword's own value *is* the subschema: an empty path under it is
    # the whole value, applied via `ctx.apply(("unevaluatedProperties",), ...)`.
    return StaticFacts(
        subschemas=((),),
        consumes=(PROPERTIES_ID, UNEVALUATED_PROPERTIES_ID),
        produces=(UNEVALUATED_PROPERTIES_ID,),
        evaluates_names=AllNames(),
    )


def _unevaluated_properties_evaluate(
    _value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance):
        return True
    # §4 rule 4: visibility is filtered by cursor identity, so this sees only
    # this instance location's own-schema and successfully-merged in-place
    # producers — never a cousin's, never a failed branch's.
    covered: set[str] = set()
    for view in ctx.visible((PROPERTIES_ID, UNEVALUATED_PROPERTIES_ID)):
        for name in cast(list[str], view.data):
            covered.add(name)
    ok = True
    matched: list[str] = []
    for name in instance:
        if name in covered:
            continue
        matched.append(name)
        if not ctx.apply(
            ("unevaluatedProperties",), child_cursor(cursor, name, instance[name])
        ):
            ok = False
    # Dependency data comes only from an accepting keyword (§4 rule 6).
    if ok:
        ctx.produce(matched)
    return ok


UNEVALUATED_PROPERTIES = KeywordBehavior(
    id=UNEVALUATED_PROPERTIES_ID,
    evaluate=_unevaluated_properties_evaluate,
    analyze=_unevaluated_properties_analyze,
    phase=Phase.UNEVALUATED,
)


UNEVALUATED_VOCABULARY: dict[str, KeywordBehavior] = {
    "unevaluatedProperties": UNEVALUATED_PROPERTIES,
}
