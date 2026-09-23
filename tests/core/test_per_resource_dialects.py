# `$schema` governs the resource it roots, not the document (DESIGN.md P14).
#
# The rule the walk implements: the boundary is decided from the outside,
# the contents from the inside. The parent dialect's `$id` syntax decides
# whether a resource starts at all -- a relative `$schema` has no base to
# resolve against until it has -- and the resource's own dialect decides
# everything minted into it, plus `ref_ignores_siblings` and the keyword
# table for its subtree.

import pytest

from json_schema_engine.core import (
    DIALECT_2020_12,
    DIALECT_DRAFT_07,
    InvalidIdentifierError,
    InvalidSchemaError,
    JsonValue,
    LoadedDocument,
    UnknownDialectError,
    create_engine,
)

D7 = "http://json-schema.org/draft-07/schema#"
D2020 = "https://json-schema.org/draft/2020-12/schema"


# --- the motivating case ---------------------------------------------------


def test_an_inner_dialect_rejects_what_the_outer_would_accept() -> None:
    # draft-07 reads `$id: "#foo"` as an anchor; 2020-12 reads it as a base
    # URI and forbids the fragment. The inner resource declares 2020-12, so
    # 2020-12 decides -- and the error names the dialect that objected.
    engine = create_engine()
    with pytest.raises(InvalidIdentifierError) as raised:
        engine.register_schema(
            {
                "$schema": D7,
                "$id": "https://m.test/outer",
                "definitions": {
                    "inner": {
                        "$id": "https://m.test/inner",
                        "$schema": D2020,
                        "$defs": {"x": {"$id": "#foo"}},
                    }
                },
            },
            "https://m.test/outer",
        )
    assert DIALECT_2020_12 in str(raised.value)
    assert raised.value.schema_location == "https://m.test/inner#/$defs/x"
    # All-or-nothing (P13): nothing from the attempt survives.
    assert not engine.schemas.has("https://m.test/outer")


def test_the_same_document_is_legal_under_draft_07_throughout() -> None:
    engine = create_engine()
    engine.register_schema(
        {
            "$schema": D7,
            "$id": "https://m.test/outer",
            "definitions": {
                "inner": {
                    "$id": "https://m.test/inner",
                    # `definitions`, not `$defs`: draft-07 all the way down.
                    "definitions": {"x": {"$id": "#foo"}},
                }
            },
        },
        "https://m.test/outer",
    )
    assert engine.schemas.dialect_uri_for("https://m.test/inner") == DIALECT_DRAFT_07
    assert engine.schemas.resolve_ref("#foo", "https://m.test/inner").pointer == (
        "/definitions/x"
    )


# --- the other direction ---------------------------------------------------

# 2020-12 outer, draft-07 inner. Array-form `items` is legal draft-07 and a
# non-schema value under 2020-12, so registration itself is the assertion.
MIXED: JsonValue = {
    "$id": "https://x.test/o",
    "properties": {
        "modern": {"$ref": "#/$defs/str", "minLength": 100},
        "legacy": {"$ref": "https://x.test/l"},
    },
    "$defs": {
        "str": {"type": "string"},
        "inner": {
            "$id": "https://x.test/l",
            "$schema": D7,
            "items": [{"type": "string"}],
            "definitions": {"t": {"$id": "#tag", "type": "string"}},
        },
    },
}


def test_an_embedded_resource_keeps_its_own_dialect() -> None:
    engine = create_engine()
    engine.register_schema(MIXED, "https://x.test/o")
    assert engine.schemas.dialect_uri_for("https://x.test/o") == DIALECT_2020_12
    assert engine.schemas.dialect_uri_for("https://x.test/l") == DIALECT_DRAFT_07


def test_legacy_identifier_syntax_applies_inside_the_inner_resource() -> None:
    # `$id: "#tag"` is an anchor here and an error two resources up.
    engine = create_engine()
    engine.register_schema(MIXED, "https://x.test/o")
    hit = engine.schemas.resolve_ref("#tag", "https://x.test/l")
    assert hit.pointer == "/definitions/t"


def test_ref_ignores_siblings_applies_only_inside_the_legacy_resource() -> None:
    engine = create_engine()
    uri = engine.register_schema(MIXED, "https://x.test/o")
    # 2020-12 outer: the `minLength` sibling of `$ref` applies.
    assert engine.evaluate(uri, {"modern": "short"}).valid is False
    assert engine.evaluate(uri, {"modern": "x" * 100}).valid is True


# --- inheritance -----------------------------------------------------------


def test_an_embedded_resource_without_a_schema_inherits() -> None:
    engine = create_engine()
    engine.register_schema(
        {
            "$schema": D7,
            "$id": "https://i.test/o",
            "definitions": {"inner": {"$id": "https://i.test/l", "items": [True]}},
        },
        "https://i.test/o",
    )
    # Array-form `items` registered, so draft-07 was still in force.
    assert engine.schemas.dialect_uri_for("https://i.test/l") == DIALECT_DRAFT_07


def test_an_embedded_schema_naming_the_dialect_already_in_force_is_a_no_op() -> None:
    # The suite's one nested `$schema` has this shape; it takes the fast
    # path with no lookup at all.
    engine = create_engine()
    engine.register_schema(
        {
            "$id": "https://s.test/o",
            "$defs": {"i": {"$id": "https://s.test/l", "$schema": D2020}},
        },
        "https://s.test/o",
    )
    assert engine.schemas.dialect_uri_for("https://s.test/l") == DIALECT_2020_12


# --- assembling a dialect the walk discovers -------------------------------

META: JsonValue = {
    "$id": "https://v.test/meta",
    "$schema": D2020,
    "$vocabulary": {"https://json-schema.org/draft/2020-12/vocab/core": True},
}
OTHER: JsonValue = {
    "$id": "https://v.test/other",
    "$schema": D2020,
    "$vocabulary": {"https://json-schema.org/draft/2020-12/vocab/core": True},
}


def _counting_loader(*docs: JsonValue) -> tuple[object, list[str]]:
    known = {d["$id"]: d for d in docs if isinstance(d, dict)}
    calls: list[str] = []

    def loader(uri: str) -> LoadedDocument | None:
        calls.append(uri)
        found = known.get(uri)
        return None if found is None else LoadedDocument(found, uri)

    return loader, calls


def test_an_embedded_dialect_is_assembled_on_demand() -> None:
    loader, calls = _counting_loader(META)
    engine = create_engine(loaders=[loader])  # type: ignore[arg-type]
    engine.register_schema(
        {
            "$id": "https://d.test/o",
            "$defs": {"i": {"$id": "inner", "$schema": "https://v.test/meta"}},
        },
        "https://d.test/o",
    )
    assert engine.schemas.dialect_uri_for("https://d.test/inner") == (
        "https://v.test/meta"
    )
    # Exactly one fetch: the retry assembles and tries again, it does not
    # re-fetch what it already has.
    assert calls == ["https://v.test/meta"]


def test_two_embedded_dialects_each_cost_one_attempt() -> None:
    # The bounded-loop test: three walks, two fetches, no spinning.
    loader, calls = _counting_loader(META, OTHER)
    engine = create_engine(loaders=[loader])  # type: ignore[arg-type]
    engine.register_schema(
        {
            "$id": "https://d.test/two",
            "$defs": {
                "a": {"$id": "a", "$schema": "https://v.test/meta"},
                "b": {"$id": "b", "$schema": "https://v.test/other"},
            },
        },
        "https://d.test/two",
    )
    assert sorted(calls) == ["https://v.test/meta", "https://v.test/other"]
    assert engine.schemas.dialect_uri_for("https://d.test/a") == "https://v.test/meta"
    assert engine.schemas.dialect_uri_for("https://d.test/b") == "https://v.test/other"


def test_an_unavailable_embedded_dialect_names_where_it_was_demanded() -> None:
    engine = create_engine()
    with pytest.raises(UnknownDialectError) as raised:
        engine.register_schema(
            {
                "$id": "https://d.test/o",
                "$defs": {"i": {"$id": "inner", "$schema": "https://v.test/meta"}},
            },
            "https://d.test/o",
        )
    # What is missing, and where it was asked for -- the second half is
    # carried over from the walk's own error when assembly fails.
    assert "https://v.test/meta" in str(raised.value)
    assert raised.value.dialect_uri == "https://v.test/meta"
    assert raised.value.schema_location == "https://d.test/o#/$defs/i"
    assert not engine.schemas.has("https://d.test/o")
    assert not engine.schemas.has("https://d.test/inner")


# --- `dialect_uri` names what to supply ---------------------------------------
#
# Wherever an `UnknownDialectError` reaches a caller, `dialect_uri` is the
# dialect that could not be found or assembled: the URI to hand a loader.


def test_an_unknown_root_dialect_is_named() -> None:
    with pytest.raises(UnknownDialectError) as raised:
        create_engine().register_schema(
            {"$schema": "https://v.test/meta"}, "https://d.test/root"
        )
    assert raised.value.dialect_uri == "https://v.test/meta"


def test_a_metaschema_cycle_is_named() -> None:
    selfish: JsonValue = {
        "$id": "https://v.test/self",
        "$schema": "https://v.test/self",
    }
    loader, _ = _counting_loader(selfish)
    engine = create_engine(loaders=[loader])  # type: ignore[arg-type]
    with pytest.raises(UnknownDialectError) as raised:
        engine.register_schema(
            {"$schema": "https://v.test/self"}, "https://d.test/cyclic"
        )
    assert "metaschema cycle" in str(raised.value)
    assert raised.value.dialect_uri == "https://v.test/self"


def test_a_metaschemas_own_missing_dialect_is_the_one_named() -> None:
    # The document asks for `meta`, which the loader has; `meta` asks for
    # `deeper`, which nobody has. `deeper` is what the caller must supply.
    meta: JsonValue = {"$id": "https://v.test/meta", "$schema": "https://v.test/deeper"}
    loader, _ = _counting_loader(meta)
    engine = create_engine(loaders=[loader])  # type: ignore[arg-type]
    with pytest.raises(UnknownDialectError) as raised:
        engine.register_schema(
            {
                "$id": "https://d.test/o",
                "$defs": {"i": {"$id": "inner", "$schema": "https://v.test/meta"}},
            },
            "https://d.test/o",
        )
    assert raised.value.dialect_uri == "https://v.test/deeper"


# --- pointer navigation across a boundary ----------------------------------


def test_a_pointer_crossing_a_boundary_uses_the_inner_syntax() -> None:
    # The bug here is identity, not validity: with 2020-12 identifiers used
    # for the whole navigation, `$id: "#tag"` rebound the base and reset the
    # pointer, so `t` came back claiming to be its resource's root -- which
    # then corrupts `$ref: "#"` inside it and every location it appears in.
    engine = create_engine()
    engine.register_schema(MIXED, "https://x.test/o")
    hit = engine.schemas.resolve_ref("#/$defs/inner/definitions/t", "https://x.test/o")
    assert hit.base_uri == "https://x.test/l"
    assert hit.pointer == "/definitions/t"


def test_navigation_into_an_unindexed_base_still_resolves() -> None:
    # draft-07 suppresses every identifier beside a `$ref`, so the walk
    # never mints this base -- but pointer navigation reads the document,
    # not the index, so it must still resolve rather than start raising.
    engine = create_engine()
    uri = engine.register_schema(
        {
            "$schema": D7,
            "definitions": {
                "y": {
                    "$ref": "#/definitions/z",
                    "$id": "https://u.test/never",
                    "properties": {"a": {"type": "string"}},
                },
                "z": {"type": "integer"},
            },
        },
        "urn:unindexed",
    )
    hit = engine.schemas.resolve_ref("#/definitions/y/properties/a", uri)
    assert hit.node == {"type": "string"}


# --- `$schema` where no resource starts ------------------------------------


@pytest.mark.parametrize(
    "dialect",
    [
        D2020,
        "https://json-schema.org/draft/2019-09/schema",
        D7,
        "http://json-schema.org/draft-06/schema#",
    ],
)
def test_a_misplaced_schema_keyword_is_ignored_not_refused(dialect: str) -> None:
    # The spec forbids `$schema` outside a resource root, but refusing it is
    # strict-mode hygiene, which D14 keeps opt-in. It is also load-bearing:
    # this is Bowtie's "bottom" schema -- how it spells "allows nothing" for
    # every dialect it tests -- so refusing it fails the smoke test that
    # every conformant implementation passes.
    engine = create_engine()
    top = engine.register_schema({"$schema": dialect}, "urn:smoke:top")
    bottom = engine.register_schema(
        {"$schema": dialect, "not": {"$schema": dialect}}, "urn:smoke:bottom"
    )
    # Bowtie's smoke examples, one per JSON type.
    examples: list[JsonValue] = [None, True, 37, 37.37, "37", [37], {"foo": 37}]
    for instance in examples:
        assert engine.evaluate(top, instance).valid is True
        assert engine.evaluate(bottom, instance).valid is False


def test_a_misplaced_schema_keyword_does_not_switch_dialects() -> None:
    # Ignored means ignored: the subschema is still governed by the resource
    # containing it, so draft-07's array-form `items` stays an error there.
    engine = create_engine()
    with pytest.raises(InvalidSchemaError) as raised:
        engine.register_schema(
            {"properties": {"a": {"$schema": D7, "items": [{"type": "string"}]}}},
            "urn:misplaced",
        )
    assert "non-schema value (array)" in str(raised.value)
