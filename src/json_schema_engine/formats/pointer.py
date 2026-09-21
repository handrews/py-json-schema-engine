# JSON Pointer formats (M7): `json-pointer` (RFC 6901 §3) and
# `relative-json-pointer` (the Relative JSON Pointer draft).
#
# Dependency direction: standard library and this package's `_abnf`.

from json_schema_engine.formats._abnf import anchored as _anchored

# --- `json-pointer` (RFC 6901 §3) --------------------------------------
#
# json-pointer    = *( "/" reference-token )
# reference-token = *( unescaped / escaped )
# unescaped       = %x00-2E / %x30-7D / %x7F-10FFFF
#                   ; %x2F ('/') and %x7E ('~') excluded
# escaped         = "~" ( "0" / "1" )
#
# `unescaped` is "any character except '/' and '~'", including raw
# control characters (the suite's fixture keeps a NUL, LF and TAB in a
# valid pointer: escaping is a JSON *string* concern, already undone by
# the time this predicate sees the value) and non-BMP characters (`re`
# matches those against `[^/~]` as single characters, no `re.UNICODE`
# caveat applies since this isn't `\d`/`\w`/`\s`). A "~" is only ever
# followed by "0" or "1"; anything else (including end of string) fails
# to match either alternative and so fails the whole pointer.

_JSON_POINTER_FRAGMENT = r"(?:/(?:[^/~]|~[01])*)*"
_JSON_POINTER_RE = _anchored(_JSON_POINTER_FRAGMENT)


def json_pointer(value: str) -> bool:
    """RFC 6901 `json-pointer`."""
    return _JSON_POINTER_RE.match(value) is not None


# --- `relative-json-pointer` (draft-handrews-relative-json-pointer) ----
#
# relative-json-pointer = non-negative-integer ( "#" / json-pointer )
# non-negative-integer  = %x30 / ( %x31-39 *DIGIT )
#                        ; "0", or a non-zero digit then any digits
#
# The integer prefix is either exactly "0" or starts with a digit 1-9
# (rules out leading zeros like "01"); ASCII digits only (never `\d`, so
# a non-ASCII decimal digit like an Arabic-Indic digit cannot match). The
# suffix is either a single "#" (taking the member name or index) or a
# json-pointer (possibly empty, as in a bare "100"); "#" may only be the
# very last character, since the two alternatives are mutually exclusive
# and the json-pointer alternative admits no "#" at all.

_NON_NEGATIVE_INTEGER_FRAGMENT = r"0|[1-9][0-9]*"
_RELATIVE_JSON_POINTER_FRAGMENT = (
    rf"(?:{_NON_NEGATIVE_INTEGER_FRAGMENT})(?:#|{_JSON_POINTER_FRAGMENT})"
)
_RELATIVE_JSON_POINTER_RE = _anchored(_RELATIVE_JSON_POINTER_FRAGMENT)


def relative_json_pointer(value: str) -> bool:
    """Relative JSON Pointer."""
    return _RELATIVE_JSON_POINTER_RE.match(value) is not None
