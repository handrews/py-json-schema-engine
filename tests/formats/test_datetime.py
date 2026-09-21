# Direct-call coverage for `json_schema_engine.formats.datetime_` (M7 Step
# 1): the non-obvious cases the official suite's own date/date-time/time/
# duration fixtures already pin (leap seconds tied to a UTC-equivalent
# wall clock, RFC 3339 Appendix A's month-vs-minute ambiguity, arbitrary-
# length fractions and digit runs, and non-ASCII/control-character
# rejection) — a compact matrix, not a restatement of the suite.

from collections.abc import Callable

import pytest

from json_schema_engine.formats.datetime_ import date, date_time, duration, time

type Predicate = Callable[[str], bool]

CASES: tuple[tuple[Predicate, str, bool], ...] = (
    # Leap second validity is `second == 60` tied to a UTC-equivalent wall
    # clock of 23:59, per offset sign (`+`, `-`, and `Z`/no offset).
    (time, "23:59:60Z", True),
    (time, "01:29:60+01:30", True),
    (time, "15:59:60-08:00", True),
    (time, "00:29:60-23:30", True),
    (time, "23:29:60+23:30", True),
    (time, "23:59:60+01:00", False),
    (time, "22:59:60Z", False),
    (time, "24:59:00+01:00", False),  # hour 24 rejected before any leap check
    (date_time, "1998-12-31T15:59:60.123-08:00", True),
    # Fractions have no upper bound on digit count.
    (time, "00:59:59.999999999999999Z", True),
    # Non-ASCII digits are never accepted (`re` is Unicode-aware; explicit
    # `[0-9]` classes throughout rule out Bengali digits). `ruff format`
    # normalizes `\u` escapes back to the literal character, so the
    # confusable-character warning is suppressed per line instead.
    (date, "2020-0৪-01", False),  # noqa: RUF001
    (time, "1২:00:00Z", False),
    (duration, "P২Y", False),
    # `\Z` (not `$`) anchors the end: a trailing newline or NUL is invalid.
    (date, "2020-01-01\n", False),
    (date, "2020-01-01\x00", False),
    (duration, "P1D\n", False),
    # RFC 3339 Appendix A, not general ISO 8601: `dur-year`'s optional
    # month can't be skipped to reach a day, hours can't skip to seconds,
    # and a week can't combine with a zero-valued other component.
    (duration, "P1Y2D", False),
    (duration, "PT1H2S", False),
    (duration, "P0Y1W", False),
    # ...but a bare month unit is valid in the date position (day follows)
    # and the time position (second follows) alike, disambiguated by
    # which alternative of `dur-date` / `dur-time` matched.
    (duration, "P1M2D", True),
    (duration, "PT1M2S", True),
)


@pytest.mark.parametrize(
    "predicate,value,expected",
    CASES,
    ids=[f"{fn.__name__}:{value!r}" for fn, value, _ in CASES],
)
def test_case(predicate: Predicate, value: str, expected: bool) -> None:
    assert predicate(value) is expected
