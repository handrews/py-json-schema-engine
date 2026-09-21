# Generated api-payload instance corpus (M8 Step 2 bench harness), ported
# in intent (not code) from `generatePayloads` in the TS reference engine's
# `bench/corpora/index.ts` (DESIGN.md D15 read-for-intent allowance). The
# schema itself is vendored verbatim as `api-payload-schema.json` beside
# this module; this file only generates instances.
#
# Deterministic (`random.Random(0xBE5C0DE)`), no wall-clock, no
# third-party data. Half the instances are valid; the other half each
# carry exactly one planted defect, rotating through five kinds the
# schema actually rejects (checked against `api-payload-schema.json`):
# a missing required property, a keyword's declared `type` violated, a
# numeric range violated, a `pattern` violated, and an
# `additionalProperties: false` violation. Format assertions
# (`format: uuid`, `format: date-time`) are never checked by this bench
# harness (see `subjects.py`'s header), so no defect relies on one.

from __future__ import annotations

import random
from typing import cast

from json_schema_engine.core import JsonValue

_SEED = 0xBE5C0DE
INSTANCE_COUNT = 32
_DEFECT_KINDS = 5

_KINDS = ("order", "invoice", "shipment", "refund")
_CURRENCIES = ("USD", "EUR", "JPY")
_STATUSES = ("pending", "settled", "failed", "cancelled")
_REGIONS = ("us-east", "eu-west")
_HEX_DIGITS = "0123456789abcdef"
_UUID_TEMPLATE = "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx"


def _uuid(rng: random.Random) -> str:
    return "".join(
        rng.choice(_HEX_DIGITS) if ch == "x" else ch for ch in _UUID_TEMPLATE
    )


def _line_item(rng: random.Random) -> dict[str, JsonValue]:
    return {
        "sku": f"SKU-{rng.randint(1000, 9999)}",
        "quantity": rng.randint(1, 9),
        "unitPrice": round(rng.uniform(0, 10000), 2),
        "discount": round(rng.uniform(0, 1), 2),
    }


def _base_payload(rng: random.Random, index: int) -> dict[str, JsonValue]:
    return {
        "id": _uuid(rng),
        "kind": rng.choice(_KINDS),
        "createdAt": "2026-07-10T12:00:00Z",
        "amount": round(rng.uniform(0, 1000), 2),
        "currency": rng.choice(_CURRENCIES),
        "tags": [f"t{index}", "bench"],
        "attributes": {
            "status": rng.choice(_STATUSES),
            "priority": rng.randint(1, 5),
            "region": rng.choice(_REGIONS),
        },
        "lineItems": [_line_item(rng) for _ in range(rng.randint(1, 4))],
    }


def _plant_defect(payload: dict[str, JsonValue], kind: int) -> None:
    """Corrupt `payload` in exactly one schema-rejected way.

    Each branch targets a distinct keyword family so the five kinds cover
    missing-required, wrong-type, out-of-range, pattern, and
    additionalProperties violations without touching anything else.
    """
    if kind == 0:
        # `attributes` is required at the root.
        del payload["attributes"]
    elif kind == 1:
        # `amount`'s declared type is `number`.
        payload["amount"] = "not-a-number"
    elif kind == 2:
        # `attributes.priority`'s maximum is 5.
        attributes = cast("dict[str, JsonValue]", payload["attributes"])
        attributes["priority"] = 99
    elif kind == 3:
        # `currency` must match `^[A-Z]{3}$`.
        payload["currency"] = "usd"
    else:
        # Root `additionalProperties` is `false`.
        payload["extra"] = True


def build_api_payloads() -> tuple[list[JsonValue], list[bool]]:
    """`INSTANCE_COUNT` payload instances and the generator's own verdicts.

    Half are valid; half carry one planted defect each, rotating through
    the five kinds in `_plant_defect`. This bookkeeping is not the
    oracle — `corpora.py` still derives `expected` from the interpreter —
    but `tests/test_bench.py` asserts the two agree, so a defect the
    schema does not actually reject would be caught rather than silently
    accepted into the corpus.
    """
    rng = random.Random(_SEED)
    instances: list[JsonValue] = []
    expected: list[bool] = []
    for i in range(INSTANCE_COUNT):
        payload = _base_payload(rng, i)
        valid = i % 2 == 0
        if not valid:
            _plant_defect(payload, (i // 2) % _DEFECT_KINDS)
        instances.append(payload)
        expected.append(valid)
    return instances, expected
