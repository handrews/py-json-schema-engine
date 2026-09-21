"""Output units, annotation selection, and the M1 document renderers (D5, D6)."""

import pytest

from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationsOption,
    AnnotationUnit,
    ErrorUnit,
    RenderInput,
    make_record_predicate,
    render_basic,
    render_flag,
    render_list,
    select_units,
)


def make_annotation(
    *,
    keyword: str = "title",
    vocabulary: str | None = "https://json-schema.org/vocab/meta-data",
    annotation: JsonValue = "A title",
    evaluation_path: str = "/title",
    schema_location: str = "https://example.com/s#/title",
    input_location: str = "",
) -> AnnotationUnit:
    unit: AnnotationUnit = {
        "evaluationPath": evaluation_path,
        "schemaLocation": schema_location,
        "inputLocation": input_location,
        "keyword": keyword,
        "annotation": annotation,
    }
    if vocabulary is not None:
        unit["vocabulary"] = vocabulary
    return unit


def make_error(
    *,
    evaluation_path: str = "/type",
    schema_location: str = "https://example.com/s#/type",
    input_location: str = "",
    error: str = "not a string",
) -> ErrorUnit:
    return {
        "evaluationPath": evaluation_path,
        "schemaLocation": schema_location,
        "inputLocation": input_location,
        "error": error,
    }


# --- make_record_predicate / select_units: selection semantics (D5) --------


def test_false_selection_records_and_selects_nothing():
    assert make_record_predicate(False) is None
    assert select_units([make_annotation()], False) == []


def test_true_selection_keeps_everything():
    predicate = make_record_predicate(True)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("anything", "urn:whatever") is True
    units = [
        make_annotation(keyword="title"),
        make_annotation(keyword="x-vendor", vocabulary=None),
    ]
    assert select_units(units, True) == units


def test_both_allow_lists_none_allows_everything():
    selection = AnnotationSelection()
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("description", "urn:example:vocab") is True


def test_keyword_allow_list_excludes_unlisted_keywords():
    selection = AnnotationSelection(keywords=frozenset({"title"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("description", None) is False


def test_vocabulary_allow_list_excludes_unlisted_vocabularies():
    selection = AnnotationSelection(vocabularies=frozenset({"urn:v1"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("anything", "urn:v1") is True
    assert predicate("anything", "urn:v2") is False
    # No vocabulary at all cannot match a vocabulary allow-list.
    assert predicate("anything", None) is False


def test_allow_lists_are_ored():
    selection = AnnotationSelection(
        keywords=frozenset({"title"}), vocabularies=frozenset({"urn:v1"})
    )
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", "urn:other") is True  # matches keywords
    assert predicate("other", "urn:v1") is True  # matches vocabularies
    assert predicate("other", "urn:other") is False


def test_deny_lists_subtract_after_allow():
    selection = AnnotationSelection(exclude_keywords=frozenset({"description"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True
    assert predicate("description", None) is False


def test_deny_vocabulary_subtracts_after_allow():
    selection = AnnotationSelection(exclude_vocabularies=frozenset({"urn:v1"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("anything", "urn:v1") is False
    assert predicate("anything", "urn:v2") is True


def test_allow_and_deny_combine_deny_wins():
    # A keyword can be both allow-listed and deny-listed; the deny list is
    # subtracted after, so it wins.
    selection = AnnotationSelection(
        keywords=frozenset({"title"}), exclude_keywords=frozenset({"title"})
    )
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is False


def test_keep_does_not_affect_make_record_predicate():
    # D5: keep runs only at render time; the record-time predicate must
    # record the superset keep might narrow, never elide on its behalf.
    selection = AnnotationSelection(keep=lambda unit: False)
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("title", None) is True


def test_select_units_applies_keep_last():
    selection = AnnotationSelection(keep=lambda unit: unit["annotation"] != "hidden")
    units = [
        make_annotation(keyword="title", annotation="shown"),
        make_annotation(keyword="description", annotation="hidden"),
    ]
    selected = select_units(units, selection)
    assert [u["keyword"] for u in selected] == ["title"]


def test_select_units_applies_allow_then_keep():
    selection = AnnotationSelection(
        keywords=frozenset({"title", "description"}),
        keep=lambda unit: unit["keyword"] == "title",
    )
    units = [
        make_annotation(keyword="title"),
        make_annotation(keyword="description"),
        make_annotation(keyword="x-vendor", vocabulary=None),
    ]
    selected = select_units(units, selection)
    assert [u["keyword"] for u in selected] == ["title"]


def test_predicate_ignores_vocabulary_none_against_deny_vocab():
    # A `None` vocabulary_uri can never match a deny-list of vocabularies.
    selection = AnnotationSelection(exclude_vocabularies=frozenset({"urn:v1"}))
    predicate = make_record_predicate(selection)
    assert predicate is not None
    assert predicate("x-vendor", None) is True


# --- render_flag -------------------------------------------------------


def test_render_flag_document():
    assert render_flag(True) == {"valid": True}
    assert render_flag(False) == {"valid": False}


# --- render_basic (IETF draft-03 §13.4.2) ----------------------------------

ROOT = "https://example.com/s#"


def _root(valid: bool) -> dict[str, object]:
    return {
        "valid": valid,
        "keywordLocation": "",
        "absoluteKeywordLocation": ROOT,
        "instanceLocation": "",
    }


def test_render_basic_valid_with_no_annotations_omits_both_keys():
    render_input = RenderInput(
        valid=True, errors=[], annotations=[], root_location=ROOT
    )
    assert render_basic(render_input) == _root(True)


def test_render_basic_valid_with_annotations_uses_draft_names():
    annotation = make_annotation(
        evaluation_path="/properties/x/title", input_location="/x"
    )
    render_input = RenderInput(
        valid=True, errors=[], annotations=[annotation], root_location=ROOT
    )
    assert render_basic(render_input) == {
        **_root(True),
        "annotations": [
            {
                "keywordLocation": "/properties/x/title",
                "absoluteKeywordLocation": "https://example.com/s#/title",
                "instanceLocation": "/x",
                "annotation": "A title",
            }
        ],
    }


def test_render_basic_invalid_always_carries_errors_key():
    error = make_error()
    render_input = RenderInput(
        valid=False, errors=[error], annotations=[], root_location=ROOT
    )
    assert render_basic(render_input) == {
        **_root(False),
        "errors": [
            {
                "keywordLocation": "/type",
                "absoluteKeywordLocation": "https://example.com/s#/type",
                "instanceLocation": "",
                "error": "not a string",
            }
        ],
    }


def test_render_basic_is_mutually_exclusive():
    error = make_error()
    annotation = make_annotation()
    valid_input = RenderInput(
        valid=True, errors=[error], annotations=[annotation], root_location=ROOT
    )
    assert "errors" not in render_basic(valid_input)
    invalid_input = RenderInput(
        valid=False, errors=[error], annotations=[annotation], root_location=ROOT
    )
    assert "annotations" not in render_basic(invalid_input)


# --- render_list (machines-oriented proposal, grouped by application) -----


def test_render_list_empty():
    render_input = RenderInput(
        valid=True, errors=[], annotations=[], root_location=ROOT
    )
    assert render_list(render_input) == {"valid": True, "details": []}


def test_render_list_groups_annotations_by_application():
    a1 = make_annotation(keyword="title", evaluation_path="/title", annotation="T")
    a2 = make_annotation(
        keyword="readOnly",
        evaluation_path="/properties/id/readOnly",
        schema_location="https://example.com/s#/properties/id/readOnly",
        input_location="/id",
        annotation=True,
    )
    a3 = make_annotation(
        keyword="title",
        evaluation_path="/properties/id/title",
        schema_location="https://example.com/s#/properties/id/title",
        input_location="/id",
        annotation="Identifier",
    )
    render_input = RenderInput(
        valid=True, errors=[], annotations=[a1, a2, a3], root_location=ROOT
    )
    assert render_list(render_input) == {
        "valid": True,
        "details": [
            {
                "valid": True,
                "evaluationPath": "",
                "schemaLocation": "https://example.com/s#",
                "instanceLocation": "",
                "annotations": {"title": "T"},
            },
            {
                "valid": True,
                "evaluationPath": "/properties/id",
                "schemaLocation": "https://example.com/s#/properties/id",
                "instanceLocation": "/id",
                "annotations": {"readOnly": True, "title": "Identifier"},
            },
        ],
    }


def test_render_list_orders_parent_before_children_and_joins_messages():
    # Encounter order puts the branches' errors before anyOf's own error;
    # the document puts the parent application first, then the branches.
    errors = [
        make_error(
            evaluation_path="/anyOf/0/required",
            schema_location=ROOT + "/anyOf/0/required",
            error="missing 'a'",
        ),
        make_error(
            evaluation_path="/anyOf/0/required",
            schema_location=ROOT + "/anyOf/0/required",
            error="missing 'b'",
        ),
        make_error(
            evaluation_path="/anyOf/1/type",
            schema_location=ROOT + "/anyOf/1/type",
            error="not a string",
        ),
        make_error(
            evaluation_path="/anyOf", schema_location=ROOT + "/anyOf", error="no branch"
        ),
    ]
    render_input = RenderInput(
        valid=False,
        errors=errors,
        annotations=[],
        root_location=ROOT,
        error_keywords=["required", "required", "type", "anyOf"],
    )
    document = render_list(render_input)
    assert [u["evaluationPath"] for u in document["details"]] == [
        "",
        "/anyOf/0",
        "/anyOf/1",
    ]
    assert document["details"][0].get("errors") == {"anyOf": "no branch"}
    assert document["details"][1].get("errors") == {
        "required": "missing 'a'; missing 'b'"
    }
    assert all(u["valid"] is False for u in document["details"])


def test_render_list_keys_false_schema_error_under_empty_name():
    error = make_error(
        evaluation_path="/properties/x",
        schema_location=ROOT + "/properties/x",
        input_location="/x",
        error="schema is false",
    )
    render_input = RenderInput(
        valid=False,
        errors=[error],
        annotations=[],
        root_location=ROOT,
        error_keywords=[None],
    )
    assert render_list(render_input)["details"] == [
        {
            "valid": False,
            "evaluationPath": "/properties/x",
            "schemaLocation": ROOT + "/properties/x",
            "instanceLocation": "/x",
            "errors": {"": "schema is false"},
        }
    ]


def test_render_input_tree_defaults_to_none():
    render_input = RenderInput(
        valid=True, errors=[], annotations=[], root_location="https://example.com/s#"
    )
    assert render_input.tree is None


@pytest.mark.parametrize("selection", [False, True, AnnotationSelection()])
def test_annotations_option_accepts_bool_or_selection(
    selection: AnnotationsOption,
) -> None:
    # Type-level smoke test: every AnnotationsOption member is accepted.
    make_record_predicate(selection)
