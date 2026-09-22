"""RFC 3986 §5 reference resolution, including the §5.4 example tables."""

import re

import pytest

from json_schema_engine.core.uri import (
    has_scheme,
    is_absolute,
    merge,
    pointer_fragment,
    pointer_from_fragment,
    remove_dot_segments,
    resolve,
    schema_location,
    split_fragment,
    strip_fragment,
)

RFC_BASE = "http://a/b/c/d;p?q"

# RFC 3986 §5.4.1, complete and in the RFC's order.
NORMAL_EXAMPLES: list[tuple[str, str]] = [
    ("g:h", "g:h"),
    ("g", "http://a/b/c/g"),
    ("./g", "http://a/b/c/g"),
    ("g/", "http://a/b/c/g/"),
    ("/g", "http://a/g"),
    ("//g", "http://g"),
    ("?y", "http://a/b/c/d;p?y"),
    ("g?y", "http://a/b/c/g?y"),
    ("#s", "http://a/b/c/d;p?q#s"),
    ("g#s", "http://a/b/c/g#s"),
    ("g?y#s", "http://a/b/c/g?y#s"),
    (";x", "http://a/b/c/;x"),
    ("g;x", "http://a/b/c/g;x"),
    ("g;x?y#s", "http://a/b/c/g;x?y#s"),
    ("", "http://a/b/c/d;p?q"),
    (".", "http://a/b/c/"),
    ("./", "http://a/b/c/"),
    ("..", "http://a/b/"),
    ("../", "http://a/b/"),
    ("../g", "http://a/b/g"),
    ("../..", "http://a/"),
    ("../../", "http://a/"),
    ("../../g", "http://a/g"),
]

# RFC 3986 §5.4.2, complete and in the RFC's order. `http:g` takes the
# strict-parser result, which §5.4.2 gives as the primary answer.
ABNORMAL_EXAMPLES: list[tuple[str, str]] = [
    ("../../../g", "http://a/g"),
    ("../../../../g", "http://a/g"),
    ("/./g", "http://a/g"),
    ("/../g", "http://a/g"),
    ("g.", "http://a/b/c/g."),
    (".g", "http://a/b/c/.g"),
    ("g..", "http://a/b/c/g.."),
    ("..g", "http://a/b/c/..g"),
    ("./../g", "http://a/b/g"),
    ("./g/.", "http://a/b/c/g/"),
    ("g/./h", "http://a/b/c/g/h"),
    ("g/../h", "http://a/b/c/h"),
    ("g;x=1/./y", "http://a/b/c/g;x=1/y"),
    ("g;x=1/../y", "http://a/b/c/y"),
    ("g?y/./x", "http://a/b/c/g?y/./x"),
    ("g?y/../x", "http://a/b/c/g?y/../x"),
    ("g#s/./x", "http://a/b/c/g#s/./x"),
    ("g#s/../x", "http://a/b/c/g#s/../x"),
    ("http:g", "http:g"),
]


@pytest.mark.parametrize(("ref", "expected"), NORMAL_EXAMPLES)
def test_rfc3986_normal_examples(ref: str, expected: str) -> None:
    assert resolve(RFC_BASE, ref) == expected


@pytest.mark.parametrize(("ref", "expected"), ABNORMAL_EXAMPLES)
def test_rfc3986_abnormal_examples(ref: str, expected: str) -> None:
    assert resolve(RFC_BASE, ref) == expected


def test_rfc3986_tables_are_complete() -> None:
    # A guard against a future edit quietly dropping rows from either table.
    assert len(NORMAL_EXAMPLES) == 23
    assert len(ABNORMAL_EXAMPLES) == 19


@pytest.mark.parametrize(
    ("base", "ref", "expected"),
    [
        # The case `urllib.parse.urljoin` gets wrong: `urn` is not on its
        # relative-scheme list, so it returns the bare fragment.
        ("urn:uuid:deadbeef", "#/$defs/a", "urn:uuid:deadbeef#/$defs/a"),
        ("urn:uuid:deadbeef", "#", "urn:uuid:deadbeef#"),
        ("urn:uuid:deadbeef", "", "urn:uuid:deadbeef"),
        ("urn:", "#anchor", "urn:#anchor"),
        ("urn:example:schema", "#anchor", "urn:example:schema#anchor"),
        # An absolute reference wins outright, whatever the base is.
        ("urn:uuid:deadbeef", "https://x/y", "https://x/y"),
        # `file:` has an empty authority, so a relative path merges from `/`.
        ("file:///x/y", "../z", "file:///z"),
        ("file:///x/y", "z", "file:///x/z"),
        ("file:///x/y", "/z", "file:///z"),
        ("file://host/x/y", "../z", "file://host/z"),
        # A base fragment is discarded: only the reference contributes one.
        ("https://a/b#frag", "", "https://a/b"),
        ("https://a/b#frag", "#/$defs/x", "https://a/b#/$defs/x"),
        ("https://a/b#frag", "c", "https://a/c"),
        ("https://a/b?q#frag", "", "https://a/b?q"),
        # A schema-relative `$id` against a document base.
        (
            "https://example.com/root.json",
            "child.json",
            "https://example.com/child.json",
        ),
        (
            "https://example.com/a/root.json",
            "../b/c.json",
            "https://example.com/b/c.json",
        ),
        (
            "https://example.com/root.json",
            "#/$defs/x",
            "https://example.com/root.json#/$defs/x",
        ),
        # An authority with no path at all.
        ("https://example.com", "b", "https://example.com/b"),
        ("https://example.com", "#f", "https://example.com#f"),
        # Percent-encoding is passed through untouched, neither decoded nor
        # re-encoded, in the path and in the fragment.
        ("https://a/b%20c/d", "e%2Ff", "https://a/b%20c/e%2Ff"),
        ("https://a/b", "#/$defs/tilde%7E", "https://a/b#/$defs/tilde%7E"),
        # Dot segments are removed, but only as path segments.
        ("https://a/b/c", "%2E%2E/d", "https://a/b/%2E%2E/d"),
    ],
)
def test_resolve(base: str, ref: str, expected: str) -> None:
    assert resolve(base, ref) == expected


def test_empty_reference_keeps_the_query_and_drops_the_fragment() -> None:
    assert resolve("https://a/b?q=1#frag", "") == "https://a/b?q=1"
    assert resolve("https://a/b?q=1#frag", "?q=2") == "https://a/b?q=2"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", ""),
        ("/", "/"),
        (".", ""),
        ("..", ""),
        ("/a/b/c/./../../g", "/a/g"),
        ("mid/content=5/../6", "mid/6"),
        ("/../../../a", "/a"),
        ("/a/..", "/"),
        ("/a/.", "/a/"),
        ("a/b/", "a/b/"),
    ],
)
def test_remove_dot_segments(path: str, expected: str) -> None:
    assert remove_dot_segments(path) == expected


@pytest.mark.parametrize(
    ("authority", "base_path", "ref_path", "expected"),
    [
        (None, "/b/c/d;p", "g", "/b/c/g"),
        ("a", "", "g", "/g"),
        (None, "", "g", "g"),
        (None, "b", "g", "g"),
        ("a", "/", "g", "/g"),
    ],
)
def test_merge(
    authority: str | None, base_path: str, ref_path: str, expected: str
) -> None:
    assert merge(authority, base_path, ref_path) == expected


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        # Absent fragment and empty fragment are different answers; this is
        # the distinction `urllib.parse.urldefrag` cannot express, and
        # `$ref: "#"` depends on it.
        ("https://a/b", ("https://a/b", None)),
        ("https://a/b#", ("https://a/b", "")),
        ("#", ("", "")),
        ("", ("", None)),
        ("https://a/b#/$defs/x", ("https://a/b", "/$defs/x")),
        ("https://a/b#anchor", ("https://a/b", "anchor")),
        ("urn:uuid:x#", ("urn:uuid:x", "")),
        # Only the first `#` splits; the rest belongs to the fragment.
        ("https://a/b#x#y", ("https://a/b", "x#y")),
        # The fragment is handed back exactly as written, still encoded.
        ("https://a/b#%2F", ("https://a/b", "%2F")),
    ],
)
def test_split_fragment(uri: str, expected: tuple[str, str | None]) -> None:
    assert split_fragment(uri) == expected


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("https://a/b", "https://a/b"),
        ("https://a/b#", "https://a/b"),
        ("https://a/b#/x", "https://a/b"),
        ("#/x", ""),
    ],
)
def test_strip_fragment(uri: str, expected: str) -> None:
    assert strip_fragment(uri) == expected


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("https://a/b", True),
        ("urn:uuid:x", True),
        ("file:///x", True),
        ("a+b-c.d:x", True),
        ("HTTPS://a", True),
        ("", False),
        ("//a/b", False),
        ("/a/b", False),
        ("a/b", False),
        ("#frag", False),
        # A scheme must start with a letter and may not contain `/` before
        # the colon, so neither of these is scheme-prefixed.
        ("1a:b", False),
        ("a/b:c", False),
    ],
)
def test_has_scheme(uri: str, expected: bool) -> None:
    assert has_scheme(uri) is expected


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("https://a/b", True),
        ("urn:uuid:x", True),
        # RFC 3986 §4.3: an absolute URI carries no fragment.
        ("https://a/b#", False),
        ("https://a/b#x", False),
        ("/a/b", False),
    ],
)
def test_is_absolute(uri: str, expected: bool) -> None:
    assert is_absolute(uri) is expected


# --- pointer <-> fragment (P10) --------------------------------------------

# Left column is the plain-text JSON Pointer (RFC 6901 escaping already
# applied); right column is its URI fragment form (RFC 3986 `fragment`).
FRAGMENT_CASES: list[tuple[str, str]] = [
    # The root pointer and every ordinary one survive untouched, which is
    # what keeps locations readable in the common case.
    ("", ""),
    ("/properties/a", "/properties/a"),
    ("/$defs/x", "/$defs/x"),
    ("/items/0/allOf/1", "/items/0/allOf/1"),
    # `~0`/`~1` are pointer syntax, not URI syntax: RFC 6901 escaping has
    # already happened and must not be touched again.
    ("/properties/a~1b", "/properties/a~1b"),
    ("/properties/a~0b", "/properties/a~0b"),
    # `sub-delims`, `:` and `@` are all legal in a fragment, so a member
    # name made of them costs nothing.
    ("/properties/c:d@e", "/properties/c:d@e"),
    ("/properties/!$&'()*+,;=", "/properties/!$&'()*+,;="),
    ("/properties/-._~", "/properties/-._~"),
    # The characters RFC 3986 excludes from a fragment.
    ("/properties/a b", "/properties/a%20b"),
    ('/properties/a"b', "/properties/a%22b"),
    ("/properties/a<b>c", "/properties/a%3Cb%3Ec"),
    ("/properties/a\\b", "/properties/a%5Cb"),
    ("/properties/a^b", "/properties/a%5Eb"),
    ("/properties/a`b", "/properties/a%60b"),
    ("/properties/{x}", "/properties/%7Bx%7D"),
    ("/properties/a|b", "/properties/a%7Cb"),
    # `#` would end the fragment and `%` would make the rest of it a
    # percent-escape: the two that corrupt rather than merely offend.
    ("/properties/a#b", "/properties/a%23b"),
    ("/properties/100%", "/properties/100%25"),
    ("/properties/%2F", "/properties/%252F"),
    # Controls, and non-ASCII as UTF-8 bytes (a URI, not an IRI — P10).
    ("/properties/a\nb", "/properties/a%0Ab"),
    ("/properties/名前", "/properties/%E5%90%8D%E5%89%8D"),
    ("/properties/é", "/properties/%C3%A9"),
]


@pytest.mark.parametrize(("pointer", "fragment"), FRAGMENT_CASES)
def test_pointer_fragment(pointer: str, fragment: str) -> None:
    assert pointer_fragment(pointer) == fragment


@pytest.mark.parametrize(("pointer", "fragment"), FRAGMENT_CASES)
def test_pointer_from_fragment_is_the_inverse(pointer: str, fragment: str) -> None:
    assert pointer_from_fragment(fragment) == pointer
    assert pointer_from_fragment(pointer_fragment(pointer)) == pointer


def test_encoded_fragment_is_a_legal_uri_fragment() -> None:
    # RFC 3986: `fragment = *( pchar / "/" / "?" )`. Nothing outside that
    # production may survive encoding, for any of the cases above.
    legal = re.compile(r"^(?:[A-Za-z0-9\-._~!$&'()*+,;=:@/?]|%[0-9A-Fa-f]{2})*$")
    for pointer, _ in FRAGMENT_CASES:
        assert legal.match(pointer_fragment(pointer)), pointer


def test_schema_location_joins_base_and_encoded_pointer() -> None:
    assert schema_location("https://x.example/s", "") == "https://x.example/s#"
    assert (
        schema_location("https://x.example/s", "/properties/a")
        == "https://x.example/s#/properties/a"
    )
    assert (
        schema_location("urn:uuid:deadbeef", "/properties/100%")
        == "urn:uuid:deadbeef#/properties/100%25"
    )


def test_schema_location_round_trips_through_split_fragment() -> None:
    # The pair that `Engine.locate` and `SchemaRegistry._split` rely on:
    # splitting an emitted location and decoding its fragment gives back
    # the base and pointer it was built from.
    for pointer, _ in FRAGMENT_CASES:
        base = "https://round.example/s"
        resource, fragment = split_fragment(schema_location(base, pointer))
        assert resource == base
        assert fragment is not None
        assert pointer_from_fragment(fragment) == pointer
