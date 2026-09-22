"""JSON model: type dispatch, equality, canonical keys, RFC 6901 escaping (P2)."""

import operator
from collections.abc import Sequence

import pytest

from json_schema_engine.core.json_model import (
    JsonType,
    JsonValue,
    canonical_key,
    code_point_length,
    escape_segment,
    first_duplicate_pair,
    has_duplicate_items,
    is_integer_value,
    is_multiple_of,
    is_object,
    json_equal,
    json_type_of,
    pointer_of,
    unescape_segment,
)

TYPE_CASES: list[tuple[JsonValue, JsonType]] = [
    (None, JsonType.NULL),
    (True, JsonType.BOOLEAN),
    (False, JsonType.BOOLEAN),
    (0, JsonType.NUMBER),
    (1, JsonType.NUMBER),
    (-17, JsonType.NUMBER),
    (2**70, JsonType.NUMBER),
    (1.0, JsonType.NUMBER),
    (1.5, JsonType.NUMBER),
    ("", JsonType.STRING),
    ("true", JsonType.STRING),
    ([], JsonType.ARRAY),
    ([1, 2], JsonType.ARRAY),
    ({}, JsonType.OBJECT),
    ({"a": 1}, JsonType.OBJECT),
]


@pytest.mark.parametrize(("value", "expected"), TYPE_CASES)
def test_json_type_of(value: JsonValue, expected: JsonType) -> None:
    assert json_type_of(value) is expected


@pytest.mark.parametrize("value", [v for v, _ in TYPE_CASES])
def test_json_type_of_never_returns_integer(value: JsonValue) -> None:
    assert json_type_of(value) is not JsonType.INTEGER


def test_json_type_names_are_the_spec_spellings() -> None:
    assert [t.value for t in JsonType] == [
        "null",
        "boolean",
        "object",
        "array",
        "number",
        "string",
        "integer",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, True),
        (1, True),
        (-3, True),
        (2**70, True),
        (1.0, True),
        (-0.0, True),
        (1e21, True),
        (1.5, False),
        (float("nan"), False),
        (float("inf"), False),
        (float("-inf"), False),
        (True, False),
        (False, False),
        ("1", False),
        (None, False),
        ([1], False),
        ({"a": 1}, False),
    ],
)
def test_is_integer_value(value: JsonValue, expected: bool) -> None:
    assert is_integer_value(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, True),
        ({"a": 1}, True),
        ([], False),
        (None, False),
        ("{}", False),
        (1, False),
    ],
)
def test_is_object(value: JsonValue, expected: bool) -> None:
    assert is_object(value) is expected


EQUAL_PAIRS: list[tuple[JsonValue, JsonValue]] = [
    (None, None),
    (True, True),
    (False, False),
    (1, 1),
    (1, 1.0),
    (1.0, 1),
    (0, -0.0),
    (2**70, float(2**70)),
    ("a", "a"),
    ("", ""),
    ([], []),
    ([1, 2], [1, 2.0]),
    ([[1], [2]], [[1.0], [2]]),
    ({}, {}),
    ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
    ({"a": {"b": [1, {"c": None}]}}, {"a": {"b": [1.0, {"c": None}]}}),
    ({"__proto__": 1}, {"__proto__": 1.0}),
]

UNEQUAL_PAIRS: list[tuple[JsonValue, JsonValue]] = [
    (True, 1),
    (True, 1.0),
    (False, 0),
    (False, None),
    (None, 0),
    (None, ""),
    (None, []),
    (None, {}),
    (0, ""),
    (1, "1"),
    (1, 2),
    (1, 1.5),
    (2**70, 2**70 + 1),
    ("a", "b"),
    ("1", [1]),
    ([1, 2], [2, 1]),
    ([1, 2], [1, 2, 3]),
    ([1], {"0": 1}),
    ({"a": 1}, {"a": True}),
    ({"a": 1}, {"b": 1}),
    ({"a": 1}, {"a": 1, "b": 2}),
    ({"a": {"b": 1}}, {"a": {"b": 2}}),
    ([True], [1]),
    ({"a": [True]}, {"a": [1]}),
]


@pytest.mark.parametrize(("a", "b"), EQUAL_PAIRS)
def test_json_equal_holds_in_both_directions(a: JsonValue, b: JsonValue) -> None:
    assert json_equal(a, b)
    assert json_equal(b, a)


@pytest.mark.parametrize(("a", "b"), UNEQUAL_PAIRS)
def test_json_equal_fails_in_both_directions(a: JsonValue, b: JsonValue) -> None:
    assert not json_equal(a, b)
    assert not json_equal(b, a)


def test_json_equal_separates_true_from_one_where_python_does_not() -> None:
    # The whole point of P2: plain `==` and `hash` both conflate these.
    assert operator.eq(True, 1)
    assert hash(True) == hash(1)
    assert not json_equal(True, 1)
    assert not json_equal(1, True)
    assert not json_equal([True], [1])
    assert not json_equal({"a": True}, {"a": 1})


@pytest.mark.parametrize(("a", "b"), EQUAL_PAIRS)
def test_canonical_key_agrees_with_json_equal(a: JsonValue, b: JsonValue) -> None:
    assert canonical_key(a) == canonical_key(b)


@pytest.mark.parametrize(("a", "b"), UNEQUAL_PAIRS)
def test_canonical_key_separates_values_that_could_collide(
    a: JsonValue, b: JsonValue
) -> None:
    # Not required by the contract (which is one-directional), but every
    # distinct pair the engine actually meets must land in its own bucket,
    # or `uniqueItems` degrades to a linear scan per item.
    assert canonical_key(a) != canonical_key(b)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, "n1"),
        (1.0, "n1"),
        (True, "true"),
        (False, "false"),
        (None, "null"),
    ],
)
def test_canonical_key_renderings(value: JsonValue, expected: str) -> None:
    assert canonical_key(value) == expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        # Each pair collides under a key that joins raw string content with
        # separators instead of quoting it.
        (["a,b"], ["a", "b"]),
        ([""], []),
        ({"a,b": 1}, {"a": 1, "b": 1}),
        ({'a":n1,"b': 1}, {"a": 1, "b": 1}),
        ({"[": "]"}, {"[": "]", "": ""}),
        (["]"], [["]"]]),
    ],
)
def test_canonical_key_structure_cannot_be_forged_by_string_content(
    a: JsonValue, b: JsonValue
) -> None:
    assert not json_equal(a, b)
    assert canonical_key(a) != canonical_key(b)


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("", ""),
        ("a", "a"),
        ("a/b", "a~1b"),
        ("a~b", "a~0b"),
        ("~1", "~01"),
        ("~0", "~00"),
        ("/", "~1"),
        ("~", "~0"),
        ("~/~", "~0~1~0"),
        ("m~n", "m~0n"),
        ("a~1b", "a~01b"),
        ("c%d", "c%d"),
        ('k"l', 'k"l'),
        (" ", " "),
    ],
)
def test_escape_segment_round_trip(raw: str, escaped: str) -> None:
    assert escape_segment(raw) == escaped
    assert unescape_segment(escaped) == raw


@pytest.mark.parametrize(
    "raw",
    ["", "~", "/", "~0", "~1", "~01", "a/b~c", "~~//", "0", "-", "foo bar"],
)
def test_escape_unescape_is_the_identity(raw: str) -> None:
    assert unescape_segment(escape_segment(raw)) == raw


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        ([], ""),
        ([""], "/"),
        (["a"], "/a"),
        (["a", "b"], "/a/b"),
        ([0], "/0"),
        (["a", 0, "b"], "/a/0/b"),
        (["m~n"], "/m~0n"),
        (["a/b"], "/a~1b"),
        (["", ""], "//"),
    ],
)
def test_pointer_of(segments: Sequence[str | int], expected: str) -> None:
    assert pointer_of(segments) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("abc", 3),
        # One astral code point: two UTF-16 code units, one code point.
        ("\U0001f600", 1),
        ("a\U0001f600b", 3),
        # A combining sequence is two code points, not one grapheme.
        ("é", 2),
    ],
)
def test_code_point_length(text: str, expected: int) -> None:
    assert code_point_length(text) == expected


# --- M2 helpers: multipleOf exactness and uniqueItems duplicates (P2, D20) --


@pytest.mark.parametrize(
    ("instance", "divisor", "expected"),
    [
        (10, 5, True),
        (7, 5, False),
        (0.0075, 0.0001, True),  # suite: decimal, not binary, semantics
        (3e-8, 1e-8, True),
        (4.5, 1.5, True),
        (0.3, 0.1, True),  # 0.3/0.1 is 2.9999… in binary, 3 in decimal
        (1e308, 0.123456789, False),  # suite: "float division = inf"
        (12391239123, 1e-8, True),
        (10**40, 10**20, True),
        (3, 0.5, True),
        (5, 0, False),
    ],
)
def test_is_multiple_of(
    instance: int | float, divisor: int | float, expected: bool
) -> None:
    assert is_multiple_of(instance, divisor) is expected


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([1, 2, 3], None),
        ([1, 1.0], [0, 1]),
        ([1, True], None),
        ([0, False], None),
        (["a", "a"], [0, 1]),
        ([{"a": 1, "b": 2}, {"b": 2, "a": 1}], [0, 1]),
        ([{"a": 1}, {"a": True}], None),
        ([[1, 2], [2, 1]], None),
        ([None, None], [0, 1]),
        ([1, 2, 1, 2], [0, 2]),
        ([], None),
    ],
)
def test_first_duplicate_pair(
    items: list[JsonValue], expected: tuple[int, int] | None
) -> None:
    assert first_duplicate_pair(items) == expected
    assert has_duplicate_items(items) is (expected is not None)
