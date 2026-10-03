# Informative error messages (DESIGN.md D13, P18) come out of the compiled
# evaluator exactly as they come out of the interpreter: the same text and
# the same params, for every message shape that carries runtime data.

import pytest

from json_schema_engine.compiler import compile_evaluator
from json_schema_engine.core import JsonValue, create_engine

CASES: list[tuple[str, JsonValue, JsonValue]] = [
    ("type-scalar", {"type": "string"}, 3.0),
    ("type-container", {"type": ["string", "null"]}, [1, 2]),
    ("bound", {"minimum": 5}, 4.5),
    ("length", {"maxLength": 2}, "x" * 300),
    ("count", {"minItems": 3}, [1]),
    ("enum", {"enum": [1, "a", {"b": None}]}, {"b": False}),
    ("required", {"required": ["a", "b", "c"]}, {"b": 1}),
    ("dependentRequired", {"dependentRequired": {"a": ["b", "c"]}}, {"a": 1}),
    ("uniqueItems", {"uniqueItems": True}, [1, 2, 1, 2, 1.0]),
    ("contains-min", {"contains": {"type": "string"}, "minContains": 3}, ["a", 1]),
    ("contains-max", {"contains": {"type": "string"}, "maxContains": 1}, ["a", "b"]),
    ("anyOf", {"anyOf": [{"type": "string"}, {"minimum": 9}]}, 1),
    ("oneOf-two", {"oneOf": [{}, {"type": "integer"}, False]}, 1),
    ("oneOf-empty", {"oneOf": []}, 1),
    ("pattern", {"pattern": "^a"}, "b"),
    # `false` subschemas: one summary error per applicator (D13).
    (
        "additionalProperties-false",
        {"properties": {"a": {}}, "additionalProperties": False},
        {"a": 1, "b": 2, "c": 3},
    ),
    (
        "unevaluatedProperties-false",
        {"properties": {"a": {}}, "unevaluatedProperties": False},
        {"a": 1, "b": 2},
    ),
    (
        "properties-false",
        {"properties": {"a": False, "b": {"type": "string"}}},
        {"a": 1, "b": 2},
    ),
    (
        "patternProperties-false",
        {"patternProperties": {"^x": False, "a$": False}},
        {"xa": 1, "xb": 2, "ya": 3},
    ),
    ("propertyNames-false", {"propertyNames": False}, {"a": 1, "b": 2}),
    ("dependentSchemas-false", {"dependentSchemas": {"a": False}}, {"a": 1}),
    ("items-false", {"prefixItems": [{}], "items": False}, [1, 2, 3, 4, 5]),
    ("prefixItems-false", {"prefixItems": [{}, False, {}, False]}, [1, 2, 3, 4]),
    (
        "unevaluatedItems-false",
        {
            "prefixItems": [{}],
            "contains": {"type": "string"},
            "unevaluatedItems": False,
        },
        [1, 2, "x", 3, 4],
    ),
    ("allOf-false", {"allOf": [{}, False, {"type": "string"}]}, 1),
    ("contains-false", {"contains": False}, [1, 2]),
]


@pytest.mark.parametrize(
    ("schema", "instance"),
    [(case[1], case[2]) for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_compiled_messages_match_the_interpreter(
    schema: JsonValue, instance: JsonValue
) -> None:
    engine = create_engine()
    uri = engine.register_schema(schema, "urn:test:message-parity")
    interpreted = engine.evaluate(uri, instance, output="list", error_params=True)
    assert interpreted.valid is False
    for conservative in (False, True):
        compiled = compile_evaluator(engine, uri, conservative=conservative)
        assert (
            compiled.evaluate(instance, output="list", error_params=True) == interpreted
        )
