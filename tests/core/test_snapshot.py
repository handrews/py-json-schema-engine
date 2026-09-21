# Registry snapshots (M6): a compiled artifact binds a frozen copy of the
# schema and dialect registries, so later registration on the engine cannot
# change what the artifact's islands resolve.

import pytest

from json_schema_engine.core import (
    DIALECT_2020_12,
    ReadOnlyRegistryError,
    UnresolvableReferenceError,
    create_engine,
)


def test_snapshot_is_read_only_and_isolated() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"$ref": "https://snap.example/later"}, "https://snap.example/root"
    )
    snapshot = engine.schemas.snapshot()
    with pytest.raises(UnresolvableReferenceError):
        snapshot.resolve_ref("https://snap.example/later", uri)
    # Registering on the live registry afterwards is invisible to the snapshot.
    engine.register_schema({"type": "string"}, "https://snap.example/later")
    assert engine.schemas.resolve_ref("https://snap.example/later", uri).node == {
        "type": "string"
    }
    with pytest.raises(UnresolvableReferenceError):
        snapshot.resolve_ref("https://snap.example/later", uri)
    with pytest.raises(ReadOnlyRegistryError):
        snapshot.register({"type": "string"}, "https://snap.example/later")
    assert snapshot.root_ref(uri).node == {"$ref": "https://snap.example/later"}


def test_snapshot_still_resolves_bundled_metaschemas_lazily() -> None:
    engine = create_engine()
    uri = engine.register_schema({"$ref": DIALECT_2020_12}, "https://snap.example/meta")
    snapshot = engine.schemas.snapshot()
    target = snapshot.resolve_ref(DIALECT_2020_12, uri)
    assert target.base_uri == DIALECT_2020_12
    # The lazy registration landed in the snapshot only.
    assert DIALECT_2020_12 in list(snapshot.resources())
    assert DIALECT_2020_12 not in list(engine.schemas.resources())


def test_dialect_snapshot_refuses_registration() -> None:
    engine = create_engine()
    dialects = engine.dialects.snapshot()
    assert dialects.get_dialect(DIALECT_2020_12) is engine.dialects.get_dialect(
        DIALECT_2020_12
    )
    with pytest.raises(ReadOnlyRegistryError):
        dialects.register_vocabulary("urn:x", {})
    with pytest.raises(ReadOnlyRegistryError):
        dialects.register_dialect("urn:d", [])
