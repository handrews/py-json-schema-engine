# Unregistering a document (DESIGN.md P15), matching the TypeScript
# engine's ADR 0005: remove then register is how a document is replaced,
# a resource goes with whichever document owns it now, and a snapshot keeps
# everything it had.
#
# pyright: reportPrivateUsage=false

from collections.abc import Mapping

import pytest
from tests.core.test_registry import DIALECT, KEYWORDS, VOCAB, _accept

from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DuplicateResourceError,
    JsonValue,
    ReadOnlyRegistryError,
    UnresolvableReferenceError,
    create_engine,
    parse_json_with_ranges,
)
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    StaticFacts,
)
from json_schema_engine.core.registry import SchemaRegistry

DECLARED = "https://u.example/declared"
RETRIEVAL = "https://u.example/retrieval"
INNER = "https://u.example/inner"
EXTERNAL = "https://elsewhere.example/thing"


def test_removes_a_document_and_everything_it_owned() -> None:
    text = f"""{{
      "$id": "{DECLARED}",
      "$recursiveAnchor": true,
      "$defs": {{
        "a": {{"$anchor": "plain"}},
        "i": {{"$id": "{INNER}", "$anchor": "in", "$recursiveAnchor": true}}
      }}
    }}"""
    loaded = parse_json_with_ranges(text, RETRIEVAL)
    engine = create_engine(default_dialect=DIALECT_2019_09)
    engine.register_schema(loaded.value, RETRIEVAL, get_range=loaded.get_range)
    reg = engine.schemas
    view = reg.snapshot()
    located = engine.locate(f"{DECLARED}#")
    assert located is not None and "range" in located

    engine.unregister_schema(RETRIEVAL)

    for uri in (DECLARED, RETRIEVAL, INNER):
        assert not reg.has(uri)
    with pytest.raises(UnresolvableReferenceError):
        reg.root_ref(RETRIEVAL)
    with pytest.raises(UnresolvableReferenceError):
        reg.resolve_ref("#plain", DECLARED)
    with pytest.raises(UnresolvableReferenceError):
        reg.resolve_ref("#in", INNER)
    assert not reg.has_recursive_root(DECLARED)
    assert not reg.has_recursive_root(INNER)
    assert engine.locate(f"{DECLARED}#") is None
    assert list(reg.resources()) == []

    # The snapshot's indexes are copies, so it keeps all of it.
    assert view.root_ref(RETRIEVAL).base_uri == DECLARED
    assert view.resolve_ref("#plain", DECLARED).pointer == "/$defs/a"
    assert view.resolve_ref("#in", INNER).pointer == ""
    assert view.has_recursive_root(DECLARED)
    assert view.has_recursive_root(INNER)
    inner = view.document_location(INNER)
    assert inner is not None and inner.pointer == "/$defs/i"
    assert view.range(DECLARED, "") is not None


def test_removes_dynamic_anchors() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"$defs": {"d": {"$dynamicAnchor": "node"}}}, "https://u.example/dyn"
    )
    assert engine.schemas.dynamic_anchor(uri, "node") is not None
    engine.unregister_schema(uri)
    assert engine.schemas.dynamic_anchor(uri, "node") is None


def test_is_how_a_document_is_replaced() -> None:
    engine = create_engine()
    uri = "https://u.example/replace"
    engine.register_schema({"type": "string"}, uri)
    with pytest.raises(DuplicateResourceError):
        engine.register_schema({"type": "integer"}, uri)
    engine.unregister_schema(uri)
    engine.register_schema({"type": "integer"}, uri)
    assert engine.evaluate(uri, 1).valid is True


def test_drops_the_range_lookup_with_the_document() -> None:
    uri = "https://u.example/ranges"
    loaded = parse_json_with_ranges("{}", uri)
    engine = create_engine()
    engine.register_schema(loaded.value, uri, get_range=loaded.get_range)
    engine.unregister_schema(uri)
    engine.register_schema({}, uri)
    assert engine.locate(f"{uri}#") == {"documentUri": uri, "pointer": ""}


def test_refuses_an_unknown_uri_and_an_embedded_resource() -> None:
    engine = create_engine()
    holder = engine.register_schema(
        {"$defs": {"s": {"$id": "https://u.example/embedded"}}},
        "https://u.example/embedder",
    )
    with pytest.raises(UnresolvableReferenceError, match="unknown schema"):
        engine.unregister_schema("https://u.example/nowhere")
    with pytest.raises(UnresolvableReferenceError, match=holder):
        engine.unregister_schema("https://u.example/embedded")
    assert engine.schemas.has(holder)
    assert engine.schemas.has("https://u.example/embedded")


def _unions(engine_schemas: SchemaRegistry) -> tuple[set[str], set[str]]:
    return (
        set(engine_schemas._produced_ids),
        set(engine_schemas._consumed_ids),
    )


def test_leaves_the_unions_and_the_pending_queue_alone() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"$ref": EXTERNAL, "properties": {"p": True}, "unevaluatedProperties": False},
        "https://u.example/unions",
    )
    before = _unions(engine.schemas)
    engine.unregister_schema(uri)
    assert _unions(engine.schemas) == before
    assert engine.schemas.take_unresolved() == [EXTERNAL]


# --- a resource goes with its current owner ----------------------------------


def test_an_equal_embedded_copy_takes_a_resource_over() -> None:
    engine = create_engine()
    shared = "https://u.example/shared"
    body: JsonValue = {"$defs": {"s": {"$id": shared, "type": "string"}}}
    a = engine.register_schema(body, "https://u.example/eq-a")
    b = engine.register_schema(body, "https://u.example/eq-b")
    location = engine.schemas.document_location(shared)
    assert location is not None and location.document_uri == b
    # Removing the older holder keeps it; removing the newer takes it away.
    engine.unregister_schema(a)
    assert engine.schemas.has(shared)
    engine.unregister_schema(b)
    assert not engine.schemas.has(shared)


def test_a_root_registration_of_an_embedded_resource_takes_it_over() -> None:
    engine = create_engine()
    sub = "https://u.example/sub"
    holder = engine.register_schema(
        {"$defs": {"s": {"$id": sub, "type": "string"}}},
        "https://u.example/sub-holder",
    )
    assert engine.register_schema({"$id": sub, "type": "string"}, sub) == sub
    engine.unregister_schema(holder)
    assert engine.schemas.has(sub)
    assert engine.evaluate(sub, "s").valid is True


def test_a_document_absorbed_by_an_equal_copy_is_no_longer_one() -> None:
    engine = create_engine()
    solo = "https://u.example/solo"
    engine.register_schema({"$id": solo, "type": "string"}, solo)
    holder = engine.register_schema(
        {"$defs": {"s": {"$id": solo, "type": "string"}}},
        "https://u.example/absorber",
    )
    with pytest.raises(UnresolvableReferenceError, match=holder):
        engine.unregister_schema(solo)


# --- aliases -------------------------------------------------------------------


def test_every_alias_survives_an_equal_re_registration() -> None:
    # Unlike the TypeScript engine, whose equal re-registration evicts every
    # alias but the newest: a document reachable from two URLs would
    # otherwise break one set of `$ref`s each time it is loaded through the
    # other.
    engine = create_engine()
    doc: JsonValue = {"$id": DECLARED, "type": "string"}
    engine.register_schema(doc, "https://u.example/url-1")
    engine.register_schema(doc, "https://u.example/url-2")
    for alias in ("https://u.example/url-1", "https://u.example/url-2"):
        assert engine.schemas.root_ref(alias).base_uri == DECLARED
    engine.unregister_schema("https://u.example/url-2")
    for uri in (DECLARED, "https://u.example/url-1", "https://u.example/url-2"):
        assert not engine.schemas.has(uri)


# --- refusals ------------------------------------------------------------------


@pytest.mark.parametrize("used", [False, True], ids=["fresh", "after-use"])
def test_a_bundled_metaschema_cannot_be_unregistered(used: bool) -> None:
    engine = create_engine()
    if used:
        engine.evaluate(DIALECT_2020_12, {})
    with pytest.raises(ReadOnlyRegistryError, match="bundled"):
        engine.unregister_schema(DIALECT_2020_12)
    # Refusing never registered it as a side effect.
    assert (DIALECT_2020_12 in engine.schemas.resources()) is used


def test_a_snapshot_cannot_unregister() -> None:
    engine = create_engine()
    uri = engine.register_schema({}, "https://u.example/snap")
    with pytest.raises(ReadOnlyRegistryError):
        engine.schemas.snapshot().unregister(uri)


def test_unregistering_from_inside_a_walk_is_refused() -> None:
    # Caller code runs inside the walk; an unregister there would be
    # silently undone, or worse redone, by the enclosing rollback.
    reg: SchemaRegistry | None = None

    def analyze(value: JsonValue, _ctx: object) -> StaticFacts:
        assert reg is not None
        reg.unregister("urn:kept")
        return StaticFacts()

    keywords: Mapping[str, KeywordBehavior] = {
        **KEYWORDS,
        "meddle": KeywordBehavior("urn:test:meddle", _accept, analyze),  # type: ignore[arg-type]
    }
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, keywords)
    dialects.register_dialect(DIALECT, [VOCAB])
    reg = SchemaRegistry(dialects, DIALECT)
    reg.register({}, "urn:kept")
    with pytest.raises(ReadOnlyRegistryError, match="in progress"):
        reg.register({"meddle": 1}, "urn:meddler")
    assert reg.has("urn:kept")
    assert not reg.has("urn:meddler")
