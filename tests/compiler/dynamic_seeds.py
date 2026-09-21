# Dynamic-reference seed corpus (M9, after the TS engine's ADR 0004): the
# shapes plan-time resolution must get right, each pinned to a
# classification. Stable shapes compile with no interpreted unit; unstable
# ones keep an island (and so keep the trampoline covered). Shared by the
# dynamic-resolution tests and the differential fuzz.

from dataclasses import dataclass
from typing import Literal

from json_schema_engine.core import DIALECT_2019_09, DIALECT_2020_12, JsonValue


@dataclass(frozen=True, slots=True)
class DynamicSeed:
    key: str
    dialect: str
    schema: JsonValue
    tests: tuple[tuple[JsonValue, bool], ...]
    classification: Literal["static", "island"]


DYNAMIC_SEEDS: tuple[DynamicSeed, ...] = (
    DynamicSeed(
        "stable-single",
        DIALECT_2020_12,
        {
            "$dynamicAnchor": "node",
            "type": "object",
            "properties": {"child": {"$dynamicRef": "#node"}},
        },
        (({}, True), ({"child": {}}, True), ({"child": {"child": 1}}, False)),
        "static",
    ),
    DynamicSeed(
        "stable-two-paths",
        DIALECT_2020_12,
        {
            "$defs": {
                "item": {"$dynamicAnchor": "item", "type": "integer"},
                "a": {"items": {"$dynamicRef": "#item"}},
                "b": {"$ref": "#/$defs/a"},
            },
            "anyOf": [{"$ref": "#/$defs/a"}, {"$ref": "#/$defs/b"}],
        },
        (([1, 2], True), (["x"], False), ([], True)),
        "static",
    ),
    DynamicSeed(
        "chained",
        DIALECT_2020_12,
        {
            "$defs": {
                "mid": {
                    "$dynamicAnchor": "mid",
                    "properties": {"x": {"$dynamicRef": "#inner"}},
                },
                "inner": {"$dynamicAnchor": "inner", "type": "string"},
            },
            "properties": {"m": {"$dynamicRef": "#mid"}},
        },
        (({"m": {"x": "s"}}, True), ({"m": {"x": 1}}, False)),
        "static",
    ),
    DynamicSeed(
        "bookend-absent",
        DIALECT_2020_12,
        {
            "$defs": {
                "n": {"$id": "n", "$anchor": "node", "type": "string"},
                "other": {"$id": "other", "$dynamicAnchor": "node", "type": "number"},
            },
            "properties": {"p": {"$ref": "other"}, "q": {"$dynamicRef": "n#node"}},
        },
        (({"p": 1, "q": "s"}, True), ({"q": 1}, False)),
        "static",
    ),
    DynamicSeed(
        "metaschema-wrapper",
        DIALECT_2020_12,
        {"$ref": "https://json-schema.org/draft/2020-12/schema"},
        (
            ({"type": "string"}, True),
            ({"type": 12}, False),
            ({"properties": {"a": {"minimum": "x"}}}, False),
        ),
        "static",
    ),
    DynamicSeed(
        "unstable-two-paths",
        DIALECT_2020_12,
        {
            "$defs": {
                "genericList": {
                    "$id": "genericList",
                    "$defs": {
                        "defaultItem": {"$dynamicAnchor": "item", "type": "null"}
                    },
                    "items": {"$dynamicRef": "#item"},
                },
                "numberList": {
                    "$id": "numberList",
                    "$defs": {"item": {"$dynamicAnchor": "item", "type": "number"}},
                    "$ref": "genericList",
                },
                "stringList": {
                    "$id": "stringList",
                    "$defs": {"item": {"$dynamicAnchor": "item", "type": "string"}},
                    "$ref": "genericList",
                },
            },
            "if": {"properties": {"kind": {"const": "numbers"}}},
            "then": {"properties": {"list": {"$ref": "#/$defs/numberList"}}},
            "else": {"properties": {"list": {"$ref": "#/$defs/stringList"}}},
        },
        (
            ({"kind": "numbers", "list": [1, 2]}, True),
            ({"kind": "numbers", "list": ["a"]}, False),
            ({"kind": "strings", "list": ["a"]}, True),
            ({"kind": "strings", "list": [1]}, False),
        ),
        "island",
    ),
    DynamicSeed(
        "unstable-recursive",
        DIALECT_2020_12,
        {
            "$defs": {
                "tree": {
                    "$id": "tree",
                    "title": "tree",
                    "type": "object",
                    "$defs": {"node": {"$dynamicAnchor": "node"}},
                    "properties": {"child": {"$dynamicRef": "#node"}},
                },
                "strict": {
                    "$id": "strict",
                    "$defs": {
                        "node": {
                            "$dynamicAnchor": "node",
                            "title": "node-title",
                            "$ref": "tree",
                            "required": ["child"],
                        }
                    },
                    "$ref": "tree",
                },
                "loose": {
                    "$id": "loose",
                    "$defs": {
                        "node": {
                            "$dynamicAnchor": "node",
                            "title": "node-title",
                            "$ref": "tree",
                        }
                    },
                    "$ref": "tree",
                },
            },
            "anyOf": [{"$ref": "#/$defs/strict"}, {"$ref": "#/$defs/loose"}],
        },
        (({}, True), ({"child": {}}, True), ({"child": 1}, False)),
        "island",
    ),
    DynamicSeed(
        "recursive-stable",
        DIALECT_2019_09,
        {
            "$recursiveAnchor": True,
            "type": "object",
            "properties": {"child": {"$recursiveRef": "#"}},
        },
        (({}, True), ({"child": {}}, True), ({"child": 1}, False)),
        "static",
    ),
    DynamicSeed(
        "recursive-unstable",
        DIALECT_2019_09,
        {
            "$defs": {
                "tree": {
                    "$id": "tree",
                    "$recursiveAnchor": True,
                    "type": "object",
                    "properties": {"child": {"$recursiveRef": "#"}},
                },
                "strict": {
                    "$id": "strict",
                    "$recursiveAnchor": True,
                    "$ref": "tree",
                    "required": ["child"],
                },
                "loose": {"$id": "loose", "$recursiveAnchor": True, "$ref": "tree"},
            },
            "anyOf": [{"$ref": "#/$defs/strict"}, {"$ref": "#/$defs/loose"}],
        },
        (({}, True), ({"child": {}}, True), ({"child": 1}, False)),
        "island",
    ),
)
