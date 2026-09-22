# Embedded-resource location chains (DESIGN.md P11).
#
# A chain answers "which resource, inside which", where `Engine.locate`
# answers "where in the file". The two must never disagree, which is what
# `test_chain_composes_to_the_document_pointer` pins.

from itertools import pairwise

import pytest
from tests.core.test_registry import KEYWORDS, VOCAB, make_registry

from json_schema_engine.core import JsonValue, create_engine
from json_schema_engine.core.dialect import (
    DialectRegistry,
    identifiers_legacy,
)
from json_schema_engine.core.locations import format_location_chain
from json_schema_engine.core.registry import SchemaRegistry
from json_schema_engine.core.uri import pointer_fragment

# Three resources deep, mixing an absolute `$id` with two relative ones, so
# the resolved URIs of the inner two appear nowhere in the document text.
BUNDLE: JsonValue = {
    "$id": "https://x.example/bundle",
    "$defs": {
        "a": {
            "$id": "sub/",
            "$defs": {
                "b": {
                    "$id": "b.json",
                    "properties": {"p": {"$anchor": "here"}},
                }
            },
        }
    },
}
INNER = "https://x.example/sub/b.json"
MIDDLE = "https://x.example/sub/"
ROOT = "https://x.example/bundle"


def _bundle_registry(retrieval: str = ROOT) -> SchemaRegistry:
    reg = make_registry()
    reg.register(BUNDLE, retrieval)
    return reg


# --- shape -----------------------------------------------------------------


def test_a_single_resource_document_gives_one_hop() -> None:
    # The common case: a chain says nothing the location did not, and the
    # formatter is required to produce exactly the location back.
    reg = make_registry()
    reg.register({"properties": {"a": {}}}, "urn:plain")
    chain = reg.location_chain("urn:plain#/properties/a")
    assert len(chain) == 1
    assert chain[0].resource_uri == "urn:plain"
    assert chain[0].pointer == "/properties/a"
    assert format_location_chain(chain) == "urn:plain#/properties/a"


def test_three_deep_chain_walks_out_to_the_document() -> None:
    chain = _bundle_registry().location_chain(f"{INNER}#/properties/p")
    assert [(h.resource_uri, h.pointer) for h in chain] == [
        (INNER, "/properties/p"),
        (MIDDLE, "/$defs/b"),
        (ROOT, "/$defs/a"),
    ]


def test_each_hop_reports_the_id_as_written() -> None:
    # Neither `https://x.example/sub/` nor `.../b.json` is in the document;
    # `sub/` and `b.json` are. Without this a reader searching the file for
    # the URI in the error finds nothing.
    chain = _bundle_registry().location_chain(f"{INNER}#/properties/p")
    assert [h.declared_id for h in chain] == ["b.json", "sub/", ROOT]


def test_an_error_at_a_resource_root_gives_an_empty_first_pointer() -> None:
    # Hop 0 and hop 1 then describe the same node from two sides, which the
    # one-rule-per-hop design handles without a special case.
    chain = _bundle_registry().location_chain(f"{INNER}#")
    assert chain[0].pointer == ""
    assert chain[1].pointer == "/$defs/b"


# --- retrieval URI ---------------------------------------------------------


def test_the_outermost_hop_names_the_retrieval_uri() -> None:
    reg = _bundle_registry("file:///srv/bundle.json")
    chain = reg.location_chain(f"{INNER}#/properties/p")
    assert chain[-1].resource_uri == ROOT
    assert chain[-1].retrieval_uri == "file:///srv/bundle.json"
    # Only the outermost hop carries one.
    assert all(h.retrieval_uri is None for h in chain[:-1])


def test_no_retrieval_uri_when_it_matched_the_id() -> None:
    assert _bundle_registry().location_chain(f"{INNER}#")[-1].retrieval_uri is None


def test_a_retrieval_uri_resolves_to_the_same_chain() -> None:
    reg = _bundle_registry("file:///srv/bundle.json")
    # Passing the alias in normalizes hop 0 to the canonical `$id`.
    by_alias = reg.location_chain("file:///srv/bundle.json#/$defs/a")
    by_canonical = reg.location_chain(f"{ROOT}#/$defs/a")
    assert by_alias == by_canonical
    assert by_alias[0].resource_uri == ROOT


# --- composition with D17 --------------------------------------------------


def test_chain_composes_to_the_document_pointer() -> None:
    # The invariant that keeps the chain and `Engine.locate` from drifting:
    # concatenating the hops outermost-first must rebuild the document-rooted
    # pointer the flat D17 record holds.
    reg = _bundle_registry()
    chain = reg.location_chain(f"{INNER}#/properties/p")
    flat = reg.document_location(chain[0].resource_uri)
    assert flat is not None
    assert flat.pointer == "".join(h.pointer for h in reversed(chain[1:]))


def test_every_hop_resolves_to_the_root_of_the_hop_below() -> None:
    reg = _bundle_registry()
    chain = reg.location_chain(f"{INNER}#/properties/p")
    for below, hop in pairwise(chain):
        target = reg.resolve_ref("#" + pointer_fragment(hop.pointer), hop.resource_uri)
        assert target.base_uri == below.resource_uri
        assert target.pointer == ""


def test_a_hop_location_is_a_locate_argument() -> None:
    engine = create_engine()
    engine.register_schema(BUNDLE, "file:///srv/bundle.json")
    chain = engine.location_chain(f"{INNER}#/properties/p")
    assert engine.locate(chain[0].location) == {
        "documentUri": ROOT,
        "pointer": "/$defs/a/$defs/b/properties/p",
    }
    # The outermost hop's pointer names where the hop below it sits, so it
    # locates the middle resource's root rather than the document's.
    assert engine.locate(chain[-1].location) == {
        "documentUri": ROOT,
        "pointer": "/$defs/a",
    }


def test_the_outermost_hop_agrees_with_locate_about_the_document() -> None:
    reg = _bundle_registry()
    for resource in list(reg.resources()):
        chain = reg.location_chain(f"{resource}#")
        flat = reg.document_location(resource)
        assert flat is not None
        assert chain[-1].resource_uri == flat.document_uri


# --- anchors ---------------------------------------------------------------


def test_an_anchor_location_chains_like_its_pointer_form() -> None:
    reg = _bundle_registry()
    assert reg.location_chain(f"{INNER}#here") == reg.location_chain(
        f"{INNER}#/properties/p"
    )


def test_an_unknown_anchor_has_no_chain() -> None:
    assert _bundle_registry().location_chain(f"{INNER}#absent") == ()


# --- empty chains ----------------------------------------------------------


def test_an_unregistered_resource_has_no_chain() -> None:
    assert make_registry().location_chain("https://never.example/x#/a") == ()


def test_a_base_registration_never_minted_has_no_chain() -> None:
    # Under draft-07 a `$ref` sibling suppresses identifiers, so pointer
    # navigation can produce a lexical base the walk never indexed. An empty
    # chain is the honest answer: a one-hop chain would claim it is a root.
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialects.register_dialect(
        "urn:test:legacy",
        [VOCAB],
        identifiers=identifiers_legacy,
        ref_ignores_siblings=True,
    )
    reg = SchemaRegistry(dialects, "urn:test:legacy")
    reg.register(
        {
            "$ref": "#/$defs/y/properties/a",
            "$defs": {"y": {"$id": "https://z.example/", "properties": {"a": {}}}},
        },
        "urn:d7",
    )
    reached = reg.resolve_ref("#/$defs/y/properties/a", "urn:d7")
    assert reached.base_uri == "https://z.example/"
    assert list(reg.resources()) == ["urn:d7"]
    assert reg.location_chain(reached.location) == ()


# --- urn: bases ------------------------------------------------------------


def test_a_urn_relative_id_is_explained_by_its_chain() -> None:
    # `urn:` has no path to merge against, so a relative `$id` replaces the
    # whole of it: `sub/rel.json` under `urn:example:root` resolves to
    # `urn:sub/rel.json`, which looks unrelated to the document it is in.
    # Reading that URI in an error is baffling until the chain explains it.
    reg = make_registry()
    reg.register(
        {"$id": "urn:example:root", "$defs": {"r": {"$id": "sub/rel.json"}}},
        "urn:example:root",
    )
    chain = reg.location_chain("urn:sub/rel.json#")
    assert [(h.resource_uri, h.pointer) for h in chain] == [
        ("urn:sub/rel.json", ""),
        ("urn:example:root", "/$defs/r"),
    ]
    assert chain[0].declared_id == "sub/rel.json"


# --- the formatter ---------------------------------------------------------


def test_format_renders_a_three_hop_chain() -> None:
    reg = _bundle_registry("file:///srv/bundle.json")
    chain = reg.location_chain(f"{INNER}#/properties/p")
    assert format_location_chain(chain) == (
        "https://x.example/sub/b.json#/properties/p\n"
        '  in https://x.example/sub/ at /$defs/b (written as "b.json")\n'
        '  in https://x.example/bundle at /$defs/a (written as "sub/")\n'
        "  retrieved as file:///srv/bundle.json"
    )


def test_format_indents_under_a_message() -> None:
    reg = _bundle_registry()
    chain = reg.location_chain(f"{INNER}#/properties/p")
    rendered = format_location_chain(chain, message="something went wrong")
    assert rendered.splitlines()[0] == "something went wrong"
    # The whole block shifts by two under a message; the hop lines keep
    # their own two on top of that.
    assert rendered.splitlines()[1] == ("  https://x.example/sub/b.json#/properties/p")
    assert rendered.splitlines()[2].startswith("    in https://x.example/sub/")


def test_format_omits_the_id_when_it_matches_the_resolved_uri() -> None:
    # An absolute `$id` is already in the text; repeating it would be noise.
    reg = make_registry()
    reg.register(
        {
            "$id": "https://x.example/outer",
            "$defs": {"i": {"$id": "https://x.example/inner"}},
        },
        "https://x.example/outer",
    )
    rendered = format_location_chain(reg.location_chain("https://x.example/inner#"))
    assert "written as" not in rendered


def test_format_of_an_empty_chain_is_the_message_alone() -> None:
    assert format_location_chain((), message="no location") == "no location"
    assert format_location_chain(()) == ""


# --- errors carry chains ---------------------------------------------------


def test_an_evaluation_error_is_given_a_chain() -> None:
    from json_schema_engine.core import UnresolvableReferenceError

    engine = create_engine()
    engine.register_schema(
        {
            "$id": "https://x.example/catalog",
            "$defs": {"i": {"$id": "items/", "$ref": "#/$defs/absent"}},
        },
        "file:///srv/catalog.json",
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate("https://x.example/items/", 1)
    chain = raised.value.location_chain
    assert chain is not None
    assert [h.resource_uri for h in chain] == [
        "https://x.example/items/",
        "https://x.example/catalog",
    ]
    assert chain[-1].retrieval_uri == "file:///srv/catalog.json"


def test_a_registration_error_is_given_a_chain() -> None:
    from json_schema_engine.core import InvalidSchemaError

    engine = create_engine()
    with pytest.raises(InvalidSchemaError) as raised:
        engine.register_schema(
            {
                "$id": "https://x.example/doc",
                "$defs": {"i": {"$id": "part/", "properties": {"a": "nope"}}},
            },
            "https://x.example/doc",
        )
    chain = raised.value.location_chain
    assert chain is not None
    assert [h.resource_uri for h in chain] == [
        "https://x.example/part/",
        "https://x.example/doc",
    ]


def test_str_is_unchanged_for_a_single_resource_error() -> None:
    from json_schema_engine.core import UnresolvableReferenceError

    engine = create_engine()
    uri = engine.register_schema({"$ref": "#/$defs/absent"}, "urn:one-resource")
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate(uri, 1)
    # A chain of one adds nothing, so the message is exactly the message.
    assert "\n" not in str(raised.value)
    assert raised.value.location_chain is None or len(raised.value.location_chain) == 1


def test_str_appends_the_chain_for_a_multi_resource_error() -> None:
    from json_schema_engine.core import UnresolvableReferenceError

    engine = create_engine()
    engine.register_schema(
        {
            "$id": "https://x.example/multi",
            "$defs": {"i": {"$id": "inner/", "$ref": "#/$defs/absent"}},
        },
        "https://x.example/multi",
    )
    with pytest.raises(UnresolvableReferenceError) as raised:
        engine.evaluate("https://x.example/inner/", 1)
    lines = str(raised.value).splitlines()
    assert lines[0].startswith("pointer '/$defs/absent' not found")
    assert lines[1].strip() == "https://x.example/inner/#/$ref"
    assert 'in https://x.example/multi at /$defs/i (written as "inner/")' in lines[2]


# --- snapshots -------------------------------------------------------------


def test_a_snapshot_answers_the_same_chains() -> None:
    reg = _bundle_registry("file:///srv/bundle.json")
    snap = reg.snapshot()
    for resource in list(reg.resources()):
        assert snap.location_chain(f"{resource}#") == reg.location_chain(f"{resource}#")


def test_a_snapshot_chains_a_lazily_registered_metaschema() -> None:
    # The case a parallel parent map would have gotten wrong: a snapshot
    # grows resources after it is taken, through lazy bundled registration,
    # so the parent data has to travel in a record `snapshot()` already
    # copies rather than in a map someone must remember to copy.
    engine = create_engine()
    live = engine.schemas
    snap = live.snapshot()
    meta = "https://json-schema.org/draft/2020-12/schema"
    assert snap.location_chain(f"{meta}#/$defs") != ()
    assert meta not in list(live.resources())
