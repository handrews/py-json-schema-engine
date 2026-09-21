# Cross-cutting format edge cases (M7 Step 3): one consolidated,
# suite-independent matrix of the cases most likely to regress across a
# suite bump, pinning the three validation surfaces together — the
# interpreter (`create_engine(formats=..., assert_formats=True)` +
# `register_schema`/`evaluate`), both compiled-artifact optimization
# settings (`compile_validator`), and the standalone emitter
# (`emit_standalone`, exec'd into a namespace) — so a divergence between
# any two surfaces shows up here even if each surface's own suite/direct
# tests stay green.
#
# This is not a restatement of `test_datetime.py`/`test_uri.py`/
# `test_net.py`/`test_pointer_misc.py` (those hold the per-family direct-
# call matrices; read them first) — a case appearing in both places is
# deliberate where the point here is the engine/compiler/standalone
# surfaces agreeing, not the predicate's own correctness.
#
# IP policy (DESIGN.md D15): every row is derived from the format RFCs and
# the official test suite's own fixtures (see the per-row comments); no
# third-party validator was read.

from collections.abc import Callable
from typing import cast

import pytest

from json_schema_engine.compiler import (
    CompiledValidator,
    compile_validator,
    emit_standalone,
)
from json_schema_engine.core import DIALECT_2020_12, Engine, JsonValue, create_engine
from json_schema_engine.formats import format_table_for

type Validator = Callable[[JsonValue], bool]

_TABLE = format_table_for(DIALECT_2020_12)

# --- per-format-name caches (module-level: the ~60+ rows share a handful
# of distinct format names, so each engine/artifact pair is built once) --

_ENGINE_CACHE: dict[str, tuple[Engine, str]] = {}
_ARTIFACT_CACHE: dict[str, tuple[CompiledValidator, CompiledValidator]] = {}
_STANDALONE_CACHE: dict[str, Validator] = {}


def _engine_for(format_name: str) -> tuple[Engine, str]:
    cached = _ENGINE_CACHE.get(format_name)
    if cached is None:
        engine = create_engine(formats=_TABLE, assert_formats=True)
        uri = engine.register_schema(
            {"format": format_name}, f"https://edge.example/{format_name}"
        )
        cached = (engine, uri)
        _ENGINE_CACHE[format_name] = cached
    return cached


def _artifacts_for(format_name: str) -> tuple[CompiledValidator, CompiledValidator]:
    cached = _ARTIFACT_CACHE.get(format_name)
    if cached is None:
        engine, uri = _engine_for(format_name)
        cached = (
            compile_validator(engine, uri),
            compile_validator(engine, uri, conservative=True),
        )
        _ARTIFACT_CACHE[format_name] = cached
    return cached


def _standalone_for(format_name: str) -> Validator:
    cached = _STANDALONE_CACHE.get(format_name)
    if cached is None:
        engine, uri = _engine_for(format_name)
        source = emit_standalone(engine, uri)
        namespace: dict[str, object] = {}
        exec(compile(source, f"<standalone:{format_name}>", "exec"), namespace)
        cached = cast(Validator, namespace["validate"])
        _STANDALONE_CACHE[format_name] = cached
    return cached


def _check(format_name: str, value: JsonValue, expected: bool) -> None:
    engine, uri = _engine_for(format_name)
    assert engine.evaluate(uri, value).valid is expected, (
        "interpreter",
        format_name,
        value,
    )
    fast, conservative = _artifacts_for(format_name)
    assert fast.validate(value) is expected, ("compiled", format_name, value)
    assert conservative.validate(value) is expected, (
        "compiled (conservative)",
        format_name,
        value,
    )
    standalone = _standalone_for(format_name)
    assert standalone(value) is expected, ("standalone", format_name, value)


# --- the matrix --------------------------------------------------------
#
# (format_name, value, expected); grouped and commented by the rule each
# row pins. Values shared with a per-family direct-call test are
# deliberate (see the module docstring).

CASES: tuple[tuple[str, JsonValue, bool], ...] = (
    # `time`/`date-time`: leap-second validity is `second == 60` tied to a
    # UTC-equivalent wall clock of 23:59, per offset sign.
    ("time", "23:59:60Z", True),
    ("time", "01:29:60+01:30", True),
    ("time", "15:59:60-08:00", True),
    ("time", "00:29:60-23:30", True),
    ("time", "23:29:60+23:30", True),
    ("time", "23:59:60+01:00", False),
    ("time", "22:59:60Z", False),
    ("time", "24:59:00+01:00", False),  # hour 24 rejected before any leap check
    ("time", "23:59:60-00:30", False),
    ("date-time", "1998-12-31T15:59:60.123-08:00", True),
    ("date-time", "2016-12-31T24:59:60+01:00", False),
    # RFC 3339 §5.6: "T"/"Z" are case-insensitive.
    ("date-time", "1963-06-19t08:30:06.283185z", True),
    # Non-ASCII digits are never accepted (explicit `[0-9]` classes
    # throughout rule out Bengali/Arabic-Indic digits, `re`'s Unicode-aware
    # matching notwithstanding).
    ("date", "২020-01-01", False),
    ("time", "২3:59:59Z", False),
    ("ipv4", "১27.0.0.1", False),
    ("ipv6", "২001:db8::1", False),
    ("relative-json-pointer", "١/foo", False),  # noqa: RUF001 -- ARABIC-INDIC DIGIT ONE
    ("uuid", "২eb8aa08-aa98-11ea-b4aa-73b441d16380", False),
    # `\Z` (never `$`) anchors the end: a trailing newline is invalid.
    ("date", "2020-01-01\n", False),
    ("time", "00:00:00Z\n", False),
    ("duration", "P1D\n", False),
    ("ipv4", "127.0.0.1\n", False),
    ("ipv6", "::1\n", False),
    ("hostname", "example.com\n", False),
    ("uri", "http://example.com/\n", False),
    ("email", "test@iana.org\n", False),
    ("uuid", "2eb8aa08-aa98-11ea-b4aa-73b441d16380\n", False),
    # A NUL byte after an otherwise-valid string is invalid.
    ("date", "2020-01-01\x00", False),
    # `duration` (RFC 3339 Appendix A): a bare month can't be skipped to
    # reach a day, hours can't skip to seconds, a week can't combine with
    # a zero-valued other component, and a date component can't be
    # followed by a bare digit (unanchored leftover) before its "T".
    ("duration", "P1Y2D", False),
    ("duration", "PT1H2S", False),
    ("duration", "P0Y1W", False),
    ("duration", "P1D2T3H", False),
    ("duration", "PT0.5S", False),  # no fraction in `dur-second`
    # ...but a bare month unit is valid in the date position (day follows),
    # an hour count has no upper bound, and a day count has no leading-zero
    # restriction (duration components are plain `1*DIGIT`, not `2DIGIT`).
    ("duration", "P1M2D", True),
    ("duration", "PT36H", True),
    ("duration", "P01D", True),
    # `uri-template` (RFC 6570 §2): the suite widens `literal` to admit an
    # apostrophe; a `max-length` modifier is 1-4 digits, no leading zero.
    ("uri-template", "a'b", True),
    ("uri-template", "{a..b}", False),  # a doubled "." in varname
    ("uri-template", "{v:01}", False),  # leading zero
    ("uri-template", "{v:10000}", False),  # five digits
    ("uri-template", "{v:1000}", True),
    # `uri`: a failed IP-literal/IPv4address host falls back to reg-name
    # (admits digits/dots freely); inside "[...]" there is no fallback, so
    # a leading zero in an embedded IPv4 octet is invalid there.
    ("uri", "http://999.999.999.999/", True),
    ("uri", "http://087.10.0.1/", True),
    ("uri", "http://[::ffff:01.2.3.4]", False),
    # A single "/" after the scheme is path-absolute; square brackets
    # aren't in `pchar`.
    ("uri", "http:/[::1]", False),
    ("uri", "\\\\WINDOWS\\fileshare", False),
    # `pct-encoded` is exactly "%" HEXDIG HEXDIG.
    ("uri", "%A", False),
    # `uri-reference`: `relative-part` includes path-empty ("//" alone is
    # a valid network-path reference); `path-noscheme`'s first segment
    # forbids ":", fixed by a leading dot-segment.
    ("uri-reference", "//", True),
    ("uri-reference", "./this:that", True),
    ("uri-reference", "1:b", False),
    # `iri`/`iri-reference`: ucschar folds into `iunreserved` everywhere,
    # including supplementary-plane characters; a relative reference has
    # no scheme to anchor "iri" (absolute) vs. "iri-reference" on.
    ("iri", "http://ƒøø.ßår/𐌀", True),
    ("iri", "âππ", False),
    ("iri-reference", "âππ", True),
    # `email`: a quoted local part can hide "@"; address literals accept
    # a case-insensitive "IPv6:" tag or a bare IPv4 literal, never a
    # General-address-literal or a stray prefix before "[...]"; a
    # trailing-dot domain and any non-ASCII character are both invalid.
    ("email", '"joe@bloggs"@example.com', True),
    ("email", "a@[ipv6:::1]", True),
    ("email", "test@255.255.255.255", True),
    ("email", "test@a[255.255.255.255]", False),
    ("email", "test@iana.org.", False),  # trailing-dot domain
    ("email", "aé@iana.org", False),
    ("email", "a＠iana.org", False),  # noqa: RUF001 -- fullwidth "@" is not a separator
    # `idn-email`: non-ASCII is admitted, with no IDNA normalization (an
    # NFD domain is left as-is); a fullwidth "@" still isn't a separator.
    ("idn-email", "user@café.com", True),  # NFD "café"
    ("idn-email", "user＠example.com", False),  # noqa: RUF001
    # `ipv6`: a zone id is not part of the text form; an embedded IPv4
    # octet with a leading zero is invalid; 8 explicit groups leave no
    # room for "::" to compress anything.
    ("ipv6", "fe80::a%eth1", False),
    ("ipv6", "::ffff:192.168.0.01", False),
    ("ipv6", "1:2:3:4:5:6:7:8::", False),
    ("ipv6", "2001:0db8:0000:0000:0000:0000:0000:0001", True),
    # `ipv4`: exactly four decimal octets, no hex, no trailing junk.
    ("ipv4", "127.1", False),
    ("ipv4", "0x7f.0.0.1", False),
    ("ipv4", "192.168.0.1\x00.evil.com", False),
    # `hostname`: consecutive hyphens inside a label and a leading digit
    # are fine; a confusable-but-not-identical code point (KELVIN SIGN,
    # FULLWIDTH FULL STOP) and an underscore are not.
    ("hostname", "a--b.com", True),
    ("hostname", "1host", True),
    ("hostname", "\N{KELVIN SIGN}elvin.example.com", False),  # KELVIN SIGN, not ASCII K
    ("hostname", "example．com", False),  # noqa: RUF001 -- fullwidth full stop
    ("hostname", "host_name", False),
    # `json-pointer`: "~" only ever precedes "0"/"1"; empty segments and
    # the empty pointer are valid; a fragment-identifier "#" form is not a
    # json-pointer at all.
    ("json-pointer", "/foo/bar~", False),
    ("json-pointer", "/~2", False),
    ("json-pointer", "a", False),
    ("json-pointer", "#", False),
    ("json-pointer", "/foo//bar", True),
    ("json-pointer", "/", True),
    ("json-pointer", "", True),
    # `regex` (ECMA-262 syntax through `ecma_regex`): named-group/
    # backreference and variable-width lookbehind syntax, and an empty
    # character class, are valid; Python-only syntax and an unescaped
    # dangling "[" are not.
    ("regex", "(?<=a+)b", True),
    ("regex", "[]", True),
    ("regex", "\\cA", True),
    ("regex", "(?P<n>x)", False),
    ("regex", "\\a", False),
    ("regex", "^(abc]", False),
    # An unrecognized format name is never asserted in any standard
    # dialect (`assert_formats=True` is best-effort): every instance type
    # is valid.
    ("not-a-format", "anything at all", True),
    ("not-a-format", 12, True),
    ("not-a-format", None, True),
)


@pytest.mark.parametrize(
    ("format_name", "value", "expected"),
    CASES,
    ids=[f"{name}:{value!r}" for name, value, _ in CASES],
)
def test_case(format_name: str, value: JsonValue, expected: bool) -> None:
    _check(format_name, value, expected)


# --- IDNA-dependent cases (need the optional `idna` extra) --------------
#
# `idn-hostname` is marked `unavailable` without the extra (asserting it
# fails at registration), and `hostname`'s own `xn--` check degrades to
# "any LDH-valid A-label is accepted" without it — so this whole block is
# skipped, not merely individual rows, when `idna` isn't installed.

IDNA_CASES: tuple[tuple[str, JsonValue, bool], ...] = (
    # `hostname`: an `xn--` label is only a valid host label if it is a
    # canonical A-label (round-trips through IDNA2008 decode/re-encode).
    ("hostname", "xn--ll-0ea", True),  # MIDDLE DOT with surrounding 'l's
    ("hostname", "xn--nxasmq6b", True),
    ("hostname", "xn---9uc", False),  # non-canonical Punycode
    ("hostname", "xn--example-", False),  # decodes to only ASCII
    ("hostname", "XN--aa---o47jg78q", False),  # "--" in 3rd/4th position
    ("hostname", "xn--X", False),  # invalid Punycode
    # `idn-hostname` (RFC 5890/5891, UTS 46 mapping): fullwidth/ignorable
    # characters are mapped away, separators come in four forms, and the
    # RFC 5893 bidi rule and joiner-context rules apply per label.
    ("idn-hostname", "ｘｎ--nxasmq6b", True),  # noqa: RUF001 -- ACE prefix, decoded as A-label
    ("idn-hostname", "a​b", True),  # zero-width space ignored by mapping
    ("idn-hostname", "１２３", True),  # noqa: RUF001 -- fullwidth digits mapped to ASCII
    ("idn-hostname", "café.com", True),  # non-NFC U-label, valid after UTS 46
    ("idn-hostname", "ب٠.ب۰", True),  # Arabic-Indic digit blocks in different labels
    ("idn-hostname", "a。b", True),  # ideographic full stop separator
    ("idn-hostname", "a．b", True),  # noqa: RUF001 -- fullwidth full stop separator
    ("idn-hostname", "a｡b", True),  # halfwidth ideographic full stop separator
    ("idn-hostname", "0a.א", False),  # Bidi domain, digit-first label
    ("idn-hostname", "٠١", False),  # noqa: RUF001 -- Arabic-Indic digits only
    ("idn-hostname", "a..b", False),  # empty label between two dots
    ("idn-hostname", "。", False),  # single ideographic full stop
    ("idn-hostname", "a。", False),  # trailing separator: empty final label
    ("idn-hostname", "xn---9uc", False),  # non-canonical Punycode
    ("idn-hostname", "क्‌षx‌y", False),  # ZWNJ must pass at every occurrence
    # A label that is only too long once its separator is folded in with
    # the rest (51 Greek letters, then a plain "." worth of length via a
    # non-ASCII separator) is still within the 63-octet label limit.
    ("idn-hostname", "α" * 51 + "。com", True),  # noqa: RUF001
)


@pytest.mark.parametrize(
    ("format_name", "value", "expected"),
    IDNA_CASES,
    ids=[f"{name}:{value!r}" for name, value, _ in IDNA_CASES],
)
def test_idna_case(format_name: str, value: JsonValue, expected: bool) -> None:
    pytest.importorskip("idna")
    _check(format_name, value, expected)


# --- format never applies to a non-string instance ----------------------

NON_STRING_INSTANCES: tuple[JsonValue, ...] = (12, {}, [], None, True)

_ALL_FORMAT_NAMES = sorted({name for name, _, _ in CASES})
_IDNA_FORMAT_NAMES = sorted({name for name, _, _ in IDNA_CASES})


@pytest.mark.parametrize("format_name", _ALL_FORMAT_NAMES)
@pytest.mark.parametrize("instance", NON_STRING_INSTANCES, ids=repr)
def test_non_string_instances_are_always_valid(
    instance: JsonValue, format_name: str
) -> None:
    _check(format_name, instance, True)


@pytest.mark.parametrize("format_name", _IDNA_FORMAT_NAMES)
@pytest.mark.parametrize("instance", NON_STRING_INSTANCES, ids=repr)
def test_non_string_instances_are_always_valid_idna(
    instance: JsonValue, format_name: str
) -> None:
    pytest.importorskip("idna")
    _check(format_name, instance, True)
