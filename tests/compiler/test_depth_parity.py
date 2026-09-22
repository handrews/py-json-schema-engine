# Depth parity (DESIGN.md D20, P3; M6): the interpreter, the compiled
# validator, and a standalone module all raise `MaxDepthExceededError` on
# the same inputs — by class, never by exact depth (the interpreter trips
# CPython's frame limit near ~200 applications; compiled units reach the
# counter).

from collections.abc import Callable
from typing import cast

import pytest

from json_schema_engine.compiler import (
    build_plan,
    compile_evaluator,
    compile_validator,
    emit_standalone,
    explain_compilation,
)
from json_schema_engine.core import (
    Engine,
    JsonValue,
    MaxDepthExceededError,
    create_engine,
)

type Validator = Callable[[JsonValue], bool]


def _nest(depth: int) -> JsonValue:
    value: JsonValue = {}
    for _ in range(depth):
        value = {"child": value}
    return value


def _standalone(engine: Engine, uri: str) -> Validator:
    namespace: dict[str, object] = {}
    exec(compile(emit_standalone(engine, uri), "<standalone>", "exec"), namespace)
    return cast(Validator, namespace["validate"])


def test_recursive_ref_chain_trips_the_budget_on_every_surface() -> None:
    engine = create_engine(max_depth=64)
    uri = engine.register_schema(
        {"type": "object", "properties": {"child": {"$ref": "#"}}},
        "https://depth.example/s",
    )
    compiled = compile_validator(engine, uri).validate
    standalone = _standalone(engine, uri)
    evaluator = compile_evaluator(engine, uri).evaluate
    shallow = _nest(20)
    assert engine.evaluate(uri, shallow).valid
    assert compiled(shallow) is True
    assert standalone(shallow) is True
    assert evaluator(shallow, output="hierarchical").valid is True
    deep = _nest(200)
    surfaces: list[Callable[[], bool]] = [
        lambda: engine.evaluate(uri, deep).valid,
        lambda: evaluator(deep, output="hierarchical", trace=True).valid,
        lambda: compiled(deep),
        lambda: standalone(deep),
    ]
    for surface in surfaces:
        with pytest.raises(MaxDepthExceededError):
            surface()


def test_island_shares_the_budget() -> None:
    # Two declarers of `node` keep the site an island (M9), so the recursion
    # runs through the trampoline and the interpreter's own depth counter.
    engine = create_engine(max_depth=20)
    uri = engine.register_schema(
        {
            "$defs": {
                "tree": {
                    "$id": "tree",
                    "$defs": {"node": {"$dynamicAnchor": "node", "type": "object"}},
                    "properties": {"child": {"$dynamicRef": "#node"}},
                },
                "strict": {
                    "$id": "strict",
                    "$defs": {
                        "node": {
                            "$dynamicAnchor": "node",
                            "$ref": "tree",
                            "required": ["child"],
                        }
                    },
                    "$ref": "tree",
                },
                "loose": {
                    "$id": "loose",
                    "$defs": {"node": {"$dynamicAnchor": "node", "$ref": "tree"}},
                    "$ref": "tree",
                },
            },
            "anyOf": [{"$ref": "#/$defs/strict"}, {"$ref": "#/$defs/loose"}],
        },
        "https://depth.example/island",
    )
    assert explain_compilation(build_plan(engine, uri)).causes == {"dynamic": 1}
    compiled = compile_validator(engine, uri).validate
    assert compiled(_nest(5)) is True
    with pytest.raises(MaxDepthExceededError):
        compiled(_nest(60))
    with pytest.raises(MaxDepthExceededError):
        engine.evaluate(uri, _nest(60))


def test_backstop_converts_a_stray_recursion_error() -> None:
    engine = create_engine(max_depth=1_000_000)
    uri = engine.register_schema(
        {"properties": {"child": {"$ref": "#"}}}, "https://depth.example/backstop"
    )
    compiled = compile_validator(engine, uri).validate
    with pytest.raises(MaxDepthExceededError):
        compiled(_nest(5000))
    assert compiled(_nest(3)) is True
