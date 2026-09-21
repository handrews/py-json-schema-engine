# The pre-2020-12 keywords shared by 2019-09 and draft-07/06 (DESIGN.md
# D11). 2019-09 folds the 2020-12 pair `prefixItems`/`items` into a single
# `items` keyword accepting either a schema (2020-12 `items`' shape) or a
# tuple of schemas (2020-12 `prefixItems`' shape), and keeps
# `additionalItems` to cover what the tuple form leaves uncovered — the gap
# 2020-12 no longer needs because its `items` already starts past
# `prefixItems`. draft-07/06 fold 2019-09's `dependentRequired` and
# `dependentSchemas` into a single `dependencies` keyword whose per-member
# value shape (array vs. schema) picks the behavior.
#
# Dependency-data shapes for `items` (tuple form) deliberately match
# 2020-12 `prefixItems` (int or `True`), and the schema form matches
# 2020-12 `items` (`True`): the 2019-09 `unevaluatedItems` folds coverage
# from this one keyword exactly the way 2020-12's `unevaluatedItems` folds
# coverage from two, so no consumer-side special case is needed.
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and
# `_ids`. Never the evaluator or the registry.

from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    IndexesFrom,
    KeywordBehavior,
    KeywordContext,
    PrefixIndexes,
    StaticFacts,
    SubschemaApplication,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import (
    VOCAB_APPLICATOR_07,
    VOCAB_APPLICATOR_2019,
    keyword_id,
)
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    Const,
    ForEachIndex,
    LoweringContext,
    Stmt,
    apply,
    child,
    cmp,
    cond,
    const,
    fail,
    has_key,
    helper,
    not_,
    produce,
    type_is,
    when,
)

ITEMS_LEGACY_ID = keyword_id(VOCAB_APPLICATOR_2019, "items")
ADDITIONAL_ITEMS_ID = keyword_id(VOCAB_APPLICATOR_2019, "additionalItems")
DEPENDENCIES_ID = keyword_id(VOCAB_APPLICATOR_07, "dependencies")


def _is_schema_value(value: JsonValue) -> bool:
    return is_object(value) or isinstance(value, bool)


# --- items (2019-09: prefixItems + items folded into one keyword) --------


def _items_legacy_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if isinstance(value, list):
        count = len(value)
        return StaticFacts(
            subschemas=tuple((index,) for index in range(count)),
            produces=(ITEMS_LEGACY_ID,),
            evaluates_indexes=PrefixIndexes(count),
            applications=tuple(
                SubschemaApplication(
                    (index,), "child_by_index", conditional=False, asserts=True
                )
                for index in range(count)
            ),
        )
    if _is_schema_value(value):
        return StaticFacts(
            subschemas=((),),
            produces=(ITEMS_LEGACY_ID,),
            evaluates_indexes=IndexesFrom(0),
            applications=(
                SubschemaApplication(
                    (), "child_sweep", conditional=False, asserts=True
                ),
            ),
        )
    return StaticFacts()


def _items_legacy_lower(value: JsonValue, lctx: LoweringContext) -> None:
    instance = lctx.instance
    length = helper("length_of", instance)
    if isinstance(value, list):
        # Tuple form: same shape as 2020-12 `prefixItems`, dependency data
        # included (`True` when every element was covered, else the
        # largest applied index; nothing for an empty array).
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
        return
    if not _is_schema_value(value):
        return
    # Schema form: same shape as 2020-12 `items`, with no sibling
    # `prefixItems` to start after.
    binding = lctx.binding()
    lctx.emit(
        when(
            type_is(instance, "array"),
            (
                ForEachIndex(
                    instance,
                    binding,
                    (apply((), child(HERE, Binding(binding))),),
                    start=0,
                ),
                when(cmp(">", length, const(0)), (produce(const(True)),)),
            ),
        )
    )


def _items_legacy_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not isinstance(instance, list):
        return True
    if isinstance(value, list):
        # Tuple form: positional, guarded by the shorter of the two lengths
        # — same shape as 2020-12 `prefixItems`.
        n = min(len(value), len(instance))
        ok = True
        for index in range(n):
            if not ctx.apply(
                ("items", index), child_cursor(cursor, index, instance[index])
            ):
                ok = False
        # Dependency data comes only from an accepting keyword (§4 rule 6):
        # the largest applied index, or True when it covered the whole array.
        if n > 0 and ok:
            ctx.produce(True if n == len(instance) else n - 1)
        return ok
    if not _is_schema_value(value):
        return True
    # Schema form: every element, from index 0 — same shape as 2020-12
    # `items` but with no sibling `prefixItems` to start after.
    ok = True
    applied = False
    for index in range(len(instance)):
        applied = True
        if not ctx.apply(("items",), child_cursor(cursor, index, instance[index])):
            ok = False
    if applied and ok:
        ctx.produce(True)
    return ok


ITEMS_LEGACY = KeywordBehavior(
    id=ITEMS_LEGACY_ID,
    evaluate=_items_legacy_evaluate,
    analyze=_items_legacy_analyze,
    lower=_items_legacy_lower,
)


# --- additionalItems (2019-09: covers the tail of a tuple `items`) -------
#
# Sibling-read, the same pattern as `if`/`then`/`else` and `contains`'
# `minContains`/`maxContains`: it applies only when the sibling `items` is
# present *and* a tuple (array) — a schema-form `items` already covers
# every element, so `additionalItems` does nothing against it (suite:
# "when items is a schema, additionalItems does nothing").


def _additional_items_analyze(_value: JsonValue, ctx: AnalyzeContext) -> StaticFacts:
    sibling = ctx.schema.get("items")
    if isinstance(sibling, list):
        return StaticFacts(
            subschemas=((),),
            produces=(ADDITIONAL_ITEMS_ID,),
            evaluates_indexes=IndexesFrom(len(sibling)),
            applications=(
                SubschemaApplication(
                    (), "child_sweep", conditional=False, asserts=True
                ),
            ),
        )
    return StaticFacts(subschemas=((),), produces=(ADDITIONAL_ITEMS_ID,))


def _additional_items_lower(_value: JsonValue, lctx: LoweringContext) -> None:
    sibling = lctx.schema.get("items")
    if not isinstance(sibling, list):
        return
    start = len(sibling)
    instance = lctx.instance
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


def _additional_items_evaluate(
    _value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    sibling = ctx.schema.get("items")
    if not isinstance(instance, list) or not isinstance(sibling, list):
        return True
    start = len(sibling)
    ok = True
    applied = False
    for index in range(start, len(instance)):
        applied = True
        if not ctx.apply(
            ("additionalItems",), child_cursor(cursor, index, instance[index])
        ):
            ok = False
    if applied and ok:
        ctx.produce(True)
    return ok


ADDITIONAL_ITEMS = KeywordBehavior(
    id=ADDITIONAL_ITEMS_ID,
    evaluate=_additional_items_evaluate,
    analyze=_additional_items_analyze,
    lower=_additional_items_lower,
)


# --- dependencies (draft-07/06: dependentRequired + dependentSchemas) ----
#
# A single keyword folding what 2019-09+ split into `dependentRequired`
# (array-valued members) and `dependentSchemas` (schema-valued members);
# per-member dispatch is by the member value's own shape.


def _dependencies_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not is_object(value):
        return StaticFacts()
    names = tuple(name for name, dep in value.items() if _is_schema_value(dep))
    return StaticFacts(
        subschemas=tuple((name,) for name in names),
        applications=tuple(
            SubschemaApplication((name,), "in_place", conditional=True, asserts=True)
            for name in names
        ),
    )


def _dependencies_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not is_object(value):
        return
    instance = lctx.instance
    checks: list[Stmt] = []
    for name, dep in value.items():
        if isinstance(dep, list):
            # Array member: the `dependentRequired` shape.
            required_checks = tuple(
                when(
                    not_(has_key(instance, required)),
                    (
                        fail(
                            (f"'{name}' requires '{required}' to be present",),
                            {
                                "property": Const(name),
                                "missingProperty": Const(required),
                            },
                        ),
                    ),
                )
                for required in dep
                if isinstance(required, str)
            )
            if required_checks:
                checks.append(when(has_key(instance, name), required_checks))
        elif _is_schema_value(dep):
            # Schema member: an in-place application guarded by presence,
            # same as `dependentSchemas`.
            checks.append(when(has_key(instance, name), (apply((name,), HERE),)))
        # Any other member shape is unreachable per the metaschema; ignored
        # defensively, mirroring `evaluate`.
    if checks:
        lctx.emit(when(type_is(instance, "object"), tuple(checks)))


def _dependencies_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    for name, dep in value.items():
        if name not in instance:
            continue
        if isinstance(dep, list):
            for required in dep:
                if isinstance(required, str) and required not in instance:
                    ctx.error(
                        f"'{name}' requires '{required}' to be present",
                        {"property": name, "missingProperty": required},
                    )
                    ok = False
        elif _is_schema_value(dep) and not ctx.apply(("dependencies", name), cursor):
            ok = False
        # Any other member shape is unreachable per the metaschema
        # (`anyOf`: schema or string array); ignored defensively.
    return ok


DEPENDENCIES = KeywordBehavior(
    id=DEPENDENCIES_ID,
    evaluate=_dependencies_evaluate,
    analyze=_dependencies_analyze,
    lower=_dependencies_lower,
)


LEGACY_ARRAY_VOCABULARY: dict[str, KeywordBehavior] = {
    "items": ITEMS_LEGACY,
    "additionalItems": ADDITIONAL_ITEMS,
}

DEPENDENCIES_VOCABULARY: dict[str, KeywordBehavior] = {
    "dependencies": DEPENDENCIES,
}
