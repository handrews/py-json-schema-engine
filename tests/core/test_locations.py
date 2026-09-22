# Schema locations are URIs; evaluation and instance paths are plain-text
# JSON Pointers (DESIGN.md P10).
#
# The distinction only becomes visible when a member or keyword name holds a
# character RFC 3986 keeps out of a fragment, so every schema here is built
# around one: `a b` (a space), `100%` (the escape introducer), `名前`
# (non-ASCII), `a"b`, `x y` as a keyword name.


from typing import cast

import pytest

from json_schema_engine.core import (
    InvalidSchemaError,
    JsonValue,
    MaxDepthExceededError,
    UnresolvableReferenceError,
    create_engine,
)
from json_schema_engine.core.positions import parse_json_with_ranges

AWKWARD = ["a b", "100%", "名前", 'a"b', "a#b"]
ENCODED = {
    "a b": "a%20b",
    "100%": "100%25",
    "名前": "%E5%90%8D%E5%89%8D",
    'a"b': "a%22b",
    "a#b": "a%23b",
}


def _engine_for(name: str, uri: str = "https://loc.example/s"):
    schema: JsonValue = {"properties": {name: {"type": "string"}}}
    engine = create_engine()
    return engine, engine.register_schema(schema, uri)


# --- native units ----------------------------------------------------------


@pytest.mark.parametrize("name", AWKWARD)
def test_schema_location_is_a_uri_and_paths_stay_plain(name: str) -> None:
    engine, uri = _engine_for(name)
    result = engine.evaluate(uri, {name: 1}, output="list")
    assert result.errors is not None
    unit = result.errors[0]
    assert unit["schemaLocation"] == (
        f"https://loc.example/s#/properties/{ENCODED[name]}/type"
    )
    # An `evaluationPath` and an `inputLocation` are plain-text pointers:
    # neither is ever a URI, so neither is encoded.
    assert unit["evaluationPath"] == f"/properties/{name}/type"
    assert unit["inputLocation"] == f"/{name}"


def test_unknown_keyword_name_is_encoded_in_the_schema_location() -> None:
    # An unknown keyword is annotation-only (§3), and its name is whatever
    # the author wrote — so the keyword segment appended at render time
    # needs the same encoding as the rest of the pointer.
    engine = create_engine()
    uri = engine.register_schema(
        {"properties": {"a b": {"x y": 1}}}, "https://loc.example/kw"
    )
    result = engine.evaluate(uri, {"a b": 1}, output="list", annotations=True)
    assert result.annotations is not None
    unit = next(a for a in result.annotations if a["keyword"] == "x y")
    assert unit["schemaLocation"] == "https://loc.example/kw#/properties/a%20b/x%20y"
    assert unit["evaluationPath"] == "/properties/a b/x y"


# --- legacy documents ------------------------------------------------------


def _walk(unit: object) -> list[dict[str, object]]:
    """Every unit in a legacy output document, root included."""
    if not isinstance(unit, dict):
        return []
    found = [cast(dict[str, object], unit)]
    for key in ("errors", "annotations"):
        children = found[0].get(key)
        if isinstance(children, list):
            for child in cast(list[object], children):
                found += _walk(child)
    return found


@pytest.mark.parametrize("output", ["basic", "detailed", "verbose"])
def test_absolute_keyword_location_is_a_uri(output: str) -> None:
    engine, uri = _engine_for("a b")
    document = engine.evaluate(uri, {"a b": 1}, output=output).output_document
    units = _walk(document)
    absolute = {str(u["absoluteKeywordLocation"]) for u in units}
    keyword = {str(u["keywordLocation"]) for u in units}
    # `absoluteKeywordLocation` is specified as a URI and `keywordLocation`
    # as a JSON Pointer, so the same position appears in both forms and
    # the raw member name never reaches the absolute one.
    assert "https://loc.example/s#/properties/a%20b/type" in absolute
    assert "/properties/a b/type" in keyword
    assert not any(" " in location for location in absolute)
    assert all(u["instanceLocation"] in ("", "/a b") for u in units)


# --- round trip ------------------------------------------------------------


@pytest.mark.parametrize("name", AWKWARD)
def test_emitted_location_resolves_back_to_the_position_it_names(name: str) -> None:
    # The point of encoding: a location the engine hands out can be fed
    # straight back in, as a `$ref` target or to the registry.
    engine = create_engine()
    uri = engine.register_schema(
        {"$defs": {name: {"type": "string"}}}, "https://rt.example/s"
    )
    target = engine.schemas.resolve_ref(f"#/$defs/{ENCODED[name]}", uri)
    location = target.location
    assert location == f"https://rt.example/s#/$defs/{ENCODED[name]}"
    assert engine.schemas.root_ref(location).node is target.node


def test_emitted_location_is_a_usable_ref_value() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"$ref": "#/$defs/100%25", "$defs": {"100%": {"type": "string"}}},
        "https://rt.example/ref",
    )
    result = engine.evaluate(uri, 1, output="list")
    assert result.valid is False
    assert result.errors is not None
    assert result.errors[0]["schemaLocation"] == (
        "https://rt.example/ref#/$defs/100%25/type"
    )


@pytest.mark.parametrize("name", AWKWARD)
def test_locate_accepts_an_emitted_location(name: str) -> None:
    # `Engine.locate` is the other half of the round trip: it takes a
    # location the engine emitted and must decode the fragment back into
    # the plain pointer its range table is keyed by (D17).
    engine, uri = _engine_for(name, "https://pos.example/s")
    result = engine.evaluate(uri, {name: 1}, output="list")
    assert result.errors is not None
    assert engine.locate(result.errors[0]["schemaLocation"]) == {
        "documentUri": "https://pos.example/s",
        "pointer": f"/properties/{name}/type",
    }


def test_locate_finds_the_source_range_of_an_encoded_location() -> None:
    text = '{"properties": {"a b": {"type": "string"}}}'
    loaded = parse_json_with_ranges(text, "urn:doc")
    engine = create_engine()
    uri = engine.register_schema(loaded.value, "urn:doc", get_range=loaded.get_range)
    result = engine.evaluate(uri, {"a b": 1}, output="list", positions=True)
    assert result.errors is not None
    unit = result.errors[0]
    assert "source" in unit
    source = unit["source"]
    assert source["documentUri"] == "urn:doc"
    assert source["pointer"] == "/properties/a b/type"
    assert "range" in source
    value = source["range"]["value"]
    assert text[value["start"]["offset"] : value["end"]["offset"]] == '"string"'
    assert "key" in source["range"]
    key = source["range"]["key"]
    assert text[key["start"]["offset"] : key["end"]["offset"]] == '"type"'


# --- raised errors ---------------------------------------------------------


def test_raised_error_carries_an_encoded_schema_location() -> None:
    engine = create_engine()
    with pytest.raises(InvalidSchemaError) as raised:
        engine.register_schema(
            {"properties": {"a b": "not a schema"}}, "https://raise.example/s"
        )
    assert raised.value.schema_location == ("https://raise.example/s#/properties/a%20b")
    # And it round-trips: the location names a real position in the
    # document, which is what makes it worth printing.
    assert engine.locate(raised.value.schema_location) == {
        "documentUri": "https://raise.example/s",
        "pointer": "/properties/a b",
    }


def test_max_depth_error_location_is_encoded() -> None:
    schema: JsonValue = {"type": "string"}
    for _ in range(6):
        schema = {"properties": {"a b": schema}}
    engine = create_engine(max_depth=4)
    with pytest.raises(MaxDepthExceededError) as raised:
        engine.register_schema(schema, "https://raise.example/deep")
    location = raised.value.schema_location
    assert location is not None
    assert "a%20b" in location
    assert "a b" not in location


# --- the embedded-resource case (P11's motivation, encoding half only) ------


def test_encoding_survives_an_embedded_id() -> None:
    engine = create_engine()
    engine.register_schema(
        {
            "$defs": {
                "inner": {
                    "$id": "https://loc.example/inner",
                    "properties": {"100%": {"type": "string"}},
                }
            }
        },
        "https://loc.example/outer",
    )
    result = engine.evaluate("https://loc.example/inner", {"100%": 1}, output="list")
    assert result.errors is not None
    # The location is canonical (the embedded `$id`, not the document) and
    # encoded. Which document it lives in is P11's problem, not P10's.
    assert result.errors[0]["schemaLocation"] == (
        "https://loc.example/inner#/properties/100%25/type"
    )
    assert engine.locate(result.errors[0]["schemaLocation"]) == {
        "documentUri": "https://loc.example/outer",
        "pointer": "/$defs/inner/properties/100%/type",
    }


# --- errors raised during evaluation ---------------------------------------
#
# The registration walk back-fills a location onto an error escaping a
# keyword's `facts()`; `_evaluate_keyword` does the same for `evaluate()`.
# Without it the `$ref` family -- the keywords most likely to fail at
# evaluation time, and the ones whose failure is hardest to place by eye --
# reached the caller with no location at all.


def test_unresolvable_ref_during_evaluation_names_the_ref_keyword() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"$ref": "https://ev.example/missing"}, "https://ev.example/s"
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate(uri, 1)
    assert raised.value.schema_location == "https://ev.example/s#/$ref"
    # And it round-trips, which is what makes it worth printing.
    assert engine.locate(raised.value.schema_location) == {
        "documentUri": "https://ev.example/s",
        "pointer": "/$ref",
    }


def test_evaluation_error_location_is_the_keyword_not_the_schema_object() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"properties": {"a b": {"$ref": "#/$defs/nope"}}}, "https://ev.example/deep"
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate(uri, {"a b": 1})
    # Encoded per P10, and the keyword segment is appended, so the location
    # names the `$ref` rather than the schema that holds it.
    assert raised.value.schema_location == (
        "https://ev.example/deep#/properties/a%20b/$ref"
    )


def test_evaluation_error_location_uses_the_embedded_resource() -> None:
    # The P11 motivation in miniature: the location is canonical, so it
    # names the embedded `$id` and not the document the caller registered.
    engine = create_engine()
    engine.register_schema(
        {
            "$id": "https://ev.example/bundle",
            "$defs": {
                "inner": {
                    "$id": "https://ev.example/inner",
                    "$ref": "#/$defs/absent",
                }
            },
        },
        "https://ev.example/bundle",
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate("https://ev.example/inner", 1)
    assert raised.value.schema_location == "https://ev.example/inner#/$ref"
    assert engine.locate(raised.value.schema_location) == {
        "documentUri": "https://ev.example/bundle",
        "pointer": "/$defs/inner/$ref",
    }


def test_a_backfilled_location_never_overwrites_one_already_set() -> None:
    # First writer wins, innermost frame -- the same rule the registration
    # walk follows, so a keyword that located its own error keeps it.
    engine = create_engine()
    uri = engine.register_schema(
        {"properties": {"a": {"$ref": "#/$defs/gone"}}}, "https://ev.example/inner-most"
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate(uri, {"a": 1})
    assert raised.value.schema_location == (
        "https://ev.example/inner-most#/properties/a/$ref"
    )
