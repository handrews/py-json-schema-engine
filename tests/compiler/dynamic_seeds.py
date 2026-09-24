# Dynamic-reference seed corpus (M9, after the TS engine's ADR 0004): the
# shapes plan-time resolution must get right, each pinned to a
# classification. Stable shapes compile with no interpreted unit; shapes
# whose site's target differs by path are specialized per dynamic context
# under the default cap, and keep an island under `max_dynamic_winners=0`
# (so the trampoline stays covered). Shared by the dynamic-resolution tests
# and the differential fuzz.

from dataclasses import dataclass
from typing import Literal

from json_schema_engine.compiler.plan import DEFAULT_MAX_DYNAMIC_WINNERS
from json_schema_engine.core import DIALECT_2019_09, DIALECT_2020_12, JsonValue


@dataclass(frozen=True, slots=True)
class DynamicSeed:
    key: str
    dialect: str
    schema: JsonValue
    tests: tuple[tuple[JsonValue, bool], ...]
    classification: Literal["static", "island", "specialized"]
    # The planner's specialization cap the seed is pinned under.
    max_dynamic_winners: int = DEFAULT_MAX_DYNAMIC_WINNERS


# Two declarers of `item` reach `genericList`'s site through different paths.
GENERIC_LIST: JsonValue = {
    "$defs": {
        "genericList": {
            "$id": "genericList",
            "$defs": {"defaultItem": {"$dynamicAnchor": "item", "type": "null"}},
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
}
GENERIC_LIST_TESTS: tuple[tuple[JsonValue, bool], ...] = (
    ({"kind": "numbers", "list": [1, 2]}, True),
    ({"kind": "numbers", "list": ["a"]}, False),
    ({"kind": "strings", "list": ["a"]}, True),
    ({"kind": "strings", "list": [1]}, False),
)

# A recursive base whose anchor sits on a `$defs` entry, extended twice.
TREE_NODE: JsonValue = {
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
}
TREE_NODE_TESTS: tuple[tuple[JsonValue, bool], ...] = (
    ({}, True),
    ({"child": {}}, True),
    ({"child": 1}, False),
)

# The 2019-09 shape of the same tree.
RECURSIVE_TREE: JsonValue = {
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
}

# The extensible recursive type: a base `tree` re-declared by each
# extension, both of which close their properties. Every node below the
# first must rebind to the extension the path entered.
EXTENSIBLE_TREE: JsonValue = {
    "$defs": {
        "tree": {
            "$id": "tree",
            "$dynamicAnchor": "tree",
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "children": {"type": "array", "items": {"$dynamicRef": "#tree"}},
            },
        },
        "taxonomyTree": {
            "$id": "taxonomyTree",
            "$dynamicAnchor": "tree",
            "$ref": "tree",
            "properties": {"rank": {"type": "string"}},
            "required": ["rank"],
            "unevaluatedProperties": False,
        },
        "phylogenyTree": {
            "$id": "phylogenyTree",
            "$dynamicAnchor": "tree",
            "$ref": "tree",
            "properties": {"support": {"type": "number"}},
            "unevaluatedProperties": False,
        },
    },
    "properties": {
        "taxonomy": {"$ref": "taxonomyTree"},
        "phylogeny": {"$ref": "phylogenyTree"},
    },
}
EXTENSIBLE_TREE_RECURSIVE: JsonValue = {
    "$defs": {
        "tree": {
            "$id": "tree",
            "$recursiveAnchor": True,
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "children": {"type": "array", "items": {"$recursiveRef": "#"}},
            },
        },
        "taxonomyTree": {
            "$id": "taxonomyTree",
            "$recursiveAnchor": True,
            "$ref": "tree",
            "properties": {"rank": {"type": "string"}},
            "required": ["rank"],
            "unevaluatedProperties": False,
        },
        "phylogenyTree": {
            "$id": "phylogenyTree",
            "$recursiveAnchor": True,
            "$ref": "tree",
            "properties": {"support": {"type": "number"}},
            "unevaluatedProperties": False,
        },
    },
    "properties": {
        "taxonomy": {"$ref": "taxonomyTree"},
        "phylogeny": {"$ref": "phylogenyTree"},
    },
}
EXTENSIBLE_TREE_TESTS: tuple[tuple[JsonValue, bool], ...] = (
    (
        {
            "taxonomy": {
                "rank": "Class",
                "children": [
                    {"rank": "Order", "children": [{"rank": "Family", "name": "f"}]}
                ],
            }
        },
        True,
    ),
    # A nested node must rebind to `taxonomyTree`, which requires `rank`.
    ({"taxonomy": {"rank": "Class", "children": [{"name": "x"}]}}, False),
    # ... and closes its properties against the other extension's field.
    (
        {"taxonomy": {"rank": "Class", "children": [{"rank": "Order", "support": 1}]}},
        False,
    ),
    (
        {
            "phylogeny": {
                "support": 0.9,
                "children": [{"support": 0.5, "children": [{"name": "leaf"}]}],
            }
        },
        True,
    ),
    ({"phylogeny": {"children": [{"rank": "Order"}]}}, False),
    ({"phylogeny": {"children": [{"support": "high"}]}}, False),
    ({"taxonomy": {"rank": "Class"}, "phylogeny": {"children": []}}, True),
)

# A site resolved in an early planning round gains a second winner only
# once `b`'s target is planned: `r2#/$defs/y` reaches `r1#/$defs/u` with
# `r2` already in scope. The plan must re-derive the decision.
STALE_DECISION: JsonValue = {
    "$defs": {
        "r1": {
            "$id": "r1",
            "$defs": {
                "u": {"$dynamicRef": "#x"},
                "x": {"$dynamicAnchor": "x", "type": "number"},
            },
        },
        "r2": {
            "$id": "r2",
            "$defs": {
                "y": {"$dynamicAnchor": "y", "$ref": "r1#/$defs/u"},
                "x": {"$dynamicAnchor": "x", "type": "string"},
            },
        },
    },
    "properties": {"a": {"$ref": "r1#/$defs/u"}, "b": {"$dynamicRef": "r2#y"}},
}
STALE_DECISION_TESTS: tuple[tuple[JsonValue, bool], ...] = (
    ({"b": "s"}, True),
    ({"b": 1}, False),
    ({"a": 1}, True),
    ({"a": "s"}, False),
)


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
        GENERIC_LIST,
        GENERIC_LIST_TESTS,
        "island",
        max_dynamic_winners=0,
    ),
    DynamicSeed(
        "specialized-two-paths",
        DIALECT_2020_12,
        GENERIC_LIST,
        GENERIC_LIST_TESTS,
        "specialized",
    ),
    DynamicSeed(
        "unstable-recursive",
        DIALECT_2020_12,
        TREE_NODE,
        TREE_NODE_TESTS,
        "island",
        max_dynamic_winners=0,
    ),
    DynamicSeed(
        "specialized-recursive",
        DIALECT_2020_12,
        TREE_NODE,
        TREE_NODE_TESTS,
        "specialized",
    ),
    DynamicSeed(
        "extensible-tree",
        DIALECT_2020_12,
        EXTENSIBLE_TREE,
        EXTENSIBLE_TREE_TESTS,
        "specialized",
    ),
    DynamicSeed(
        "stale-decision",
        DIALECT_2020_12,
        STALE_DECISION,
        STALE_DECISION_TESTS,
        "specialized",
    ),
    DynamicSeed(
        "stale-decision-islanded",
        DIALECT_2020_12,
        STALE_DECISION,
        STALE_DECISION_TESTS,
        "island",
        max_dynamic_winners=0,
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
        RECURSIVE_TREE,
        TREE_NODE_TESTS,
        "island",
        max_dynamic_winners=0,
    ),
    DynamicSeed(
        "recursive-specialized",
        DIALECT_2019_09,
        RECURSIVE_TREE,
        TREE_NODE_TESTS,
        "specialized",
    ),
    DynamicSeed(
        "extensible-tree-recursive",
        DIALECT_2019_09,
        EXTENSIBLE_TREE_RECURSIVE,
        EXTENSIBLE_TREE_TESTS,
        "specialized",
    ),
)
