# Direct-call coverage for `json_schema_engine.formats.pointer` and
# `.misc` (M7 Step 1): the non-obvious cases the official suite's own
# json-pointer/relative-json-pointer/uuid/regex/ecmascript-regex fixtures
# already pin (the "~" escape rule, the "#" must-be-last rule, leading-
# zero and non-ASCII-digit rejection in the relative prefix, every
# version/variant nibble accepted for `uuid`, and the ECMA-262-vs-Python
# regex-dialect divergences) — a compact matrix, not a restatement of the
# suite.

from collections.abc import Callable

import pytest

from json_schema_engine.formats.misc import regex, uuid
from json_schema_engine.formats.pointer import json_pointer, relative_json_pointer

type Predicate = Callable[[str], bool]

CASES: tuple[tuple[Predicate, str, bool], ...] = (
    # `json_pointer`: "~" only ever precedes "0" or "1"; empty segments and
    # raw control characters (already JSON-unescaped by the time this
    # predicate runs) are valid; a fragment-identifier "#" form is not a
    # json-pointer at all.
    (json_pointer, "", True),
    (json_pointer, "/", True),
    (json_pointer, "/foo//bar", True),
    (json_pointer, "/~0~1", True),
    (json_pointer, "/foo\x00bar\n\tbaz", True),
    (json_pointer, "#", False),
    (json_pointer, "#/", False),
    (json_pointer, "#a", False),
    (json_pointer, "a", False),
    (json_pointer, "0", False),
    (json_pointer, "/~2", False),
    (json_pointer, "/~-1", False),
    (json_pointer, "/~~", False),
    (json_pointer, "/foo/bar~", False),
    # `relative_json_pointer`: the non-negative-integer prefix is "0" or a
    # digit 1-9 followed by any digits (no leading zeros); ASCII digits
    # only, so a non-ASCII decimal digit never starts a match; "#" may
    # only be the very last character.
    (relative_json_pointer, "0#", True),
    (relative_json_pointer, "1", True),
    (relative_json_pointer, "120/foo/bar", True),
    (relative_json_pointer, "100", True),
    (relative_json_pointer, "0//", True),
    (relative_json_pointer, "01/a", False),
    (relative_json_pointer, "01#", False),
    (relative_json_pointer, "-1/foo", False),
    (relative_json_pointer, "+1/foo", False),
    (relative_json_pointer, "\N{ARABIC-INDIC DIGIT ONE}/foo", False),
    (relative_json_pointer, "0##", False),
    (relative_json_pointer, "1#/foo/bar", False),
    (relative_json_pointer, "", False),
    (relative_json_pointer, "0/~2", False),
    (relative_json_pointer, "1\n", False),
    # `uuid`: any version/variant nibble is accepted, including all-zeros;
    # wrapping, prefixing, or otherwise decorating an otherwise-valid UUID
    # is rejected, unlike the lenient `uuid.UUID(str)` constructor.
    (uuid, "00000000-0000-0000-0000-000000000000", True),
    (uuid, "99c17cbb-656f-664a-940f-1a4568f03487", True),
    (uuid, "99c17cbb-656f-f64a-940f-1a4568f03487", True),
    (uuid, "2eb8aa08-aa98-11ea-f4aa-73b441d16380", True),
    (uuid, "urn:uuid:2eb8aa08-aa98-11ea-b4aa-73b441d16380", False),
    (uuid, "{2eb8aa08-aa98-11ea-b4aa-73b441d16380}", False),
    (uuid, "2eb8aa08-aa98-11ea-b4aa-73b441d16380-", False),
    (uuid, "\N{BENGALI DIGIT TWO}eb8aa08-aa98-11ea-b4aa-73b441d16380", False),
    (uuid, "2eb8aa08-aa98-11ea-b4aa-73b441d1_380", False),
    (uuid, "2eb8aa08-aa98-11ea-b4aa-73b441d16380\n", False),
    (uuid, "2eb8aa08aa9811eab4aa73b441d16380", False),
    # `regex`: ECMA-262 named groups/backreferences and variable-width
    # lookbehind are valid; Python-only syntax (`(?P<name>...)`,
    # `(?P=name)`, `(?#...)`) and global inline-flag groups are not.
    (regex, "([abc])+\\s+$", True),
    (regex, "(?<name>x)", True),
    (regex, "(?<n>a)\\k<n>", True),
    (regex, "(?<=a+)b", True),
    (regex, "[]", True),
    (regex, "[^]", True),
    (regex, "\\cA", True),
    (regex, "^(abc]", False),
    (regex, "\\a", False),
    (regex, "(?P<name>x)", False),
    (regex, "(?P<n>a)(?P=n)", False),
    (regex, "(?#comment)a", False),
    (regex, "(?i)abc", False),
    (regex, "(?ims)abc", False),
)


@pytest.mark.parametrize(
    "predicate,value,expected",
    CASES,
    ids=[f"{fn.__name__}:{value!r}" for fn, value, _ in CASES],
)
def test_case(predicate: Predicate, value: str, expected: bool) -> None:
    assert predicate(value) is expected
