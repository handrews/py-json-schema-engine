# Cycle parity (DESIGN.md D8, D20/P3): the compiled tier raises
# `InfiniteLoopError` exactly when the interpreter does (in-place cycles
# are islanded, so the interpreter's own guard fires), and child-cursor
# recursion is progress until the depth budget.

import pytest

from json_schema_engine.compiler import compile_validator
from json_schema_engine.core import (
    InfiniteLoopError,
    JsonValue,
    MaxDepthExceededError,
    create_engine,
)


def compiled_and_interpreted(schema: JsonValue, max_depth: int = 512):
    engine = create_engine(max_depth=max_depth)
    uri = engine.register_schema(schema, "https://cycle.example/s")
    compiled = compile_validator(engine, uri)
    return engine, uri, compiled


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "#"},
        {"allOf": [{"$ref": "#/$defs/a"}], "$defs": {"a": {"$ref": "#"}}},
        {"anyOf": [{"type": "string"}, {"$ref": "#"}]},
        # A mixed cycle: the static root reaches an interpreted member.
        {"allOf": [{"$ref": "#/$defs/a"}], "$defs": {"a": {"$dynamicRef": "#"}}},
        # A cycle through a resource that binds a split anchor (`a` has two
        # declarers, so `S`'s site is specialized): the back-edge from
        # `S#/$defs/inner` lands on the root by location, whatever the
        # clone context, so the root islands and the short-circuiting
        # `anyOf` cannot hide the loop the interpreter's second branch hits.
        {
            "anyOf": [{"type": "integer"}, {"$ref": "S#/$defs/inner"}],
            "properties": {"p": {"$ref": "T"}, "q": {"$ref": "S"}},
            "$defs": {
                "S": {
                    "$id": "S",
                    "$dynamicAnchor": "a",
                    "properties": {"x": {"$dynamicRef": "#a"}},
                    "$defs": {"inner": {"$ref": "s"}},
                },
                "T": {"$id": "T", "$dynamicAnchor": "a", "$ref": "S"},
            },
        },
    ],
)
def test_in_place_cycles_raise_like_the_interpreter(schema: JsonValue) -> None:
    engine, uri, compiled = compiled_and_interpreted(schema)
    with pytest.raises(InfiniteLoopError):
        engine.evaluate(uri, 1)
    with pytest.raises(InfiniteLoopError):
        compiled.validate(1)


def test_child_cursor_recursion_is_progress_until_the_budget() -> None:
    engine, uri, compiled = compiled_and_interpreted(
        {"properties": {"child": {"$ref": "#"}}, "type": "object"}, max_depth=32
    )
    shallow: JsonValue = {}
    for _ in range(10):
        shallow = {"child": shallow}
    assert compiled.validate(shallow) is True
    assert engine.evaluate(uri, shallow).valid
    deep: JsonValue = {}
    for _ in range(100):
        deep = {"child": deep}
    with pytest.raises(MaxDepthExceededError):
        engine.evaluate(uri, deep)
    with pytest.raises(MaxDepthExceededError):
        compiled.validate(deep)
    # The artifact stays usable.
    assert compiled.validate(shallow) is True


def test_an_accepting_branch_hides_a_cycle_the_interpreter_never_enters() -> None:
    # `anyOf` runs every branch in the interpreter, so the cycle in the
    # second branch fires there. A compiled `anyOf` would short-circuit on
    # the first branch — but the back-edge lands on the root, which the
    # planner islands as a cycle, so the whole schema runs interpreted and
    # the error is raised exactly as before.
    engine, uri, compiled = compiled_and_interpreted(
        {"anyOf": [{"type": "integer"}, {"$ref": "#"}]}
    )
    with pytest.raises(InfiniteLoopError):
        engine.evaluate(uri, 1)
    with pytest.raises(InfiniteLoopError):
        compiled.validate(1)
