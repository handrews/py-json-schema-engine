# Channel semantics through the public API with the real M1 keywords
# (DESIGN.md §4, D5). The expectations are the TS engine's channel gate,
# carried over as behavior, not code; the evaluator-level gate in
# test_evaluator.py checks the same rules against a hand-written vocabulary.

from json_schema_engine.core import (
    AnnotationSelection,
    AnnotationsOption,
    JsonValue,
    Result,
    create_engine,
)

SCHEMA_URI = "https://channels.example/schema"


def run(
    schema: JsonValue,
    instance: JsonValue,
    *,
    annotations: AnnotationsOption = True,
    output: str = "list",
) -> Result:
    engine = create_engine()
    uri = engine.register_schema(schema, SCHEMA_URI)
    return engine.evaluate(uri, instance, output=output, annotations=annotations)


def tuples(result: Result) -> list[tuple[str, str, JsonValue]]:
    return [
        (a["evaluationPath"], a["inputLocation"], a["annotation"])
        for a in result.annotations or []
    ]


PROFILE: JsonValue = {
    "title": "User profile",
    "type": "object",
    "required": ["id"],
    "properties": {
        "id": {"type": "string", "title": "Identifier", "readOnly": True},
        "displayName": {"type": "string", "title": "Display name", "default": ""},
    },
    "$comment": "must never be collected",
}


def test_collects_annotations_with_evaluation_paths_on_success() -> None:
    result = run(PROFILE, {"id": "u1", "displayName": "Ada"})
    assert result.valid
    got = tuples(result)
    assert ("/properties/id/readOnly", "/id", True) in got
    assert ("/properties/id/title", "/id", "Identifier") in got
    assert ("/title", "", "User profile") in got
    # properties communicates matched names as dependency data, never as an
    # annotation (draft-03 Appendix D).
    assert not any(a["keyword"] == "properties" for a in result.annotations or [])


def test_no_annotations_when_the_schema_fails() -> None:
    result = run(PROFILE, {"displayName": "Ada"})
    assert not result.valid
    assert result.annotations is None
    assert result.errors is not None
    assert [e["evaluationPath"] for e in result.errors] == ["/required"]


def test_never_collects_comment() -> None:
    result = run(PROFILE, {"id": "u1"})
    assert not any(a["keyword"] == "$comment" for a in result.annotations or [])


def test_unknown_keywords_annotate() -> None:
    result = run({"x-vendor-hint": {"cache": True}}, 42)
    assert ("/x-vendor-hint", "", {"cache": True}) in tuples(result)


def test_failed_branch_annotations_dropped_successful_kept() -> None:
    schema: JsonValue = {
        "anyOf": [
            {"pattern": "^a", "title": "starts with a"},
            {"pattern": "^b", "title": "starts with b"},
        ]
    }
    result = run(schema, "abc")
    assert result.valid
    titles = [a for a in result.annotations or [] if a["keyword"] == "title"]
    assert [a["annotation"] for a in titles] == ["starts with a"]
    assert titles[0]["evaluationPath"] == "/anyOf/0/title"
    assert titles[0]["schemaLocation"] == f"{SCHEMA_URI}#/anyOf/0/title"


def test_failed_branch_does_not_mark_properties_evaluated() -> None:
    schema: JsonValue = {
        "anyOf": [
            {"properties": {"x": {"type": "string"}}, "required": ["x"]},
            {"properties": {"y": {"type": "number"}}, "required": ["missing"]},
        ],
        "unevaluatedProperties": False,
    }
    assert run(schema, {"x": "s", "y": 1}).valid is False
    assert run(schema, {"x": "s"}).valid is True


INSTANCE: JsonValue = {"id": "u1", "displayName": "Ada"}


def test_keyword_allow_list_does_not_change_validation() -> None:
    everything = run(PROFILE, INSTANCE)
    only = run(
        PROFILE,
        INSTANCE,
        annotations=AnnotationSelection(keywords=frozenset({"readOnly"})),
    )
    assert only.valid is everything.valid
    assert only.annotations is not None and everything.annotations is not None
    assert [a["keyword"] for a in only.annotations] == ["readOnly"]
    assert len(everything.annotations) > 1


def test_vocabulary_filter() -> None:
    meta = "https://json-schema.org/draft/2020-12/vocab/meta-data"
    result = run(
        PROFILE,
        INSTANCE,
        annotations=AnnotationSelection(vocabularies=frozenset({meta})),
    )
    assert result.annotations
    assert {a["keyword"] for a in result.annotations} <= {
        "title",
        "readOnly",
        "default",
    }


def test_keep_predicate_over_rendered_units() -> None:
    selection = AnnotationSelection(
        keep=lambda u: u["evaluationPath"].startswith("/properties/id/")
    )
    result = run(PROFILE, INSTANCE, annotations=selection)
    assert result.annotations
    assert all(a["inputLocation"] == "/id" for a in result.annotations)


def test_selection_does_not_starve_internal_consumers() -> None:
    schema: JsonValue = {
        "allOf": [{"properties": {"x": True}}],
        "unevaluatedProperties": False,
    }
    nothing = AnnotationSelection(keywords=frozenset())
    result = run(schema, {"x": 1}, annotations=nothing)
    assert result.valid
    assert result.annotations == []
    assert run(schema, {"x": 1, "y": 2}, annotations=nothing).valid is False


def test_basic_document_carries_root_location() -> None:
    result = run(PROFILE, {"id": "u1"}, output="basic")
    document = result.output_document
    assert document is not None
    assert document["valid"] is True
    assert document.get("absoluteKeywordLocation") == f"{SCHEMA_URI}#"
