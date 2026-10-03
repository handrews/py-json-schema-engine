# Error message building, shared by both tiers (DESIGN.md D13, P18).
#
# A keyword describes its error once, as a `LowerMessage` and `LowerParams`
# built from lowering IR. `lower()` emits that description and the compiler
# renders it into code; `evaluate()` hands the same description to
# `realize`, which interprets it against the concrete instance. One
# builder, so the two tiers cannot drift — which matters more now that
# messages carry instance data rather than only schema constants.
#
# The formatting helpers below are what messages call to show values: they
# are pure, bounded, and bound under fixed names in the compiled runtime.
# Bounded matters: an error is often recorded and then dropped (a losing
# `anyOf` branch, an `if` condition), so `preview` must cost the same for a
# ten-megabyte instance as for a short one.
#
# Dependency direction: imports `json_model` and `lowering`; keyword modules
# and the compiled runtime import this.

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Final

from json_schema_engine.core.json_model import (
    JsonValue,
    canonical_key,
    code_point_length,
    first_duplicate_pair,
    has_duplicate_items,
    is_integer_value,
    is_multiple_of,
    is_object,
    json_equal,
    json_type_name,
    json_type_of,
)
from json_schema_engine.core.lowering import (
    Binding,
    Cmp,
    Cond,
    Const,
    Expr,
    HasKey,
    Helper,
    HelperName,
    Instance,
    Item,
    Logic,
    LowerMessage,
    LowerParams,
    Member,
    Not,
    TypeIs,
)

# The longest a value is shown in a message, `…` included (owner ruling,
# 2026-10-03). Params carry the full value.
PREVIEW_LIMIT: Final = 64

# The most names `name_list` shows before summarizing the rest.
NAME_LIMIT: Final = 10

_ELLIPSIS: Final = "…"


# --- formatting helpers ------------------------------------------------------


def _chunks(value: JsonValue, budget: int) -> Iterator[str]:
    """Compact JSON for `value`, lazily, in pieces.

    Lazy so `preview` can stop once it has enough: containers are walked
    only as far as the text is shown, and a string is escaped only up to
    the budget.
    """
    if value is None:
        yield "null"
    elif isinstance(value, bool):
        yield "true" if value else "false"
    elif isinstance(value, int):
        yield str(value)
    elif isinstance(value, float):
        yield json.dumps(value)
    elif isinstance(value, str):
        # One character past the budget is enough to know it was cut.
        yield json.dumps(value[: budget + 1], ensure_ascii=False)
        if len(value) > budget + 1:
            yield _ELLIPSIS * 2
    elif isinstance(value, list):
        yield "["
        for index, item in enumerate(value):
            if index:
                yield ", "
            yield from _chunks(item, budget)
        yield "]"
    else:
        assert is_object(value)
        yield "{"
        for index, (key, item) in enumerate(value.items()):
            if index:
                yield ", "
            yield json.dumps(key[: budget + 1], ensure_ascii=False)
            yield ": "
            yield from _chunks(item, budget)
        yield "}"


def preview(value: JsonValue) -> str:
    """`value` as compact JSON, cut to `PREVIEW_LIMIT` characters with `…`.

    JSON rather than Python's `str()`, which would show `{'a': True}`.
    """
    text = ""
    for chunk in _chunks(value, PREVIEW_LIMIT):
        text += chunk
        if len(text) > PREVIEW_LIMIT:
            return text[: PREVIEW_LIMIT - 1] + _ELLIPSIS
    return text


def apparent_type(value: JsonValue) -> str:
    """The type a reader would name: `integer` for a mathematical integer
    (`3`, `3.0`), otherwise the JSON type. A boolean is never a number."""
    if not isinstance(value, bool) and is_integer_value(value):
        return "integer"
    return json_type_of(value).value


def typed_preview(value: JsonValue) -> str:
    """A scalar with its apparent type, `3 (integer)`; a container by its
    type alone, `array`, since its value can be arbitrarily large."""
    if isinstance(value, list) or is_object(value):
        return apparent_type(value)
    return f"{preview(value)} ({apparent_type(value)})"


def _sorted_unique(indexes: Sequence[int]) -> list[int]:
    return sorted(set(indexes))


def ranges(indexes: Sequence[int]) -> list[list[int]]:
    """Consecutive runs as `[first, last]` pairs: `[1, 2, 3, 5]` gives
    `[[1, 3], [5, 5]]`. The params form of `index_ranges`."""
    runs: list[list[int]] = []
    for index in _sorted_unique(indexes):
        if runs and index == runs[-1][1] + 1:
            runs[-1][1] = index
        else:
            runs.append([index, index])
    return runs


def index_ranges(indexes: Sequence[int]) -> str:
    """Indexes with runs of three or more collapsed: `0, 1, 3-5`; `none` if
    empty. A pair stays a pair, since `0-1` reads as a range of nothing."""
    parts: list[str] = []
    for a, b in ranges(indexes):
        if b - a >= 2:
            parts.append(f"{a}-{b}")
        else:
            parts.extend(str(i) for i in range(a, b + 1))
    return ", ".join(parts) or "none"


def name_list(names: Sequence[str]) -> str:
    """Names as JSON strings, the first `NAME_LIMIT` of them, then a count
    of the rest: `"a", "b" and 12 more`."""
    shown = ", ".join(preview(name) for name in names[:NAME_LIMIT])
    rest = len(names) - NAME_LIMIT
    return f"{shown} and {rest} more" if rest > 0 else shown


def labeled_names(names: Sequence[str], singular: str, plural: str) -> str:
    """`property "b"` or `properties "b", "c"`: a `name_list` with its
    noun agreeing in number."""
    return f"{singular if len(names) == 1 else plural} {name_list(names)}"


def counted_indexes(indexes: Sequence[int], singular: str, plural: str) -> str:
    """`none`, `1 item (4)`, or `2 items (0, 3)`."""
    if not indexes:
        return "none"
    noun = singular if len(indexes) == 1 else plural
    return f"{len(indexes)} {noun} ({index_ranges(indexes)})"


def index_groups(groups: Sequence[Sequence[int]]) -> str:
    """Groups of equal items: `0 = 2; 1 = 4 = 5`."""
    return "; ".join(" = ".join(str(i) for i in group) for group in groups)


def duplicate_groups(items: Sequence[JsonValue]) -> list[list[int]]:
    """Every group of two or more equal items, as indexes, ordered by each
    group's first index. One pass bucketed by `canonical_key`; a bucket is
    split by `json_equal`, since equal keys do not guarantee equal values."""
    buckets: dict[str, list[list[int]]] = {}
    for index, item in enumerate(items):
        groups = buckets.setdefault(canonical_key(item), [])
        for group in groups:
            if json_equal(items[group[0]], item):
                group.append(index)
                break
        else:
            groups.append([index])
    found = [g for groups in buckets.values() for g in groups if len(g) > 1]
    return sorted(found, key=lambda g: g[0])


def missing_names(instance: JsonValue, names: Sequence[JsonValue]) -> list[str]:
    """The string `names` an object instance lacks, in keyword order."""
    if not is_object(instance):
        return []
    return [n for n in names if isinstance(n, str) and n not in instance]


def missing_dependencies(
    instance: JsonValue, spec: Mapping[str, JsonValue]
) -> dict[str, list[str]]:
    """For each property present whose array member in `spec` names
    properties the instance lacks, those missing names. Non-array members
    (`dependencies`' schemas) are not this helper's concern."""
    if not is_object(instance):
        return {}
    found: dict[str, list[str]] = {}
    for name, deps in spec.items():
        if name in instance and isinstance(deps, list):
            missing = missing_names(instance, deps)
            if missing:
                found[name] = missing
    return found


def dependency_list(missing: Mapping[str, Sequence[str]]) -> str:
    """`"a" requires "b", "c"; "d" requires "e"`."""
    return "; ".join(
        f"{preview(name)} requires {name_list(deps)}" for name, deps in missing.items()
    )


# Every helper a lowered expression may call, by its IR name. The compiled
# runtime binds the same functions under its own names.
HELPERS: Final[Mapping[HelperName, Callable[..., JsonValue]]] = {
    "json_equal": json_equal,
    "is_multiple_of": is_multiple_of,
    "has_duplicate_items": has_duplicate_items,
    "first_duplicate_pair": first_duplicate_pair,  # type: ignore[dict-item]
    "length_of": len,
    "code_point_length": code_point_length,
    "json_type_name": json_type_name,
    "preview": preview,
    "apparent_type": apparent_type,
    "index_ranges": index_ranges,
    "name_list": name_list,
    "duplicate_groups": duplicate_groups,  # type: ignore[dict-item]
    "ranges": ranges,  # type: ignore[dict-item]
    "missing_names": missing_names,  # type: ignore[dict-item]
    "missing_dependencies": missing_dependencies,  # type: ignore[dict-item]
    "dependency_list": dependency_list,
    "typed_preview": typed_preview,
    "labeled_names": labeled_names,  # type: ignore[dict-item]
    "counted_indexes": counted_indexes,  # type: ignore[dict-item]
    "index_groups": index_groups,  # type: ignore[dict-item]
}


# --- realize ------------------------------------------------------------------


def _type_is(value: JsonValue, types: Sequence[str]) -> bool:
    for name in types:
        if name == "integer":
            if not isinstance(value, bool) and is_integer_value(value):
                return True
        elif json_type_of(value).value == name:
            return True
    return False


def _compare(op: str, left: JsonValue, right: JsonValue) -> bool:
    match op:
        case "<":
            return left < right  # type: ignore[operator]
        case "<=":
            return left <= right  # type: ignore[operator]
        case ">":
            return left > right  # type: ignore[operator]
        case ">=":
            return left >= right  # type: ignore[operator]
        case "==":
            return left == right
        case _:
            return left != right


def value_of(
    expr: Expr, instance: JsonValue, bindings: Mapping[int, JsonValue]
) -> JsonValue:
    """Evaluate the IR subset a message or its params may use."""

    def ev(node: Expr) -> JsonValue:
        match node:
            case Const(value=value):
                return value
            case Instance():
                return instance
            case Binding(id=binding):
                return bindings[binding]
            case Member(target=target, key=key):
                container = ev(target)
                assert is_object(container)
                return container[key]
            case Item(target=target, index=index):
                container = ev(target)
                position = ev(index)
                assert isinstance(container, list) and isinstance(position, int)
                return container[position]
            case Helper(name=name, args=args):
                return HELPERS[name](*(ev(a) for a in args))
            case Cond(test=test, then=then, orelse=orelse):
                return ev(then) if ev(test) else ev(orelse)
            case TypeIs(target=target, types=types):
                return _type_is(ev(target), types)
            case HasKey(target=target, key=key):
                container = ev(target)
                name = key if isinstance(key, str) else ev(key)
                return is_object(container) and name in container
            case Cmp(op=op, left=left, right=right):
                return _compare(op, ev(left), ev(right))
            case Not(expr=inner):
                return not ev(inner)
            case Logic(op=op, parts=parts):
                if op == "and":
                    return all(ev(p) for p in parts)
                return any(ev(p) for p in parts)
            case _:
                raise TypeError(f"not a message expression: {node!r}")

    return ev(expr)


def realize(
    message: LowerMessage,
    params: LowerParams | None,
    instance: JsonValue,
    bindings: Mapping[int, JsonValue] | None = None,
) -> tuple[str, dict[str, JsonValue] | None]:
    """The message text and params `evaluate()` reports for a description.

    Exactly what the compiled evaluator builds from the same description:
    literal parts as written, expression parts through `str()`.
    """
    scope = bindings or {}
    text = "".join(
        part if isinstance(part, str) else str(value_of(part, instance, scope))
        for part in message
    )
    if params is None:
        return text, None
    return text, {k: value_of(v, instance, scope) for k, v in params.items()}
