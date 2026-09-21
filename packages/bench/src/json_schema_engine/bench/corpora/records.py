# Generated 150-property record corpus (M6 Step 5 bench harness).
#
# Deterministic (`random.Random(0xBE5C0DE)`), no wall-clock, no third-party
# data. One shared schema; two record-shape variants exercise the same
# validators under differing instance shapes:
#
# - `uniform`: every record carries every one of the 150 properties, in the
#   same key order.
# - `sparse`: each record drops 0-3 of the optional (non-required)
#   properties and has its remaining keys reordered, so property access is
#   polymorphic across instances.
#
# Roughly one in four records in each variant is invalid, rotating through
# distinct violation kinds so the hot path exercises more than one failure
# shape. `uniform` only uses violation kinds that preserve the full
# property set (value corruption, an extra property, a bad pattern); only
# `sparse` also drops a required property outright, since dropping a
# property in `uniform` would contradict "every record has every property".

from __future__ import annotations

import random
from typing import Literal, cast

from json_schema_engine.core import JsonValue

FIELD_COUNT = 150
RECORD_COUNT = 2000
_TYPES = ("string", "integer", "number", "boolean", "array")
_SEED = 0xBE5C0DE


def _field_type(index: int) -> str:
    return _TYPES[index % len(_TYPES)]


def _field_schema(index: int) -> JsonValue:
    field_type = _field_type(index)
    if field_type == "array":
        array_schema: dict[str, JsonValue] = {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        }
        return array_schema
    schema: dict[str, JsonValue] = {"type": field_type}
    if field_type == "string" and index % 30 == 0:
        # Multiples of 30 are always even, so a patterned field is always
        # required too (see `_required_fields`) — a pattern violation must
        # survive the `sparse` variant's dropping of optional properties.
        schema["pattern"] = "^v[0-9]+$"
    return schema


def _required_fields() -> list[str]:
    return [f"f{p}" for p in range(FIELD_COUNT) if p % 2 == 0]


def _optional_fields() -> list[str]:
    return [f"f{p}" for p in range(FIELD_COUNT) if p % 2 == 1]


def _patterned_fields() -> list[str]:
    return [f"f{p}" for p in range(FIELD_COUNT) if p % 30 == 0]


def build_records_schema() -> JsonValue:
    """The shared 150-property object schema.

    ~Half the properties are required (even indices), a few string
    properties carry a `pattern`, and `additionalProperties` is `false`.
    """
    properties: dict[str, JsonValue] = {
        f"f{p}": _field_schema(p) for p in range(FIELD_COUNT)
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": cast("list[JsonValue]", _required_fields()),
        "additionalProperties": False,
    }


def _field_value(rng: random.Random, index: int) -> JsonValue:
    field_type = _field_type(index)
    if field_type == "string":
        if index % 30 == 0:
            return f"v{rng.randint(0, 999)}"
        return f"s{index}-{rng.randint(0, 999999):x}"
    if field_type == "integer":
        return rng.randint(0, 100_000)
    if field_type == "number":
        return round(rng.uniform(0, 1000), 3)
    if field_type == "boolean":
        return rng.choice([True, False])
    return [f"tag{rng.randint(0, 9)}" for _ in range(rng.randint(0, 3))]


def _base_record(rng: random.Random) -> dict[str, JsonValue]:
    return {f"f{p}": _field_value(rng, p) for p in range(FIELD_COUNT)}


def _apply_violation(record: dict[str, JsonValue], index: int, *, kind: int) -> None:
    required = _required_fields()
    patterned = _patterned_fields()
    if kind == 0:
        # Drops a required property outright (sparse only — uniform never
        # loses a property).
        record.pop(required[index % len(required)], None)
    elif kind == 1:
        # A required property set to a value no declared type accepts.
        record[required[(index * 7) % len(required)]] = None
    elif kind == 2:
        record["unexpectedExtra"] = True  # additionalProperties violation
    else:
        field = patterned[index % len(patterned)]
        record[field] = "not-matching-pattern"


def _sparsify(
    rng: random.Random, record: dict[str, JsonValue], index: int
) -> dict[str, JsonValue]:
    optional = _optional_fields()
    drop_count = index % 4  # 0-3
    dropped: set[str] = set(rng.sample(optional, drop_count)) if drop_count else set()
    keys = [k for k in record if k not in dropped]
    rng.shuffle(keys)
    return {k: record[k] for k in keys}


def build_records(
    variant: Literal["uniform", "sparse"],
) -> tuple[list[JsonValue], list[bool]]:
    """2000 record instances and their expected verdicts for `variant`."""
    rng = random.Random(_SEED)
    kinds = (0, 1, 2, 3) if variant == "sparse" else (1, 2, 3)
    instances: list[JsonValue] = []
    expected: list[bool] = []
    for i in range(RECORD_COUNT):
        record = _base_record(rng)
        valid = i % 4 != 3
        if not valid:
            _apply_violation(record, i, kind=kinds[(i // 4) % len(kinds)])
        shaped: JsonValue = _sparsify(rng, record, i) if variant == "sparse" else record
        instances.append(shaped)
        expected.append(valid)
    return instances, expected
