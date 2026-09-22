# Dynamic scope (DESIGN.md D8), `$vocabulary` assembly, bundled
# metaschemas, and the `validate_schemas` policy through the public API.

import pytest

from json_schema_engine.core import (
    InvalidSchemaError,
    JsonValue,
    LoadedDocument,
    SchemaValidationError,
    UnknownDialectError,
    UnknownVocabularyError,
    UnresolvableReferenceError,
    create_engine,
)

META_2020 = "https://json-schema.org/draft/2020-12/schema"
VOCAB = "https://json-schema.org/draft/2020-12/vocab/"


def run(schema: JsonValue, instance: JsonValue, **options: object) -> bool:
    engine = create_engine()
    uri = engine.register_schema(schema, "https://dyn.example/root")
    return engine.evaluate(uri, instance).valid


# --- dynamic scope ---------------------------------------------------------


def test_dynamic_ref_resolves_to_first_anchor_in_scope() -> None:
    # The classic list/string-list shape: the outer resource's
    # $dynamicAnchor overrides the inner default.
    schema: JsonValue = {
        "$id": "https://dyn.example/strings",
        "$ref": "list",
        "$defs": {
            "foo": {"$dynamicAnchor": "items", "type": "string"},
            "list": {
                "$id": "list",
                "type": "array",
                "items": {"$dynamicRef": "#items"},
                "$defs": {"items": {"$dynamicAnchor": "items"}},
            },
        },
    }
    assert run(schema, ["a", "b"]) is True
    assert run(schema, ["a", 1]) is False


def test_dynamic_ref_without_matching_anchor_behaves_like_ref() -> None:
    schema: JsonValue = {
        "$defs": {"target": {"$anchor": "t", "type": "integer"}},
        "$dynamicRef": "#t",
    }
    assert run(schema, 3) is True
    assert run(schema, "x") is False


def test_dynamic_ref_pointer_fragment_is_plain_ref() -> None:
    schema: JsonValue = {
        "$defs": {"t": {"type": "boolean"}},
        "$dynamicRef": "#/$defs/t",
    }
    assert run(schema, True) is True
    assert run(schema, 1) is False


def test_leaving_a_scope_forgets_its_anchor() -> None:
    # `mid` carries the overriding anchor and is entered only under `a`;
    # under `b` the scope is root -> inner, and inner's own anchor wins.
    schema: JsonValue = {
        "$id": "https://dyn.example/leave",
        "properties": {"a": {"$ref": "mid"}, "b": {"$ref": "inner"}},
        "$defs": {
            "mid": {
                "$id": "mid",
                "$ref": "inner",
                "$defs": {"n": {"$dynamicAnchor": "n", "type": "integer"}},
            },
            "inner": {
                "$id": "inner",
                "$dynamicRef": "#n",
                "$defs": {"n": {"$dynamicAnchor": "n", "type": "string"}},
            },
        },
    }
    assert run(schema, {"a": 1}) is True
    assert run(schema, {"a": "s"}) is False
    assert run(schema, {"b": "s"}) is True
    assert run(schema, {"b": 1}) is False


def test_dynamic_ref_to_boolean_schema() -> None:
    schema: JsonValue = {
        "$defs": {"f": {"$dynamicAnchor": "f", "not": {}}},
        "$dynamicRef": "#f",
    }
    assert run(schema, 1) is False


# --- bundled metaschemas ---------------------------------------------------


def test_ref_to_bundled_metaschema_needs_no_loader() -> None:
    engine = create_engine()
    uri = engine.load_schema({"$ref": META_2020}, "https://meta.example/s")
    assert engine.evaluate(uri, {"type": "integer"}).valid is True
    assert engine.evaluate(uri, {"type": 1}).valid is False
    assert engine.evaluate(uri, {"minLength": -1}).valid is False
    assert engine.evaluate(uri, {"$defs": {"a": {"type": "string"}}}).valid is True


def test_bundled_resources_are_lazy() -> None:
    engine = create_engine()
    assert META_2020 not in list(engine.schemas.resources())
    assert engine.schemas.has(META_2020)
    engine.schemas.root_ref(META_2020)
    assert META_2020 in list(engine.schemas.resources())


# --- $vocabulary assembly --------------------------------------------------

NO_VALIDATION = "https://vocab.example/no-validation"
OPTIONAL_UNKNOWN = "https://vocab.example/optional-unknown"
REQUIRED_UNKNOWN = "https://vocab.example/required-unknown"
BARE = "https://vocab.example/bare"
SELF_REFERENTIAL = "https://vocab.example/self"

METASCHEMAS: dict[str, JsonValue] = {
    NO_VALIDATION: {
        "$schema": META_2020,
        "$id": NO_VALIDATION,
        "$vocabulary": {VOCAB + "applicator": True, VOCAB + "core": True},
        "$dynamicAnchor": "meta",
        "allOf": [
            {"$ref": "https://json-schema.org/draft/2020-12/meta/applicator"},
            {"$ref": "https://json-schema.org/draft/2020-12/meta/core"},
        ],
    },
    OPTIONAL_UNKNOWN: {
        "$schema": META_2020,
        "$id": OPTIONAL_UNKNOWN,
        "$vocabulary": {
            VOCAB + "validation": True,
            VOCAB + "core": True,
            "https://vocab.example/custom": False,
        },
    },
    REQUIRED_UNKNOWN: {
        "$schema": META_2020,
        "$id": REQUIRED_UNKNOWN,
        "$vocabulary": {VOCAB + "core": True, "https://vocab.example/custom": True},
    },
    BARE: {"$schema": META_2020, "$id": BARE, "required": ["title"]},
    SELF_REFERENTIAL: {"$schema": SELF_REFERENTIAL, "$id": SELF_REFERENTIAL},
}


def meta_loader(uri: str) -> LoadedDocument | None:
    document = METASCHEMAS.get(uri)
    return None if document is None else LoadedDocument(document, uri)


def test_dialect_without_validation_vocabulary_ignores_minimum() -> None:
    engine = create_engine(loaders=[meta_loader])
    uri = engine.load_schema(
        {"$schema": NO_VALIDATION, "properties": {"n": {"minimum": 10}, "x": False}},
        "https://vocab.example/doc",
    )
    assert engine.evaluate(uri, {"n": 1}).valid is True
    assert engine.evaluate(uri, {"x": 1}).valid is False


def test_unknown_optional_vocabulary_is_skipped() -> None:
    engine = create_engine(loaders=[meta_loader])
    uri = engine.load_schema(
        {"$schema": OPTIONAL_UNKNOWN, "type": "number"}, "https://vocab.example/doc"
    )
    assert engine.evaluate(uri, 1).valid is True
    assert engine.evaluate(uri, "s").valid is False


def test_unknown_required_vocabulary_is_loud() -> None:
    engine = create_engine(loaders=[meta_loader])
    with pytest.raises(UnknownVocabularyError):
        engine.load_schema({"$schema": REQUIRED_UNKNOWN}, "https://vocab.example/doc")


def test_metaschema_without_vocabulary_gets_the_default_dialect() -> None:
    engine = create_engine(loaders=[meta_loader])
    uri = engine.load_schema(
        {"$schema": BARE, "minimum": 2}, "https://vocab.example/doc"
    )
    assert engine.evaluate(uri, 1).valid is False


def test_metaschema_cycle_is_loud() -> None:
    engine = create_engine(loaders=[meta_loader])
    with pytest.raises(UnknownDialectError):
        engine.load_schema({"$schema": SELF_REFERENTIAL}, "https://vocab.example/doc")


def test_unknown_dialect_without_loader_is_loud() -> None:
    engine = create_engine()
    with pytest.raises(UnknownDialectError):
        engine.register_schema({"$schema": "https://nope.example/meta"}, "urn:doc")


# --- validate_schemas ------------------------------------------------------


def test_validate_schemas_rejects_a_malformed_document() -> None:
    engine = create_engine(validate_schemas=True)
    with pytest.raises(SchemaValidationError) as info:
        engine.register_schema({"minLength": -1}, "https://val.example/bad")
    assert info.value.errors
    # "Rejects" means it is not registered: the check runs before the walk,
    # so a document that fails its metaschema never enters the registry.
    assert not engine.schemas.has("https://val.example/bad")
    with pytest.raises(UnresolvableReferenceError):
        engine.evaluate("https://val.example/bad", 1)
    assert engine.register_schema({"minLength": 1}, "https://val.example/ok")


def test_validate_schemas_checks_a_loaded_metaschema() -> None:
    engine = create_engine(loaders=[meta_loader], validate_schemas=True)
    with pytest.raises(SchemaValidationError):
        engine.load_schema({"$schema": BARE, "x": 1}, "https://val.example/d")
    assert not engine.schemas.has("https://val.example/d")
    assert engine.load_schema({"$schema": BARE, "title": "t"}, "https://val.example/ok")


def test_validate_schemas_reports_the_metaschema_before_the_walk() -> None:
    # Ordering is observable when a document is broken both ways: the
    # metaschema gets the first word, and it explains more — every
    # violated keyword, rather than the first bad schema position.
    engine = create_engine(validate_schemas=True)
    with pytest.raises(SchemaValidationError) as info:
        engine.register_schema(
            {"minLength": -1, "properties": {"a": "not a schema"}},
            "https://val.example/doubly-bad",
        )
    assert info.value.errors
    assert not engine.schemas.has("https://val.example/doubly-bad")


def test_validate_schemas_skips_a_dialect_without_a_metaschema_resource() -> None:
    engine = create_engine(validate_schemas=True)
    engine.dialects.register_dialect(
        "urn:custom:dialect", [VOCAB + "core", VOCAB + "validation"]
    )
    # The dialect exists but no document is registered under its URI:
    # "cannot check" is not a failure.
    assert engine.register_schema(
        {"minLength": -1}, "https://val.example/custom", "urn:custom:dialect"
    )


def test_bundled_metaschemas_are_complete() -> None:
    from json_schema_engine.core.metaschemas import bundled_metaschemas

    documents = bundled_metaschemas()
    assert len(documents) == 18
    for uri, document in documents.items():
        # draft-07/06 spell their `$id` with a trailing `#`; resources are
        # keyed fragment-free.
        assert isinstance(document, dict)
        assert str(document.get("$id")).rstrip("#") == uri


# --- a failed drain keeps its queue ----------------------------------------


def test_a_failed_drain_leaves_the_rest_of_the_queue_pending() -> None:
    # `take_unresolved` empties the pending set before the drain loop has
    # fetched anything, so a failure part-way used to discard every URI the
    # loop had not reached — and nothing ever queued them again.
    good: JsonValue = {"$id": "https://q.example/good", "type": "string"}
    attempts: list[str] = []

    def loader(uri: str) -> LoadedDocument | None:
        attempts.append(uri)
        if uri == "https://q.example/bad":
            # A document that cannot register: a non-schema value in a
            # schema position.
            return LoadedDocument({"properties": {"a": 1}}, uri)
        if uri == "https://q.example/good":
            return LoadedDocument(good, uri)
        return None

    engine = create_engine(loaders=[loader])
    # Sorted order puts "bad" before "good", so the failure happens first.
    with pytest.raises(InvalidSchemaError):
        engine.load_schema(
            {
                "$defs": {
                    "a": {"$ref": "https://q.example/bad"},
                    "b": {"$ref": "https://q.example/good"},
                }
            },
            "https://q.example/root",
        )
    assert attempts == ["https://q.example/bad"]
    assert not engine.schemas.has("https://q.example/good")

    # The unreached URI is still queued, so a later drain picks it up.
    # The one that raised is not: it was already reported to this caller,
    # and requeuing it would raise the same error inside a later drain.
    assert engine.schemas.take_unresolved() == ["https://q.example/good"]
