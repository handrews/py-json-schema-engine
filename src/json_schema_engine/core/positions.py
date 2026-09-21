# D17: the reference loader capability "report source ranges". A
# recursive-descent JSON parser that records, for every value it parses,
# the source span of that value (and, for an object member, the span of
# its key token too), keyed by the JSON Pointer (RFC 6901) of the value's
# location in the document. `parse_json_with_ranges` is the public way to
# get positions without writing a parser: its result is a `LoadedResource`
# with a `get_range`, so a loader can return it directly.
#
# IP policy (DESIGN.md D15): implemented from RFC 8259 (JSON) and RFC 6901
# (JSON Pointer) only. The parser walks the JSON grammar itself rather
# than delegating structure to `json.loads`, so it rejects non-JSON
# extensions such as `NaN`/`Infinity` that `json.loads` accepts (P2).
#
# Dependency direction: imports core's `errors`, `json_model`, and
# `loader` leaves only.

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn

from json_schema_engine.core.errors import JsonSyntaxError
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.loader import SourcePosition, SourceRange, SourceSpan

_WHITESPACE = " \t\n\r"
_ESCAPABLE = frozenset('"\\/bfnrtu')
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """A parsed JSON document plus its source-position lookup.

    Satisfies `LoadedResource` (`value`, `uri`) with the D17 extension
    (`get_range`), so a loader may return it as is.
    """

    value: JsonValue
    uri: str
    get_range: Callable[[str], SourceRange | None]


def _escape_pointer_token(token: str) -> str:
    """RFC 6901 §3: encode `~` and `/` within one reference token."""
    return token.replace("~", "~0").replace("/", "~1")


def _is_ascii_digit(ch: str | None) -> bool:
    return ch is not None and "0" <= ch <= "9"


class _Parser:
    """Recursive-descent parser over the RFC 8259 JSON grammar.

    Walks `text` once, left to right, tracking line/column/offset as it
    goes and recording a `SourceRange` for every JSON Pointer it visits.
    Only an already-delimited leaf token (a string or number literal) is
    handed to `json.loads`, to decode its Python value.
    """

    __slots__ = ("column", "length", "line", "pos", "ranges", "text")

    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.pos = 0
        self.line = 1
        self.column = 1
        self.ranges: dict[str, SourceRange] = {}

    def _position(self) -> SourcePosition:
        return SourcePosition(line=self.line, column=self.column, offset=self.pos)

    def _fail(self, message: str) -> NoReturn:
        raise JsonSyntaxError(
            f"{message} at line {self.line}, column {self.column}",
            line=self.line,
            column=self.column,
            offset=self.pos,
        )

    def _peek(self) -> str | None:
        return self.text[self.pos] if self.pos < self.length else None

    def _advance(self) -> str:
        ch = self.text[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _skip_ws(self) -> None:
        while self.pos < self.length and self.text[self.pos] in _WHITESPACE:
            self._advance()

    def _expect(self, ch: str) -> None:
        if self._peek() != ch:
            self._fail(f"expected {ch!r}")
        self._advance()

    def parse_document(self) -> JsonValue:
        self._skip_ws()
        value = self._parse_value("")
        self._skip_ws()
        if self.pos != self.length:
            self._fail("trailing content after JSON document")
        return value

    def _parse_value(
        self, pointer: str, key_span: SourceSpan | None = None
    ) -> JsonValue:
        self._skip_ws()
        if self.pos >= self.length:
            self._fail("unexpected end of input")
        start = self._position()
        ch = self._peek()
        value: JsonValue
        if ch == "{":
            value = self._parse_object(pointer)
        elif ch == "[":
            value = self._parse_array(pointer)
        elif ch == '"':
            value, _ = self._parse_string()
        elif ch == "-" or _is_ascii_digit(ch):
            value = self._parse_number()
        elif self.text.startswith("true", self.pos):
            self._skip_literal("true")
            value = True
        elif self.text.startswith("false", self.pos):
            self._skip_literal("false")
            value = False
        elif self.text.startswith("null", self.pos):
            self._skip_literal("null")
            value = None
        else:
            self._fail("unexpected character; expected a JSON value")
        end = self._position()
        source_range: SourceRange = {"value": SourceSpan(start=start, end=end)}
        if key_span is not None:
            source_range["key"] = key_span
        self.ranges[pointer] = source_range
        return value

    def _skip_literal(self, literal: str) -> None:
        for _ in literal:
            self._advance()

    def _parse_object(self, pointer: str) -> dict[str, JsonValue]:
        self._expect("{")
        self._skip_ws()
        obj: dict[str, JsonValue] = {}
        if self._peek() == "}":
            self._advance()
            return obj
        while True:
            self._skip_ws()
            if self._peek() != '"':
                self._fail("expected a string key")
            key, key_span = self._parse_string()
            self._skip_ws()
            self._expect(":")
            member_pointer = f"{pointer}/{_escape_pointer_token(key)}"
            obj[key] = self._parse_value(member_pointer, key_span=key_span)
            self._skip_ws()
            ch = self._peek()
            if ch == ",":
                self._advance()
                continue
            if ch == "}":
                self._advance()
                break
            self._fail("expected ',' or '}'")
        return obj

    def _parse_array(self, pointer: str) -> list[JsonValue]:
        self._expect("[")
        self._skip_ws()
        arr: list[JsonValue] = []
        if self._peek() == "]":
            self._advance()
            return arr
        while True:
            element_pointer = f"{pointer}/{len(arr)}"
            arr.append(self._parse_value(element_pointer))
            self._skip_ws()
            ch = self._peek()
            if ch == ",":
                self._advance()
                continue
            if ch == "]":
                self._advance()
                break
            self._fail("expected ',' or ']'")
        return arr

    def _parse_string(self) -> tuple[str, SourceSpan]:
        start = self._position()
        start_offset = self.pos
        self._expect('"')
        while True:
            if self.pos >= self.length:
                self._fail("unterminated string")
            ch = self.text[self.pos]
            if ch == '"':
                self._advance()
                break
            if ch == "\\":
                self._advance()
                if self.pos >= self.length:
                    self._fail("unterminated escape sequence")
                esc = self.text[self.pos]
                if esc not in _ESCAPABLE:
                    self._fail(f"invalid escape sequence '\\{esc}'")
                self._advance()
                if esc == "u":
                    for _ in range(4):
                        digit = self._peek()
                        if digit is None or digit not in _HEX_DIGITS:
                            self._fail("invalid \\u escape sequence")
                        self._advance()
            elif ord(ch) < 0x20:
                self._fail("unescaped control character in string")
            else:
                self._advance()
        end = self._position()
        token = self.text[start_offset : end["offset"]]
        try:
            decoded = json.loads(token)
        except ValueError:
            self._fail("invalid string literal")
        if not isinstance(decoded, str):
            self._fail("invalid string literal")
        return decoded, SourceSpan(start=start, end=end)

    def _parse_number(self) -> int | float:
        start_offset = self.pos
        if self._peek() == "-":
            self._advance()
        if not _is_ascii_digit(self._peek()):
            self._fail("invalid number literal")
        if self._peek() == "0":
            self._advance()
        else:
            while _is_ascii_digit(self._peek()):
                self._advance()
        if self._peek() == ".":
            self._advance()
            if not _is_ascii_digit(self._peek()):
                self._fail("invalid number literal: expected digit after '.'")
            while _is_ascii_digit(self._peek()):
                self._advance()
        if self._peek() in ("e", "E"):
            self._advance()
            if self._peek() in ("+", "-"):
                self._advance()
            if not _is_ascii_digit(self._peek()):
                self._fail("invalid number literal: expected digit in exponent")
            while _is_ascii_digit(self._peek()):
                self._advance()
        token = self.text[start_offset : self.pos]
        return json.loads(token)


def parse_json_with_ranges(text: str, uri: str) -> ParsedDocument:
    """Parse `text` as JSON, returning the value plus a source-position
    lookup by document-rooted JSON Pointer (RFC 6901).

    The result is a `LoadedResource` with `get_range`, so a loader can
    return it and `evaluate(..., positions=True)` and `Engine.locate` will
    report line/column/offset. Raises `JsonSyntaxError` (also a
    `ValueError`) with the position on any syntax error, including
    trailing content and the non-JSON extensions `NaN`/`Infinity`.
    """
    parser = _Parser(text)
    value = parser.parse_document()
    ranges = dict(parser.ranges)

    def get_range(pointer: str) -> SourceRange | None:
        return ranges.get(pointer)

    return ParsedDocument(value=value, uri=uri, get_range=get_range)
