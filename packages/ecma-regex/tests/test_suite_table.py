"""Every ECMA-262 pattern the JSON Schema suite uses must round-trip.

The table is collected programmatically from the draft2020-12 files whose
schemas carry `pattern` / `patternProperties`, so a suite update widens the
table automatically rather than silently leaving new patterns untested.
"""

import json
from pathlib import Path
from typing import cast

import pytest

import ecma_regex

SUITE_FILES = (
    "pattern.json",
    "patternProperties.json",
    "properties.json",
    "unevaluatedProperties.json",
    "ref.json",
)


def _property_names(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(cast("dict[str, object]", value))
    return set()


def _collect(node: object, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in cast("dict[str, object]", node).items():
            if key == "pattern" and isinstance(value, str):
                found.add(value)
            elif key == "patternProperties":
                found.update(_property_names(value))
            _collect(value, found)
    elif isinstance(node, list):
        for item in cast("list[object]", node):
            _collect(item, found)


def _suite_patterns() -> list[str]:
    base = Path(__file__).resolve().parents[3] / "test-suite" / "tests" / "draft2020-12"
    if not base.is_dir():
        return []
    found: set[str] = set()
    for name in SUITE_FILES:
        path = base / name
        if path.is_file():
            _collect(
                cast("object", json.loads(path.read_text(encoding="utf-8"))), found
            )
    return sorted(found)


SUITE_PATTERNS = _suite_patterns()

pytestmark = pytest.mark.skipif(
    not SUITE_PATTERNS,
    reason="the JSON Schema test suite submodule is not checked out",
)


def test_table_is_not_accidentally_empty() -> None:
    # A guard against the collector silently breaking: the draft2020-12
    # files above have carried well over ten distinct patterns for years.
    assert len(SUITE_PATTERNS) >= 10


@pytest.mark.parametrize("pattern", SUITE_PATTERNS)
def test_suite_pattern_parses_translates_and_compiles(pattern: str) -> None:
    parsed = ecma_regex.parse(pattern)
    assert isinstance(parsed, ecma_regex.Pattern)
    translated = ecma_regex.translate(parsed)
    assert isinstance(translated, str)
    compiled = ecma_regex.compile(pattern)
    assert compiled.translated == translated
    assert isinstance(compiled.search(""), bool)


@pytest.mark.parametrize("pattern", SUITE_PATTERNS)
def test_suite_pattern_star_height_is_computable(pattern: str) -> None:
    assert ecma_regex.star_height(ecma_regex.parse(pattern)) >= 0


SUITE_PROBES = (
    "",
    "foo",
    "bar",
    "foobar",
    "aaa",
    "aaa\n",
    "X_",
    "12",
    "abc123",
    "olé",
    "字",
    "٣",
    "f\ro",
    "fxo",
)


def test_regex_backend_agrees_with_re_backend_on_the_whole_table() -> None:
    pytest.importorskip("regex")
    for pattern in SUITE_PATTERNS:
        with_re = ecma_regex.compile(pattern, backend="re")
        with_regex = ecma_regex.compile(pattern, backend="regex")
        for probe in SUITE_PROBES:
            assert with_re.search(probe) == with_regex.search(probe), (
                pattern,
                probe,
            )
