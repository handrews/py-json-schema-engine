# Location chains leave a compiled artifact exactly as they leave the
# interpreter (DESIGN.md P11). The flag tier's `validate` is the emitted
# function itself, so its chain is attached in the interpreter trampolines
# rather than around the entry; the evaluator tier wraps its entry.

from collections.abc import Callable

import pytest

from json_schema_engine.compiler import compile_evaluator, compile_validator
from json_schema_engine.core import (
    Engine,
    JsonValue,
    UnresolvableReferenceError,
    create_engine,
)

type Run = Callable[[Engine, str, JsonValue], object]

RUNS: dict[str, Run] = {
    "interpreter": lambda engine, uri, instance: engine.evaluate(uri, instance),
    "evaluator": lambda engine, uri, instance: compile_evaluator(engine, uri).evaluate(
        instance
    ),
    "validator": lambda engine, uri, instance: compile_validator(engine, uri).validate(
        instance
    ),
    "validator-conservative": lambda engine, uri, instance: compile_validator(
        engine, uri, conservative=True
    ).validate(instance),
}


def _engine(schema: JsonValue) -> Engine:
    engine = create_engine()
    engine.register_schema(schema, "file:///srv/catalog.json")
    return engine


@pytest.mark.parametrize("run", RUNS.values(), ids=RUNS.keys())
def test_every_tier_chains_an_error_under_an_embedded_id(run: Run) -> None:
    engine = _engine(
        {
            "$id": "https://x.example/catalog",
            "$defs": {"i": {"$id": "items/", "$ref": "#/$defs/absent"}},
        }
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        run(engine, "https://x.example/items/", 1)
    chain = raised.value.location_chain
    assert chain is not None
    assert [h.resource_uri for h in chain] == [
        "https://x.example/items/",
        "https://x.example/catalog",
    ]
    assert chain[-1].retrieval_uri == "file:///srv/catalog.json"


@pytest.mark.parametrize("run", RUNS.values(), ids=RUNS.keys())
def test_every_tier_chains_an_error_under_unevaluated_tracking(run: Run) -> None:
    # An in-place island beside `unevaluatedProperties` must report what it
    # evaluated, which in the flag tier is the other trampoline.
    engine = _engine(
        {
            "$id": "https://x.example/catalog",
            "$ref": "items/",
            "unevaluatedProperties": False,
            "$defs": {"i": {"$id": "items/", "$ref": "#/$defs/absent"}},
        }
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        run(engine, "https://x.example/catalog", {"a": 1})
    chain = raised.value.location_chain
    assert chain is not None
    assert [h.resource_uri for h in chain] == [
        "https://x.example/items/",
        "https://x.example/catalog",
    ]
