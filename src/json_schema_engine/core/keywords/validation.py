# Validation vocabulary keywords (DESIGN.md D2, D3, §3; M1 scope). Pure
# assertions: they inspect the instance, report through `ctx.error()`, and
# never descend or produce dependency data. `pattern` is the assertion-class
# EXEMPLAR (§3): analyze() declares its regex so `reject_unsafe_regex` can
# screen it at registration, and evaluate() is vacuously true for a
# non-string instance. `type` and `required` complete the M1 subset that
# `VALIDATION_VOCABULARY` exports; the rest of the validation vocabulary
# (`enum`, `const`, `minLength`, ...) is M2's job.
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and this
# package's `_ids`. Never imports the registry or evaluator.

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
)
from json_schema_engine.core.json_model import (
    JsonValue,
    is_integer_value,
    is_object,
    json_type_of,
)
from json_schema_engine.core.keywords._ids import VOCAB_VALIDATION, keyword_id

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


pattern = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "pattern"),
    evaluate=_pattern_evaluate,
    analyze=_pattern_analyze,
)


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


_type_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "type"),
    evaluate=_type_evaluate,
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


_required_behavior = KeywordBehavior(
    id=keyword_id(VOCAB_VALIDATION, "required"),
    evaluate=_required_evaluate,
)


VALIDATION_VOCABULARY = {
    "pattern": pattern,
    "type": _type_behavior,
    "required": _required_behavior,
}
