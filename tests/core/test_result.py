"""Record rendering (records.py), output demand, and result assembly (D5, D6, D13)."""

import pytest

from json_schema_engine.core.channel import AnnotationRecord, ErrorRecord, PathNode
from json_schema_engine.core.cursor import child_cursor, root_cursor
from json_schema_engine.core.errors import OutputOptionsError
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.output import (
    AnnotationSelection,
    ErrorUnit,
    RenderNode,
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
    UnitSets,
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
    selected = render_selected(records, False)
    assert selected.units == [] and selected.records == []


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
    selected = render_selected(records, selection)
    assert [u["keyword"] for u in selected.units] == ["title"]
    assert selected.units[0]["annotation"] == "shown"
    # The survivors' records stay paired with their units.
    assert selected.records == [records[0]]


def test_render_selected_true_renders_every_record_once() -> None:
    records = [_annotation("title", "urn:v1", "T"), _annotation("x-vendor", None, 1)]
    units = render_selected(records, True).units
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


@pytest.mark.parametrize("output_format", ["basic", "detailed"])
def test_verbose_true_is_rejected_for_relevant_level_formats(
    output_format: str,
) -> None:
    with pytest.raises(OutputOptionsError, match="relevant-level format"):
        resolve_output_demand(output=output_format, verbose=True)
    # `verbose=False` merely restates the default there.
    assert resolve_output_demand(output=output_format, verbose=False).verbose is False


def test_verbose_false_contradicts_the_verbose_format() -> None:
    with bare_raises("verbose level by definition"):
        resolve_output_demand(output="verbose", verbose=False)
    assert resolve_output_demand(output="verbose").verbose is True
    assert resolve_output_demand(output="verbose", verbose=True).verbose is True


def bare_raises(match: str) -> pytest.RaisesExc[OutputOptionsError]:
    return pytest.raises(OutputOptionsError, match=match)


@pytest.mark.parametrize(
    ("kwargs", "verbose", "tracing"),
    [
        ({"output": "basic"}, False, False),
        ({"output": "basic", "trace": True}, False, True),
        ({"output": "list"}, False, True),
        ({"output": "list", "verbose": True}, True, True),
        ({"output": "hierarchical"}, False, True),
        ({"output": "hierarchical", "verbose": True}, True, True),
        ({"output": "detailed"}, False, True),
        ({"output": "verbose"}, True, True),
        ({"output": "verbose", "trace": True, "positions": True}, True, True),
    ],
)
def test_admitted_combinations_set_verbose_and_tracing(
    kwargs: dict[str, object], verbose: bool, tracing: bool
) -> None:
    # The verbose level: the `verbose` format, or `verbose=True`. Tracing:
    # every format but `flag`, and `basic` only with `trace=True`.
    demand = resolve_output_demand(**kwargs)  # type: ignore[arg-type]
    assert demand.verbose is verbose
    assert demand.tracing is tracing


@pytest.mark.parametrize(
    "output_format", ["basic", "list", "hierarchical", "detailed", "verbose"]
)
def test_positions_and_error_params_are_admitted_for_record_carrying_formats(
    output_format: str,
) -> None:
    # D17/D13: decoration and params live on the flat units, so any format
    # that carries units admits them; `flag` still rejects them.
    demand = resolve_output_demand(
        output=output_format, positions=True, error_params=True
    )
    assert demand.format.value == output_format
    assert demand.error_params is True


def test_output_format_enum_accepts_an_existing_output_format_value() -> None:
    demand = resolve_output_demand(output=OutputFormat.BASIC)
    assert demand.format is OutputFormat.BASIC


# --- assemble_result: presence rules (D6) -------------------------------

ROOT_LOCATION = "https://example.com/s#"


def _root(
    valid: bool, *, errors: tuple[int, ...] = (), annotations: tuple[int, ...] = ()
) -> RenderNode:
    return RenderNode(
        evaluation_path="",
        schema_location=ROOT_LOCATION,
        input_location="",
        valid=valid,
        keywords=(),
        errors=errors,
        dropped_errors=(),
        annotations=annotations,
        dropped_annotations=(),
        children=(),
    )


def _error_unit() -> ErrorUnit:
    return render_error(
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


def test_assemble_result_flag_carries_nothing() -> None:
    demand = resolve_output_demand()
    result = assemble_result(demand, True, UnitSets(), None, ROOT_LOCATION, False)
    assert result == Result(True, None, None, None)
    result = assemble_result(demand, False, UnitSets(), None, ROOT_LOCATION, False)
    assert result == Result(False, None, None, None)


def test_assemble_result_basic_invalid_has_errors_no_annotations() -> None:
    error = _error_unit()
    demand = resolve_output_demand(output="basic", annotations=True)
    result = assemble_result(
        demand, False, UnitSets(errors=[error]), None, ROOT_LOCATION, False
    )
    assert result.valid is False
    assert result.errors == [error]
    assert result.annotations is None
    assert result.dropped_errors is None
    assert result.dropped_annotations is None
    assert result.trace is None
    assert result.output_document is not None
    assert result.output_document["valid"] is False
    assert "errors" in result.output_document


def test_assemble_result_basic_valid_with_selection_has_annotations_no_errors() -> None:
    annotation = render_annotation(_annotation("title", "urn:v1", "T"))
    demand = resolve_output_demand(output="basic", annotations=True)
    result = assemble_result(
        demand, True, UnitSets(annotations=[annotation]), None, ROOT_LOCATION, False
    )
    assert result.valid is True
    assert result.errors is None
    assert result.annotations == [annotation]
    assert result.output_document is not None
    assert "annotations" in result.output_document


def test_assemble_result_basic_valid_without_selection_has_neither() -> None:
    demand = resolve_output_demand(output="basic")
    result = assemble_result(demand, True, UnitSets(), None, ROOT_LOCATION, False)
    assert result.errors is None
    assert result.annotations is None
    assert result.output_document is not None
    assert "annotations" not in result.output_document


def test_assemble_result_selection_requested_but_empty_is_still_present() -> None:
    # A selection was requested but nothing survived it: annotations is
    # `[]`, not `None` (D6: presence tracks whether selection was requested,
    # not whether anything matched).
    demand = resolve_output_demand(output="basic", annotations=True)
    result = assemble_result(demand, True, UnitSets(), None, ROOT_LOCATION, False)
    assert result.annotations == []
    assert result.output_document is not None
    assert "annotations" not in result.output_document


def test_assemble_result_verbose_level_exposes_the_dropped_lists() -> None:
    error = _error_unit()
    annotation = render_annotation(_annotation("title", "urn:v1", "T"))
    units = UnitSets(dropped_errors=[error], dropped_annotations=[annotation])
    demand = resolve_output_demand(output="list", verbose=True, annotations=True)
    result = assemble_result(demand, True, units, _root(True), ROOT_LOCATION, False)
    assert result.dropped_errors == [error]
    assert result.dropped_annotations == [annotation]
    # Without a selection the dropped annotations are absent, like the
    # relevant ones.
    demand = resolve_output_demand(output="list", verbose=True)
    result = assemble_result(demand, True, units, _root(True), ROOT_LOCATION, False)
    assert result.dropped_errors == [error]
    assert result.dropped_annotations is None
    assert result.annotations is None
    # The relevant level never exposes them.
    demand = resolve_output_demand(output="list", annotations=True)
    result = assemble_result(demand, True, units, _root(True), ROOT_LOCATION, False)
    assert result.dropped_errors is None
    assert result.dropped_annotations is None


def test_assemble_result_renders_the_tree_formats_from_the_root() -> None:
    error = _error_unit()
    units = UnitSets(errors=[error])
    root = _root(False, errors=(0,))
    for output_format in ("list", "hierarchical", "detailed", "verbose"):
        demand = resolve_output_demand(output=output_format)
        result = assemble_result(demand, False, units, root, ROOT_LOCATION, False)
        assert result.output_document is not None
        assert result.output_document["valid"] is False
    document = assemble_result(
        resolve_output_demand(output="hierarchical"),
        False,
        units,
        root,
        ROOT_LOCATION,
        False,
    ).output_document
    assert document == {
        "valid": False,
        "evaluationPath": "",
        "schemaLocation": ROOT_LOCATION,
        "instanceLocation": "",
        "errors": {"type": "nope"},
    }


def test_assemble_result_requires_a_root_for_a_tracing_demand() -> None:
    demand = resolve_output_demand(output="list")
    with pytest.raises(ValueError, match="located tree"):
        assemble_result(demand, True, UnitSets(), None, ROOT_LOCATION, False)


def test_assemble_result_trace_is_present_only_when_asked() -> None:
    root = _root(False, errors=(0,))
    units = UnitSets(errors=[_error_unit()])
    demand = resolve_output_demand(output="basic", trace=True)
    result = assemble_result(demand, False, units, root, ROOT_LOCATION, True)
    assert result.trace == {
        "segments": [],
        "schemaLocation": ROOT_LOCATION,
        "inputLocation": "",
        "valid": False,
        "errorIndexes": [0],
        "children": [],
    }
    assert result.output_document is not None
    assert "keywordLocation" in result.output_document
    demand = resolve_output_demand(output="list")
    result = assemble_result(demand, False, units, root, ROOT_LOCATION, False)
    assert result.trace is None
