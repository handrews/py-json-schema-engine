"""Record rendering (records.py), output demand, and result assembly (D5, D6, D13)."""

from collections.abc import Sequence

import pytest

from json_schema_engine.core.channel import AnnotationRecord, ErrorRecord, PathNode
from json_schema_engine.core.cursor import child_cursor, root_cursor
from json_schema_engine.core.errors import OutputOptionsError
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationUnit,
    ErrorUnit,
    RenderInput,
)
from json_schema_engine.core.records import (
    render_annotation,
    render_error,
    render_selected,
)
from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.result import (
    OutputDemand,
    OutputFormat,
    Result,
    assemble_result,
    resolve_output_demand,
)

SCHEMA_REF = SchemaRef({"type": "string"}, "https://example.com/s", "/properties/name")
FALSE_SCHEMA_REF = SchemaRef(False, "https://example.com/s", "/$defs/never")


# --- records.py: render_error / render_annotation / render_selected ----


def test_render_error_basic_fields() -> None:
    record = ErrorRecord(
        behavior_id="https://json-schema.org/keyword/type",
        keyword_name="type",
        vocabulary_uri="https://json-schema.org/vocab/validation",
        schema_ref=SCHEMA_REF,
        path_node=PathNode(None, "properties"),
        cursor=child_cursor(root_cursor({"name": 1}), "name", 1),
        message="value is not a string",
    )
    unit = render_error(record, error_params=False)
    assert unit == {
        "evaluationPath": "/properties/type",
        "schemaLocation": "https://example.com/s#/properties/name/type",
        "inputLocation": "/name",
        "error": "value is not a string",
    }
    assert "keyword" not in unit
    assert "vocabulary" not in unit
    assert "params" not in unit


def test_render_error_with_error_params_adds_keyword_vocabulary_and_params() -> None:
    record = ErrorRecord(
        behavior_id="https://json-schema.org/keyword/maxLength",
        keyword_name="maxLength",
        vocabulary_uri="https://json-schema.org/vocab/validation",
        schema_ref=SCHEMA_REF,
        path_node=None,
        cursor=root_cursor("abcd"),
        message="string is longer than 3 characters",
        params={"limit": 3, "length": 4},
    )
    unit = render_error(record, error_params=True)
    assert unit.get("keyword") == "maxLength"
    assert unit.get("vocabulary") == "https://json-schema.org/vocab/validation"
    assert unit.get("params") == {"limit": 3, "length": 4}


def test_render_error_with_error_params_defaults_missing_params_to_empty_dict() -> None:
    record = ErrorRecord(
        behavior_id="https://json-schema.org/keyword/not",
        keyword_name="not",
        vocabulary_uri="https://json-schema.org/vocab/applicator",
        schema_ref=SCHEMA_REF,
        path_node=None,
        cursor=root_cursor(1),
        message="matched the 'not' subschema",
    )
    unit = render_error(record, error_params=True)
    assert unit.get("params") == {}


def test_render_error_false_schema_omits_keyword_vocab_with_error_params() -> None:
    record = ErrorRecord(
        behavior_id=None,
        keyword_name=None,
        vocabulary_uri=None,
        schema_ref=FALSE_SCHEMA_REF,
        path_node=PathNode(None, "$defs"),
        cursor=root_cursor(1),
        message="schema is false",
    )
    unit = render_error(record, error_params=True)
    assert unit["evaluationPath"] == "/$defs"
    assert unit["schemaLocation"] == "https://example.com/s#/$defs/never"
    assert "keyword" not in unit
    assert "vocabulary" not in unit
    assert unit.get("params") == {}


def test_render_annotation_basic_fields() -> None:
    record = AnnotationRecord(
        behavior_id="https://json-schema.org/keyword/title",
        keyword_name="title",
        vocabulary_uri="https://json-schema.org/vocab/meta-data",
        schema_ref=SCHEMA_REF,
        path_node=PathNode(None, "properties"),
        cursor=root_cursor({"name": "Ada"}),
        value="A name",
    )
    unit = render_annotation(record)
    assert unit == {
        "evaluationPath": "/properties/title",
        "schemaLocation": "https://example.com/s#/properties/name/title",
        "inputLocation": "",
        "keyword": "title",
        "annotation": "A name",
        "vocabulary": "https://json-schema.org/vocab/meta-data",
    }


def test_render_annotation_unknown_keyword_has_no_vocabulary_key() -> None:
    record = AnnotationRecord(
        behavior_id="x-vendor",
        keyword_name="x-vendor",
        vocabulary_uri=None,
        schema_ref=SCHEMA_REF,
        path_node=None,
        cursor=root_cursor(1),
        value=42,
    )
    unit = render_annotation(record)
    assert "vocabulary" not in unit
    assert unit["schemaLocation"] == "https://example.com/s#/properties/name/x-vendor"


def _annotation(
    keyword: str, vocabulary: str | None, value: JsonValue
) -> AnnotationRecord:
    return AnnotationRecord(
        behavior_id=f"id:{keyword}",
        keyword_name=keyword,
        vocabulary_uri=vocabulary,
        schema_ref=SCHEMA_REF,
        path_node=None,
        cursor=root_cursor(1),
        value=value,
    )


def test_render_selected_false_selection_yields_nothing() -> None:
    records = [_annotation("title", "urn:v1", "T")]
    assert render_selected(records, False) == []


def test_render_selected_applies_allow_list_and_keep() -> None:
    records = [
        _annotation("title", "urn:v1", "shown"),
        _annotation("description", "urn:v1", "hidden"),
        _annotation("x-vendor", None, "unrelated"),
    ]
    selection = AnnotationSelection(
        keywords=frozenset({"title", "description"}),
        keep=lambda unit: unit["annotation"] == "shown",
    )
    units = render_selected(records, selection)
    assert [u["keyword"] for u in units] == ["title"]
    assert units[0]["annotation"] == "shown"


def test_render_selected_true_renders_every_record_once() -> None:
    records = [_annotation("title", "urn:v1", "T"), _annotation("x-vendor", None, 1)]
    units = render_selected(records, True)
    assert [u["keyword"] for u in units] == ["title", "x-vendor"]
    assert "vocabulary" not in units[1]


# --- resolve_output_demand: the option-combination matrix (D6) ---------


def test_default_demand_is_flag_with_nothing_recorded() -> None:
    demand = resolve_output_demand()
    assert demand == OutputDemand(
        format=OutputFormat.FLAG,
        annotations=None,
        error_params=False,
        verbose=False,
        tracing=False,
    )


def test_basic_demand_builds_a_recording_predicate() -> None:
    demand = resolve_output_demand(output="basic", annotations=True)
    assert demand.format is OutputFormat.BASIC
    assert demand.annotations is not None
    assert demand.annotations("anything", None) is True


def test_list_demand_default_annotations_records_nothing() -> None:
    demand = resolve_output_demand(output="list")
    assert demand.format is OutputFormat.LIST
    assert demand.annotations is None


def test_unknown_format_string_raises() -> None:
    with pytest.raises(OutputOptionsError, match="unknown output format"):
        resolve_output_demand(output="bogus")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"annotations": True},
        {"error_params": True},
        {"verbose": True},
        {"trace": True},
        {"positions": True},
    ],
)
def test_flag_rejects_every_control(kwargs: dict[str, bool]) -> None:
    with pytest.raises(OutputOptionsError, match='output "flag"'):
        resolve_output_demand(output="flag", **kwargs)


def test_verbose_on_basic_is_rejected_as_never_supported_not_deferred() -> None:
    with pytest.raises(OutputOptionsError) as excinfo:
        resolve_output_demand(output="basic", verbose=True)
    message = str(excinfo.value)
    assert "not implemented in this milestone" not in message
    assert "basic" in message


def test_verbose_on_list_is_rejected_as_deferred_to_m5() -> None:
    with pytest.raises(OutputOptionsError, match="not implemented in this milestone"):
        resolve_output_demand(output="list", verbose=True)


@pytest.mark.parametrize("output_format", ["detailed", "verbose", "hierarchical"])
def test_m5_formats_are_rejected_as_deferred(output_format: str) -> None:
    with pytest.raises(OutputOptionsError, match="not implemented in this milestone"):
        resolve_output_demand(output=output_format)


@pytest.mark.parametrize("output_format", ["basic", "list"])
def test_trace_is_rejected_as_deferred_regardless_of_format(output_format: str) -> None:
    with pytest.raises(OutputOptionsError, match="not implemented in this milestone"):
        resolve_output_demand(output=output_format, trace=True)


@pytest.mark.parametrize("output_format", ["basic", "list"])
def test_positions_is_rejected_as_deferred_regardless_of_format(
    output_format: str,
) -> None:
    with pytest.raises(OutputOptionsError, match="not implemented in this milestone"):
        resolve_output_demand(output=output_format, positions=True)


def test_output_format_enum_accepts_an_existing_output_format_value() -> None:
    demand = resolve_output_demand(output=OutputFormat.BASIC)
    assert demand.format is OutputFormat.BASIC


# --- assemble_result: presence rules (D6) -------------------------------


def _render_input(
    *,
    valid: bool,
    errors: Sequence[ErrorUnit] = (),
    annotations: Sequence[AnnotationUnit] = (),
) -> RenderInput:
    return RenderInput(
        valid=valid,
        errors=list(errors),
        annotations=list(annotations),
        root_location="https://example.com/s#",
    )


def test_assemble_result_flag_carries_nothing() -> None:
    demand = resolve_output_demand()
    result = assemble_result(demand, _render_input(valid=True), False)
    assert result == Result(True, None, None, None)
    result = assemble_result(demand, _render_input(valid=False), False)
    assert result == Result(False, None, None, None)


def test_assemble_result_basic_invalid_has_errors_no_annotations() -> None:
    error = render_error(
        ErrorRecord(
            behavior_id="id",
            keyword_name="type",
            vocabulary_uri=None,
            schema_ref=SCHEMA_REF,
            path_node=None,
            cursor=root_cursor(1),
            message="nope",
        ),
        error_params=False,
    )
    demand = resolve_output_demand(output="basic", annotations=True)
    result = assemble_result(demand, _render_input(valid=False, errors=[error]), True)
    assert result.valid is False
    assert result.errors == [error]
    assert result.annotations is None
    assert result.output_document is not None
    assert result.output_document["valid"] is False
    assert "errors" in result.output_document


def test_assemble_result_basic_valid_with_selection_has_annotations_no_errors() -> None:
    annotation = render_annotation(_annotation("title", "urn:v1", "T"))
    demand = resolve_output_demand(output="basic", annotations=True)
    result = assemble_result(
        demand, _render_input(valid=True, annotations=[annotation]), True
    )
    assert result.valid is True
    assert result.errors is None
    assert result.annotations == [annotation]
    assert result.output_document is not None
    assert "annotations" in result.output_document


def test_assemble_result_basic_valid_without_selection_has_neither() -> None:
    demand = resolve_output_demand(output="basic")
    result = assemble_result(demand, _render_input(valid=True), False)
    assert result.errors is None
    assert result.annotations is None
    assert result.output_document is not None
    assert "annotations" not in result.output_document


def test_assemble_result_selection_truthy_but_empty_result_still_present() -> None:
    # A selection was requested (selection is not False) but nothing
    # survived it: annotations is `[]`, not `None` (D6: presence tracks
    # whether selection was requested, not whether anything matched).
    demand = resolve_output_demand(output="basic", annotations=True)
    selection = AnnotationSelection(keep=lambda unit: False)
    annotation = render_annotation(_annotation("title", "urn:v1", "T"))
    result = assemble_result(
        demand, _render_input(valid=True, annotations=[annotation]), selection
    )
    assert result.annotations == []
    assert result.output_document is not None
    assert "annotations" not in result.output_document


def test_assemble_result_list_document_mirrors_flat_surface() -> None:
    error = render_error(
        ErrorRecord(
            behavior_id="id",
            keyword_name="type",
            vocabulary_uri=None,
            schema_ref=SCHEMA_REF,
            path_node=None,
            cursor=root_cursor(1),
            message="nope",
        ),
        error_params=False,
    )
    demand = resolve_output_demand(output="list", annotations=True)
    result = assemble_result(demand, _render_input(valid=False, errors=[error]), True)
    assert result.output_document is not None
    assert result.output_document.get("details") is not None


def test_assemble_result_applies_keep_that_make_record_predicate_ignored() -> None:
    # The annotation was "recorded" (it is present in render_input, as if
    # make_record_predicate had allowed it); assemble_result must still
    # apply `keep` at render time.
    annotation = render_annotation(_annotation("title", "urn:v1", "hide me"))
    selection = AnnotationSelection(keep=lambda unit: unit["annotation"] != "hide me")
    demand = resolve_output_demand(output="basic", annotations=True)
    result = assemble_result(
        demand, _render_input(valid=True, annotations=[annotation]), selection
    )
    assert result.annotations == []
    assert result.output_document is not None
    assert "annotations" not in result.output_document
