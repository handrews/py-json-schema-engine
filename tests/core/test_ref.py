"""`SchemaRef`: a frozen position whose location is built once (P7, P10)."""

import pytest

from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.uri import schema_location


def test_location_is_the_canonical_schema_location() -> None:
    ref = SchemaRef({"type": "string"}, "https://example.com/s", "/properties/100%")
    assert ref.location == schema_location("https://example.com/s", "/properties/100%")
    assert ref.location == "https://example.com/s#/properties/100%25"


def test_location_is_built_once() -> None:
    ref = SchemaRef({}, "https://example.com/s", "/$defs/a")
    first = ref.location
    # The second read is the cached string itself, not a rebuilt equal one.
    assert ref.location is first


def test_root_location_is_an_empty_fragment() -> None:
    assert (
        SchemaRef({}, "https://example.com/s", "").location == "https://example.com/s#"
    )


def test_ref_stays_frozen_and_identity_keyed() -> None:
    ref = SchemaRef({}, "https://example.com/s", "")
    twin = SchemaRef({}, "https://example.com/s", "")
    assert ref.location
    assert ref != twin
    assert len({ref, twin}) == 2
    with pytest.raises(AttributeError):
        setattr(ref, "pointer", "/x")  # noqa: B010 -- frozen field
