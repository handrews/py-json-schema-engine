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
    DuplicateAnchorError,
    DuplicateResourceError,
    InvalidIdentifierError,
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
    with pytest.raises(UnresolvableReferenceError) as info:
        reg.resolve_ref(ref, "urn:doc")
    # Whichever way it failed, the attempt is reported: what was written,
    # what it resolved against, and what came out.
    assert info.value.reference == ref
    assert info.value.resolved_against == "urn:doc"
    assert info.value.resolved_to is not None


def test_a_pointer_miss_names_the_failing_segment() -> None:
    # `#/$defs/a/b/c/d` failing at `c` must not read like it failed at `d`.
    reg = make_registry()
    reg.register({"$defs": {"a": {"$defs": {"b": {}}}}}, "urn:deep")
    with pytest.raises(UnresolvableReferenceError) as info:
        reg.resolve_ref("#/$defs/a/$defs/b/c/d", "urn:deep")
    message = str(info.value)
    assert "no 'c' at /$defs/a/$defs/b" in message
    assert "(object)" in message


def test_a_pointer_miss_into_a_scalar_names_what_it_stood_on() -> None:
    reg = make_registry()
    reg.register({"$defs": {"a": {"title": "t"}}}, "urn:scalar")
    with pytest.raises(UnresolvableReferenceError) as info:
        reg.resolve_ref("#/$defs/a/title/nope", "urn:scalar")
    assert "no 'nope' at /$defs/a/title (string)" in str(info.value)


def test_the_resolution_attempt_survives_an_embedded_id() -> None:
    # The case the attributes exist for: the reference is a plain relative
    # name, but the base in force is an embedded `$id` the reader may never
    # have seen, so the URI that failed looks unrelated to the document.
    reg = make_registry()
    reg.register(
        {
            "$id": "https://x.example/bundle",
            "$defs": {"i": {"$id": "sub/", "$ref": "other.json"}},
        },
        "https://x.example/bundle",
    )
    with pytest.raises(UnresolvableReferenceError) as info:
        reg.resolve_ref("other.json", "https://x.example/sub/")
    assert info.value.reference == "other.json"
    assert info.value.resolved_against == "https://x.example/sub/"
    assert info.value.resolved_to == "https://x.example/sub/other.json"


def test_root_ref_reports_the_uri_it_was_given() -> None:
    reg = make_registry()
    with pytest.raises(UnresolvableReferenceError) as info:
        reg.root_ref("urn:absent")
    assert info.value.reference == "urn:absent"
    # Nothing resolved it against anything: the caller named it directly.
    assert info.value.resolved_against is None


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


# --- duplicate identifiers (P12) --------------------------------------


def test_duplicate_id_in_one_document_is_rejected() -> None:
    reg = make_registry()
    with pytest.raises(DuplicateResourceError) as info:
        reg.register(
            {
                "$id": "https://x.example/root",
                "$defs": {
                    "a": {"$id": "https://x.example/dup"},
                    "b": {"$id": "https://x.example/dup"},
                },
            },
            "https://x.example/root",
        )
    assert "https://x.example/dup" in str(info.value)
    # The location blames the `$id`-bearing position, not the resource it
    # tried to mint, so a reader can find the second one in the file.
    assert info.value.schema_location == "https://x.example/root#/$defs/b"


def test_duplicate_id_nested_inside_its_own_subtree_is_rejected() -> None:
    # Left alone this builds a cycle in the resource-parent relation: the
    # inner `A` is written last, from inside `B`'s subtree, so `A` would
    # claim `B` as its parent while `B` claims `A`.
    reg = make_registry()
    with pytest.raises(DuplicateResourceError):
        reg.register(
            {
                "$id": "https://x.example/r",
                "$defs": {
                    "a": {
                        "$id": "https://x.example/a",
                        "$defs": {
                            "b": {
                                "$id": "https://x.example/b",
                                "$defs": {"c": {"$id": "https://x.example/a"}},
                            }
                        },
                    }
                },
            },
            "https://x.example/r",
        )


def test_identical_subschemas_claiming_one_id_are_still_two_resources() -> None:
    # Value equality does not rescue this: they are two positions, so one
    # would have to shadow the other whatever it holds.
    reg = make_registry()
    with pytest.raises(DuplicateResourceError):
        reg.register(
            {
                "$id": "https://x.example/root",
                "$defs": {
                    "a": {"$id": "https://x.example/same", "$anchor": "x"},
                    "b": {"$id": "https://x.example/same", "$anchor": "x"},
                },
            },
            "https://x.example/root",
        )


def test_reregistering_an_equal_document_is_a_no_op() -> None:
    reg = make_registry()
    schema: JsonValue = {"$id": "https://x.example/s", "$defs": {"a": {}}}
    assert reg.register(schema, "https://x.example/s") == "https://x.example/s"
    # A separately-built but equal document: the check is `json_equal`, not
    # identity, so a caller that re-parses the same text is not punished.
    again: JsonValue = {"$id": "https://x.example/s", "$defs": {"a": {}}}
    assert reg.register(again, "https://x.example/s") == "https://x.example/s"


def test_reregistering_a_different_document_is_rejected() -> None:
    reg = make_registry()
    reg.register(
        {"$id": "https://x.example/s", "$defs": {"a": {}}}, "https://x.example/s"
    )
    with pytest.raises(DuplicateResourceError) as info:
        reg.register({"$id": "https://x.example/s"}, "https://x.example/s")
    assert "already registered" in str(info.value)


def test_two_documents_cannot_share_an_embedded_id() -> None:
    # The loader-displacement case: a second document quietly rebinding a
    # resource the caller registered themselves.
    reg = make_registry()
    reg.register(
        {"$id": "urn:one", "$defs": {"i": {"$id": "https://x.example/shared"}}},
        "urn:one",
    )
    with pytest.raises(DuplicateResourceError) as info:
        reg.register(
            {
                "$id": "urn:two",
                "$defs": {"i": {"$id": "https://x.example/shared", "$anchor": "a"}},
            },
            "urn:two",
        )
    assert "https://x.example/shared" in str(info.value)


def test_duplicate_anchor_in_one_resource_is_rejected() -> None:
    reg = make_registry()
    with pytest.raises(DuplicateAnchorError) as info:
        reg.register(
            {
                "$id": "https://x.example/root",
                "$defs": {"a": {"$anchor": "dup"}, "b": {"$anchor": "dup"}},
            },
            "https://x.example/root",
        )
    assert "https://x.example/root#dup" in str(info.value)


def test_plain_and_dynamic_anchors_collide_across_indexes() -> None:
    # The nastiest shape: a dynamic anchor is also a plain anchor (D8), so
    # left alone `$ref: "#n"` and `$dynamicRef: "#n"` resolve to different
    # schemas. Checking the `_anchors` key catches both kinds at once.
    reg = make_registry()
    with pytest.raises(DuplicateAnchorError):
        reg.register(
            {
                "$id": "https://x.example/root",
                "$defs": {"a": {"$anchor": "n"}, "b": {"$dynamicAnchor": "n"}},
            },
            "https://x.example/root",
        )


def test_one_schema_may_carry_both_anchor_kinds_under_one_name() -> None:
    # It names itself twice, which is not two schemas claiming one name.
    reg = make_registry()
    uri = reg.register(
        {
            "$id": "https://x.example/root",
            "$defs": {"a": {"$anchor": "self", "$dynamicAnchor": "self"}},
        },
        "https://x.example/root",
    )
    hit = reg.resolve_ref("#self", uri)
    assert reg.dynamic_anchor(uri, "self") is hit


def test_the_same_anchor_name_in_different_resources_is_fine() -> None:
    reg = make_registry()
    uri = reg.register(
        {
            "$id": "https://x.example/root",
            "$defs": {
                "a": {"$id": "one", "$anchor": "n"},
                "b": {"$id": "two", "$anchor": "n"},
            },
        },
        "https://x.example/root",
    )
    assert uri == "https://x.example/root"
    first = reg.resolve_ref("#n", "https://x.example/one")
    second = reg.resolve_ref("#n", "https://x.example/two")
    assert first is not second


def test_legacy_id_beside_a_ref_claims_nothing() -> None:
    # draft-07/06: a `$ref` sibling suppresses every identifier (D18), so
    # two such `$id`s are not a duplicate — nothing was ever claimed.
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialects.register_dialect(DIALECT, [VOCAB], identifiers=identifiers_legacy)
    reg = SchemaRegistry(dialects, DIALECT)
    uri = reg.register(
        {
            "$defs": {
                "a": {"$ref": "#/$defs/b", "$id": "https://z.example/"},
                "b": {"$ref": "#/$defs/a", "$id": "https://z.example/"},
            }
        },
        "urn:d7",
    )
    assert list(reg.resources()) == [uri]


def test_a_failed_registration_leaves_the_registry_untouched() -> None:
    # Registration is all-or-nothing (DESIGN.md §7). The half-indexed
    # document this used to leave behind was still evaluable, while missing
    # every anchor and sub-resource past the failure point.
    reg = make_registry()
    with pytest.raises(DuplicateAnchorError):
        reg.register(
            {
                "$id": "https://x.example/half",
                "$defs": {"a": {"$anchor": "n"}, "b": {"$anchor": "n"}},
            },
            "https://x.example/half",
        )
    assert not reg.has("https://x.example/half")
    # Including the anchor the walk did successfully claim before failing.
    assert list(reg.resources()) == []
    with pytest.raises(UnresolvableReferenceError):
        reg.resolve_ref("#n", "https://x.example/half")


# --- embedded `$id` syntax --------------------------------------------


@pytest.mark.parametrize("bad", ["#frag", "#", ""])
def test_an_embedded_id_that_names_no_new_resource_is_rejected(bad: str) -> None:
    # Each of these resolves back to the enclosing resource, so before the
    # check they surfaced as a duplicate of an `$id` nobody wrote.
    reg = make_registry()
    with pytest.raises(InvalidIdentifierError) as info:
        reg.register(
            {"$id": "https://x.example/r", "$defs": {"a": {"$id": bad}}},
            "https://x.example/r",
        )
    assert info.value.schema_location == "https://x.example/r#/$defs/a"
    assert not isinstance(info.value, DuplicateResourceError)


def test_an_empty_fragment_on_an_embedded_id_is_fine() -> None:
    # 2020-12's metaschema allows a bare trailing `#`, and the bundled
    # draft-06/07 metaschemas spell their own root `$id` that way.
    reg = make_registry()
    uri = reg.register(
        {"$id": "https://x.example/r", "$defs": {"a": {"$id": "sub#"}}},
        "https://x.example/r",
    )
    assert uri == "https://x.example/r"
    assert reg.has("https://x.example/sub")


def test_a_legacy_fragment_id_is_an_anchor_not_an_error() -> None:
    # The same document, legal under draft-07/06: the extractor turns
    # `#name` into an anchor, so the base-URI rule is never reached.
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialects.register_dialect(DIALECT, [VOCAB], identifiers=identifiers_legacy)
    reg = SchemaRegistry(dialects, DIALECT)
    uri = reg.register(
        {"$id": "https://x.example/r", "$defs": {"a": {"$id": "#frag"}}},
        "https://x.example/r",
    )
    assert reg.resolve_ref("#frag", uri).pointer == "/$defs/a"


def test_two_positions_claiming_one_uri_is_still_a_duplicate() -> None:
    reg = make_registry()
    with pytest.raises(DuplicateResourceError):
        reg.register(
            {
                "$id": "https://x.example/r",
                "$defs": {"a": {"$id": "x"}, "b": {"$id": "x"}},
            },
            "https://x.example/r",
        )
