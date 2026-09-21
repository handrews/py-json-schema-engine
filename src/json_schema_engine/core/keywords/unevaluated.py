# The unevaluated vocabulary (DESIGN.md D2, §3, §4 rule 4): the channel
# consumer keyword class. EXEMPLAR: `unevaluatedProperties` runs in
# `Phase.UNEVALUATED`, after every phase-0 keyword of its schema object has
# merged, reads the dependency data those keywords produced through
# `ctx.visible()`, and applies its own subschema to whatever member no
# visible producer covered. `unevaluatedItems` is the array-side twin,
# folding `prefixItems`/`items`/`contains` coverage the same way.
#
# `patternProperties`/`additionalProperties` ids are built locally with
# `keyword_id()` rather than imported from `applicator_object`, so this
# module's `consumes` declaration does not couple to that module's
# implementation state.
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, `_ids`,
# and this package's `applicator_object` module (for `PROPERTIES_ID`) and
# `applicator_array` module (for the array producer ids). Never the
# evaluator or the registry.

from typing import cast

from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AllIndexes,
    AllNames,
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    Phase,
    StaticFacts,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import (
    VOCAB_APPLICATOR,
    VOCAB_UNEVALUATED,
    keyword_id,
)
from json_schema_engine.core.keywords.applicator_array import (
    CONTAINS_ID,
    ITEMS_ID,
    PREFIX_ITEMS_ID,
)
from json_schema_engine.core.keywords.applicator_object import PROPERTIES_ID

PATTERN_PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "patternProperties")
ADDITIONAL_PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "additionalProperties")

UNEVALUATED_PROPERTIES_ID = keyword_id(VOCAB_UNEVALUATED, "unevaluatedProperties")
UNEVALUATED_ITEMS_ID = keyword_id(VOCAB_UNEVALUATED, "unevaluatedItems")


def _unevaluated_properties_analyze(
    _value: JsonValue, _ctx: AnalyzeContext
) -> StaticFacts:
    # The keyword's own value *is* the subschema: an empty path under it is
    # the whole value, applied via `ctx.apply(("unevaluatedProperties",), ...)`.
    return StaticFacts(
        subschemas=((),),
        consumes=(
            PROPERTIES_ID,
            PATTERN_PROPERTIES_ID,
            ADDITIONAL_PROPERTIES_ID,
            UNEVALUATED_PROPERTIES_ID,
        ),
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
    for view in ctx.visible(
        (
            PROPERTIES_ID,
            PATTERN_PROPERTIES_ID,
            ADDITIONAL_PROPERTIES_ID,
            UNEVALUATED_PROPERTIES_ID,
        )
    ):
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


# --- unevaluatedItems (array-side channel consumer) -----------------------


def _unevaluated_items_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        consumes=(PREFIX_ITEMS_ID, ITEMS_ID, CONTAINS_ID, UNEVALUATED_ITEMS_ID),
        produces=(UNEVALUATED_ITEMS_ID,),
        evaluates_indexes=AllIndexes(),
    )


def _unevaluated_items_evaluate(
    _value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not isinstance(instance, list):
        return True
    length = len(instance)
    # §4 rule 4: visibility is filtered by cursor identity, so this sees only
    # this instance location's own-schema and successfully-merged in-place
    # producers — never a cousin's, never a failed branch's.
    covered_prefix = 0
    covered: set[int] = set()
    for view in ctx.visible(
        (PREFIX_ITEMS_ID, ITEMS_ID, CONTAINS_ID, UNEVALUATED_ITEMS_ID)
    ):
        if view.behavior_id == CONTAINS_ID:
            if view.data is True:
                covered_prefix = length
            else:
                for index in cast(list[int], view.data):
                    covered.add(index)
        elif view.data is True:
            covered_prefix = length
        elif view.behavior_id == PREFIX_ITEMS_ID and isinstance(view.data, int):
            covered_prefix = max(covered_prefix, view.data + 1)
    ok = True
    applied = False
    for index in range(covered_prefix, length):
        if index in covered:
            continue
        applied = True
        if not ctx.apply(
            ("unevaluatedItems",), child_cursor(cursor, index, instance[index])
        ):
            ok = False
    # Dependency data comes only from an accepting keyword (§4 rule 6).
    if applied and ok:
        ctx.produce(True)
    return ok


UNEVALUATED_ITEMS = KeywordBehavior(
    id=UNEVALUATED_ITEMS_ID,
    evaluate=_unevaluated_items_evaluate,
    analyze=_unevaluated_items_analyze,
    phase=Phase.UNEVALUATED,
)


UNEVALUATED_VOCABULARY: dict[str, KeywordBehavior] = {
    "unevaluatedProperties": UNEVALUATED_PROPERTIES,
    "unevaluatedItems": UNEVALUATED_ITEMS,
}
