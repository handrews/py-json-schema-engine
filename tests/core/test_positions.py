# Source positions (DESIGN.md D17): a loader that reports ranges, the
# registry's document/pointer bridge, `Engine.locate`, and unit decoration
# under `positions=True`. The expectations mirror the TS engine's own test.

import pytest

from json_schema_engine.core import (
    OutputOptionsError,
    ParsedDocument,
    create_engine,
    parse_json_with_ranges,
)

TEXT = """{
  "$id": "https://pos.example/root",
  "$ref": "https://pos.example/leaf",
  "$defs": {
    "leaf": {
      "$id": "https://pos.example/leaf",
      "required": ["x"]
    }
  }
}"""


def loader(uri: str) -> ParsedDocument | None:
    if uri == "https://pos.example/root":
        return parse_json_with_ranges(TEXT, uri)
    return None


def test_round_trip_through_an_embedded_id_resource() -> None:
    engine = create_engine(loaders=[loader])
    uri = engine.load("https://pos.example/root")
    result = engine.evaluate(uri, {}, output="list", positions=True)
    assert result.valid is False
    assert result.errors is not None
    unit = next(e for e in result.errors if "'x'" in e["error"])
    assert unit["schemaLocation"] == "https://pos.example/leaf#/required"

    assert "source" in unit
    source = unit["source"]
    assert source["documentUri"] == "https://pos.example/root"
    assert source["pointer"] == "/$defs/leaf/required"
    assert "range" in source
    source_range = source["range"]
    value_line = TEXT.splitlines()[source_range["value"]["start"]["line"] - 1]
    assert '"required"' in value_line
    assert "key" in source_range
    key = source_range["key"]
    assert TEXT[key["start"]["offset"] : key["end"]["offset"]] == '"required"'
    assert engine.locate(unit["schemaLocation"]) == source


def test_annotations_are_decorated_too() -> None:
    text = '{"title": "T", "properties": {"a": {"title": "A"}}}'
    engine = create_engine()
    uri = engine.register_schema(
        parse_json_with_ranges(text, "urn:doc").value,
        "urn:doc",
        get_range=parse_json_with_ranges(text, "urn:doc").get_range,
    )
    result = engine.evaluate(
        uri, {"a": 1}, output="list", annotations=True, positions=True
    )
    assert result.annotations is not None
    inner = next(a for a in result.annotations if a["inputLocation"] == "/a")
    assert "source" in inner and "range" in inner["source"]
    source_range = inner["source"]["range"]
    assert "key" in source_range
    key = source_range["key"]
    assert text[key["start"]["offset"] : key["end"]["offset"]] == '"title"'


def test_locate_degrades_to_pointer_only_without_ranges() -> None:
    engine = create_engine()
    engine.register_schema(
        {"$defs": {"s": {"type": "number"}}}, "https://pos.example/plain"
    )
    assert engine.locate("https://pos.example/plain#/$defs/s") == {
        "documentUri": "https://pos.example/plain",
        "pointer": "/$defs/s",
    }
    assert engine.locate("https://pos.example/unknown#/x") is None


def test_positions_without_ranges_leaves_units_bare_of_range() -> None:
    engine = create_engine()
    uri = engine.register_schema({"type": "string"}, "urn:plain")
    result = engine.evaluate(uri, 1, output="basic", positions=True)
    assert result.errors is not None
    assert result.errors[0].get("source") == {
        "documentUri": "urn:plain",
        "pointer": "/type",
    }


def test_positions_with_flag_is_rejected() -> None:
    engine = create_engine()
    uri = engine.register_schema({}, "urn:x")
    with pytest.raises(OutputOptionsError):
        engine.evaluate(uri, 1, positions=True)
