# M6 Step 4: instance-mutation strategies for the differential fuzzer
# (test_fuzz.py). Hypothesis (`st`) drives every random choice, so a
# divergence shrinks and reproduces the way any other Hypothesis failure
# does; nothing here rolls its own PRNG.
#
# IP policy (DESIGN.md D15): the mutator IDEAS (type flips, numeric nudges,
# string edge values, trap keys, container mutation, nesting/depth probes,
# recursive sub-mutation, emptying) are ported from the TS reference
# engine's `packages/test-kit/src/fuzz.ts` — our own prior work — as
# Hypothesis strategies, not as translated code; the edge-value corpora
# below are re-derived for Python's number/string model (e.g. `2**53 + 1`
# rather than a float literal that would silently round), not copied
# verbatim. No third-party validator or fuzzer library was read.

import copy
import math
from collections.abc import Callable
from typing import cast

from hypothesis import strategies as st

from json_schema_engine.core import JsonValue

# --- edge-value corpora ------------------------------------------------

NUMERIC_EDGES: tuple[JsonValue, ...] = (
    0,
    -0.0,
    1,
    -1,
    0.5,
    1e-7,
    5e-324,
    1e308,
    2**53,
    2**53 + 1,
    2**63,
    10**30,
    -(10**30),
    1.0,
    2.0,
)

STRING_EDGES: tuple[str, ...] = (
    "",
    " ",
    "0",
    "1",
    "true",
    "null",
    "~",
    "/",
    "~0",
    "~1",
    "a/b",
    chr(0x2028),  # line separator
    chr(0x2029),  # paragraph separator
    "\ud800",  # a lone (unpaired) surrogate
    "café",
    "😀",
    "__proto__",
    "constructor",
    "__class__",
    "x" * 200,
)

TRAP_KEYS: tuple[str, ...] = (
    "__proto__",
    "constructor",
    "__class__",
    "__init__",
    "__dict__",
    "toString",
    "~",
    "/",
    "~0",
    "~1",
    "",
)

PRIMITIVE_EDGES: tuple[JsonValue, ...] = (None, True, False, 0, 1, -1, "", "x")


def _clone(value: JsonValue) -> JsonValue:
    return copy.deepcopy(value)


def _chance(draw: st.DrawFn, numerator: int, denominator: int) -> bool:
    """True with probability `numerator / denominator`, via a Hypothesis draw."""
    return draw(st.integers(min_value=0, max_value=denominator - 1)) < numerator


# --- mutators ------------------------------------------------------------
#
# Each mutator has the shape `(draw, value) -> JsonValue`: a plain function
# that uses `draw` (from an enclosing `st.composite`) to make every random
# choice, and never mutates `value` in place (a prior pool member, e.g. a
# suite seed instance, must stay stable for reuse across examples).


def type_flip(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Replace with a value of another JSON type."""
    candidates: list[JsonValue] = [
        None,
        draw(st.booleans()),
        draw(st.sampled_from(NUMERIC_EDGES)),
        draw(st.sampled_from(STRING_EDGES)),
        [],
        {},
        [_clone(value)],
        {"wrapped": _clone(value)},
    ]
    return draw(st.sampled_from(candidates))


def numeric_nudge(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Nudge a number by +-1 or +-0.5, negate it, or swap in a numeric edge."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return draw(st.sampled_from(NUMERIC_EDGES))
    kind = draw(st.integers(min_value=0, max_value=5))
    result: JsonValue
    if kind == 0:
        result = value + 1
    elif kind == 1:
        result = value - 1
    elif kind == 2:
        result = value + 0.5
    elif kind == 3:
        result = value - 0.5
    elif kind == 4:
        result = value * -1
    else:
        result = draw(st.sampled_from(NUMERIC_EDGES))
    if isinstance(result, float) and not math.isfinite(result):
        return draw(st.sampled_from(NUMERIC_EDGES))  # never hand back NaN/inf
    return result


def string_edge(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Swap in a string edge value, or perturb an existing string."""
    if not isinstance(value, str) or draw(st.booleans()):
        return draw(st.sampled_from(STRING_EDGES))
    kind = draw(st.integers(min_value=0, max_value=3))
    if kind == 0:
        return value + draw(st.sampled_from(STRING_EDGES))
    if kind == 1:
        return draw(st.sampled_from(STRING_EDGES)) + value
    if kind == 2:
        return draw(st.sampled_from(STRING_EDGES)) if value == "" else value[1:]
    return value.lower() if value.upper() == value else value.upper()


def add_trap_key(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Add a hazardous member name to an object (or start a fresh one)."""
    obj = dict(value) if isinstance(value, dict) else {}
    key = draw(st.sampled_from(TRAP_KEYS))
    obj[key] = draw(st.sampled_from(PRIMITIVE_EDGES))
    return obj


def array_mutate(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Append, drop, duplicate, or swap an element of an array."""
    arr = list(value) if isinstance(value, list) else []
    kind = draw(st.integers(min_value=0, max_value=3))
    if kind == 0 or not arr:
        arr.append(draw(st.sampled_from(PRIMITIVE_EDGES)))
        return arr
    if kind == 1:
        del arr[draw(st.integers(min_value=0, max_value=len(arr) - 1))]
        return arr
    if kind == 2 and len(arr) >= 2:
        i = draw(st.integers(min_value=0, max_value=len(arr) - 1))
        j = draw(st.integers(min_value=0, max_value=len(arr) - 1))
        arr[i], arr[j] = arr[j], arr[i]
        return arr
    idx = draw(st.integers(min_value=0, max_value=len(arr) - 1))
    arr.append(_clone(arr[idx]))
    return arr


def object_mutate(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Add, drop, or replace a member of an object."""
    source = value if isinstance(value, dict) else {}
    keys = list(source.keys())
    kind = draw(st.integers(min_value=0, max_value=2))
    if kind == 1 and keys:
        drop = draw(st.sampled_from(keys))
        return {k: v for k, v in source.items() if k != drop}
    obj = dict(source)
    if kind == 2 and keys:
        obj[draw(st.sampled_from(keys))] = draw(st.sampled_from(PRIMITIVE_EDGES))
        return obj
    key = (
        draw(st.sampled_from(TRAP_KEYS))
        if _chance(draw, 3, 10)
        else draw(st.sampled_from(STRING_EDGES))
    )
    obj[key] = draw(st.sampled_from(PRIMITIVE_EDGES))
    return obj


def nesting_wrap(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Wrap 40-60 levels deep, in single-key objects or doubled arrays, to
    probe the depth budget (both tiers must agree on where it bites)."""
    depth = draw(st.integers(min_value=40, max_value=60))
    acc: JsonValue = _clone(value)
    if draw(st.booleans()):
        for _ in range(depth):
            acc = {"a": acc}
    else:
        for _ in range(depth):
            acc = [[acc]]
    return acc


def mutate_within(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Descend to a random child location and apply one mutation there."""
    if isinstance(value, list) and value:
        idx = draw(st.integers(min_value=0, max_value=len(value) - 1))
        copy_ = list(value)
        copy_[idx] = mutate_instance(draw, copy_[idx])
        return copy_
    if isinstance(value, dict) and value:
        key = draw(st.sampled_from(list(value.keys())))
        copy_ = dict(value)
        copy_[key] = mutate_instance(draw, copy_[key])
        return copy_
    return type_flip(draw, value)


def empty_container(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Replace with `{}`/`[]`, at the root or at a nested location.

    M6 postmortem (per the TS reference engine's fuzz.ts): emptying a
    container found real lowering divergences (`enum []`, `anyOf []`,
    `oneOf []`) that no other mutator reaches, since nothing else ever
    empties a value outright.
    """
    kind = draw(st.integers(min_value=0, max_value=2))
    if kind == 0:
        return []
    if kind == 1:
        return {}
    if isinstance(value, list) and value:
        copy_ = list(value)
        idx = draw(st.integers(min_value=0, max_value=len(copy_) - 1))
        copy_[idx] = [] if draw(st.booleans()) else {}
        return copy_
    if isinstance(value, dict) and value:
        key = draw(st.sampled_from(list(value.keys())))
        copy_ = dict(value)
        copy_[key] = [] if draw(st.booleans()) else {}
        return copy_
    return [] if draw(st.booleans()) else {}


_MUTATORS: tuple[Callable[[st.DrawFn, JsonValue], JsonValue], ...] = (
    type_flip,
    numeric_nudge,
    string_edge,
    add_trap_key,
    array_mutate,
    object_mutate,
    nesting_wrap,
    mutate_within,
    empty_container,
)


def mutate_instance(draw: st.DrawFn, value: JsonValue) -> JsonValue:
    """Apply one uniformly chosen mutation to `value`."""
    mutator = draw(st.sampled_from(_MUTATORS))
    return mutator(draw, value)


@st.composite
def mutated(draw: st.DrawFn, seed: JsonValue) -> JsonValue:
    """Apply 1-3 successive mutations to `seed`, threading the result through
    each (never mutating `seed` itself)."""
    steps = draw(st.integers(min_value=1, max_value=3))
    value = seed
    for _ in range(steps):
        value = mutate_instance(draw, value)
    return value


def is_json_shaped(value: object) -> bool:
    """Whether `value` is plain JSON data: the allowed types only, and any
    float finite (no NaN/inf)."""
    if value is None or isinstance(value, bool | int | str):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        items = cast("list[object]", value)
        return all(is_json_shaped(v) for v in items)
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return all(isinstance(k, str) and is_json_shaped(v) for k, v in mapping.items())
    return False
