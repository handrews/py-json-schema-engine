"""A recursive-descent parser for the ECMA-262 pattern grammar (``u`` mode).

The grammar implemented is ECMA-262 22.2.1 with the ``u`` flag set, which
is the dialect JSON Schema's ``pattern`` keyword is written against. Annex B
web-compatibility extensions (legacy octal escapes, quantifiable
assertions, unescaped ``{``, identity escapes of arbitrary characters) are
*not* accepted: under ``u`` they are early errors, and accepting them would
make this parser disagree with every conformant host.
"""

from __future__ import annotations

from typing import cast

from .ast import (
    Alternation,
    Anchor,
    Backreference,
    CharClass,
    ClassEscape,
    ClassEscapeKind,
    ClassItem,
    ClassRange,
    Concatenation,
    Dot,
    Flags,
    Group,
    Literal,
    Lookaround,
    Node,
    Pattern,
    PropertyEscape,
    Quantifier,
    WordBoundary,
)
from .errors import EcmaRegexSyntaxError, UnsupportedPatternError
from .unicode_data import MAX_CODE_POINT, UnknownPropertyError, validate_property

__all__ = ["parse"]

_SYNTAX_CHARACTERS = frozenset("^$\\.*+?()[]{}|")
_CONTROL_ESCAPES = {"f": 0x0C, "n": 0x0A, "r": 0x0D, "t": 0x09, "v": 0x0B}
_CLASS_ESCAPES = frozenset("dDsSwW")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_PROPERTY_TOKEN = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)
_ZERO_WIDTH_JOINERS = frozenset("\u200c\u200d")


def _is_ascii_digit(character: str) -> bool:
    return "0" <= character <= "9"


def _is_identifier_start(character: str) -> bool:
    return character in "$_" or character.isidentifier()


def _is_identifier_part(character: str) -> bool:
    return (
        character in "$_"
        or character in _ZERO_WIDTH_JOINERS
        or ("a" + character).isidentifier()
    )


def _is_property_token(token: str) -> bool:
    return bool(token) and all(character in _PROPERTY_TOKEN for character in token)


def parse(pattern: str, *, flags: str = "") -> Pattern:
    """Parse ``pattern`` as an ECMA-262 pattern under ``u``-mode semantics.

    ``flags`` is an ECMA-262 flag string; ``i``, ``m``, ``s`` and ``u`` are
    accepted (``u`` is implied whether or not it is given).

    Raises :class:`~ecma_regex.errors.EcmaRegexSyntaxError` for an invalid
    pattern and :class:`~ecma_regex.errors.UnsupportedPatternError` for a
    flag this package does not model.
    """
    parsed_flags = _parse_flags(flags)
    root = _Parser(pattern, parsed_flags).parse()
    return Pattern(root=root, flags=parsed_flags)


def _parse_flags(flags: str) -> Flags:
    seen: set[str] = set()
    ignore_case = False
    multiline = False
    dot_all = False
    for index, letter in enumerate(flags):
        if letter in seen:
            raise EcmaRegexSyntaxError(f"duplicate flag {letter!r}", index)
        seen.add(letter)
        match letter:
            case "i":
                ignore_case = True
            case "m":
                multiline = True
            case "s":
                dot_all = True
            case "u":
                pass
            case "g" | "y" | "d" | "v":
                raise UnsupportedPatternError(
                    f"flag {letter!r} is not supported; this package models "
                    f"a stateless, unanchored, u-mode match",
                    index,
                )
            case _:
                raise EcmaRegexSyntaxError(f"unknown flag {letter!r}", index)
    return Flags(
        ignore_case=ignore_case,
        multiline=multiline,
        dot_all=dot_all,
        unicode=True,
    )


def _prescan(source: str) -> tuple[int, dict[str, int]]:
    """Count capturing groups and collect their names.

    ECMA-262 permits forward references (``\\1(a)`` and ``\\k<x>(?<x>a)``),
    so the capture table must exist before the real parse begins. This scan
    is purely lexical; anything malformed it skips over is reported by the
    real parse.
    """
    count = 0
    names: dict[str, int] = {}
    index = 0
    in_class = False
    length = len(source)
    while index < length:
        character = source[index]
        if character == "\\":
            index += 2
            continue
        if in_class:
            in_class = character != "]"
            index += 1
            continue
        if character == "[":
            in_class = True
        elif character == "(":
            if not source.startswith("(?", index):
                count += 1
            elif source.startswith("(?<", index) and not source.startswith(
                ("(?<=", "(?<!"), index
            ):
                end = source.find(">", index + 3)
                if end != -1:
                    count += 1
                    names[source[index + 3 : end]] = count
        index += 1
    return count, names


class _Parser:
    """Mutable parse state. One instance per :func:`parse` call."""

    def __init__(self, source: str, flags: Flags) -> None:
        self.source = source
        self.flags = flags
        self.pos = 0
        self.depth = 0
        self.group_count = 0
        self.total_groups, self.group_names = _prescan(source)
        self.seen_names: set[str] = set()

    # -- cursor ---------------------------------------------------------

    def _peek(self, offset: int = 0) -> str | None:
        index = self.pos + offset
        return self.source[index] if index < len(self.source) else None

    def _error(self, message: str, position: int | None = None) -> EcmaRegexSyntaxError:
        return EcmaRegexSyntaxError(message, self.pos if position is None else position)

    # -- grammar --------------------------------------------------------

    def parse(self) -> Node:
        node = self._disjunction()
        if self.pos < len(self.source):
            raise self._error(f"unexpected {self.source[self.pos]!r}")
        return node

    def _disjunction(self) -> Node:
        options = [self._alternative()]
        while self._peek() == "|":
            self.pos += 1
            options.append(self._alternative())
        if len(options) == 1:
            return options[0]
        return Alternation(tuple(options))

    def _alternative(self) -> Node:
        parts: list[Node] = []
        while True:
            character = self._peek()
            if character is None or character == "|":
                break
            if character == ")":
                if self.depth == 0:
                    raise self._error("unmatched ')'")
                break
            parts.append(self._term())
        if len(parts) == 1:
            return parts[0]
        return Concatenation(tuple(parts))

    def _term(self) -> Node:
        node, quantifiable = self._atom()
        quantifier = self._maybe_quantifier()
        if quantifier is None:
            return node
        minimum, maximum, greedy, position = quantifier
        if not quantifiable:
            raise self._error(
                "an assertion may not be quantified in unicode mode", position
            )
        if maximum is not None and minimum > maximum:
            raise self._error("quantifier minimum exceeds its maximum", position)
        return Quantifier(target=node, min=minimum, max=maximum, greedy=greedy)

    def _maybe_quantifier(self) -> tuple[int, int | None, bool, int] | None:
        position = self.pos
        bounds: tuple[int, int | None]
        match self._peek():
            case "*":
                self.pos += 1
                bounds = (0, None)
            case "+":
                self.pos += 1
                bounds = (1, None)
            case "?":
                self.pos += 1
                bounds = (0, 1)
            case "{":
                bounds = self._braced_quantifier()
            case _:
                return None
        greedy = True
        if self._peek() == "?":
            self.pos += 1
            greedy = False
        return bounds[0], bounds[1], greedy, position

    def _braced_quantifier(self) -> tuple[int, int | None]:
        start = self.pos
        source = self.source
        index = self.pos + 1
        first = index
        while index < len(source) and _is_ascii_digit(source[index]):
            index += 1
        if index == first:
            raise self._error("'{' must begin a quantifier or be escaped", start)
        minimum = int(source[first:index])
        maximum: int | None = minimum
        if index < len(source) and source[index] == ",":
            index += 1
            second = index
            while index < len(source) and _is_ascii_digit(source[index]):
                index += 1
            maximum = int(source[second:index]) if index > second else None
        if index >= len(source) or source[index] != "}":
            raise self._error("'{' must begin a quantifier or be escaped", start)
        self.pos = index + 1
        return minimum, maximum

    def _atom(self) -> tuple[Node, bool]:
        character = self._peek()
        if character is None:
            raise self._error("unexpected end of pattern")
        position = self.pos
        match character:
            case "^":
                self.pos += 1
                return Anchor("start"), False
            case "$":
                self.pos += 1
                return Anchor("end"), False
            case ".":
                self.pos += 1
                return Dot(), True
            case "(":
                return self._group()
            case "[":
                return self._char_class(), True
            case "\\":
                return self._atom_escape()
            case "*" | "+" | "?":
                raise self._error("nothing to repeat", position)
            case "{" | "}" | "]":
                raise self._error(
                    f"{character!r} must be escaped in unicode mode", position
                )
            case ")":
                raise self._error("unmatched ')'", position)
            case _:
                self.pos += 1
                return Literal(ord(character)), True

    def _group(self) -> tuple[Node, bool]:
        start = self.pos
        self.pos += 1
        if self._peek() != "?":
            self.group_count += 1
            index = self.group_count
            body = self._nested(start)
            return Group(body=body, capturing=True, index=index), True
        match self._peek(1):
            case ":":
                self.pos += 2
                return Group(body=self._nested(start), capturing=False), True
            case "=":
                self.pos += 2
                return Lookaround(self._nested(start), "ahead", negated=False), False
            case "!":
                self.pos += 2
                return Lookaround(self._nested(start), "ahead", negated=True), False
            case "<":
                return self._lookbehind_or_named_group(start)
            case _:
                raise self._error("invalid group prefix", start)

    def _lookbehind_or_named_group(self, start: int) -> tuple[Node, bool]:
        match self._peek(2):
            case "=":
                self.pos += 3
                return Lookaround(self._nested(start), "behind", negated=False), False
            case "!":
                self.pos += 3
                return Lookaround(self._nested(start), "behind", negated=True), False
            case _:
                self.pos += 1
                name = self._group_name()
                if name in self.seen_names:
                    raise self._error(f"duplicate group name {name!r}", start)
                self.seen_names.add(name)
                self.group_count += 1
                index = self.group_count
                body = self._nested(start)
                return (
                    Group(body=body, capturing=True, index=index, name=name),
                    True,
                )

    def _nested(self, start: int) -> Node:
        self.depth += 1
        node = self._disjunction()
        self.depth -= 1
        if self._peek() != ")":
            raise self._error("unterminated group", start)
        self.pos += 1
        return node

    def _group_name(self) -> str:
        start = self.pos
        self.pos += 1
        characters: list[str] = []
        while True:
            character = self._peek()
            if character is None:
                raise self._error("unterminated group name", start)
            if character == ">":
                self.pos += 1
                break
            if character == "\\":
                if self._peek(1) != "u":
                    raise self._error("invalid escape in a group name")
                self.pos += 2
                characters.append(chr(self._unicode_escape_value()))
                continue
            characters.append(character)
            self.pos += 1
        name = "".join(characters)
        valid = (
            bool(name)
            and _is_identifier_start(name[0])
            and all(_is_identifier_part(character) for character in name[1:])
        )
        if not valid:
            raise self._error(f"invalid group name {name!r}", start)
        return name

    # -- escapes --------------------------------------------------------

    def _atom_escape(self) -> tuple[Node, bool]:
        start = self.pos
        self.pos += 1
        character = self._peek()
        if character is None:
            raise self._error("trailing backslash", start)
        if character == "b":
            self.pos += 1
            return WordBoundary(negated=False), False
        if character == "B":
            self.pos += 1
            return WordBoundary(negated=True), False
        if character in _CLASS_ESCAPES:
            self.pos += 1
            return ClassEscape(cast(ClassEscapeKind, character)), True
        if character in "pP":
            return self._property_escape(), True
        if character == "k":
            self.pos += 1
            if self._peek() != "<":
                raise self._error("'\\k' must be followed by a group name")
            name = self._group_name()
            if name not in self.group_names:
                raise self._error(f"reference to undefined group name {name!r}", start)
            return Backreference(name=name), True
        if "1" <= character <= "9":
            first = self.pos
            while (digit := self._peek()) is not None and _is_ascii_digit(digit):
                self.pos += 1
            number = int(self.source[first : self.pos])
            if number > self.total_groups:
                raise self._error(f"reference to undefined group {number}", start)
            return Backreference(index=number), True
        return Literal(self._character_escape_value(start)), True

    def _character_escape_value(self, start: int) -> int:
        character = self._peek()
        if character is None:
            raise self._error("trailing backslash", start)
        if character in _CONTROL_ESCAPES:
            self.pos += 1
            return _CONTROL_ESCAPES[character]
        if character == "0":
            self.pos += 1
            following = self._peek()
            if following is not None and _is_ascii_digit(following):
                raise self._error("'\\0' may not be followed by a digit")
            return 0
        if character == "c":
            letter = self._peek(1)
            if letter is None or not letter.isascii() or not letter.isalpha():
                raise self._error("'\\c' must be followed by an ASCII letter", start)
            self.pos += 2
            return ord(letter) % 32
        if character == "x":
            self.pos += 1
            return self._hex_digits(2, start)
        if character == "u":
            self.pos += 1
            return self._unicode_escape_value()
        if character in _SYNTAX_CHARACTERS or character == "/":
            self.pos += 1
            return ord(character)
        raise self._error(f"invalid escape '\\{character}' in unicode mode", start)

    def _hex_digits(self, count: int, start: int) -> int:
        chunk = self.source[self.pos : self.pos + count]
        if len(chunk) != count or any(
            character not in _HEX_DIGITS for character in chunk
        ):
            raise self._error("invalid hexadecimal escape", start)
        self.pos += count
        return int(chunk, 16)

    def _unicode_escape_value(self) -> int:
        start = self.pos
        if self._peek() == "{":
            self.pos += 1
            first = self.pos
            while (digit := self._peek()) is not None and digit in _HEX_DIGITS:
                self.pos += 1
            if self.pos == first or self._peek() != "}":
                raise self._error("invalid '\\u{...}' escape", start)
            value = int(self.source[first : self.pos], 16)
            self.pos += 1
            if value > MAX_CODE_POINT:
                raise self._error("code point out of range", start)
            return value
        value = self._hex_digits(4, start)
        if 0xD800 <= value <= 0xDBFF and self.source.startswith("\\u", self.pos):
            saved = self.pos
            self.pos += 2
            chunk = self.source[self.pos : self.pos + 4]
            if len(chunk) == 4 and all(character in _HEX_DIGITS for character in chunk):
                trail = int(chunk, 16)
                if 0xDC00 <= trail <= 0xDFFF:
                    self.pos += 4
                    return 0x10000 + (value - 0xD800) * 0x400 + (trail - 0xDC00)
            self.pos = saved
        return value

    def _property_escape(self) -> PropertyEscape:
        start = self.pos - 1
        negated = self._peek() == "P"
        self.pos += 1
        if self._peek() != "{":
            raise self._error("'\\p' must be followed by '{'", start)
        self.pos += 1
        end = self.source.find("}", self.pos)
        if end == -1:
            raise self._error("unterminated '\\p{...}'", start)
        body = self.source[self.pos : end]
        self.pos = end + 1
        name, separator, value = body.partition("=")
        if not _is_property_token(name) or (
            separator and not _is_property_token(value)
        ):
            raise self._error(f"invalid property expression {body!r}", start)
        try:
            validate_property(name, value if separator else None)
        except UnknownPropertyError as error:
            raise EcmaRegexSyntaxError(error.description, start) from error
        return PropertyEscape(
            name=name, value=value if separator else None, negated=negated
        )

    # -- character classes ----------------------------------------------

    def _char_class(self) -> CharClass:
        start = self.pos
        self.pos += 1
        negated = self._peek() == "^"
        if negated:
            self.pos += 1
        items: list[ClassItem] = []
        while True:
            character = self._peek()
            if character is None:
                raise self._error("unterminated character class", start)
            if character == "]":
                self.pos += 1
                break
            low = self._class_atom()
            following = self._peek()
            if following != "-" or self._peek(1) in (None, "]"):
                items.append(low)
                continue
            dash = self.pos
            self.pos += 1
            high_position = self.pos
            high = self._class_atom()
            if not isinstance(low, Literal) or not isinstance(high, Literal):
                raise self._error(
                    "a character-class range endpoint must be a single code "
                    "point in unicode mode",
                    dash,
                )
            if low.code_point > high.code_point:
                raise self._error(
                    "character-class range is out of order", high_position
                )
            items.append(ClassRange(low.code_point, high.code_point))
        return CharClass(negated=negated, items=tuple(items))

    def _class_atom(self) -> ClassItem:
        character = self._peek()
        if character is None:
            raise self._error("unterminated character class")
        if character != "\\":
            self.pos += 1
            return Literal(ord(character))
        start = self.pos
        self.pos += 1
        escaped = self._peek()
        if escaped is None:
            raise self._error("trailing backslash", start)
        if escaped == "b":
            self.pos += 1
            return Literal(0x08)
        if escaped == "-":
            self.pos += 1
            return Literal(0x2D)
        if escaped in _CLASS_ESCAPES:
            self.pos += 1
            return ClassEscape(cast(ClassEscapeKind, escaped))
        if escaped in "pP":
            return self._property_escape()
        return Literal(self._character_escape_value(start))
