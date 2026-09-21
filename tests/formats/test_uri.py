# Direct-call coverage for `json_schema_engine.formats.uri` (M7 Step 1):
# the non-obvious cases the official suite's own uri/uri-reference/iri/
# iri-reference/uri-template fixtures pin (reg-name fallback for
# structurally-invalid IPv4, strict IP-literal parsing inside brackets,
# `segment-nz-nc`'s no-colon rule, percent-encoding strictness, the
# ucschar/iprivate split between `uri`/`iri` and between query/fragment)
# — a compact matrix, not a restatement of the suite — plus a
# regex-backtracking budget test for pathological input.

import time
from collections.abc import Callable

import pytest

from json_schema_engine.formats.uri import (
    iri,
    iri_reference,
    uri,
    uri_reference,
    uri_template,
)

type Predicate = Callable[[str], bool]

CASES: tuple[tuple[Predicate, str, bool], ...] = (
    # `uri`: a failed IP-literal/IPv4address host falls back to reg-name,
    # which admits digits and dots freely (RFC 3986 §3.2.2).
    (uri, "http://999.999.999.999/", True),
    (uri, "http://087.10.0.1/", True),
    # ...but inside "[...]" there is no reg-name fallback: only a strict
    # IPv6address/IPvFuture is admitted, so a leading zero in an embedded
    # IPv4 octet (dec-octet has no such alternative) is invalid.
    (uri, "http://[::ffff:01.2.3.4]", False),
    # A single "/" after the scheme is path-absolute, not "//authority" -
    # square brackets aren't in `pchar`, so an IP-literal-shaped path
    # segment is invalid, with or without a scheme.
    (uri, "http:/[::1]", False),
    (uri_reference, "/[::1]", False),
    # `path-noscheme`'s first segment (`segment-nz-nc`) forbids ":", so a
    # bare "1:b" is neither a URI (scheme must start with ALPHA) nor a
    # relative-path reference; preceding it with a dot-segment fixes that.
    (uri_reference, "1:b", False),
    (uri_reference, "./this:that", True),
    # `relative-part` includes path-empty, so "//" (an empty-authority
    # network-path reference) is a valid reference on its own.
    (uri_reference, "//", True),
    (uri, "\\\\WINDOWS\\fileshare", False),
    # `pct-encoded` is exactly "%" HEXDIG HEXDIG - no non-hex digits, no
    # incomplete triplets, no lone "%".
    (uri, "http://example.com/%6G", False),
    (uri, "http://example.com/%A", False),
    (uri, "http://example.com/%", False),
    # A comma isn't in `scheme`'s tail character class.
    (uri, "bar,baz:foo", False),
    # Neither `userinfo` nor `reg-name` admits a literal "@": a second "@"
    # in the authority has nowhere valid to land.
    (uri_reference, "//a@b@example.com/", False),
    # `port` is `*DIGIT`; non-digit text after the authority's ":" can't
    # be consumed as a port, and reg-name admits no colon either.
    (uri, "http://example.com:abc/path", False),
    # No production in the fragment grammar admits a literal backslash.
    (uri_reference, "#frag\\ment", False),
    # No production anywhere admits %x0A; `\Z` (never `$`) enforces this.
    (uri, "http://foo.bar/\n", False),
    # `iri`/`iri-reference`: ucschar is folded into `iunreserved`
    # everywhere `unreserved` appears (host, path, ...), including
    # supplementary-plane characters (a plane-1 ucschar range).
    (iri, "http://ƒøø.ßår/\U00010300", True),
    (uri, "http://ƒøø.ßår/\U00010300", False),
    # A relative IRI reference has no scheme to anchor "iri" vs.
    # "iri-reference" on, so a bare non-ASCII relative path is a valid
    # iri-reference but not a valid (absolute) iri.
    (iri_reference, "âππ", True),
    (iri, "âππ", False),
    # `uri-template`: RFC 6570 §2's varspec/expression grammar.
    (uri_template, "{v:1000}", True),
    (uri_template, "{v:10000}", False),  # five-digit max-length
    (uri_template, "{v:0}", False),  # max-length can't be "0"
    (uri_template, "{v:01}", False),  # max-length can't have a leading zero
    (uri_template, "{a..b}", False),  # a doubled "." in varname
    (uri_template, "{a,,b}", False),  # an empty varspec in the list
    (uri_template, "{a,}", False),  # a trailing comma in the list
    (uri_template, "{}", False),  # an expression needs at least one varspec
    (uri_template, "{term", False),  # unclosed brace
    (uri_template, "foo}bar", False),  # unmatched closing brace
    (uri_template, "{%}", False),  # lone "%" in a varname
    (uri_template, "{%4}", False),  # incomplete pct-encoded triplet
    (uri_template, "{%GG}", False),  # non-hex pct-encoded triplet
    (uri_template, "a%41b", True),  # pct-encoded triplet in a literal
    (uri_template, "a%", False),  # lone "%" in a literal
    (uri_template, "a%4", False),  # incomplete pct-encoded triplet
    (uri_template, "a%GG", False),  # non-hex pct-encoded triplet
    (uri_template, "a\U0001f600b", True),  # supplementary-plane literal (ucschar)
    (uri_template, "", True),  # the empty template
    (uri_template, "a b", False),  # a space is not a literal character
    (uri_template, "ab", False),  # DEL is not a literal character
)


@pytest.mark.parametrize(
    "predicate,value,expected",
    CASES,
    ids=[f"{fn.__name__}:{value!r}" for fn, value, _ in CASES],
)
def test_case(predicate: Predicate, value: str, expected: bool) -> None:
    assert predicate(value) is expected


def test_uri_budget() -> None:
    # A long reg-name host followed by a path segment full of characters
    # that are each one hexdigit short of a valid pct-encoded triplet:
    # a grammar with catastrophic alternation would thrash trying to
    # re-split `pchar*`'s consumption once the trailing text can't be
    # completed.
    value = "http://" + "a" * 20000 + "/" + "b%" * 5000
    start = time.perf_counter()
    result = uri(value)
    assert time.perf_counter() - start < 0.5
    assert result is False


def test_uri_reference_budget() -> None:
    # A reference built almost entirely of path separators forces the
    # maximum number of `path-abempty` iterations the grammar allows (one
    # empty segment per "/"), with a long final segment - a grammar with
    # catastrophic nested-star backtracking would thrash here even though
    # the parse is actually unambiguous (a valid network-path reference:
    # many empty segments, then one non-empty segment of "a"s).
    value = "/" * 25000 + "a" * 25000
    start = time.perf_counter()
    result = uri_reference(value)
    assert time.perf_counter() - start < 0.5
    assert result is True
