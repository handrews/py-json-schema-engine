# Registration is all-or-nothing (DESIGN.md §7).
#
# A walk that raised part-way used to leave the document registered and
# evaluable, missing every anchor and sub-resource past the failure point,
# with partial contributions to `_produced_ids`/`_consumed_ids` — which feed
# D5's elision predicate, so the failure surfaced as a wrong answer rather
# than a loud one.
#
# This file is the one place that reaches into registry privates: the
# rollback's whole point is the state a public API cannot show you once it
# is gone. The coupling is confined to `_fingerprint` and
# `test_index_census`.
#
# pyright: reportPrivateUsage=false

from collections.abc import Mapping

import pytest
from tests.core.test_registry import DIALECT, KEYWORDS, VOCAB, _accept, make_registry

from json_schema_engine.core import (
    DuplicateAnchorError,
    DuplicateResourceError,
    InvalidSchemaError,
    JsonValue,
    MaxDepthExceededError,
    UnsafeRegexError,
    UnsupportedPatternError,
    create_engine,
    parse_json_with_ranges,
)
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    StaticFacts,
)
from json_schema_engine.core.registry import SchemaRegistry

# --- the property ----------------------------------------------------------


def _fingerprint(reg: SchemaRegistry) -> dict[str, object]:
    """Every index a registration can write, in order, by identity.

    Identity rather than equality, and lists rather than dicts: an undo
    that restored an *equal* copy of a document, or reinserted a key at the
    end of `_documents`, compares equal and is still a bug — `resources()`
    promises registration order, and `_claim_anchor` keys on `SchemaRef`
    identity.
    """
    return {
        "documents": [(k, id(v)) for k, v in reg._documents.items()],
        "anchors": [(k, id(v)) for k, v in reg._anchors.items()],
        "dynamic_anchors": [(k, id(v)) for k, v in reg._dynamic_anchors.items()],
        "document_dialects": list(reg._document_dialects.items()),
        "resource_locations": list(reg._resource_locations.items()),
        "document_ranges": [(k, id(v)) for k, v in reg._document_ranges.items()],
        "aliases": list(reg._aliases.items()),
        "recursive_roots": sorted(reg._recursive_roots),
        "produced_ids": sorted(reg._produced_ids),
        "consumed_ids": sorted(reg._consumed_ids),
        "pending_resources": sorted(reg._pending_resources),
    }


# A resource the failing documents below re-claim, so the restore-prior path
# is exercised by the property itself rather than by one bespoke test.
SHARED: dict[str, JsonValue] = {
    "$id": "urn:shared",
    "$anchor": "keep",
    "properties": {"a": {}},
}


def _populated(**kwargs: object) -> SchemaRegistry:
    """A registry with something to lose: several documents, an embedded
    `$id`, anchors, a dynamic anchor, an alias, and a pending reference."""
    reg = make_registry(**kwargs)  # type: ignore[arg-type]
    reg.register(dict(SHARED), "urn:shared")
    reg.register(
        {
            "$id": "https://x.example/outer",
            "$defs": {
                "inner": {"$id": "sub/", "$anchor": "here"},
                "dyn": {"$dynamicAnchor": "d"},
                "away": {"$ref": "https://elsewhere.example/thing"},
            },
        },
        "https://x.example/fetched",
    )
    return reg


def _embedding(broken: JsonValue) -> JsonValue:
    """A document that re-registers `SHARED` (legal, it is equal) and then
    hits `broken` — so the walk has real prior entries to rebind first."""
    return {
        "$id": "urn:wrapper",
        "$defs": {"equal": dict(SHARED), "bad": broken},
    }


BAD: list[tuple[str, JsonValue, type[BaseException]]] = [
    ("non-schema value", _embedding("not a schema"), InvalidSchemaError),
    (
        "duplicate anchor in one resource",
        _embedding({"$defs": {"x": {"$anchor": "dup"}, "y": {"$anchor": "dup"}}}),
        DuplicateAnchorError,
    ),
    (
        "anchor kinds collide",
        _embedding({"$defs": {"x": {"$anchor": "n"}, "y": {"$dynamicAnchor": "n"}}}),
        DuplicateAnchorError,
    ),
    (
        "duplicate resource embedded",
        _embedding({"$defs": {"x": {"$id": "urn:twice"}, "y": {"$id": "urn:twice"}}}),
        DuplicateResourceError,
    ),
    (
        "duplicate resource at the root",
        {"$id": "urn:shared", "properties": {"different": {}}},
        DuplicateResourceError,
    ),
    (
        "failure below sub-resources and anchors",
        _embedding(
            {
                "$id": "deep/",
                "$anchor": "one",
                "$defs": {
                    "a": {"$id": "deeper/", "$anchor": "two"},
                    "b": {"$dynamicAnchor": "three"},
                    "c": {"producer": True, "consumer": True},
                    "d": {"$ref": "https://pending.example/x"},
                    "e": {"properties": {"boom": 7}},
                },
            }
        ),
        InvalidSchemaError,
    ),
]


@pytest.mark.parametrize(
    ("schema", "expected"),
    [(s, e) for _, s, e in BAD],
    ids=[name for name, _, _ in BAD],
)
def test_a_failed_registration_restores_every_index(
    schema: JsonValue, expected: type[BaseException]
) -> None:
    reg = _populated()
    before = _fingerprint(reg)
    with pytest.raises(expected):
        reg.register(schema, "urn:attempt")
    assert _fingerprint(reg) == before


def test_max_depth_failure_restores_every_index() -> None:
    nested: JsonValue = {"$anchor": "bottom"}
    for _ in range(8):
        nested = {"properties": {"a": nested}}
    reg = _populated(max_depth=4)
    before = _fingerprint(reg)
    with pytest.raises(MaxDepthExceededError):
        reg.register(_embedding(nested), "urn:deep")
    assert _fingerprint(reg) == before


@pytest.mark.parametrize(
    ("pattern", "expected", "reject"),
    [("(", UnsupportedPatternError, False), ("(a+)+b", UnsafeRegexError, True)],
)
def test_a_regex_screen_failure_restores_every_index(
    pattern: str, expected: type[BaseException], reject: bool
) -> None:
    # The `on_regex` hook fires mid-walk, *after* this keyword's produces
    # and consumes have already been unioned in.
    engine = create_engine(reject_unsafe_regex=reject)
    reg = engine.schemas
    reg.register({"$id": "urn:before", "$anchor": "a"}, "urn:before")
    before = _fingerprint(reg)
    with pytest.raises(expected):
        reg.register({"properties": {"p": {"pattern": pattern}}}, "urn:regex")
    assert _fingerprint(reg) == before


# --- exceptions that are not engine errors ---------------------------------


def _explode(value: JsonValue, _ctx: object) -> StaticFacts:
    raise ValueError("a keyword's analyze() may raise anything")


def _recurse(value: JsonValue, _ctx: object) -> StaticFacts:
    return _recurse(value, _ctx)


@pytest.mark.parametrize(
    ("analyze", "expected"),
    [(_explode, ValueError), (_recurse, RecursionError)],
    ids=["ValueError", "RecursionError"],
)
def test_a_non_engine_exception_still_rolls_back(
    analyze: object, expected: type[BaseException]
) -> None:
    # Pins the `BaseException` breadth: a half-indexed document is equally
    # wrong whichever exception got us there, and caller code runs inside
    # the walk. `_step` also raises bare KeyError/TypeError.
    keywords: Mapping[str, KeywordBehavior] = {
        **KEYWORDS,
        "boom": KeywordBehavior("urn:test:boom", _accept, analyze),  # type: ignore[arg-type]
    }
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, keywords)
    dialects.register_dialect(DIALECT, [VOCAB])
    reg = SchemaRegistry(dialects, DIALECT)
    reg.register({"$id": "urn:kept", "$anchor": "a"}, "urn:kept")
    before = _fingerprint(reg)
    with pytest.raises(expected):
        reg.register({"$id": "urn:boom", "$anchor": "b", "boom": 1}, "urn:boom")
    # Propagates unwrapped — the rollback is not an error-translation layer.
    assert _fingerprint(reg) == before


# --- the specific traps ----------------------------------------------------


def test_a_rebound_entry_is_restored_not_deleted() -> None:
    # The test a delete-the-keys undo fails. A walk may legitimately rebind
    # entries an *earlier* registration owns, so the undo has to put the
    # old values back rather than remove the keys.
    reg = make_registry()
    original: JsonValue = dict(SHARED)
    reg.register(original, "urn:shared")
    anchor_before = reg.resolve_ref("#keep", "urn:shared")

    with pytest.raises(InvalidSchemaError):
        reg.register(_embedding("not a schema"), "urn:wrapper")

    assert reg.document("urn:shared") is original
    assert reg.resolve_ref("#keep", "urn:shared") is anchor_before
    location = reg.document_location("urn:shared")
    assert location is not None
    assert location.document_uri == "urn:shared"


def test_registration_order_survives_a_failure() -> None:
    reg = make_registry()
    reg.register({"$id": "urn:a"}, "urn:a")
    reg.register({"$id": "urn:b"}, "urn:b")
    with pytest.raises(InvalidSchemaError):
        reg.register({"$id": "urn:c", "properties": {"x": 1}}, "urn:c")
    reg.register({"$id": "urn:d"}, "urn:d")
    assert list(reg.resources()) == ["urn:a", "urn:b", "urn:d"]


def test_a_failed_root_claim_leaves_no_alias() -> None:
    # `_aliases` is written before the root's resource claim, so a
    # duplicate root used to leave the retrieval URI aliased to a document
    # that never registered.
    reg = make_registry()
    reg.register({"$id": "urn:taken", "properties": {"a": {}}}, "urn:taken")
    with pytest.raises(DuplicateResourceError):
        reg.register({"$id": "urn:taken", "properties": {"b": {}}}, "urn:fetched")
    assert not reg.has("urn:fetched")


def test_pending_references_are_rolled_back() -> None:
    # Otherwise a later `load_schema` on an unrelated document drains
    # fetches for references only a rolled-back document ever made.
    reg = make_registry()
    with pytest.raises(InvalidSchemaError):
        reg.register(
            {
                "$defs": {
                    "a": {"$ref": "https://ghost.example/never"},
                    "b": {"properties": {"x": 1}},
                }
            },
            "urn:pending",
        )
    assert reg.take_unresolved() == []


def test_index_census() -> None:
    # A twelfth index fails here until `snapshot()` and `_fingerprint` both
    # learn about it.
    reg = SchemaRegistry(DialectRegistry(), DIALECT)
    found = {
        name
        for name, value in vars(reg).items()
        if isinstance(value, dict | set) and name != "_bundled"
    }
    assert found == {
        # Restored by a rollback, and (bar the last) copied by `snapshot()`.
        "_documents",
        "_anchors",
        "_dynamic_anchors",
        "_recursive_roots",
        "_produced_ids",
        "_consumed_ids",
        "_document_dialects",
        "_resource_locations",
        "_document_ranges",
        "_aliases",
        "_pending_resources",
        # Deliberately not rolled back: a pure derived cache, and the two
        # per-walk claim sets that are replaced per transaction anyway.
        "_reference_memo",
        "_claimed_resources",
        "_claimed_anchors",
    }


# --- captured diagnostics --------------------------------------------------


def test_the_error_keeps_a_source_position_with_a_range() -> None:
    # `locate` cannot answer after a rollback, so the position is captured
    # on the way out — including the loader's range, which is plain ints
    # and so pins nothing.
    text = '{"properties": {"a": {"type": "string"}, "b": 7}}'
    loaded = parse_json_with_ranges(text, "urn:ranged")
    engine = create_engine()
    with pytest.raises(InvalidSchemaError) as raised:
        engine.register_schema(loaded.value, "urn:ranged", get_range=loaded.get_range)

    assert engine.locate(raised.value.schema_location or "") is None
    source = raised.value.schema_source
    assert source is not None
    assert source["pointer"] == "/properties/b"
    assert "range" in source
    value = source["range"]["value"]
    assert text[value["start"]["offset"] : value["end"]["offset"]] == "7"


def test_the_error_keeps_its_location_chain() -> None:
    # The ordering the whole design turns on: the chain is read from
    # indexes the undo is about to remove, so it must be captured first.
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
    assert not engine.schemas.has("https://x.example/part/")
