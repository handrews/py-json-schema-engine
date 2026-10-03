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
    AllNames,
    AnalyzeContext,
    CompiledRegex,
    KeywordBehavior,
    KeywordContext,
    NamesCoverage,
    PatternsCoverage,
    StaticFacts,
    SubschemaApplication,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id
from json_schema_engine.core.keywords._rejects import is_false, names_rejected
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    Const,
    Expr,
    ForEachKey,
    LoweringContext,
    LowerMessage,
    LowerParams,
    Stmt,
    append,
    apply,
    child,
    collect,
    has_key,
    helper,
    in_consts,
    key,
    not_,
    or_,
    produce,
    regex_test,
    reject,
    reject_check,
    type_is,
    when,
)
from json_schema_engine.core.messages import name_list, realize

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
        applications=tuple(
            SubschemaApplication(
                (name,), "child_by_key", conditional=False, asserts=True
            )
            for name in names
        ),
    )


def _properties_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not is_object(value):
        return
    instance = lctx.instance
    n = lctx.binding()
    r = lctx.binding()
    forbidden = any(is_false(schema) for schema in value.values())

    def step(name: str) -> tuple[Stmt, ...]:
        if is_false(value[name]):
            return (append(n, Const(name)), reject(r, Const(name)))
        return (append(n, Const(name)), apply((name,), child(HERE, name)))

    lctx.emit(
        when(
            type_is(instance, "object"),
            (
                collect(n),
                *((collect(r, errors=True),) if forbidden else ()),
                *(when(has_key(instance, name), step(name)) for name in value),
                *(
                    (reject_check(r, *names_rejected("", " not allowed", Binding(r))),)
                    if forbidden
                    else ()
                ),
                produce(Binding(n)),
            ),
        )
    )


def _properties_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    matched: list[str] = []
    rejected: list[JsonValue] = []
    for name in value:
        if name in instance:
            matched.append(name)
            if is_false(value[name]):
                # One summary error below instead of `schema is false`.
                rejected.append(name)
            elif not ctx.apply(
                ("properties", name), child_cursor(cursor, name, instance[name])
            ):
                ok = False
    if rejected:
        ctx.error(
            *realize(*names_rejected("", " not allowed", Const(rejected)), instance)
        )
        ok = False
    # Dependency data comes only from an accepting keyword (§4 rule 6,
    # draft-03 Appendix D): a rejecting `properties` communicates nothing.
    if ok:
        ctx.produce(matched)
    return ok


PROPERTIES = KeywordBehavior(
    id=PROPERTIES_ID,
    evaluate=_properties_evaluate,
    analyze=_properties_analyze,
    lower=_properties_lower,
)


# --- patternProperties (child applicator) ---------------------------------


def _pattern_properties_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not is_object(value):
        return StaticFacts()
    patterns = tuple(value)
    return StaticFacts(
        subschemas=tuple((pattern,) for pattern in patterns),
        regexes=patterns,
        produces=(PATTERN_PROPERTIES_ID,),
        evaluates_names=PatternsCoverage(patterns),
        applications=tuple(
            SubschemaApplication(
                (pattern,), "child_sweep", conditional=False, asserts=True
            )
            for pattern in patterns
        ),
    )


def _forbidden_patterns(value: dict[str, JsonValue]) -> list[str]:
    return [pattern for pattern, schema in value.items() if is_false(schema)]


def _pattern_properties_rejected(
    patterns: list[str], names: Expr
) -> tuple[LowerMessage, LowerParams]:
    return names_rejected(
        "",
        f" matching {name_list(patterns)} not allowed",
        names,
        {"patterns": Const(list(patterns))},
    )


def _pattern_properties_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not is_object(value):
        return
    instance = lctx.instance
    b = lctx.binding()
    n = lctx.binding()
    r = lctx.binding()
    forbidden = _forbidden_patterns(value)

    def step(pattern: str) -> Stmt:
        if is_false(value[pattern]):
            return reject(r, Binding(b), unique=True)
        return apply((pattern,), child(HERE, Binding(b)))

    # Pattern-outermost, as `evaluate` sweeps: the error and annotation
    # order (and the produced name order) must match the interpreter's.
    lctx.emit(
        when(
            type_is(instance, "object"),
            (
                collect(n),
                *((collect(r, errors=True),) if forbidden else ()),
                *(
                    ForEachKey(
                        instance,
                        b,
                        (
                            when(
                                regex_test(pattern, Binding(b)),
                                (append(n, Binding(b), unique=True), step(pattern)),
                            ),
                        ),
                    )
                    for pattern in value
                ),
                *(
                    (
                        reject_check(
                            r, *_pattern_properties_rejected(forbidden, Binding(r))
                        ),
                    )
                    if forbidden
                    else ()
                ),
                produce(Binding(n)),
            ),
        )
    )


def _pattern_properties_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    matched: list[str] = []
    rejected: list[JsonValue] = []
    for pattern in value:
        regex = ctx.compile_regex(pattern)
        for name in instance:
            if regex.search(name):
                if name not in matched:
                    matched.append(name)
                if is_false(value[pattern]):
                    if name not in rejected:
                        rejected.append(name)
                elif not ctx.apply(
                    ("patternProperties", pattern),
                    child_cursor(cursor, name, instance[name]),
                ):
                    ok = False
    if rejected:
        described = _pattern_properties_rejected(
            _forbidden_patterns(value), Const(rejected)
        )
        ctx.error(*realize(*described, instance))
        ok = False
    if ok:
        ctx.produce(matched)
    return ok


PATTERN_PROPERTIES = KeywordBehavior(
    id=PATTERN_PROPERTIES_ID,
    evaluate=_pattern_properties_evaluate,
    analyze=_pattern_properties_analyze,
    lower=_pattern_properties_lower,
)


# --- additionalProperties (child applicator, sibling-dependent) -----------


def _additional_properties_analyze(
    _value: JsonValue, _ctx: AnalyzeContext
) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        produces=(ADDITIONAL_PROPERTIES_ID,),
        evaluates_names=AllNames(),
        applications=(
            SubschemaApplication((), "child_sweep", conditional=False, asserts=True),
        ),
    )


def _additional_properties_lower(value: JsonValue, lctx: LoweringContext) -> None:
    instance = lctx.instance
    sibling_properties = lctx.schema.get("properties")
    names = tuple(sibling_properties) if is_object(sibling_properties) else ()
    sibling_patterns = lctx.schema.get("patternProperties")
    patterns = tuple(sibling_patterns) if is_object(sibling_patterns) else ()
    b = lctx.binding()
    n = lctx.binding()
    parts: list[Expr] = []
    if names:
        parts.append(in_consts(Binding(b), names))
    parts.extend(regex_test(pattern, Binding(b)) for pattern in patterns)
    covered = or_(*parts)
    if is_false(value):
        # Every additional name fails: report them once, apply nothing.
        r = lctx.binding()
        step: Stmt = reject(r, Binding(b))
        head: tuple[Stmt, ...] = (collect(n), collect(r, errors=True))
        tail: tuple[Stmt, ...] = (
            reject_check(r, *names_rejected("additional ", " not allowed", Binding(r))),
        )
    else:
        step = apply((), child(HERE, Binding(b)))
        head = (collect(n),)
        tail = ()
    lctx.emit(
        when(
            type_is(instance, "object"),
            (
                *head,
                ForEachKey(
                    instance,
                    b,
                    (when(not_(covered), (append(n, Binding(b)), step)),),
                ),
                *tail,
                produce(Binding(n)),
            ),
        )
    )


def _additional_properties_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance):
        return True
    sibling_properties = ctx.schema.get("properties")
    names: set[str] = (
        set(sibling_properties) if is_object(sibling_properties) else set()
    )
    sibling_patterns = ctx.schema.get("patternProperties")
    patterns: list[CompiledRegex] = (
        [ctx.compile_regex(pattern) for pattern in sibling_patterns]
        if is_object(sibling_patterns)
        else []
    )
    ok = True
    matched: list[str] = []
    for name in instance:
        if name in names or any(regex.search(name) for regex in patterns):
            continue
        matched.append(name)
        if not is_false(value) and not ctx.apply(
            ("additionalProperties",), child_cursor(cursor, name, instance[name])
        ):
            ok = False
    if is_false(value) and matched:
        rejected: list[JsonValue] = list(matched)
        ctx.error(
            *realize(
                *names_rejected("additional ", " not allowed", Const(rejected)),
                instance,
            )
        )
        ok = False
    if ok:
        ctx.produce(matched)
    return ok


ADDITIONAL_PROPERTIES = KeywordBehavior(
    id=ADDITIONAL_PROPERTIES_ID,
    evaluate=_additional_properties_evaluate,
    analyze=_additional_properties_analyze,
    lower=_additional_properties_lower,
)


# --- propertyNames (child applicator over member names) -------------------


def _property_names_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        applications=(
            SubschemaApplication((), "property_name", conditional=False, asserts=True),
        ),
    )


def _property_names_rejected(names: Expr) -> tuple[LowerMessage, LowerParams]:
    return (
        ("no property names allowed, got ", helper("name_list", names)),
        {"properties": names},
    )


def _property_names_lower(value: JsonValue, lctx: LoweringContext) -> None:
    instance = lctx.instance
    b = lctx.binding()
    if is_false(value):
        r = lctx.binding()
        lctx.emit(
            when(
                type_is(instance, "object"),
                (
                    collect(r, errors=True),
                    ForEachKey(instance, b, (reject(r, Binding(b)),)),
                    reject_check(r, *_property_names_rejected(Binding(r))),
                ),
            )
        )
        return
    lctx.emit(
        when(
            type_is(instance, "object"),
            (ForEachKey(instance, b, (apply((), key(b)),)),),
        )
    )


def _property_names_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance):
        return True
    if is_false(value):
        if not instance:
            return True
        names: list[JsonValue] = list(instance)
        ctx.error(*realize(*_property_names_rejected(Const(names)), instance))
        return False
    ok = True
    for name in instance:
        if not ctx.apply(("propertyNames",), child_cursor(cursor, name, name)):
            ok = False
    return ok


PROPERTY_NAMES = KeywordBehavior(
    id=PROPERTY_NAMES_ID,
    evaluate=_property_names_evaluate,
    analyze=_property_names_analyze,
    lower=_property_names_lower,
)


OBJECT_APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {
    "properties": PROPERTIES,
    "patternProperties": PATTERN_PROPERTIES,
    "additionalProperties": ADDITIONAL_PROPERTIES,
    "propertyNames": PROPERTY_NAMES,
}
