"""Tests for json_schema_engine.test_kit.positions (DESIGN.md D17)."""

from __future__ import annotations

import json

import pytest

from json_schema_engine.test_kit.positions import (
    ParsedDocument,
    SourceSpan,
    parse_json_with_ranges,
)

# Deliberately multi-line so line/column assertions below are meaningful, and
# packed with edge cases: nested objects/arrays, escapes (including a
# surrogate-pair \u escape and a literal astral character), non-ASCII text,
# and keys containing '~', '/', and a double quote.
FIXTURE_TEXT = """{
  "name": "caf\\u00e9",
  "emoji": "😀",
  "tilde~key": 1,
  "slash/key": 2,
  "quote\\"key": 3,
  "nested": {
    "list": [1, 2, {"deep": true}]
  },
  "escapes": "line\\nbreak\\ttab\\uD83D\\uDE00"
}"""


def _slice(text: str, span: SourceSpan) -> str:
    return text[span["start"]["offset"] : span["end"]["offset"]]


def _parse(text: str) -> ParsedDocument:
    return parse_json_with_ranges(text, uri="urn:test:doc")


def test_value_matches_json_loads() -> None:
    doc = _parse(FIXTURE_TEXT)
    assert doc.value == json.loads(FIXTURE_TEXT)
    assert doc.uri == "urn:test:doc"


def test_value_spans_slice_back_to_source_text() -> None:
    doc = _parse(FIXTURE_TEXT)

    range_ = doc.get_range("/tilde~0key")
    assert range_ is not None
    assert _slice(FIXTURE_TEXT, range_["value"]) == "1"

    nested_bool = doc.get_range("/nested/list/2/deep")
    assert nested_bool is not None
    assert _slice(FIXTURE_TEXT, nested_bool["value"]) == "true"


def test_key_spans_slice_back_to_quoted_key_token() -> None:
    doc = _parse(FIXTURE_TEXT)

    range_ = doc.get_range("/tilde~0key")
    assert range_ is not None
    assert "key" in range_
    assert _slice(FIXTURE_TEXT, range_["key"]) == '"tilde~key"'

    slash_range = doc.get_range("/slash~1key")
    assert slash_range is not None
    assert "key" in slash_range
    assert _slice(FIXTURE_TEXT, slash_range["key"]) == '"slash/key"'

    quote_range = doc.get_range('/quote"key')
    assert quote_range is not None
    assert "key" in quote_range
    assert _slice(FIXTURE_TEXT, quote_range["key"]) == '"quote\\"key"'


def test_array_element_range_has_no_key_span() -> None:
    doc = _parse(FIXTURE_TEXT)
    range_ = doc.get_range("/nested/list/0")
    assert range_ is not None
    assert "key" not in range_


def test_line_and_column_for_value_on_third_line() -> None:
    doc = _parse(FIXTURE_TEXT)
    range_ = doc.get_range("/emoji")
    assert range_ is not None
    assert range_["value"]["start"]["line"] == 3
    # `  "emoji": ` -- the value starts at column 12.
    assert range_["value"]["start"]["column"] == 12


def test_root_pointer_span_covers_whole_document() -> None:
    doc = _parse(FIXTURE_TEXT)
    range_ = doc.get_range("")
    assert range_ is not None
    assert _slice(FIXTURE_TEXT, range_["value"]) == FIXTURE_TEXT
    assert range_["value"]["start"]["offset"] == 0
    assert range_["value"]["end"]["offset"] == len(FIXTURE_TEXT)


def test_unknown_pointer_returns_none() -> None:
    doc = _parse(FIXTURE_TEXT)
    assert doc.get_range("/does/not/exist") is None


def test_astral_character_offsets_are_code_point_based() -> None:
    text = '{"a": "😀", "b": 2}'
    doc = _parse(text)
    assert doc.value == {"a": "\U0001f600", "b": 2}

    a_range = doc.get_range("/a")
    assert a_range is not None
    # The emoji string token is `"😀"`: one code point between the quotes.
    assert a_range["value"]["end"]["offset"] - a_range["value"]["start"]["offset"] == 3

    b_range = doc.get_range("/b")
    assert b_range is not None
    assert _slice(text, b_range["value"]) == "2"


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1',
        "[1, 2",
        '"unterminated',
    ],
)
def test_truncated_input_raises_value_error_with_position(text: str) -> None:
    with pytest.raises(ValueError, match=r"line \d+, column \d+"):
        parse_json_with_ranges(text, uri="urn:test:doc")


def test_trailing_garbage_raises_value_error_with_position() -> None:
    with pytest.raises(ValueError, match=r"line \d+, column \d+"):
        parse_json_with_ranges("{}garbage", uri="urn:test:doc")


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "[NaN]"])
def test_non_finite_constants_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match=r"line \d+, column \d+"):
        parse_json_with_ranges(text, uri="urn:test:doc")


def test_empty_object_and_array() -> None:
    doc = _parse('{"o": {}, "a": []}')
    assert doc.value == {"o": {}, "a": []}
    o_range = doc.get_range("/o")
    a_range = doc.get_range("/a")
    assert o_range is not None
    assert a_range is not None
    assert _slice('{"o": {}, "a": []}', o_range["value"]) == "{}"
    assert _slice('{"o": {}, "a": []}', a_range["value"]) == "[]"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-0", 0),
        ("1e10", 1e10),
        ("123456789012345678901234567890", 123456789012345678901234567890),
    ],
)
def test_numbers_decode_exactly(text: str, expected: object) -> None:
    doc = _parse(text)
    assert doc.value == expected
    assert type(doc.value) is type(json.loads(text))


def test_source_range_shape() -> None:
    doc = _parse('{"a": 1}')
    range_ = doc.get_range("/a")
    assert range_ is not None
    assert set(range_) == {"value", "key"}
    assert range_["value"]["start"]["line"] == 1
    assert range_["value"]["start"]["column"] == 7
    assert range_["value"]["start"]["offset"] == 6
