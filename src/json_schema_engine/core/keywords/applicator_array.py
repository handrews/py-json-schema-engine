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

from collections.abc import Mapping

from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    DynamicIndexes,
    IndexesFrom,
    KeywordBehavior,
    KeywordContext,
    PrefixIndexes,
    StaticFacts,
    SubschemaApplication,
)
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    Const,
    CountRange,
    ForEachIndex,
    LoweringContext,
    LowerMessage,
    LowerParams,
    apply,
    apply_expr,
    child,
    cmp,
    cond,
    const,
    helper,
    produce,
    type_is,
    when,
)

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
        applications=tuple(
            SubschemaApplication(
                (index,), "child_by_index", conditional=False, asserts=True
            )
            for index in range(count)
        ),
    )


def _prefix_items_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not isinstance(value, list):
        return
    instance = lctx.instance
    length = helper("length_of", instance)
    lctx.emit(
        when(
            type_is(instance, "array"),
            (
                *(
                    when(
                        cmp(">", length, const(index)),
                        (apply((index,), child(HERE, index)),),
                    )
                    for index in range(len(value))
                ),
                # `True` when every element was covered, else the largest
                # applied index; nothing for an empty array (`evaluate`).
                *(
                    (
                        when(
                            cmp(">", length, const(0)),
                            (
                                produce(
                                    cond(
                                        cmp("<=", length, const(len(value))),
                                        const(True),
                                        const(len(value) - 1),
                                    )
                                ),
                            ),
                        ),
                    )
                    if value
                    else ()
                ),
            ),
        )
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
    id=PREFIX_ITEMS_ID,
    evaluate=_prefix_items_evaluate,
    analyze=_prefix_items_analyze,
    lower=_prefix_items_lower,
)


# --- items (child applicator, sweeps past sibling prefixItems) -----------


def _items_start(
    schema_context: AnalyzeContext | KeywordContext | LoweringContext,
) -> int:
    sibling = schema_context.schema.get("prefixItems")
    return len(sibling) if isinstance(sibling, list) else 0


def _items_analyze(_value: JsonValue, ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        produces=(ITEMS_ID,),
        evaluates_indexes=IndexesFrom(_items_start(ctx)),
        applications=(
            SubschemaApplication((), "child_sweep", conditional=False, asserts=True),
        ),
    )


def _items_lower(_value: JsonValue, lctx: LoweringContext) -> None:
    instance = lctx.instance
    start = _items_start(lctx)
    binding = lctx.binding()
    lctx.emit(
        when(
            type_is(instance, "array"),
            (
                ForEachIndex(
                    instance,
                    binding,
                    (apply((), child(HERE, Binding(binding))),),
                    start=start,
                ),
                when(
                    cmp(">", helper("length_of", instance), const(start)),
                    (produce(const(True)),),
                ),
            ),
        )
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


ITEMS = KeywordBehavior(
    id=ITEMS_ID, evaluate=_items_evaluate, analyze=_items_analyze, lower=_items_lower
)


# --- contains (in-place-per-element applicator, range configurable) -------


def _bound(schema: Mapping[str, JsonValue], name: str) -> int | float | None:
    value = schema.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _contains_bounds(
    schema: Mapping[str, JsonValue], *, sibling_bounds: bool
) -> tuple[int | float, int | float | None]:
    if not sibling_bounds:
        return 1, None
    minimum = _bound(schema, "minContains")
    minimum = 1 if minimum is None else minimum
    maximum = _bound(schema, "maxContains")
    return minimum, maximum


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
            applications=(
                SubschemaApplication(
                    (), "child_sweep", conditional=False, asserts=False
                ),
            ),
        )

    def lower(_value: JsonValue, lctx: LoweringContext) -> None:
        instance = lctx.instance
        minimum, maximum = _contains_bounds(lctx.schema, sibling_bounds=sibling_bounds)
        # Runtime dictates the actual match count (`count`), so — unlike
        # `evaluate()` — the message can only report the compile-time-known
        # bounds, not how many elements actually matched.
        if not sibling_bounds:
            message: LowerMessage = ("no item matches the contains subschema",)
        elif maximum is None:
            message = (
                f"expected at least {int(minimum)} item(s) matching "
                "the contains subschema",
            )
        else:
            message = (
                f"expected {int(minimum)}-{int(maximum)} item(s) matching "
                "the contains subschema",
            )
        params: LowerParams = (
            {"minContains": Const(int(minimum)), "maxContains": Const(int(maximum))}
            if maximum is not None
            else {"minContains": Const(int(minimum))}
        )
        binding = lctx.binding()
        matched = lctx.binding()
        count = helper("length_of", Binding(matched))
        lctx.emit(
            when(
                type_is(instance, "array"),
                (
                    CountRange(
                        instance,
                        binding,
                        apply_expr((), child(HERE, Binding(binding)), "discard"),
                        int(minimum),
                        int(maximum) if maximum is not None else None,
                        message=message,
                        params=params,
                        matched=matched,
                    ),
                    # Matched indexes, or `True` when every element matched;
                    # nothing when nothing matched (`evaluate`).
                    when(
                        cmp(">", count, const(0)),
                        (
                            produce(
                                cond(
                                    cmp("==", count, helper("length_of", instance)),
                                    const(True),
                                    Binding(matched),
                                )
                            ),
                        ),
                    ),
                ),
            )
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
        minimum, maximum = _contains_bounds(ctx.schema, sibling_bounds=sibling_bounds)
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

    return KeywordBehavior(
        id=behavior_id, evaluate=evaluate, analyze=analyze, lower=lower
    )


CONTAINS = contains_behavior(CONTAINS_ID, sibling_bounds=True)


ARRAY_APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {
    "prefixItems": PREFIX_ITEMS,
    "items": ITEMS,
    "contains": CONTAINS,
}
