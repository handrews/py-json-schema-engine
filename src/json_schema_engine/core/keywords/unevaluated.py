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
    SubschemaApplication,
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
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    Expr,
    ForEachIndex,
    ForEachKey,
    LoweringContext,
    apply,
    child,
    in_consts,
    not_,
    or_,
    regex_test,
    type_is,
    when,
)

PATTERN_PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "patternProperties")
ADDITIONAL_PROPERTIES_ID = keyword_id(VOCAB_APPLICATOR, "additionalProperties")

UNEVALUATED_PROPERTIES_ID = keyword_id(VOCAB_UNEVALUATED, "unevaluatedProperties")
UNEVALUATED_ITEMS_ID = keyword_id(VOCAB_UNEVALUATED, "unevaluatedItems")


def unevaluated_properties(
    behavior_id: str, consumes: tuple[str, ...]
) -> KeywordBehavior:
    """Build an `unevaluatedProperties` consumer for one dialect (D11).

    Every dialect's version is the same fold over `list[str]` dependency
    data; only the producer ids it reads differ (2019-09 has its own id
    space for the keyword itself). `consumes` must include `behavior_id`,
    since a nested `unevaluatedProperties` reports what it covered.
    """

    def analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
        # The keyword's own value *is* the subschema: an empty path under
        # it is the whole value.
        return StaticFacts(
            subschemas=((),),
            consumes=consumes,
            produces=(behavior_id,),
            evaluates_names=AllNames(),
            applications=(
                SubschemaApplication(
                    (), "child_sweep", conditional=False, asserts=True
                ),
            ),
        )

    def lower(_value: JsonValue, lctx: LoweringContext) -> None:
        cov = lctx.static_coverage()
        if cov is None:
            raise RuntimeError("unevaluatedProperties lowered without static coverage")
        if cov.covers_all_names:
            return
        instance = lctx.instance
        b = lctx.binding()
        parts: list[Expr] = []
        if cov.names:
            parts.append(in_consts(Binding(b), tuple(sorted(cov.names))))
        parts.extend(regex_test(pattern, Binding(b)) for pattern in cov.patterns)
        covered = or_(*parts)
        lctx.emit(
            when(
                type_is(instance, "object"),
                (
                    ForEachKey(
                        instance,
                        b,
                        (when(not_(covered), (apply((), child(HERE, Binding(b))),)),),
                    ),
                ),
            )
        )

    def evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        instance = cursor.value
        if not is_object(instance):
            return True
        # §4 rule 4: visibility is filtered by cursor identity, so this sees
        # only this instance location's own-schema and successfully-merged
        # in-place producers — never a cousin's, never a failed branch's.
        covered: set[str] = set()
        for view in ctx.visible(consumes):
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

    return KeywordBehavior(
        id=behavior_id,
        evaluate=evaluate,
        analyze=analyze,
        phase=Phase.UNEVALUATED,
        lower=lower,
    )


def unevaluated_items(
    behavior_id: str,
    consumes: tuple[str, ...],
    prefix_producer_id: str,
    contains_id: str = CONTAINS_ID,
) -> KeywordBehavior:
    """Build an `unevaluatedItems` consumer for one dialect (D11).

    The fold is dialect-independent: `contains` reports `True` (every
    element) or a list of matched indexes; any other `True` means the whole
    array was covered; the prefix producer (`prefixItems`, or 2019-09's
    tuple-form `items`) reports the largest applied index as an int.
    """

    def analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
        return StaticFacts(
            subschemas=((),),
            consumes=consumes,
            produces=(behavior_id,),
            evaluates_indexes=AllIndexes(),
            applications=(
                SubschemaApplication(
                    (), "child_sweep", conditional=False, asserts=True
                ),
            ),
        )

    def lower(_value: JsonValue, lctx: LoweringContext) -> None:
        cov = lctx.static_coverage()
        if cov is None:
            raise RuntimeError("unevaluatedItems lowered without static coverage")
        if cov.covers_all_indexes:
            return
        instance = lctx.instance
        b = lctx.binding()
        lctx.emit(
            when(
                type_is(instance, "array"),
                (
                    ForEachIndex(
                        instance,
                        b,
                        (apply((), child(HERE, Binding(b))),),
                        start=cov.prefix_count,
                    ),
                ),
            )
        )

    def evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        instance = cursor.value
        if not isinstance(instance, list):
            return True
        length = len(instance)
        covered_prefix = 0
        covered: set[int] = set()
        for view in ctx.visible(consumes):
            if view.behavior_id == contains_id:
                if view.data is True:
                    covered_prefix = length
                else:
                    for index in cast(list[int], view.data):
                        covered.add(index)
            elif view.data is True:
                covered_prefix = length
            elif view.behavior_id == prefix_producer_id and isinstance(view.data, int):
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

    return KeywordBehavior(
        id=behavior_id,
        evaluate=evaluate,
        analyze=analyze,
        phase=Phase.UNEVALUATED,
        lower=lower,
    )


UNEVALUATED_PROPERTIES = unevaluated_properties(
    UNEVALUATED_PROPERTIES_ID,
    (
        PROPERTIES_ID,
        PATTERN_PROPERTIES_ID,
        ADDITIONAL_PROPERTIES_ID,
        UNEVALUATED_PROPERTIES_ID,
    ),
)

UNEVALUATED_ITEMS = unevaluated_items(
    UNEVALUATED_ITEMS_ID,
    (PREFIX_ITEMS_ID, ITEMS_ID, CONTAINS_ID, UNEVALUATED_ITEMS_ID),
    PREFIX_ITEMS_ID,
)


UNEVALUATED_VOCABULARY: dict[str, KeywordBehavior] = {
    "unevaluatedProperties": UNEVALUATED_PROPERTIES,
    "unevaluatedItems": UNEVALUATED_ITEMS,
}
