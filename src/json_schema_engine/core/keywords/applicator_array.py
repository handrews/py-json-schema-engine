# Array child applicators (DESIGN.md D2, §3): `prefixItems`, `items`, and
# `contains` apply subschemas to array elements and communicate which
# indexes they covered as dependency data (§4 rule 6; draft-03 Appendix D),
# which `unevaluatedItems` folds (M2).
#
# Dependency-data shapes, shared with `unevaluatedItems`:
#   prefixItems  -> True when it covered the whole array, else the largest
#                   applied index (an int)
#   items        -> True (it applied to at least one element past the prefix)
#   contains     -> True when every element matched, else list[int] of the
#                   matched indexes
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and
# `_ids`. Never the evaluator or the registry.

from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    DynamicIndexes,
    IndexesFrom,
    KeywordBehavior,
    KeywordContext,
    PrefixIndexes,
    StaticFacts,
)
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id

PREFIX_ITEMS_ID = keyword_id(VOCAB_APPLICATOR, "prefixItems")
ITEMS_ID = keyword_id(VOCAB_APPLICATOR, "items")
CONTAINS_ID = keyword_id(VOCAB_APPLICATOR, "contains")


# --- prefixItems (child applicator, positional) ---------------------------


def _prefix_items_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not isinstance(value, list):
        return StaticFacts()
    count = len(value)
    return StaticFacts(
        subschemas=tuple((index,) for index in range(count)),
        produces=(PREFIX_ITEMS_ID,),
        evaluates_indexes=PrefixIndexes(count),
    )


def _prefix_items_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not isinstance(instance, list) or not isinstance(value, list):
        return True
    n = min(len(value), len(instance))
    ok = True
    for index in range(n):
        if not ctx.apply(
            ("prefixItems", index), child_cursor(cursor, index, instance[index])
        ):
            ok = False
    # Dependency data comes only from an accepting keyword (§4 rule 6): the
    # largest applied index, or True when it covered the whole array.
    if n > 0 and ok:
        ctx.produce(True if n == len(instance) else n - 1)
    return ok


PREFIX_ITEMS = KeywordBehavior(
    id=PREFIX_ITEMS_ID, evaluate=_prefix_items_evaluate, analyze=_prefix_items_analyze
)


# --- items (child applicator, sweeps past sibling prefixItems) -----------


def _items_start(schema_context: AnalyzeContext | KeywordContext) -> int:
    sibling = schema_context.schema.get("prefixItems")
    return len(sibling) if isinstance(sibling, list) else 0


def _items_analyze(_value: JsonValue, ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        produces=(ITEMS_ID,),
        evaluates_indexes=IndexesFrom(_items_start(ctx)),
    )


def _items_evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    instance = cursor.value
    if not isinstance(instance, list):
        return True
    start = _items_start(ctx)
    ok = True
    applied = False
    for index in range(start, len(instance)):
        applied = True
        if not ctx.apply(("items",), child_cursor(cursor, index, instance[index])):
            ok = False
    if applied and ok:
        ctx.produce(True)
    return ok


ITEMS = KeywordBehavior(id=ITEMS_ID, evaluate=_items_evaluate, analyze=_items_analyze)


# --- contains (in-place-per-element applicator, range configurable) -------


def _bound(ctx: KeywordContext, name: str) -> int | float | None:
    value = ctx.schema.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def contains_behavior(behavior_id: str, *, sibling_bounds: bool) -> KeywordBehavior:
    """Build `contains` for one dialect (D11).

    2020-12 and 2019-09 turn the count into a range through the inert
    sibling keywords `minContains`/`maxContains`; draft-07 and draft-06
    predate those, so there the requirement is a fixed "at least one" and
    a sibling spelled `minContains` is an ordinary unknown keyword.
    """

    def analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
        return StaticFacts(
            subschemas=((),),
            produces=(behavior_id,),
            evaluates_indexes=DynamicIndexes(),
        )

    def evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        instance = cursor.value
        if not isinstance(instance, list):
            return True
        matched: list[int] = []
        for index in range(len(instance)):
            if ctx.apply(("contains",), child_cursor(cursor, index, instance[index])):
                matched.append(index)
        count = len(matched)
        if sibling_bounds:
            minimum = _bound(ctx, "minContains")
            minimum = 1 if minimum is None else minimum
            maximum = _bound(ctx, "maxContains")
        else:
            minimum, maximum = 1, None
        if count < minimum or (maximum is not None and count > maximum):
            if not sibling_bounds:
                message = "no item matches the contains subschema"
            elif maximum is None:
                message = (
                    f"{count} item(s) match the contains subschema, "
                    f"expected at least {minimum}"
                )
            else:
                message = (
                    f"{count} item(s) match the contains subschema, "
                    f"expected {minimum}-{maximum}"
                )
            params: dict[str, JsonValue] = {"count": count, "minContains": minimum}
            if maximum is not None:
                params["maxContains"] = maximum
            ctx.error(message, params)
            return False
        # Dependency data comes only from an accepting keyword: matched
        # indexes, or True when every element matched. `minContains: 0`
        # with zero matches produces nothing.
        if count > 0:
            ctx.produce(True if count == len(instance) else matched)
        return True

    return KeywordBehavior(id=behavior_id, evaluate=evaluate, analyze=analyze)


CONTAINS = contains_behavior(CONTAINS_ID, sibling_bounds=True)


ARRAY_APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {
    "prefixItems": PREFIX_ITEMS,
    "items": ITEMS,
    "contains": CONTAINS,
}
