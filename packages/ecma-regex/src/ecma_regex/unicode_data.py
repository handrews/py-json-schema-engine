"""Code-point sets: the fixed ECMA-262 sets and Unicode property lookup.

Unicode property membership is derived from the standard library's
:mod:`unicodedata` and ``str`` predicates, then cached. The first use of a
derived property scans every code point once (roughly 40-80 ms); every
later use is a dict hit.

Sets are represented as a ``RangeList``: a tuple of inclusive, sorted,
non-overlapping, non-adjacent ``(low, high)`` code-point pairs.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable, Mapping
from functools import cache

__all__ = [
    "MAX_CODE_POINT",
    "RangeList",
    "complement",
    "contains",
    "property_ranges",
    "union",
]

MAX_CODE_POINT = 0x10FFFF

type RangeList = tuple[tuple[int, int], ...]

# --- fixed ECMA-262 sets ------------------------------------------------

#: ECMA-262 22.2.2.9 LineTerminator: LF, CR, LS, PS.
LINE_TERMINATORS: RangeList = ((0x0A, 0x0A), (0x0D, 0x0D), (0x2028, 0x2029))

#: ECMA-262 ``\d``: ASCII digits only.
DIGIT: RangeList = ((0x30, 0x39),)

#: ECMA-262 ``\w`` (22.2.2.9 WordCharacters): ASCII word characters only.
WORD: RangeList = ((0x30, 0x39), (0x41, 0x5A), (0x5F, 0x5F), (0x61, 0x7A))

#: ECMA-262 ``\s``: WhiteSpace (11.2) union LineTerminator (11.3).
#: TAB, LF, VT, FF, CR, SP, NBSP, every General_Category=Zs code point,
#: LS, PS and ZWNBSP (U+FEFF).
WHITESPACE: RangeList = (
    (0x09, 0x0D),
    (0x20, 0x20),
    (0xA0, 0xA0),
    (0x1680, 0x1680),
    (0x2000, 0x200A),
    (0x2028, 0x2029),
    (0x202F, 0x202F),
    (0x205F, 0x205F),
    (0x3000, 0x3000),
    (0xFEFF, 0xFEFF),
)


# --- range algebra ------------------------------------------------------


def _normalize(pairs: Iterable[tuple[int, int]]) -> RangeList:
    ordered = sorted(pairs)
    merged: list[tuple[int, int]] = []
    for low, high in ordered:
        if merged and low <= merged[-1][1] + 1:
            previous_low, previous_high = merged[-1]
            merged[-1] = (previous_low, max(previous_high, high))
        else:
            merged.append((low, high))
    return tuple(merged)


def union(*range_lists: RangeList) -> RangeList:
    """Union of any number of range lists."""
    return _normalize(pair for ranges in range_lists for pair in ranges)


def complement(ranges: RangeList) -> RangeList:
    """Complement of ``ranges`` over ``0..MAX_CODE_POINT`` inclusive.

    Lone surrogates are inside the universe: ECMA-262 ``u``-mode matches
    over code points, and a Python ``str`` may hold an unpaired surrogate.
    """
    result: list[tuple[int, int]] = []
    cursor = 0
    for low, high in _normalize(ranges):
        if low > cursor:
            result.append((cursor, low - 1))
        cursor = max(cursor, high + 1)
    if cursor <= MAX_CODE_POINT:
        result.append((cursor, MAX_CODE_POINT))
    return tuple(result)


def contains(ranges: RangeList, code_point: int) -> bool:
    """Whether ``code_point`` is a member of ``ranges``."""
    return any(low <= code_point <= high for low, high in ranges)


def _ranges_from_predicate(predicate: Callable[[int], bool]) -> RangeList:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for code_point in range(MAX_CODE_POINT + 1):
        if predicate(code_point):
            if start is None:
                start = code_point
        elif start is not None:
            result.append((start, code_point - 1))
            start = None
    if start is not None:
        result.append((start, MAX_CODE_POINT))
    return tuple(result)


# --- General_Category ---------------------------------------------------

#: General_Category value aliases (ECMA-262 Table 68), long name -> code.
_GENERAL_CATEGORY_ALIASES: Mapping[str, str] = {
    "Other": "C",
    "Control": "Cc",
    "cntrl": "Cc",
    "Format": "Cf",
    "Unassigned": "Cn",
    "Private_Use": "Co",
    "Surrogate": "Cs",
    "Letter": "L",
    "Cased_Letter": "LC",
    "Lowercase_Letter": "Ll",
    "Modifier_Letter": "Lm",
    "Other_Letter": "Lo",
    "Titlecase_Letter": "Lt",
    "Uppercase_Letter": "Lu",
    "Mark": "M",
    "Combining_Mark": "M",
    "Spacing_Mark": "Mc",
    "Enclosing_Mark": "Me",
    "Nonspacing_Mark": "Mn",
    "Number": "N",
    "Decimal_Number": "Nd",
    "digit": "Nd",
    "Letter_Number": "Nl",
    "Other_Number": "No",
    "Punctuation": "P",
    "punct": "P",
    "Connector_Punctuation": "Pc",
    "Dash_Punctuation": "Pd",
    "Close_Punctuation": "Pe",
    "Final_Punctuation": "Pf",
    "Initial_Punctuation": "Pi",
    "Other_Punctuation": "Po",
    "Open_Punctuation": "Ps",
    "Symbol": "S",
    "Currency_Symbol": "Sc",
    "Modifier_Symbol": "Sk",
    "Math_Symbol": "Sm",
    "Other_Symbol": "So",
    "Separator": "Z",
    "Line_Separator": "Zl",
    "Paragraph_Separator": "Zp",
    "Space_Separator": "Zs",
}

#: Multi-category codes and the two-letter codes they stand for.
_CATEGORY_GROUPS: Mapping[str, tuple[str, ...]] = {
    "C": ("Cc", "Cf", "Cn", "Co", "Cs"),
    "L": ("Ll", "Lm", "Lo", "Lt", "Lu"),
    "LC": ("Ll", "Lt", "Lu"),
    "M": ("Mc", "Me", "Mn"),
    "N": ("Nd", "Nl", "No"),
    "P": ("Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps"),
    "S": ("Sc", "Sk", "Sm", "So"),
    "Z": ("Zl", "Zp", "Zs"),
}

_ATOMIC_CATEGORIES: frozenset[str] = frozenset(
    code for codes in _CATEGORY_GROUPS.values() for code in codes
)

#: Every accepted General_Category value spelling.
GENERAL_CATEGORY_VALUES: frozenset[str] = frozenset(
    set(_GENERAL_CATEGORY_ALIASES) | _ATOMIC_CATEGORIES | set(_CATEGORY_GROUPS)
)


@cache
def _category_table() -> Mapping[str, RangeList]:
    """One pass over every code point, bucketed into category runs."""
    category = unicodedata.category
    runs: dict[str, list[tuple[int, int]]] = {}
    start = 0
    current = category(chr(0))
    for code_point in range(1, MAX_CODE_POINT + 1):
        found = category(chr(code_point))
        if found != current:
            runs.setdefault(current, []).append((start, code_point - 1))
            current = found
            start = code_point
    runs.setdefault(current, []).append((start, MAX_CODE_POINT))
    return {code: tuple(pairs) for code, pairs in runs.items()}


def _general_category(value: str) -> RangeList:
    code = _GENERAL_CATEGORY_ALIASES.get(value, value)
    table = _category_table()
    if code in _CATEGORY_GROUPS:
        return union(*(table.get(member, ()) for member in _CATEGORY_GROUPS[code]))
    return table.get(code, ())


# --- binary properties --------------------------------------------------

#: Binary properties whose membership is computed exactly from the
#: standard library. Maps every accepted alias to a canonical key.
_COMPUTABLE_BINARY: Mapping[str, str] = {
    "ASCII": "ASCII",
    "ASCII_Hex_Digit": "ASCII_Hex_Digit",
    "AHex": "ASCII_Hex_Digit",
    "Any": "Any",
    "Assigned": "Assigned",
    "Bidi_Control": "Bidi_Control",
    "Bidi_C": "Bidi_Control",
    "Bidi_Mirrored": "Bidi_Mirrored",
    "Bidi_M": "Bidi_Mirrored",
    "Hex_Digit": "Hex_Digit",
    "Hex": "Hex_Digit",
    "Join_Control": "Join_Control",
    "Join_C": "Join_Control",
    "Lowercase": "Lowercase",
    "Lower": "Lowercase",
    "Noncharacter_Code_Point": "Noncharacter_Code_Point",
    "NChar": "Noncharacter_Code_Point",
    "Regional_Indicator": "Regional_Indicator",
    "RI": "Regional_Indicator",
    "Uppercase": "Uppercase",
    "Upper": "Uppercase",
    "White_Space": "White_Space",
    "space": "White_Space",
    "XID_Continue": "XID_Continue",
    "XIDC": "XID_Continue",
    "XID_Start": "XID_Start",
    "XIDS": "XID_Start",
}

#: Binary property names ECMA-262 defines that this package recognizes but
#: cannot compute from the standard library. They are valid syntax; the
#: ``re`` backend raises ``UnsupportedPatternError`` for them, and the
#: ``regex`` backend emits them natively.
_KNOWN_UNCOMPUTABLE_BINARY: frozenset[str] = frozenset(
    {
        "Alphabetic", "Alpha",
        "Case_Ignorable", "CI",
        "Cased",
        "Changes_When_Casefolded", "CWCF",
        "Changes_When_Casemapped", "CWCM",
        "Changes_When_Lowercased", "CWL",
        "Changes_When_NFKC_Casefolded", "CWKCF",
        "Changes_When_Titlecased", "CWT",
        "Changes_When_Uppercased", "CWU",
        "Dash",
        "Default_Ignorable_Code_Point", "DI",
        "Deprecated", "Dep",
        "Diacritic", "Dia",
        "Emoji",
        "Emoji_Component", "EComp",
        "Emoji_Modifier", "EMod",
        "Emoji_Modifier_Base", "EBase",
        "Emoji_Presentation", "EPres",
        "Extended_Pictographic", "ExtPict",
        "Extender", "Ext",
        "Grapheme_Base", "Gr_Base",
        "Grapheme_Extend", "Gr_Ext",
        "IDS_Binary_Operator", "IDSB",
        "IDS_Trinary_Operator", "IDST",
        "ID_Continue", "IDC",
        "ID_Start", "IDS",
        "Ideographic", "Ideo",
        "Logical_Order_Exception", "LOE",
        "Math",
        "Pattern_Syntax", "Pat_Syn",
        "Pattern_White_Space", "Pat_WS",
        "Quotation_Mark", "QMark",
        "Radical",
        "Sentence_Terminal", "STerm",
        "Soft_Dotted", "SD",
        "Terminal_Punctuation", "Term",
        "Unified_Ideograph", "UIdeo",
        "Variation_Selector", "VS",
    }
)  # fmt: skip

#: Every accepted binary property name.
BINARY_PROPERTY_NAMES: frozenset[str] = frozenset(
    set(_COMPUTABLE_BINARY) | _KNOWN_UNCOMPUTABLE_BINARY
)

#: Property names that take a value (``\p{Script=Greek}``).
VALUED_PROPERTY_NAMES: Mapping[str, str] = {
    "General_Category": "General_Category",
    "gc": "General_Category",
    "Script": "Script",
    "sc": "Script",
    "Script_Extensions": "Script_Extensions",
    "scx": "Script_Extensions",
}

_BIDI_CONTROL: RangeList = (
    (0x061C, 0x061C),
    (0x200E, 0x200F),
    (0x202A, 0x202E),
    (0x2066, 0x2069),
)
_HEX_DIGIT: RangeList = (
    (0x30, 0x39),
    (0x41, 0x46),
    (0x61, 0x66),
    (0xFF10, 0xFF19),
    (0xFF21, 0xFF26),
    (0xFF41, 0xFF46),
)


def _noncharacters() -> RangeList:
    pairs = [(0xFDD0, 0xFDEF)]
    pairs.extend(
        (plane * 0x10000 + 0xFFFE, plane * 0x10000 + 0xFFFF) for plane in range(17)
    )
    return _normalize(pairs)


def _binary_property(canonical: str) -> RangeList:
    match canonical:
        case "ASCII":
            return ((0x00, 0x7F),)
        case "ASCII_Hex_Digit":
            return ((0x30, 0x39), (0x41, 0x46), (0x61, 0x66))
        case "Any":
            return ((0x00, MAX_CODE_POINT),)
        case "Assigned":
            return complement(_category_table().get("Cn", ()))
        case "Bidi_Control":
            return _BIDI_CONTROL
        case "Bidi_Mirrored":
            return _ranges_from_predicate(lambda cp: unicodedata.mirrored(chr(cp)) == 1)
        case "Hex_Digit":
            return _HEX_DIGIT
        case "Join_Control":
            return ((0x200C, 0x200D),)
        case "Lowercase":
            return _ranges_from_predicate(lambda cp: chr(cp).islower())
        case "Noncharacter_Code_Point":
            return _noncharacters()
        case "Regional_Indicator":
            return ((0x1F1E6, 0x1F1FF),)
        case "Uppercase":
            return _ranges_from_predicate(lambda cp: chr(cp).isupper())
        case "White_Space":
            table = _category_table()
            return union(
                ((0x09, 0x0D), (0x85, 0x85)),
                table.get("Zs", ()),
                table.get("Zl", ()),
                table.get("Zp", ()),
            )
        case "XID_Continue":
            return _ranges_from_predicate(lambda cp: ("a" + chr(cp)).isidentifier())
        case "XID_Start":
            return _ranges_from_predicate(lambda cp: chr(cp).isidentifier())
        case _:  # pragma: no cover - guarded by the caller
            raise KeyError(canonical)


class PropertyNotComputableError(LookupError):
    """A recognized property whose membership cannot be derived here."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


class UnknownPropertyError(LookupError):
    """The property name (or General_Category value) is not defined."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


def validate_property(name: str, value: str | None) -> None:
    """Raise :class:`UnknownPropertyError` if ``name``/``value`` is not defined.

    ``Script`` and ``Script_Extensions`` values are *not* validated: the
    standard library ships no script data, so this package cannot build
    the list of script names. See the README's divergence table.
    """
    if value is None:
        if name in GENERAL_CATEGORY_VALUES or name in BINARY_PROPERTY_NAMES:
            return
        raise UnknownPropertyError(f"unknown Unicode property or value {name!r}")
    canonical = VALUED_PROPERTY_NAMES.get(name)
    if canonical is None:
        raise UnknownPropertyError(f"unknown Unicode property name {name!r}")
    if canonical == "General_Category" and value not in GENERAL_CATEGORY_VALUES:
        raise UnknownPropertyError(f"unknown General_Category value {value!r}")


@cache
def property_ranges(name: str, value: str | None) -> RangeList:
    """The code-point set of ``\\p{name}`` or ``\\p{name=value}``.

    Raises :class:`UnknownPropertyError` for an undefined name and
    :class:`PropertyNotComputableError` for a defined name this package cannot
    derive from the standard library.
    """
    validate_property(name, value)
    if value is None:
        if name in GENERAL_CATEGORY_VALUES:
            return _general_category(name)
        canonical = _COMPUTABLE_BINARY.get(name)
        if canonical is None:
            raise PropertyNotComputableError(
                f"binary property {name!r} cannot be computed from the standard library"
            )
        return _binary_property(canonical)
    resolved = VALUED_PROPERTY_NAMES[name]
    if resolved == "General_Category":
        return _general_category(value)
    raise PropertyNotComputableError(
        f"{resolved}={value} needs Unicode script data, which the standard "
        f"library does not ship"
    )
