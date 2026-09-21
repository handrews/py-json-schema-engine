# The JSON value model: types, equality, canonical keys, RFC 6901 escaping
# (DESIGN.md §2 module table; P2 number and equality model).
#
# Dependency direction: a leaf. It imports only the standard library, and
# every other core module is free to import it.
#
# P2 in one line: Python's `bool` is an `int`, `True == 1`, `1 == 1.0`, and
# `hash(True) == hash(1)` — all four are wrong for JSON. So `bool` is tested
# before `int` everywhere, and plain `==` between two JSON values is banned
# in core: `json_equal` is the only equality.

import json
from collections.abc import Sequence
from enum import StrEnum
from typing import TypeGuard

# `None` is written last because ruff (RUF036) requires it there; member
# order in a union carries no meaning.
type JsonValue = (
    bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
)
"""A JSON-representable value.

Non-finite floats (`NaN`, `Infinity`) are outside this model even though
`float` admits them: parse boundaries reject them (P2) so the hot path never
has to test for them.
"""


class JsonType(StrEnum):
    """The seven JSON Schema primitive type names, spelled as the spec spells them.

    A `StrEnum` so a member compares and serializes as its wire name while
    still being an enum for exhaustive `match` statements.
    """

    NULL = "null"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    NUMBER = "number"
    STRING = "string"
    INTEGER = "integer"


def json_type_of(value: JsonValue) -> JsonType:
    """Return the primitive type of an instance value.

    Never returns `INTEGER`: `integer` is a numeric subtype that only the
    `type` keyword cares about, and it is tested with `is_integer_value`.
    """
    match value:
        case None:
            return JsonType.NULL
        # Before `int()`: `isinstance(True, int)` is true, and a JSON boolean
        # is not a JSON number.
        case bool():
            return JsonType.BOOLEAN
        case int() | float():
            return JsonType.NUMBER
        case str():
            return JsonType.STRING
        case list():
            return JsonType.ARRAY
        case dict():
            return JsonType.OBJECT
        case _:
            # Unreachable for a well-typed caller; loud for an untyped one,
            # because a silent fallthrough would return `None` as a type.
            raise TypeError(f"not a JSON value: {value!r}")


def is_integer_value(value: JsonValue) -> bool:
    """Return whether `value` is a JSON number with no fractional part.

    `1.0` is an integer per the spec, so `type: "integer"` accepts it.
    Non-finite floats are excluded for free: `float("nan").is_integer()` and
    `float("inf").is_integer()` are both false.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return value.is_integer() if isinstance(value, float) else False


def is_object(value: JsonValue) -> TypeGuard[dict[str, JsonValue]]:
    """Return whether `value` is a JSON object (not an array, not `null`)."""
    return isinstance(value, dict)


def json_equal(a: JsonValue, b: JsonValue) -> bool:
    """Return whether two JSON values are equal per the spec.

    Same type and same value; object member order is insignificant, array
    order is significant. Numeric equality is mathematical, so `1 == 1.0`,
    but `True` equals neither.

    Implemented by type dispatch rather than `a == b` because Python's `==`
    conflates `True` with `1` at every nesting level, including inside the
    `dict` and `list` comparisons a single `==` would delegate to.
    """
    if a is None or b is None:
        return a is None and b is None
    # Bools first and on both sides: either operand being a bool settles the
    # comparison, since nothing else in the model is bool-equal to a bool.
    if isinstance(a, bool):
        return isinstance(b, bool) and a is b
    if isinstance(b, bool):
        return False
    if isinstance(a, int | float):
        # Both operands are non-bool numbers here, so `==` is safe — and it
        # is exact: CPython compares int against float without converting,
        # so a 2**64-scale integer literal keeps its value.
        return isinstance(b, int | float) and a == b
    if isinstance(a, str):
        return isinstance(b, str) and a == b
    if isinstance(a, list):
        return (
            isinstance(b, list)
            and len(a) == len(b)
            and all(json_equal(x, y) for x, y in zip(a, b, strict=True))
        )
    return (
        isinstance(b, dict)
        and a.keys() == b.keys()
        and all(json_equal(v, b[k]) for k, v in a.items())
    )


def canonical_key(value: JsonValue) -> str:
    """Return a string key that `json_equal` values share.

    The guarantee is one-directional — `json_equal(a, b)` implies equal keys —
    which is what bucketing needs: `uniqueItems` buckets by this key for O(n)
    duplicate detection and confirms each collision with `json_equal` (D20).

    Object keys are sorted (member order is insignificant) and integral
    floats render as integers, so `1` and `1.0` share a bucket. Booleans
    render as bare `true`/`false`, which no number or string produces.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        # `n` prefixes the number space; `int()` of an integral float keeps
        # `1` and `1.0` in one bucket. `repr` is stable for equal floats.
        return f"n{int(value)}" if is_integer_value(value) else f"n{value!r}"
    if isinstance(value, str):
        # Quoted and escaped so that a string containing `,`, `:`, `[` or `{`
        # cannot forge the structure of the key around it.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical_key(item) for item in value) + "]"
    members = (
        f"{json.dumps(k, ensure_ascii=False)}:{canonical_key(value[k])}"
        for k in sorted(value)
    )
    return "{" + ",".join(members) + "}"


def code_point_length(s: str) -> int:
    """Return the length of `s` in Unicode code points, per `minLength`/`maxLength`.

    A Python `str` is already a sequence of code points, so this is `len`.
    It exists as a named function because the operation is spec-mandated and
    non-trivial in UTF-16 languages: implementations that count code units
    disagree with us on astral characters, and a reader should see that the
    choice was made rather than assumed.
    """
    return len(s)


def escape_segment(segment: str) -> str:
    """Escape one JSON Pointer reference token (RFC 6901 §3)."""
    return segment.replace("~", "~0").replace("/", "~1")


def unescape_segment(segment: str) -> str:
    """Unescape one JSON Pointer reference token (RFC 6901 §3).

    `~1` before `~0`, the reverse of the escape order: unescaping `~0` first
    would turn the escaped form of `~1` (`~01`) into `~1` and then into `/`.
    """
    return segment.replace("~1", "/").replace("~0", "~")


def pointer_of(segments: Sequence[str | int]) -> str:
    """Build a JSON Pointer from unescaped segments; the root pointer is `""`."""
    return "".join("/" + escape_segment(str(segment)) for segment in segments)
