# The public trace surface (DESIGN.md D6 `trace` control): the `TraceUnit`
# tree must mirror the evaluation — including passing subtrees — with
# positional error correlation against `Result.errors`, so a consumer never
# parses location strings to reconstruct application context.

from json_schema_engine.core import JsonValue, Result, TraceUnit, create_engine


def run(schema: JsonValue, instance: JsonValue) -> Result:
    engine = create_engine()
    uri = engine.register_schema(schema, "https://trace.example/schema")
    return engine.evaluate(uri, instance, output="list", error_params=True, trace=True)


def find(node: TraceUnit, segments: list[str]) -> TraceUnit:
    if node["segments"] == segments:
        return node
    for child in node["children"]:
        try:
            return find(child, segments)
        except LookupError:
            continue
    raise LookupError(segments)


def test_trace_is_absent_without_the_control_and_present_on_valid_results() -> None:
    engine = create_engine()
    uri = engine.register_schema({"type": "string"}, "https://trace.example/plain")
    assert engine.evaluate(uri, "ok", output="list").trace is None
    traced = engine.evaluate(uri, "ok", output="list", trace=True)
    assert traced.valid is True
    assert traced.trace == {
        "segments": [],
        "schemaLocation": "https://trace.example/plain#",
        "inputLocation": "",
        "valid": True,
        "errorIndexes": [],
        "children": [],
    }


def test_trace_with_basic_output_builds_the_tree_only_when_asked() -> None:
    engine = create_engine()
    uri = engine.register_schema({"type": "string"}, "https://trace.example/plain")
    assert engine.evaluate(uri, 1, output="basic").trace is None
    traced = engine.evaluate(uri, 1, output="basic", trace=True)
    assert traced.trace is not None and traced.trace["errorIndexes"] == [0]


def test_trace_records_any_of_branches_with_validity_and_error_indexes() -> None:
    result = run({"anyOf": [{"type": "string"}, {"minimum": 10}]}, 5)
    assert result.valid is False
    assert result.trace is not None and result.errors is not None
    assert result.trace["valid"] is False
    b0 = find(result.trace, ["anyOf", "0"])
    b1 = find(result.trace, ["anyOf", "1"])
    assert b0["valid"] is False and b1["valid"] is False
    assert b0["schemaLocation"] == "https://trace.example/schema#/anyOf/0"
    # Every branch error index resolves to a unit at that branch's location.
    for node, keyword in ((b0, "type"), (b1, "minimum")):
        assert len(node["errorIndexes"]) == 1
        unit = result.errors[node["errorIndexes"][0]]
        assert unit.get("keyword") == keyword
        assert unit["schemaLocation"] == f"{node['schemaLocation']}/{keyword}"
    # The combiner's own error sits at the parent application.
    assert "anyOf" in [
        result.errors[i].get("keyword") for i in result.trace["errorIndexes"]
    ]


def test_trace_segments_stay_dynamic_across_ref_while_location_is_canonical() -> None:
    result = run(
        {
            "properties": {"a": {"$ref": "#/$defs/x"}},
            "$defs": {"x": {"type": "string"}},
        },
        {"a": 1},
    )
    assert result.trace is not None and result.errors is not None
    via_ref = find(result.trace, ["$ref"])
    assert via_ref["schemaLocation"] == "https://trace.example/schema#/$defs/x"
    assert via_ref["inputLocation"] == "/a"
    assert via_ref["valid"] is False
    unit = result.errors[via_ref["errorIndexes"][0]]
    assert unit["evaluationPath"] == "/properties/a/$ref/type"
    assert unit["schemaLocation"] == "https://trace.example/schema#/$defs/x/type"


def test_trace_records_property_names_applications_at_the_object_location() -> None:
    result = run({"propertyNames": {"pattern": "^a"}}, {"b": 1})
    assert result.trace is not None and result.errors is not None
    app = find(result.trace, ["propertyNames"])
    assert app["valid"] is False
    assert app["inputLocation"] == "/b"
    assert result.errors[app["errorIndexes"][0]].get("keyword") == "pattern"


def test_trace_attaches_boolean_false_errors_to_the_application_node() -> None:
    result = run({"properties": {"a": False}}, {"a": 1})
    assert result.trace is not None and result.errors is not None
    app = find(result.trace, ["properties", "a"])
    assert app["valid"] is False
    assert len(app["errorIndexes"]) == 1
    unit = result.errors[app["errorIndexes"][0]]
    assert "keyword" not in unit
    assert unit["inputLocation"] == "/a"


def test_trace_decodes_escaped_path_segments() -> None:
    result = run({"properties": {"a/b~c": {"type": "string"}}}, {"a/b~c": 1})
    assert result.trace is not None and result.errors is not None
    app = find(result.trace, ["properties", "a/b~c"])
    assert app["valid"] is False
    # The string surface stays escaped; only the trace decodes.
    assert result.errors[app["errorIndexes"][0]]["evaluationPath"] == (
        "/properties/a~1b~0c/type"
    )


def test_trace_includes_applications_from_passing_subtrees() -> None:
    result = run(
        {"properties": {"good": {"type": "integer"}, "bad": {"type": "string"}}},
        {"good": 1, "bad": 2},
    )
    assert result.trace is not None
    good = find(result.trace, ["properties", "good"])
    assert good["valid"] is True
    assert good["errorIndexes"] == []


def test_trace_of_a_valid_result_has_no_error_indexes_for_dropped_errors() -> None:
    # A rejecting branch under an accepting `anyOf` has no relevant errors:
    # its indexes are empty even though the branch is invalid.
    result = run({"anyOf": [{"type": "string"}, {"type": "integer"}]}, 5)
    assert result.valid is True and result.trace is not None
    failed = find(result.trace, ["anyOf", "0"])
    assert failed["valid"] is False
    assert failed["errorIndexes"] == []
