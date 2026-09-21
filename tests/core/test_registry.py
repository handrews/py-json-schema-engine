# Registration walk, identifier indexing, and reference resolution
# (DESIGN.md D2, D18, D19, P3, §5 "schema positions only").

from collections.abc import Mapping

import pytest

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    KeywordContext,
    Phase,
    StaticFacts,
    identifiers_2019,
    identifiers_2020,
    identifiers_legacy,
)
from json_schema_engine.core.errors import (
    InvalidSchemaError,
    MaxDepthExceededError,
    UnknownDialectError,
    UnresolvableReferenceError,
)
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.registry import SchemaRegistry

# A miniature dialect: enough applicators to exercise the walk without any
# real keyword semantics. `evaluate` is never called here.

VOCAB = "urn:test:vocab"
DIALECT = "urn:test:dialect"


def _accept(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    return True


def _map_positions(value: JsonValue, _ctx: object) -> StaticFacts:
    names = tuple(value) if is_object(value) else ()
    return StaticFacts(subschemas=tuple((n,) for n in names))


def _list_positions(value: JsonValue, _ctx: object) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(subschemas=tuple((i,) for i in range(count)))


def _self_position(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(subschemas=((),))


def _ref_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(references=(value,) if isinstance(value, str) else ())


def _pattern_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(regexes=(value,) if isinstance(value, str) else ())


def _producer_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(produces=("urn:test:properties",), subschemas=())


def _consumer_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(consumes=("urn:test:properties",))


KEYWORDS: Mapping[str, KeywordBehavior] = {
    "$id": KeywordBehavior("urn:test:$id", _accept, structural=True),
    "$anchor": KeywordBehavior("urn:test:$anchor", _accept, structural=True),
    "$dynamicAnchor": KeywordBehavior(
        "urn:test:$dynamicAnchor", _accept, structural=True
    ),
    "$defs": KeywordBehavior(
        "urn:test:$defs", _accept, _map_positions, structural=True
    ),
    "properties": KeywordBehavior("urn:test:properties", _accept, _map_positions),
    "allOf": KeywordBehavior("urn:test:allOf", _accept, _list_positions),
    "items": KeywordBehavior("urn:test:items", _accept, _self_position),
    "$ref": KeywordBehavior("urn:test:$ref", _accept, _ref_facts),
    "pattern": KeywordBehavior("urn:test:pattern", _accept, _pattern_facts),
    "producer": KeywordBehavior("urn:test:producer", _accept, _producer_facts),
    "consumer": KeywordBehavior(
        "urn:test:consumer", _accept, _consumer_facts, phase=Phase.UNEVALUATED
    ),
}


def make_registry(*, max_depth: int = 512) -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialects.register_dialect(DIALECT, [VOCAB])
    return SchemaRegistry(dialects, DIALECT, max_depth=max_depth)


# --- dialect assembly -------------------------------------------------


def test_dialect_orders_phase_one_last() -> None:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialect = dialects.register_dialect(DIALECT, [VOCAB])
    names = [entry.name for entry in dialect.ordered]
    assert names[-1] == "consumer"
    assert names[:-1] == [n for n in KEYWORDS if n != "consumer"]
    assert dialect.keywords["consumer"].vocabulary_uri == VOCAB


def test_unknown_vocabulary_is_loud() -> None:
    dialects = DialectRegistry()
    with pytest.raises(UnknownDialectError):
        dialects.register_dialect(DIALECT, ["urn:test:missing"])
    with pytest.raises(UnknownDialectError):
        dialects.get_dialect(DIALECT)


def test_later_vocabulary_rebinds_a_name() -> None:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    override = KeywordBehavior("urn:test:pattern2", _accept)
    dialects.register_vocabulary("urn:test:ext", {"pattern": override})
    dialect = dialects.register_dialect(DIALECT, [VOCAB, "urn:test:ext"])
    assert dialect.keywords["pattern"].behavior is override
    assert dialect.keywords["pattern"].vocabulary_uri == "urn:test:ext"


# --- identifier extractors -------------------------------------------


def test_identifier_extractors() -> None:
    node: dict[str, JsonValue] = {
        "$id": "x",
        "$anchor": "a",
        "$dynamicAnchor": "d",
        "$recursiveAnchor": True,
    }
    ids = identifiers_2020(node)
    assert (ids.base_id, ids.anchors, ids.dynamic_anchor) == ("x", ("a",), "d")
    assert ids.recursive_anchor is False
    ids = identifiers_2019(node)
    assert ids.dynamic_anchor is None
    assert ids.recursive_anchor is True
    assert identifiers_legacy({"$id": "#frag"}).anchors == ("frag",)
    assert identifiers_legacy({"$id": "#"}).anchors == ()
    assert identifiers_legacy({"$id": "x", "$ref": "y"}).base_id is None
    assert identifiers_legacy({"$id": 3}).base_id is None


# --- registration --------------------------------------------------------


def test_register_returns_retrieval_uri_without_id() -> None:
    reg = make_registry()
    uri = reg.register({"properties": {"a": True}}, "https://x.example/s#")
    assert uri == "https://x.example/s"
    assert reg.root_ref(uri).node == {"properties": {"a": True}}


def test_root_id_aliases_retrieval_uri() -> None:
    reg = make_registry()
    schema: JsonValue = {"$id": "https://x.example/real", "$anchor": "top"}
    uri = reg.register(schema, "https://x.example/retrieved")
    assert uri == "https://x.example/real"
    assert reg.has("https://x.example/retrieved")
    assert reg.document("https://x.example/retrieved") is schema
    assert reg.resolve_ref("#top", "https://x.example/retrieved").node is schema


def test_relative_root_id_resolves_against_retrieval_uri() -> None:
    reg = make_registry()
    uri = reg.register({"$id": "child.json"}, "https://x.example/dir/base.json")
    assert uri == "https://x.example/dir/child.json"


def test_schema_keyword_selects_dialect_fragment_free() -> None:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialects.register_dialect(DIALECT, [VOCAB])
    dialects.register_dialect("urn:test:other", [VOCAB], identifiers=identifiers_legacy)
    reg = SchemaRegistry(dialects, DIALECT)
    uri = reg.register({"$schema": "urn:test:other#", "$id": "#anchorish"}, "urn:doc")
    assert reg.dialect_uri_for(uri) == "urn:test:other"
    # Under the legacy extractor a plain-fragment $id is an anchor.
    assert reg.resolve_ref("#anchorish", uri).pointer == ""
    with pytest.raises(UnknownDialectError):
        reg.register({"$schema": "urn:test:nope"}, "urn:doc2")


def test_walk_indexes_nested_ids_and_anchors() -> None:
    reg = make_registry()
    schema: JsonValue = {
        "$id": "https://x.example/root",
        "$defs": {
            "inner": {
                "$id": "https://y.example/inner",
                "$anchor": "here",
                "properties": {"deep": {"$anchor": "deeper"}},
            },
            "rel": {"$id": "sub/rel.json", "$dynamicAnchor": "dyn"},
        },
    }
    reg.register(schema, "https://x.example/root")
    inner = reg.resolve_ref("https://y.example/inner", "https://x.example/root")
    assert inner.pointer == ""
    assert inner.base_uri == "https://y.example/inner"
    deeper = reg.resolve_ref("#deeper", "https://y.example/inner")
    assert deeper.pointer == "/properties/deep"
    assert deeper.base_uri == "https://y.example/inner"
    rel = reg.resolve_ref("sub/rel.json", "https://x.example/root")
    assert rel.base_uri == "https://x.example/sub/rel.json"
    dyn = reg.dynamic_anchor("https://x.example/sub/rel.json", "dyn")
    assert dyn is not None and dyn.node is rel.node
    # A dynamic anchor is also a plain anchor.
    assert reg.resolve_ref("#dyn", "https://x.example/sub/rel.json") is dyn
    loc = reg.document_location("https://y.example/inner")
    assert loc is not None
    assert (loc.document_uri, loc.pointer) == ("https://x.example/root", "/$defs/inner")


def test_walk_ignores_identifiers_outside_schema_positions() -> None:
    reg = make_registry()
    schema: JsonValue = {
        "enum": [{"$id": "https://evil.example/", "$anchor": "trap"}],
        "unknownKeyword": {"$anchor": "alsotrap", "properties": {"a": 5}},
    }
    reg.register(schema, "urn:doc")
    with pytest.raises(UnresolvableReferenceError):
        reg.resolve_ref("#trap", "urn:doc")
    with pytest.raises(UnresolvableReferenceError):
        reg.resolve_ref("#alsotrap", "urn:doc")
    assert not reg.has("https://evil.example/")


def test_walk_descends_through_arrays_and_self_positions() -> None:
    reg = make_registry()
    schema: JsonValue = {
        "allOf": [{"$anchor": "first"}, True, {"items": {"$anchor": "inside"}}],
    }
    reg.register(schema, "urn:doc")
    assert reg.resolve_ref("#first", "urn:doc").pointer == "/allOf/0"
    assert reg.resolve_ref("#inside", "urn:doc").pointer == "/allOf/2/items"


def test_non_schema_in_schema_position_is_loud() -> None:
    reg = make_registry()
    with pytest.raises(InvalidSchemaError) as info:
        reg.register({"properties": {"a": 5}}, "urn:doc")
    assert info.value.schema_location == "urn:doc#/properties/a"
    with pytest.raises(InvalidSchemaError):
        reg.register({"allOf": [None]}, "urn:doc2")


def test_depth_bound_is_typed() -> None:
    reg = make_registry(max_depth=3)
    deep: JsonValue = {"items": {"items": {"items": {"items": {"items": True}}}}}
    with pytest.raises(MaxDepthExceededError):
        reg.register(deep, "urn:doc")
    shallow: JsonValue = {"items": {"items": {"items": True}}}
    reg.register(shallow, "urn:doc2")


def test_produced_and_consumed_unions() -> None:
    reg = make_registry()
    reg.register({"producer": True}, "urn:a")
    assert reg.is_produced("urn:test:properties")
    assert not reg.is_consumed("urn:test:properties")
    reg.register({"consumer": True}, "urn:b")
    assert reg.is_consumed("urn:test:properties")
    assert reg.consumed_ids() == frozenset({"urn:test:properties"})


def test_regex_hook_sees_keyword_location() -> None:
    reg = make_registry()
    seen: list[tuple[str, str]] = []
    reg.on_regex = lambda p, loc: seen.append((p, loc))
    reg.register({"properties": {"a/b": {"pattern": "^x$"}}}, "urn:doc")
    assert seen == [("^x$", "urn:doc#/properties/a~1b/pattern")]


def test_references_are_collected_and_drained() -> None:
    reg = make_registry()
    reg.register(
        {"$ref": "other.json", "properties": {"a": {"$ref": "#/x"}}},
        "https://x.example/dir/s.json",
    )
    assert reg.take_unresolved() == ["https://x.example/dir/other.json"]
    assert reg.take_unresolved() == []


# --- resolution ----------------------------------------------------------


def test_pointer_resolution_tracks_embedded_ids() -> None:
    reg = make_registry()
    schema: JsonValue = {
        "$id": "https://x.example/root",
        "$defs": {"a": {"$id": "https://x.example/a", "properties": {"p": True}}},
    }
    reg.register(schema, "https://x.example/root")
    ref = reg.resolve_ref("#/$defs/a/properties/p", "https://x.example/root")
    assert ref.base_uri == "https://x.example/a"
    assert ref.pointer == "/properties/p"
    assert ref.node is True
    assert ref.location == "https://x.example/a#/properties/p"


def test_pointer_escapes_and_array_indexes() -> None:
    reg = make_registry()
    reg.register({"$defs": {"a/b": {"allOf": [True, {"$anchor": "x"}]}}}, "urn:doc")
    ref = reg.resolve_ref("#/$defs/a~1b/allOf/1", "urn:doc")
    assert ref.node == {"$anchor": "x"}
    assert ref.pointer == "/$defs/a~1b/allOf/1"


@pytest.mark.parametrize(
    "ref",
    ["#/nope", "#/$defs/a/9", "#/$defs/a/-1", "#/$defs/a/x/y", "#missing", "urn:other"],
)
def test_unresolvable_references_are_typed(ref: str) -> None:
    reg = make_registry()
    reg.register({"$defs": {"a": {"allOf": [True]}}}, "urn:doc")
    with pytest.raises(UnresolvableReferenceError):
        reg.resolve_ref(ref, "urn:doc")


def test_empty_fragment_and_root_ref() -> None:
    reg = make_registry()
    schema: JsonValue = {"$defs": {"a": {"$anchor": "a"}}}
    reg.register(schema, "urn:doc")
    assert reg.resolve_ref("#", "urn:doc").node is schema
    assert reg.resolve_ref("", "urn:doc").node is schema
    assert reg.root_ref("urn:doc#").node is schema
    assert reg.root_ref("urn:doc#a").pointer == "/$defs/a"
    with pytest.raises(UnresolvableReferenceError):
        reg.root_ref("urn:missing")


def test_child_descent_rebases_on_id() -> None:
    reg = make_registry()
    schema: JsonValue = {
        "properties": {"a": {"$id": "https://x.example/a", "items": True}}
    }
    uri = reg.register(schema, "https://x.example/root")
    root = reg.root_ref(uri)
    a = reg.child(root, ["properties", "a"])
    assert (a.base_uri, a.pointer) == ("https://x.example/a", "")
    items = reg.child(a, ["items"])
    assert (items.base_uri, items.pointer) == ("https://x.example/a", "/items")
    assert items.node is True


def test_dialect_for_unknown_resource_is_typed() -> None:
    reg = make_registry()
    with pytest.raises(UnresolvableReferenceError):
        reg.dialect_for("urn:missing")
