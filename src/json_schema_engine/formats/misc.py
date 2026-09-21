# `uuid` (RFC 4122 §3) and `regex` (ECMA-262 syntax, through the
# workspace's own `ecma_regex` parser).
#
# Dependency direction: standard library, `ecma_regex`, and this package's
# `_abnf`.

from ecma_regex import EcmaRegexSyntaxError, parse
from json_schema_engine.formats._abnf import anchored as _anchored

# --- `uuid` (RFC 4122 §3) -----------------------------------------------
#
# UUID = hex_octet hex_octet hex_octet hex_octet "-"
#        hex_octet hex_octet "-"
#        hex_octet hex_octet "-"
#        hex_octet hex_octet "-"
#        hex_octet hex_octet hex_octet hex_octet hex_octet hex_octet
#      = 8-4-4-4-12 hexadecimal digits.
#
# RFC 4122 §3 fixes the version nibble (13th hex digit) and the variant
# bits (leading bits of the 17th hex digit), but the suite's fixtures
# accept every version/variant combination, including all-zeros and
# `f`-led "variant" nibbles ("hypothetical version 6/15", "a variant
# nibble not defined by RFC 4122 is valid") — so those nibbles are
# matched as plain hex digits like the rest, not pinned to `8|9|a|b` etc.
# Explicit ASCII hex classes only: never `\d`/`\w` (Unicode-aware, and the
# fixture's Bengali-digit and underscore cases must fail), never a
# `uuid.UUID(value)` round trip (it is documented to accept braces,
# `urn:uuid:` prefixes, missing dashes, and non-ASCII decimal digits that
# `int()` normalizes — all invalid here).

_HEX = "[0-9A-Fa-f]"
_UUID_FRAGMENT = rf"{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}"
_UUID_RE = _anchored(_UUID_FRAGMENT)


def uuid(value: str) -> bool:
    """RFC 4122 §3 string form: 8-4-4-4-12 hexadecimal digits."""
    return _UUID_RE.match(value) is not None


# --- `regex` (ECMA-262 syntax) -------------------------------------------
#
# A pattern is a valid `regex` format iff `ecma_regex.parse` accepts it as
# an ECMA-262 pattern (this package's own transcription of ECMA-262 22.2,
# `u`-mode grammar). `parse(value)` is called with no `flags` argument, so
# `flags` defaults to `""`: `ecma_regex.parser._parse_flags` raises
# `UnsupportedPatternError` only for the flag letters `g`, `y`, `d`, `v`
# (stateful/index/set-notation flags this package does not model), never
# for anything reachable from an empty flag string. That makes
# `UnsupportedPatternError` unreachable from this call; it is deliberately
# not caught here and left to propagate (surfacing as a bug in this
# module or in `ecma_regex` itself) rather than being swallowed as if it
# meant "not a regex".


def regex(value: str) -> bool:
    """A syntactically valid ECMA-262 regular expression."""
    try:
        parse(value)
    except EcmaRegexSyntaxError:
        return False
    return True
