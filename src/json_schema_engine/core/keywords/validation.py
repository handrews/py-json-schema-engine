# Validation vocabulary keywords (DESIGN.md D2, D3, §3; M1+M2 scope). Pure
# assertions: they inspect the instance, report through `ctx.error()`, and
# never descend or produce dependency data. `pattern` is the assertion-class
# EXEMPLAR (§3): analyze() declares its regex so `reject_unsafe_regex` can
# screen it at registration, and evaluate() is vacuously true for a
# non-string instance. `type` and `required` were M1; `assertion()` below is
# the M2 factory for the remaining "guard the instance type, then compare"
# keywords (P2: bool is never a number, so every numeric guard checks
# `isinstance(x, bool)` before any numeric test).
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and this
# package's `_ids`. Never imports the registry or evaluator.

from collections.abc import Callable
from typing import TypeGuard

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    ErrorParams,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
)
from json_schema_engine.core.json_model import (
    JsonValue,
    code_point_length,
    first_duplicate_pair,
    is_integer_value,
    is_multiple_of,
    is_object,
    json_equal,
    json_type_of,
)
from json_schema_engine.core.keywords._ids import VOCAB_VALIDATION, keyword_id
from json_schema_engine.core.lowering import (
    CmpOp,
    Const,
    Expr,
    Item,
    LowerFn,
    LoweringContext,
    LowerMessage,
    LowerParams,
    Stmt,
    TypeName,
    and_,
    cmp,
    fail,
    has_key,
    helper,
    in_consts,
    lower_nothing,
    not_,
    regex_test,
    type_is,
    when,
)

# --- pattern (EXEMPLAR: assertion class) ----------------------------------


def _pattern_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(regexes=(value,)) if isinstance(value, str) else StaticFacts()


def _pattern_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    instance = cursor.value
    if not isinstance(instance, str) or not isinstance(value, str):
        return True
    if ctx.compile_regex(value).search(instance):
        return True
    ctx.error("does not match pattern", {"pattern": value})
    return False


def _pattern_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not isinstance(value, str):
        return
    instance = lctx.instance
    lctx.emit(
        when(
            and_(type_is(instance, "string"), not_(regex_test(value, instance))),
            (fail(("does not match pattern",), {"pattern": Const(value)}),),
        )
    )


pattern = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "pattern"),
    evaluate=_pattern_evaluate,
    analyze=_pattern_analyze,
    lower=_pattern_lower,
)


# --- assertion factory (M2) --------------------------------------------


def assertion(
    name: str,
    test: Callable[[JsonValue, JsonValue], bool],
    message: Callable[[JsonValue], str],
    params: Callable[[JsonValue], ErrorParams] | None = None,
    lower: LowerFn | None = None,
    lower_test: Callable[[JsonValue, Expr], Expr | None] | None = None,
) -> KeywordBehavior:
    """Build a one-error assertion: `test(value, instance)` or `ctx.error()`.

    Covers every validation keyword whose entire behavior is "check a
    predicate against the instance, and if it fails, report exactly one
    error naming the keyword's own value" — everything here except
    `enum`/`uniqueItems` (whose lowering isn't one guard-then-compare) and
    `dependentRequired` (which can report more than one error).

    `lower_test(value, instance)` names the "guard, then compare" family:
    given the keyword's (schema-fixed) value and the instance expression,
    it returns the failing condition, or `None` when the keyword value
    itself makes the assertion always vacuous (mirroring `test`'s own
    vacuous-truth guard on `value`, decided once at lowering time rather
    than per instance). `message`/`params` are shared verbatim with
    `evaluate` so the two never drift. Pass `lower` directly instead for a
    keyword whose lowering isn't of this shape.
    """

    def _evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        if test(value, cursor.value):
            return True
        ctx.error(message(value), params(value) if params is not None else None)
        return False

    def _lower(value: JsonValue, lctx: LoweringContext) -> None:
        assert lower_test is not None
        cond = lower_test(value, lctx.instance)
        if cond is None:
            return
        raw_params = params(value) if params is not None else None
        wrapped: LowerParams | None = (
            None if raw_params is None else {k: Const(v) for k, v in raw_params.items()}
        )
        lctx.emit(when(cond, (fail((message(value),), wrapped),)))

    resolved_lower = (
        lower if lower is not None else (_lower if lower_test is not None else None)
    )

    return KeywordBehavior(
        id=keyword_id(VOCAB_VALIDATION, name), evaluate=_evaluate, lower=resolved_lower
    )


def _is_number(x: JsonValue) -> TypeGuard[int | float]:
    """P2: bool is never a number, so it is excluded before the numeric test."""
    return not isinstance(x, bool) and isinstance(x, int | float)


def _limit_params(value: JsonValue) -> ErrorParams:
    return {"limit": value}


# --- type -------------------------------------------------------------


def _type_matches(name: JsonValue, instance: JsonValue) -> bool:
    """Whether one type name matches the instance (P2: bool is never a number).

    `"integer"` is a numeric subtype, not a `json_type_of` result, so it is
    tested separately via `is_integer_value` (`1.0` is an integer; `True`
    matches neither `"integer"` nor `"number"`, only `"boolean"`).
    """
    if name == "integer":
        return is_integer_value(instance)
    return json_type_of(instance) == name


def _type_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    names = value if isinstance(value, list) else [value]
    instance = cursor.value
    if any(_type_matches(name, instance) for name in names):
        return True
    expected = [str(name) for name in names]
    ctx.error(
        "expected " + ", ".join(expected),
        {"expected": list(names), "actual": json_type_of(instance).value},
    )
    return False


_TYPE_NAMES: dict[str, TypeName] = {
    "null": "null",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
    "number": "number",
    "string": "string",
    "integer": "integer",
}


def _type_lower(value: JsonValue, lctx: LoweringContext) -> None:
    names = value if isinstance(value, list) else [value]
    # An unknown type name matches nothing, as in `_type_matches`.
    known: list[TypeName] = []
    for name in names:
        if isinstance(name, str) and (known_name := _TYPE_NAMES.get(name)) is not None:
            known.append(known_name)
    lctx.emit(
        when(
            not_(type_is(lctx.instance, *known)),
            (
                fail(
                    ("expected " + ", ".join(str(n) for n in names),),
                    {
                        "expected": Const(list(names)),
                        "actual": helper("json_type_name", lctx.instance),
                    },
                ),
            ),
        )
    )


_type_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "type"),
    evaluate=_type_evaluate,
    lower=_type_lower,
)


# --- required --------------------------------------------------------------


def _required_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    instance = cursor.value
    if not is_object(instance) or not isinstance(value, list):
        return True
    ok = True
    # Python dicts have no prototype chain (D20, §5): `name in instance` is
    # complete here where a JS engine needs `Object.hasOwn`. The suite's
    # `__proto__`/`constructor`/`toString` property names are still exercised
    # in tests, so the absence of the hazard is proven rather than assumed.
    for name in value:
        if isinstance(name, str) and name not in instance:
            ctx.error(f"missing required property '{name}'", {"missingProperty": name})
            ok = False
    return ok


def _required_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not isinstance(value, list):
        return
    instance = lctx.instance
    checks = tuple(
        when(
            not_(has_key(instance, name)),
            (
                fail(
                    (f"missing required property '{name}'",),
                    {"missingProperty": Const(name)},
                ),
            ),
        )
        for name in value
        if isinstance(name, str)
    )
    if checks:
        lctx.emit(when(type_is(instance, "object"), checks))


_required_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "required"),
    evaluate=_required_evaluate,
    lower=_required_lower,
)


# --- enum / const (M2) --------------------------------------------------


def _enum_test(value: JsonValue, instance: JsonValue) -> bool:
    candidates = value if isinstance(value, list) else []
    return any(json_equal(candidate, instance) for candidate in candidates)


def _enum_lower(value: JsonValue, lctx: LoweringContext) -> None:
    # A non-list `value` gives `_enum_test` an empty candidate set, which
    # fails for every instance (§4 rule 6 vacuous-truth guards run the
    # other way here): mirror that as an unconditional `Fail`, no `when`.
    message: LowerMessage = ("not one of the allowed values",)
    params: LowerParams = {"allowedValues": Const(value)}
    if not isinstance(value, list) or not value:
        lctx.emit(fail(message, params))
        return
    lctx.emit(
        when(not_(in_consts(lctx.instance, tuple(value))), (fail(message, params),))
    )


_enum_behavior = assertion(
    "enum",
    _enum_test,
    lambda _value: "not one of the allowed values",
    lambda value: {"allowedValues": value},
    lower=_enum_lower,
)


def _const_lower_test(value: JsonValue, instance: Expr) -> Expr | None:
    return not_(helper("json_equal", instance, Const(value)))


_const_behavior = assertion(
    "const",
    json_equal,
    lambda _value: "does not equal the required constant",
    lambda value: {"allowedValue": value},
    lower_test=_const_lower_test,
)


# --- multipleOf (M2) -----------------------------------------------------


def _multiple_of_test(value: JsonValue, instance: JsonValue) -> bool:
    if not _is_number(instance) or not _is_number(value):
        return True
    return is_multiple_of(instance, value)


def _multiple_of_lower_test(value: JsonValue, instance: Expr) -> Expr | None:
    if not _is_number(value):
        return None
    return and_(
        type_is(instance, "number"),
        not_(helper("is_multiple_of", instance, Const(value))),
    )


_multiple_of_behavior = assertion(
    "multipleOf",
    _multiple_of_test,
    lambda value: f"must be a multiple of {value}",
    lambda value: {"multipleOf": value},
    lower_test=_multiple_of_lower_test,
)


# --- numeric bounds: maximum/exclusiveMaximum/minimum/exclusiveMinimum (M2)


def _numeric_bound(
    name: str, op: Callable[[int | float, int | float], bool], symbol: CmpOp
) -> KeywordBehavior:
    def _test(value: JsonValue, instance: JsonValue) -> bool:
        if not _is_number(instance) or not _is_number(value):
            return True
        return op(instance, value)

    def _lower_test(value: JsonValue, instance: Expr) -> Expr | None:
        if not _is_number(value):
            return None
        return and_(
            type_is(instance, "number"), not_(cmp(symbol, instance, Const(value)))
        )

    return assertion(
        name,
        _test,
        lambda value: f"must be {symbol} {value}",
        _limit_params,
        lower_test=_lower_test,
    )


_maximum_behavior = _numeric_bound("maximum", lambda i, v: i <= v, "<=")
_exclusive_maximum_behavior = _numeric_bound(
    "exclusiveMaximum", lambda i, v: i < v, "<"
)
_minimum_behavior = _numeric_bound("minimum", lambda i, v: i >= v, ">=")
_exclusive_minimum_behavior = _numeric_bound(
    "exclusiveMinimum", lambda i, v: i > v, ">"
)


# --- string length: maxLength/minLength (M2) -----------------------------


def _string_bound(
    name: str, op: Callable[[int, int], bool], phrase: str, symbol: CmpOp
) -> KeywordBehavior:
    def _test(value: JsonValue, instance: JsonValue) -> bool:
        if not isinstance(instance, str) or not _is_number(value):
            return True
        return op(code_point_length(instance), int(value))

    def _lower_test(value: JsonValue, instance: Expr) -> Expr | None:
        # `evaluate` truncates a non-integer keyword value via `int(value)`
        # (§4 rule 6 does not require the value itself to be a spec-valid
        # integer): the lowered comparison bakes in the same truncation.
        if not _is_number(value):
            return None
        return and_(
            type_is(instance, "string"),
            not_(cmp(symbol, helper("code_point_length", instance), Const(int(value)))),
        )

    return assertion(
        name,
        _test,
        lambda value: f"must be {phrase} {value} characters",
        _limit_params,
        lower_test=_lower_test,
    )


_max_length_behavior = _string_bound(
    "maxLength", lambda n, limit: n <= limit, "at most", "<="
)
_min_length_behavior = _string_bound(
    "minLength", lambda n, limit: n >= limit, "at least", ">="
)


# --- array size: maxItems/minItems (M2) -----------------------------------


def _array_bound(
    name: str, op: Callable[[int, int], bool], phrase: str, symbol: CmpOp
) -> KeywordBehavior:
    def _test(value: JsonValue, instance: JsonValue) -> bool:
        if not isinstance(instance, list) or not _is_number(value):
            return True
        return op(len(instance), int(value))

    def _lower_test(value: JsonValue, instance: Expr) -> Expr | None:
        if not _is_number(value):
            return None
        return and_(
            type_is(instance, "array"),
            not_(cmp(symbol, helper("length_of", instance), Const(int(value)))),
        )

    return assertion(
        name,
        _test,
        lambda value: f"must have {phrase} {value} items",
        _limit_params,
        lower_test=_lower_test,
    )


_max_items_behavior = _array_bound(
    "maxItems", lambda n, limit: n <= limit, "at most", "<="
)
_min_items_behavior = _array_bound(
    "minItems", lambda n, limit: n >= limit, "at least", ">="
)


# --- object size: maxProperties/minProperties (M2) ------------------------


def _object_bound(
    name: str, op: Callable[[int, int], bool], phrase: str, symbol: CmpOp
) -> KeywordBehavior:
    def _test(value: JsonValue, instance: JsonValue) -> bool:
        if not is_object(instance) or not _is_number(value):
            return True
        return op(len(instance), int(value))

    def _lower_test(value: JsonValue, instance: Expr) -> Expr | None:
        if not _is_number(value):
            return None
        return and_(
            type_is(instance, "object"),
            not_(cmp(symbol, helper("length_of", instance), Const(int(value)))),
        )

    return assertion(
        name,
        _test,
        lambda value: f"must have {phrase} {value} properties",
        _limit_params,
        lower_test=_lower_test,
    )


_max_properties_behavior = _object_bound(
    "maxProperties", lambda n, limit: n <= limit, "at most", "<="
)
_min_properties_behavior = _object_bound(
    "minProperties", lambda n, limit: n >= limit, "at least", ">="
)


# --- uniqueItems (M2) ------------------------------------------------------


def _unique_items_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    # `value is True` (not merely truthy): a JSON boolean is the only "on"
    # spelling, and `value is True` also excludes `1`/`1.0`, which json_equal
    # would treat as equal to `True` but which the keyword value never is.
    if value is not True or not isinstance(instance, list):
        return True
    pair = first_duplicate_pair(instance)
    if pair is None:
        return True
    j, i = pair
    ctx.error(f"items at {j} and {i} are not unique", {"duplicates": [j, i]})
    return False


def _unique_items_lower(value: JsonValue, lctx: LoweringContext) -> None:
    # `value is not True` (not merely falsy) mirrors `evaluate`'s own guard.
    if value is not True:
        return
    instance = lctx.instance
    # The colliding pair is runtime data: the message and params name it
    # through the same helper `evaluate` uses (computed only on the failure
    # path, where the scan already ran once).
    pair = helper("first_duplicate_pair", instance)
    lctx.emit(
        when(
            and_(type_is(instance, "array"), helper("has_duplicate_items", instance)),
            (
                fail(
                    (
                        "items at ",
                        Item(pair, Const(0)),
                        " and ",
                        Item(pair, Const(1)),
                        " are not unique",
                    ),
                    {"duplicates": pair},
                ),
            ),
        )
    )


_unique_items_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "uniqueItems"),
    evaluate=_unique_items_evaluate,
    lower=_unique_items_lower,
)


# --- dependentRequired (M2) -------------------------------------------------


def _dependent_required_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    for name, deps in value.items():
        if name not in instance or not isinstance(deps, list):
            continue
        for dep in deps:
            if isinstance(dep, str) and dep not in instance:
                ctx.error(
                    f"'{name}' requires '{dep}' to be present",
                    {"property": name, "missingProperty": dep},
                )
                ok = False
    return ok


def _dependent_required_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if not is_object(value):
        return
    instance = lctx.instance
    outer: list[Stmt] = []
    for name, deps in value.items():
        if not isinstance(deps, list):
            continue
        inner = tuple(
            when(
                not_(has_key(instance, dep)),
                (
                    fail(
                        (f"'{name}' requires '{dep}' to be present",),
                        {"property": Const(name), "missingProperty": Const(dep)},
                    ),
                ),
            )
            for dep in deps
            if isinstance(dep, str)
        )
        if inner:
            outer.append(when(has_key(instance, name), inner))
    if outer:
        lctx.emit(when(type_is(instance, "object"), tuple(outer)))


_dependent_required_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "dependentRequired"),
    evaluate=_dependent_required_evaluate,
    lower=_dependent_required_lower,
)


# --- minContains / maxContains (M2) -----------------------------------------
#
# Inert siblings: `contains` (owned by another agent's applicator module)
# reads these two directly off `ctx.schema`, the same way `if` drives
# `then`/`else`. They are registered here only so the registration walk and
# unknown-keyword handling treat them as known validation keywords rather
# than falling through to annotation-only or "unknown" handling; they never
# assert or annotate on their own.


def _inert_evaluate(_value: JsonValue, _cursor: Cursor, _ctx: KeywordContext) -> bool:
    return True


_min_contains_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "minContains"),
    evaluate=_inert_evaluate,
    lower=lower_nothing,
)

_max_contains_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "maxContains"),
    evaluate=_inert_evaluate,
    lower=lower_nothing,
)


VALIDATION_VOCABULARY = {
    "pattern": pattern,
    "type": _type_behavior,
    "required": _required_behavior,
    "enum": _enum_behavior,
    "const": _const_behavior,
    "multipleOf": _multiple_of_behavior,
    "maximum": _maximum_behavior,
    "exclusiveMaximum": _exclusive_maximum_behavior,
    "minimum": _minimum_behavior,
    "exclusiveMinimum": _exclusive_minimum_behavior,
    "maxLength": _max_length_behavior,
    "minLength": _min_length_behavior,
    "maxItems": _max_items_behavior,
    "minItems": _min_items_behavior,
    "maxProperties": _max_properties_behavior,
    "minProperties": _min_properties_behavior,
    "uniqueItems": _unique_items_behavior,
    "dependentRequired": _dependent_required_behavior,
    "minContains": _min_contains_behavior,
    "maxContains": _max_contains_behavior,
}
