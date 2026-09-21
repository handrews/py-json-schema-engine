# The legacy dialects (DESIGN.md D11, D18): `$recursiveRef` scope,
# `definitions`, exact keyword sets, `$ref` ignoring its siblings at
# registration and evaluation, and dialect selection by `$schema`.

import pytest

from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
    JsonValue,
    UnresolvableReferenceError,
    create_engine,
)
from json_schema_engine.core.metaschemas import bundled_metaschemas


def run(schema: JsonValue, instance: JsonValue, dialect: str) -> bool:
    engine = create_engine(default_dialect=dialect)
    uri = engine.register_schema(schema, "https://legacy.example/root")
    return engine.evaluate(uri, instance).valid


# --- $recursiveRef ---------------------------------------------------------


def test_recursive_ref_rebinds_to_the_outermost_recursive_root() -> None:
    # The classic "extend a recursive tree": the extension's root carries
    # `$recursiveAnchor: true`, so `$recursiveRef: "#"` inside the base
    # resolves to the extension, which forbids extra properties.
    schema: JsonValue = {
        "$id": "https://legacy.example/strict-tree",
        "$recursiveAnchor": True,
        "$ref": "tree",
        "unevaluatedProperties": False,
        "$defs": {
            "tree": {
                "$id": "tree",
                "$recursiveAnchor": True,
                "type": "object",
                "properties": {
                    "data": True,
                    "children": {"type": "array", "items": {"$recursiveRef": "#"}},
                },
            }
        },
    }
    assert run(schema, {"children": [{"data": 1}]}, DIALECT_2019_09) is True
    assert run(schema, {"children": [{"daat": 1}]}, DIALECT_2019_09) is False


def test_recursive_ref_without_anchor_is_a_plain_ref() -> None:
    schema: JsonValue = {
        "$id": "https://legacy.example/loose",
        "$ref": "tree",
        "unevaluatedProperties": False,
        "$defs": {
            "tree": {
                "$id": "tree",
                "type": "object",
                "properties": {
                    "data": True,
                    "children": {"type": "array", "items": {"$recursiveRef": "#"}},
                },
            }
        },
    }
    # No `$recursiveAnchor: true` at the extension root: the reference stays
    # lexical, so the inner tree tolerates extra properties.
    assert run(schema, {"children": [{"daat": 1}]}, DIALECT_2019_09) is True


def test_recursive_ref_with_pointer_fragment_is_a_plain_ref() -> None:
    schema: JsonValue = {
        "$recursiveAnchor": True,
        "$defs": {"t": {"type": "integer"}},
        "$recursiveRef": "#/$defs/t",
    }
    assert run(schema, 1, DIALECT_2019_09) is True
    assert run(schema, "x", DIALECT_2019_09) is False


# --- definitions and $ref siblings -----------------------------------------


def test_definitions_is_walked_but_never_applied() -> None:
    schema: JsonValue = {
        "definitions": {"never": False, "a": {"$id": "#a", "type": "integer"}}
    }
    assert run(schema, "anything", DIALECT_DRAFT_07) is True
    engine = create_engine(default_dialect=DIALECT_DRAFT_07)
    uri = engine.register_schema(schema, "https://legacy.example/defs")
    assert engine.schemas.resolve_ref("#a", uri).pointer == "/definitions/a"


@pytest.mark.parametrize("dialect", [DIALECT_DRAFT_07, DIALECT_DRAFT_06])
def test_ref_ignores_siblings_in_legacy_dialects(dialect: str) -> None:
    schema: JsonValue = {
        "$ref": "#/definitions/a",
        "type": "string",
        "definitions": {"a": {"type": "integer"}},
    }
    assert run(schema, 1, dialect) is True
    assert run(schema, "s", dialect) is False


def test_ref_does_not_ignore_siblings_in_2019_09() -> None:
    schema: JsonValue = {
        "$ref": "#/$defs/a",
        "type": "string",
        "$defs": {"a": {"type": "integer"}},
    }
    assert run(schema, 1, DIALECT_2019_09) is False
    assert run(schema, "s", DIALECT_2019_09) is False


def test_identifiers_beside_a_legacy_ref_are_not_indexed() -> None:
    # Owner ruling: ignored is ignored. The anchor inside the sibling
    # `definitions` is never registered; a pointer into it still resolves.
    engine = create_engine(default_dialect=DIALECT_DRAFT_07)
    uri = engine.register_schema(
        {
            "$ref": "#/definitions/a",
            "definitions": {"a": {"$id": "#anchor", "type": "integer"}},
        },
        "https://legacy.example/ignored",
    )
    assert engine.evaluate(uri, 1).valid is True
    with pytest.raises(UnresolvableReferenceError):
        engine.schemas.resolve_ref("#anchor", uri)
    # Under 2019-09 the same shape does index the anchor.
    engine = create_engine(default_dialect=DIALECT_2019_09)
    uri = engine.register_schema(
        {"$ref": "#/$defs/a", "$defs": {"a": {"$anchor": "anchor", "type": "integer"}}},
        "https://legacy.example/indexed",
    )
    assert engine.schemas.resolve_ref("#anchor", uri).pointer == "/$defs/a"


# --- keyword sets and dialect selection -----------------------------------

DRAFT_07_ONLY = {
    "$comment",
    "if",
    "then",
    "else",
    "readOnly",
    "writeOnly",
    "contentMediaType",
    "contentEncoding",
}


def test_draft_06_is_draft_07_minus_eight_keywords() -> None:
    engine = create_engine()
    seven = set(engine.dialects.get_dialect(DIALECT_DRAFT_07).keywords)
    six = set(engine.dialects.get_dialect(DIALECT_DRAFT_06).keywords)
    assert seven - six == DRAFT_07_ONLY
    assert six <= seven
    for name in ("minContains", "maxContains", "dependentRequired", "$defs", "$anchor"):
        assert name not in seven
    for name in ("definitions", "dependencies", "additionalItems", "items", "contains"):
        assert name in six


def test_2019_09_keyword_set() -> None:
    engine = create_engine()
    keywords = set(engine.dialects.get_dialect(DIALECT_2019_09).keywords)
    assert {"$recursiveRef", "$recursiveAnchor", "additionalItems", "items"} <= keywords
    for name in ("$dynamicRef", "$dynamicAnchor", "prefixItems", "definitions"):
        assert name not in keywords
    assert "unevaluatedItems" in keywords and "unevaluatedProperties" in keywords


@pytest.mark.parametrize(
    ("declared", "dialect"),
    [
        ("http://json-schema.org/draft-07/schema#", DIALECT_DRAFT_07),
        ("http://json-schema.org/draft-07/schema", DIALECT_DRAFT_07),
        ("http://json-schema.org/draft-06/schema#", DIALECT_DRAFT_06),
        ("https://json-schema.org/draft/2019-09/schema", DIALECT_2019_09),
        ("https://json-schema.org/draft/2020-12/schema", DIALECT_2020_12),
    ],
)
def test_schema_keyword_selects_the_dialect(declared: str, dialect: str) -> None:
    engine = create_engine()
    uri = engine.register_schema({"$schema": declared}, "https://legacy.example/sel")
    assert engine.schemas.dialect_uri_for(uri) == dialect


def test_legacy_metaschemas_resolve_without_loaders() -> None:
    engine = create_engine()
    for meta in (
        "http://json-schema.org/draft-07/schema#",
        "http://json-schema.org/draft-06/schema#",
        "https://json-schema.org/draft/2019-09/schema",
    ):
        uri = engine.load_schema({"$schema": meta, "$ref": meta}, f"urn:m:{meta}")
        assert engine.evaluate(uri, {"minLength": 1}).valid is True
        assert engine.evaluate(uri, {"minLength": -1}).valid is False


def test_bundled_metaschemas_count() -> None:
    assert len(bundled_metaschemas()) == 18


def test_contains_without_sibling_bounds_in_draft_07() -> None:
    schema: JsonValue = {"contains": {"type": "integer"}, "minContains": 2}
    # `minContains` is an unknown keyword in draft-07: one match suffices.
    assert run(schema, [1], DIALECT_DRAFT_07) is True
    assert run(schema, ["a"], DIALECT_DRAFT_07) is False
    assert run(schema, [1], DIALECT_2019_09) is False
