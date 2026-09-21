# Direct-call coverage for `json_schema_engine.formats.net` (M7 Step 1):
# the non-obvious cases the official suite's own ipv6/hostname/email/
# idn-email fixtures already pin (zone ids and bracketed forms rejected,
# leading zeros in an embedded IPv4 octet rejected, non-ASCII digits
# rejected, `email` vs `idn_email` diverging on non-ASCII, and the
# quoted-local-part `@`-splitting rule) — a compact matrix, not a
# restatement of the suite — plus a budget test for pathological input.

import time
from collections.abc import Callable

import pytest

from json_schema_engine.formats.net import email, hostname, idn_email, ipv6

type Predicate = Callable[[str], bool]

CASES: tuple[tuple[Predicate, str, bool], ...] = (
    # `ipv6`: zone ids and bracketed/netmask forms are not part of RFC
    # 4291 §2.2's text form, even though `ipaddress.IPv6Address` itself
    # accepts a zone id.
    (ipv6, "fe80::a%eth1", False),
    (ipv6, "[::1]", False),
    (ipv6, "fe80::/64", False),
    # IPv4-mapped forms are valid; a leading zero in the embedded IPv4's
    # last octet is not (`ipaddress` treats it as ambiguous/octal-like).
    (ipv6, "::ffff:192.168.0.1", True),
    (ipv6, "::ffff:192.168.0.01", False),
    # Leading zeros within a hex group (not an embedded IPv4 octet) are
    # fine.
    (ipv6, "2001:0db8:0000:0000:0000:0000:0000:0001", True),
    # 8 groups already present leaves no room for "::" to compress
    # anything.
    (ipv6, "1:2:3:4:5:6:7:8::", False),
    # Trailing whitespace/newline is invalid; `\Z` (never `$`) is what
    # `_anchored`/`ipaddress` parsing both effectively enforce here.
    (ipv6, "::1\n", False),
    (ipv6, "::1  ", False),
    # Non-ASCII digits are never accepted, in a hex group or an embedded
    # IPv4 octet alike.
    (ipv6, "1:2:3:4:5:6:7:৪", False),  # noqa: RUF001
    (ipv6, "1:2::192.16৪.0.1", False),  # noqa: RUF001
    # `hostname`: an `xn--` label is only LDH-checked in Step 1 (the lead's
    # `idna_.a_label_ok` stub accepts any LDH-valid A-label unconditionally
    # until Step 2), so a well-formed-looking A-label passes here even
    # though a real IDNA2008 check would reject some of these.
    (hostname, "xn--9n2bp8q.xn--9t4b11yi5a", True),
    (hostname, "a--b.com", True),
    (hostname, "1host", True),
    (hostname, "example.com\n", False),
    (hostname, "Kelvin.example.com", False),  # noqa: RUF001 -- KELVIN SIGN
    (hostname, "example．com", False),  # noqa: RUF001 -- fullwidth full stop
    # `email`: quoted local parts can hide `@`, `.`, and whitespace; the
    # closing quote must be followed immediately by `@`.
    (email, '"joe@bloggs"@example.com', True),
    (email, '""@iana.org', True),
    (email, '"\\\\"@iana.org', True),
    (email, '"test\\test@iana.org', False),  # unclosed quote
    (email, '"test"test@iana.org', False),  # trailing text after the quote
    (email, "a@b@c.org", False),  # second "@" lands in (and breaks) the domain
    (email, "test\\@test@iana.org", False),  # backslash-escaped "@" unquoted
    # Address literals: `IPv6:` tag is case-insensitive; a bare IPv4
    # literal has no tag; General-address-literal (any other tag) is
    # rejected outright.
    (email, "joe.bloggs@[IPv6:::1]", True),
    (email, "a@[ipv6:::1]", True),
    (email, "test@255.255.255.255", True),
    (email, "test@io", True),
    (email, "test@[RFC-5322-domain-literal]", False),
    (email, "a@[]", False),
    (email, "test@a[255.255.255.255]", False),
    (email, "[1.2.3.4]@iana.org", False),
    (email, "iana.org.", False),  # not even an email (no "@")
    # ASCII-only: `email` rejects any non-ASCII character anywhere.
    (email, "aé@iana.org", False),
    (email, "a＠iana.org", False),  # noqa: RUF001 -- fullwidth "@" is not a separator
    (email, "test@iana.org\n", False),
    (email, "test@iana.org\r", False),
    # `idn_email`: the same structure, but non-ASCII is admitted in the
    # local part and in domain labels, with no IDNA normalization.
    (idn_email, "실례@실례.테스트", True),
    (idn_email, "user@café.com", True),  # NFD, left as-is
    (idn_email, '"δοκιμή"@example.com', True),
    (idn_email, "￿@example.com", True),  # noncharacter, valid in idn_email
    (idn_email, "user＠example.com", False),  # noqa: RUF001 -- fullwidth "@"
    (idn_email, "2962", False),
)


@pytest.mark.parametrize(
    "predicate,value,expected",
    CASES,
    ids=[f"{fn.__name__}:{value!r}" for fn, value, _ in CASES],
)
def test_case(predicate: Predicate, value: str, expected: bool) -> None:
    assert predicate(value) is expected


def test_email_budget() -> None:
    value = "a" * 20000 + "@" + "b." * 5000
    start = time.perf_counter()
    result = email(value)
    assert time.perf_counter() - start < 0.5
    assert result is False


def test_hostname_budget() -> None:
    value = "a." * 30000
    start = time.perf_counter()
    result = hostname(value)
    assert time.perf_counter() - start < 0.5
    assert result is False
