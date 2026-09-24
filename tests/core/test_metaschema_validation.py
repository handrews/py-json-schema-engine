# `validate_schemas` checks each dialect region against its own metaschema
# (DESIGN.md P17; 2020-12 core §9.3.3). A compound document is not one
# instance of one metaschema: the root, and every embedded resource whose
# dialect differs from its parent's, is checked separately, with the
# regions nested in it masked out.
#
# pyright: reportPrivateUsage=false

import pytest

from json_schema_engine.core import (
    DIALECT_2020_12,
    JsonValue,
    SchemaValidationError,
    create_engine,
)
from json_schema_engine.core.engine import _masked, _node_at

D7 = "http://json-schema.org/draft-07/schema#"
D2020 = "https://json-schema.org/draft/2020-12/schema"


def _strict_register(schema: JsonValue, uri: str) -> str:
    return create_engine(validate_schemas=True).register_schema(schema, uri)


def test_a_valid_legacy_resource_inside_a_modern_document_registers() -> None:
    # Used to fail: the 2020-12 metaschema judged the draft-07 resource's
    # array-form `items` as if it were 2020-12.
    assert _strict_register(
        {
            "$id": "https://v.example/o",
            "$defs": {
                "legacy": {
                    "$id": "https://v.example/l",
                    "$schema": D7,
                    "items": [{"type": "string"}],
                }
            },
        },
        "https://v.example/o",
    )


def test_an_invalid_modern_resource_inside_a_legacy_document_is_refused() -> None:
    # Used to register: draft-07's metaschema knows nothing of
    # `minContains`, so nothing checked the 2020-12 resource at all.
    engine = create_engine(validate_schemas=True)
    with pytest.raises(SchemaValidationError) as raised:
        engine.register_schema(
            {
                "$schema": D7,
                "$id": "https://v.example/o2",
                "definitions": {
                    "i": {
                        "$id": "https://v.example/l2",
                        "$schema": D2020,
                        "minContains": "bad",
                    }
                },
            },
            "https://v.example/o2",
        )
    error = raised.value
    assert error.schema_location == "https://v.example/l2#"
    assert D2020 in str(error)
    assert error.location_chain is not None
    assert [hop.resource_uri for hop in error.location_chain] == [
        "https://v.example/l2",
        "https://v.example/o2",
    ]
    assert not engine.schemas.has("https://v.example/o2")
    assert not engine.schemas.has("https://v.example/l2")


def test_an_invalid_legacy_resource_is_caught_by_its_own_metaschema() -> None:
    with pytest.raises(SchemaValidationError) as raised:
        _strict_register(
            {
                "$id": "https://v.example/o3",
                "$defs": {
                    "legacy": {
                        "$id": "https://v.example/l3",
                        "$schema": D7,
                        "minLength": -1,
                    }
                },
            },
            "https://v.example/o3",
        )
    assert raised.value.schema_location == "https://v.example/l3#"
    assert "draft-07" in str(raised.value)


def test_a_same_dialect_resource_is_checked_within_its_parent() -> None:
    with pytest.raises(SchemaValidationError) as raised:
        _strict_register(
            {
                "$id": "https://v.example/o4",
                "$defs": {"inner": {"$id": "https://v.example/l4", "minLength": -1}},
            },
            "https://v.example/o4",
        )
    # One region, so the root is the resource it names.
    assert raised.value.schema_location == "https://v.example/o4#"


THREE_DEEP: JsonValue = {
    "$id": "https://v.example/top",
    "$defs": {
        "mid": {
            "$id": "https://v.example/mid",
            "$schema": D7,
            "items": [{"type": "string"}],
            "definitions": {
                "low": {
                    "$id": "https://v.example/low",
                    "$schema": D2020,
                    "prefixItems": [{"type": "integer"}],
                }
            },
        }
    },
}


def test_regions_nest() -> None:
    assert _strict_register(THREE_DEEP, "https://v.example/top")


def test_a_failure_two_regions_down_names_its_own_resource() -> None:
    import copy

    broken = copy.deepcopy(THREE_DEEP)
    low = broken["$defs"]["mid"]["definitions"]["low"]  # type: ignore[index]
    low["prefixItems"] = "bad"  # type: ignore[index]
    with pytest.raises(SchemaValidationError) as raised:
        _strict_register(broken, "https://v.example/top")
    assert raised.value.schema_location == "https://v.example/low#"


def test_a_region_whose_metaschema_is_unavailable_is_skipped() -> None:
    engine = create_engine(validate_schemas=True)
    base = engine.dialects.get_dialect(DIALECT_2020_12)
    engine.dialects.register_dialect("urn:custom:dialect", base.vocabulary_uris)
    document: JsonValue = {
        "$id": "https://v.example/o5",
        "$defs": {
            "custom": {
                "$id": "https://v.example/l5",
                "$schema": "urn:custom:dialect",
                "minLength": -1,
            }
        },
    }
    # "Cannot check" is not failure, as at the root...
    assert engine.register_schema(document, "https://v.example/o5")
    # ...and the rest of the document is still checked.
    broken: JsonValue = {**document, "$id": "https://v.example/o6", "maxLength": -1}  # type: ignore[dict-item]
    with pytest.raises(SchemaValidationError) as raised:
        engine.register_schema(broken, "https://v.example/o6")
    assert raised.value.schema_location == "https://v.example/o6#"


# --- the masking helpers -------------------------------------------------------


def test_masking_copies_only_the_path() -> None:
    kept: JsonValue = {"deep": [1, 2]}
    doc: JsonValue = {"a": {"b": [{"x": 1}, {"y": 2}]}, "c": kept}
    masked = _masked(doc, ["/a/b/1", "/a/b/1/y"])
    assert masked == {"a": {"b": [{"x": 1}, {}]}, "c": {"deep": [1, 2]}}
    assert masked["c"] is kept  # type: ignore[index]
    assert doc == {"a": {"b": [{"x": 1}, {"y": 2}]}, "c": kept}


def test_node_at_decodes_segments() -> None:
    doc: JsonValue = {"a/b": {"c~d": [0, {"e": 1}]}}
    assert _node_at(doc, "/a~1b/c~0d/1") == {"e": 1}
    assert _node_at(doc, "") is doc
