# Output formats end to end (DESIGN.md D6): the golden documents — one
# schema/instance pair, invalid and valid, rendered into every format name at
# each supported level — plus the spec's own examples. The goldens are the
# regression contract, reviewed by hand against the spec text: `basic`,
# `detailed`, `verbose` per IETF draft-03 §13.4 (nested `errors`/
# `annotations` arrays, condensation, one node per keyword); `list`,
# `hierarchical` per the machines-oriented proposal (keyword-keyed maps,
# `details`), at the relevant level and, with `verbose=True`, the verbose
# level. The invalid instance rejects on `count`, which makes `/item`'s
# acceptance and every `title` annotation irrelevant (draft-03 §12.2):
# relevant-level documents omit them and prune the units left empty (§13.4);
# `verbose` shows them as `valid: true` nodes under the rejecting root, and
# the verbose level of `list`/`hierarchical` marks them `droppedAnnotations`.

import json
from pathlib import Path
from typing import Any, cast

import pytest

from json_schema_engine.core import (
    AnnotationUnit,
    Engine,
    ErrorUnit,
    JsonValue,
    create_engine,
)

GOLDENS_DIR = Path(__file__).parent / "goldens"


def golden(name: str) -> object:
    return json.loads((GOLDENS_DIR / f"{name}.json").read_text())


def as_json(value: object) -> object:
    """Round-trip through JSON: tuples vs lists and dict ordering do not count."""
    return json.loads(json.dumps(value))


GOLDEN_SCHEMA: JsonValue = {
    "$id": "https://golden.example/schema",
    "$defs": {
        "named": {
            "title": "a named thing",
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
    },
    "title": "root",
    "type": "object",
    "properties": {
        "item": {"$ref": "#/$defs/named"},
        "count": {"type": "integer"},
    },
}

INSTANCES: list[tuple[str, JsonValue, bool]] = [
    ("invalid", {"item": {"name": "widget"}, "count": "nope"}, False),
    ("valid", {"item": {"name": "widget"}, "count": 3}, True),
]

RENDERINGS: list[tuple[str, dict[str, Any]]] = [
    ("basic", {"output": "basic", "annotations": True}),
    ("detailed", {"output": "detailed", "annotations": True}),
    ("verbose", {"output": "verbose", "annotations": True}),
    ("list", {"output": "list", "annotations": True}),
    ("list-verbose", {"output": "list", "verbose": True, "annotations": True}),
    ("hierarchical", {"output": "hierarchical", "annotations": True}),
    (
        "hierarchical-verbose",
        {"output": "hierarchical", "verbose": True, "annotations": True},
    ),
]

META_DATA = "https://json-schema.org/draft/2020-12/vocab/meta-data"
TITLES: list[AnnotationUnit] = [
    {
        "evaluationPath": "/properties/item/$ref/title",
        "schemaLocation": "https://golden.example/schema#/$defs/named/title",
        "inputLocation": "/item",
        "keyword": "title",
        "annotation": "a named thing",
        "vocabulary": META_DATA,
    },
    {
        "evaluationPath": "/title",
        "schemaLocation": "https://golden.example/schema#/title",
        "inputLocation": "",
        "keyword": "title",
        "annotation": "root",
        "vocabulary": META_DATA,
    },
]
COUNT_ERROR: ErrorUnit = {
    "evaluationPath": "/properties/count/type",
    "schemaLocation": "https://golden.example/schema#/properties/count/type",
    "inputLocation": "/count",
    "error": "expected integer",
}


def engine_for(schema: JsonValue, name: str = "schema") -> tuple[Engine, str]:
    engine = create_engine()
    uri = engine.register_schema(schema, f"https://output.example/{name}")
    return engine, uri


@pytest.mark.parametrize(
    ("name", "options"), RENDERINGS, ids=[r[0] for r in RENDERINGS]
)
@pytest.mark.parametrize(
    ("which", "instance", "valid"), INSTANCES, ids=["invalid", "valid"]
)
def test_golden(
    name: str, options: dict[str, Any], which: str, instance: JsonValue, valid: bool
) -> None:
    engine = create_engine()
    uri = engine.register_schema(GOLDEN_SCHEMA, "https://golden.example/schema")
    result = engine.evaluate(uri, instance, **options)
    assert result.valid is valid
    assert as_json(result.output_document) == golden(f"{name}.{which}")
    # The flat surface is the same on every format.
    verbose_level = name == "verbose" or options.get("verbose") is True
    assert result.errors == (None if valid else [COUNT_ERROR])
    assert result.annotations == (TITLES if valid else None)
    assert result.dropped_errors == ([] if verbose_level else None)
    assert result.dropped_annotations == (
        ([] if valid else TITLES) if verbose_level else None
    )


# --- list (machines-oriented proposal) ------------------------------------

LIST_SCHEMA: JsonValue = {
    "title": "root",
    "properties": {"name": {"title": "the name", "type": "string"}},
}


def test_list_wraps_reporting_units_under_valid_and_details_only() -> None:
    engine, uri = engine_for(LIST_SCHEMA)
    result = engine.evaluate(uri, {"name": 3}, output="list")
    document = cast(dict[str, Any], result.output_document)
    assert set(document) == {"valid", "details"}
    assert document["valid"] is False
    (unit,) = document["details"]
    assert unit["evaluationPath"] == "/properties/name"
    assert unit["schemaLocation"] == "https://output.example/schema#/properties/name"
    assert unit["instanceLocation"] == "/name"
    assert unit["valid"] is False
    assert "string" in unit["errors"]["type"]


def test_list_includes_the_root_unit_when_it_reports_something() -> None:
    engine, uri = engine_for(LIST_SCHEMA)
    result = engine.evaluate(uri, {"name": "x"}, output="list", annotations=True)
    details = cast(dict[str, Any], result.output_document)["details"]
    assert [u["evaluationPath"] for u in details] == ["", "/properties/name"]
    assert details[0]["annotations"] == {"title": "root"}
    assert "details" not in details[0]


def test_list_verbose_level_includes_every_unit_with_markers() -> None:
    engine, uri = engine_for(LIST_SCHEMA)
    result = engine.evaluate(
        uri, {"name": 3}, output="list", verbose=True, annotations=True
    )
    details = cast(dict[str, Any], result.output_document)["details"]
    assert [u["evaluationPath"] for u in details] == ["", "/properties/name"]
    assert details[0]["droppedAnnotations"] == {"title": "root"}
    assert details[1]["droppedAnnotations"] == {"title": "the name"}
    assert details[1]["errors"] == {"type": "expected string"}
    assert result.dropped_annotations is not None
    assert [a["annotation"] for a in result.dropped_annotations] == [
        "the name",
        "root",
    ]


# --- hierarchical (machines-oriented proposal) ----------------------------

H_SCHEMA: JsonValue = {
    "title": "root",
    "type": "object",
    "properties": {
        "name": {"title": "the name", "type": "string"},
        "size": {"type": "integer"},
    },
}


def run_h(instance: JsonValue, *, verbose: bool = False, annotations: bool = True):
    engine, uri = engine_for(H_SCHEMA, "h")
    result = engine.evaluate(
        uri, instance, output="hierarchical", verbose=verbose, annotations=annotations
    )
    return result, cast(dict[str, Any], result.output_document)


def test_hierarchical_nests_failing_branches() -> None:
    result, root = run_h({"name": 3})
    assert result.valid is False
    assert root["valid"] is False
    assert root["evaluationPath"] == ""
    assert root["instanceLocation"] == ""
    (name_unit,) = [d for d in root["details"] if d["instanceLocation"] == "/name"]
    assert name_unit["valid"] is False
    assert name_unit["evaluationPath"] == "/properties/name"
    assert name_unit["schemaLocation"] == "https://output.example/h#/properties/name"
    assert "string" in name_unit["errors"]["type"]


def test_hierarchical_prunes_contribution_free_units() -> None:
    result, root = run_h({"name": "x"})
    assert result.valid is True
    assert root["annotations"]["title"] == "root"
    (name_unit,) = [d for d in root["details"] if d["instanceLocation"] == "/name"]
    assert name_unit["annotations"]["title"] == "the name"
    # `size` is absent from the instance: its subschema is never applied.
    assert all(d["instanceLocation"] != "/size" for d in root["details"])
    # Annotations are a control: unselected, the valid tree is just the root.
    _, bare = run_h({"name": "x"}, annotations=False)
    assert bare == {
        "valid": True,
        "evaluationPath": "",
        "schemaLocation": "https://output.example/h#",
        "instanceLocation": "",
    }


def test_hierarchical_verbose_keeps_valid_annotation_free_units() -> None:
    engine, uri = engine_for({"properties": {"n": {"type": "integer"}}})
    terse = cast(
        dict[str, Any],
        engine.evaluate(uri, {"n": 1}, output="hierarchical").output_document,
    )
    verbose = cast(
        dict[str, Any],
        engine.evaluate(
            uri, {"n": 1}, output="hierarchical", verbose=True
        ).output_document,
    )
    assert "details" not in terse
    assert len(verbose["details"]) == 1
    assert verbose["details"][0]["valid"] is True


def test_hierarchical_reports_dropped_annotations_at_the_verbose_level_only() -> None:
    _, verbose = run_h({"name": 3}, verbose=True)
    (name_unit,) = [d for d in verbose["details"] if d["instanceLocation"] == "/name"]
    assert name_unit["droppedAnnotations"]["title"] == "the name"
    _, terse = run_h({"name": 3})
    (terse_unit,) = [d for d in terse["details"] if d["instanceLocation"] == "/name"]
    assert "droppedAnnotations" not in terse_unit


# --- detailed (IETF draft-03 §13.4.3) --------------------------------------

# The draft's own §13.4 example: the second point lacks "y", carries a
# disallowed "z", and the array is one item short.
POLYGON: JsonValue = {
    "$id": "https://example.com/polygon",
    "$defs": {
        "point": {
            "type": "object",
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            "additionalProperties": False,
            "required": ["x", "y"],
        }
    },
    "type": "array",
    "items": {"$ref": "#/$defs/point"},
    "minItems": 3,
}
POLYGON_INPUT: JsonValue = [{"x": 2.5, "y": 1.3}, {"x": 1, "z": 6.7}]


def test_detailed_condenses_the_polygon_example_node_for_node() -> None:
    engine = create_engine()
    uri = engine.register_schema(POLYGON, "https://example.com/polygon")
    result = engine.evaluate(uri, POLYGON_INPUT, output="detailed")
    document = cast(dict[str, Any], result.output_document)
    # `/items` and its second application collapse into the `$ref` node,
    # which keeps two children; the first item's application, `type`, and
    # `properties` have no relevant results and are removed. Applicator
    # keywords evaluate before validation keywords, so
    # `additionalProperties` precedes `required`.
    min_items = document["errors"][1]
    assert isinstance(min_items.pop("error"), str)
    assert document == {
        "valid": False,
        "keywordLocation": "",
        "absoluteKeywordLocation": "https://example.com/polygon#",
        "instanceLocation": "",
        "errors": [
            {
                "valid": False,
                "keywordLocation": "/items/$ref",
                "absoluteKeywordLocation": "https://example.com/polygon#/$defs/point",
                "instanceLocation": "/1",
                "errors": [
                    {
                        "valid": False,
                        "keywordLocation": "/items/$ref/additionalProperties",
                        "absoluteKeywordLocation": "https://example.com/polygon#/$defs/point/additionalProperties",
                        "instanceLocation": "/1/z",
                        "error": "schema is false",
                    },
                    {
                        "valid": False,
                        "keywordLocation": "/items/$ref/required",
                        "absoluteKeywordLocation": "https://example.com/polygon#/$defs/point/required",
                        "instanceLocation": "/1",
                        "error": "missing required property 'y'",
                    },
                ],
            },
            {
                "valid": False,
                "keywordLocation": "/minItems",
                "absoluteKeywordLocation": "https://example.com/polygon#/minItems",
                "instanceLocation": "",
            },
        ],
    }


def test_detailed_nests_annotation_leaves_under_successful_nodes() -> None:
    engine, uri = engine_for(
        {"title": "root", "properties": {"a": {"title": "leaf", "type": "integer"}}}
    )
    result = engine.evaluate(uri, {"a": 1}, output="detailed", annotations=True)
    assert result.output_document == {
        "valid": True,
        "keywordLocation": "",
        "absoluteKeywordLocation": "https://output.example/schema#",
        "instanceLocation": "",
        "annotations": [
            # `properties` → its one application → its one annotation leaf.
            {
                "valid": True,
                "keywordLocation": "/properties/a/title",
                "absoluteKeywordLocation": "https://output.example/schema#/properties/a/title",
                "instanceLocation": "/a",
                "annotation": "leaf",
            },
            {
                "valid": True,
                "keywordLocation": "/title",
                "absoluteKeywordLocation": "https://output.example/schema#/title",
                "instanceLocation": "",
                "annotation": "root",
            },
        ],
    }


def test_detailed_keeps_a_keyword_node_with_both_a_local_error_and_nested_results() -> (
    None
):
    engine, uri = engine_for({"contains": {"type": "string"}})
    result = engine.evaluate(uri, [1], output="detailed")
    contains = cast(dict[str, Any], result.output_document)["errors"][0]
    assert contains["keywordLocation"] == "/contains"
    assert isinstance(contains["error"], str)
    assert [e["keywordLocation"] for e in contains["errors"]] == ["/contains/type"]


# --- verbose (IETF draft-03 §13.4.4) ---------------------------------------


def test_verbose_renders_the_drafts_valid_prop_example_as_a_keyword_hierarchy() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {
            "$id": "https://example.com/polygon",
            "type": "object",
            "properties": {"validProp": True},
            "additionalProperties": False,
        },
        "https://example.com/polygon",
    )
    result = engine.evaluate(
        uri, {"validProp": 5, "disallowedProp": "value"}, output="verbose"
    )
    # `$id` is structural: no node. Applicators precede `type` here, and the
    # `validProp` application appears, which the draft's abbreviated example
    # omits.
    assert result.output_document == {
        "valid": False,
        "keywordLocation": "",
        "absoluteKeywordLocation": "https://example.com/polygon#",
        "instanceLocation": "",
        "errors": [
            {
                "valid": True,
                "keywordLocation": "/properties",
                "absoluteKeywordLocation": "https://example.com/polygon#/properties",
                "instanceLocation": "",
                "annotations": [
                    {
                        "valid": True,
                        "keywordLocation": "/properties/validProp",
                        "absoluteKeywordLocation": "https://example.com/polygon#/properties/validProp",
                        "instanceLocation": "/validProp",
                    }
                ],
            },
            {
                "valid": False,
                "keywordLocation": "/additionalProperties",
                "absoluteKeywordLocation": "https://example.com/polygon#/additionalProperties",
                "instanceLocation": "",
                "errors": [
                    {
                        "valid": False,
                        "keywordLocation": "/additionalProperties",
                        "absoluteKeywordLocation": "https://example.com/polygon#/additionalProperties",
                        "instanceLocation": "/disallowedProp",
                        "error": "schema is false",
                    }
                ],
            },
            {
                "valid": True,
                "keywordLocation": "/type",
                "absoluteKeywordLocation": "https://example.com/polygon#/type",
                "instanceLocation": "",
            },
        ],
    }


def test_verbose_includes_irrelevant_results_marked_only_by_valid() -> None:
    engine, uri = engine_for({"anyOf": [{"type": "string"}, {"type": "number"}]})
    result = engine.evaluate(uri, 5, output="verbose")
    any_of = cast(dict[str, Any], result.output_document)["annotations"][0]
    assert any_of["valid"] is True
    # A successful node nests its results under `annotations` (§13.3.5),
    # rejecting branches included.
    assert [(b["keywordLocation"], b["valid"]) for b in any_of["annotations"]] == [
        ("/anyOf/0", False),
        ("/anyOf/1", True),
    ]
    failed = any_of["annotations"][0]["errors"][0]
    assert failed["keywordLocation"] == "/anyOf/0/type"
    assert failed["valid"] is False
    assert isinstance(failed["error"], str)
    assert result.dropped_errors is not None
    assert [e["evaluationPath"] for e in result.dropped_errors] == ["/anyOf/0/type"]


def test_verbose_renders_unknown_keywords_as_annotation_nodes_when_selected() -> None:
    engine, uri = engine_for({"x-note": 1, "type": "integer"})
    result = engine.evaluate(uri, 1, output="verbose", annotations=True)
    nodes = cast(dict[str, Any], result.output_document)["annotations"]
    assert [(n["keywordLocation"], n.get("annotation")) for n in nodes] == [
        ("/type", None),
        ("/x-note", 1),
    ]
    assert "annotation" not in nodes[0]


# --- the flat surface across formats ---------------------------------------


def test_flat_surface_is_populated_on_every_non_flag_format() -> None:
    engine, uri = engine_for({"type": "string", "title": "t"})
    for output_format in ("basic", "detailed", "verbose", "list", "hierarchical"):
        result = engine.evaluate(uri, 1, output=output_format, annotations=True)
        assert result.errors is not None and len(result.errors) == 1
        assert result.annotations is None
        result = engine.evaluate(uri, "s", output=output_format, annotations=True)
        assert result.errors is None
        assert result.annotations is not None
        assert [a["keyword"] for a in result.annotations] == ["title"]
    assert engine.evaluate(uri, 1).errors is None


def test_positions_decorate_all_four_unit_lists() -> None:
    from json_schema_engine.test_kit.positions import parse_json_with_ranges

    text = '{"anyOf": [{"type": "string", "title": "a"}, {"minimum": 3, "title": "b"}]}'
    doc = parse_json_with_ranges(text, uri="https://output.example/pos")
    engine = create_engine()
    uri = engine.register_schema(doc.value, doc.uri, get_range=doc.get_range)
    result = engine.evaluate(
        uri, 1, output="list", verbose=True, annotations=True, positions=True
    )
    assert result.errors is not None and all("source" in e for e in result.errors)
    assert result.dropped_errors == []
    assert result.dropped_annotations is not None
    assert [a["annotation"] for a in result.dropped_annotations] == ["a", "b"]
    assert all("source" in a for a in result.dropped_annotations)
    # Documents never embed the decorated units.
    details = cast(dict[str, Any], result.output_document)["details"]
    assert all("source" not in json.dumps(u) for u in details)
