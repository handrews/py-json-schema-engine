# Object child applicators (DESIGN.md D2, §3): keywords that apply
# subschemas to an object's members or member names and communicate which
# names they covered as dependency data (§4 rule 6; draft-03 Appendix D).
# EXEMPLAR promoted to production form here: `properties` (child applicator
# class — matched members get their own cursor and the matched names become
# dependency data, produced only on success). `patternProperties`,
# `additionalProperties`, and `propertyNames` follow the same pattern (M2).
#
# Dependency-data shape shared by every producer in this module and by
# `unevaluatedProperties`: `list[str]` of the member names it applied to.
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
PATTERN_PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "patternProperties")
ADDITIONAL_PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "additionalProperties")
PROPERTY_NAMES_ID = keyword_id(VOCAB_APPLICATOR, "propertyNames")


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


OBJECT_APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {
    "properties": PROPERTIES,
}
