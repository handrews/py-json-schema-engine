# Date and time formats (M7): `date`, `time`, `date-time` (RFC 3339 §5.6)
# and `duration` (RFC 3339 Appendix A), as ABNF transcriptions with the
# calendar and leap-second rules checked in Python.
#
# Dependency direction: standard library and this package's `_abnf`.

import re

from json_schema_engine.formats._abnf import anchored as _anchored

_Match = re.Match[str]

# --- `full-date` (RFC 3339 §5.6) --------------------------------------
#
# date-fullyear  = 4DIGIT
# date-month     = 2DIGIT  ; 01-12
# date-mday      = 2DIGIT  ; 01-28/29/30/31 depending on month/year
# full-date      = date-fullyear "-" date-month "-" date-mday
#
# The regex only pins the shape (four digits, two digits, two digits);
# month/day range and the Gregorian leap rule are checked in Python
# because they need calendar arithmetic the ABNF can't express.

_DATE_FRAGMENT = r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
_DATE_RE = _anchored(_DATE_FRAGMENT)

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap_year(year: int) -> bool:
    """Gregorian leap rule (proleptic: applies to 1582-10-10 and earlier)."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _valid_ymd(year: int, month: int, day: int) -> bool:
    if not 1 <= month <= 12:
        return False
    max_day = _DAYS_IN_MONTH[month - 1]
    if month == 2 and _is_leap_year(year):
        max_day = 29
    return 1 <= day <= max_day


def date(value: str) -> bool:
    """RFC 3339 `full-date`."""
    match = _DATE_RE.match(value)
    if match is None:
        return False
    return _valid_ymd(int(match["year"]), int(match["month"]), int(match["day"]))


# --- `full-time` (RFC 3339 §5.6) --------------------------------------
#
# time-hour      = 2DIGIT  ; 00-23
# time-minute    = 2DIGIT  ; 00-59
# time-second    = 2DIGIT  ; 00-58, 00-59, 00-60 based on leap second rules
# time-secfrac   = "." 1*DIGIT
# time-numoffset = ("+" / "-") time-hour ":" time-minute
# time-offset    = "Z" / time-numoffset
# partial-time   = time-hour ":" time-minute ":" time-second [time-secfrac]
# full-time      = partial-time time-offset
#
# The regex pins the shape and captures the fields; range checks (hour,
# minute, offset hour/minute, and the leap-second rule tying `second == 60`
# to a UTC-equivalent wall clock of 23:59) are Python-side because there is
# no fixture-driven leap-second table to consult, only the wall-clock
# equivalence the suite's fixtures pin down.

_TIME_FRAGMENT = (
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<frac>[0-9]+))?"
    r"(?P<offset>Z|z|[+-][0-9]{2}:[0-9]{2})"
)
_TIME_RE = _anchored(_TIME_FRAGMENT)


def _valid_clock(match: _Match) -> bool:
    hour = int(match["hour"])
    minute = int(match["minute"])
    second = int(match["second"])
    if hour > 23 or minute > 59 or second > 60:
        return False
    offset = match["offset"]
    if offset in ("Z", "z"):
        sign, offset_hour, offset_minute = 0, 0, 0
    else:
        sign = 1 if offset[0] == "+" else -1
        offset_hour = int(offset[1:3])
        offset_minute = int(offset[4:6])
        if offset_hour > 23 or offset_minute > 59:
            return False
    if second == 60:
        offset_total = offset_hour * 60 + offset_minute
        wall_minutes = (hour * 60 + minute - sign * offset_total) % 1440
        return wall_minutes == 23 * 60 + 59
    return True


def time(value: str) -> bool:
    """RFC 3339 `full-time`."""
    match = _TIME_RE.match(value)
    return match is not None and _valid_clock(match)


# --- `date-time` (RFC 3339 §5.6) --------------------------------------
#
# date-time = full-date "T" full-time
#
# RFC 3339 §5.6 permits "t"/"T" and "z"/"Z" case-insensitively (the ABNF
# note under the production); `_TIME_FRAGMENT` already accepts both cases
# for the offset's "Z".

_DATE_TIME_RE = _anchored(rf"{_DATE_FRAGMENT}[Tt]{_TIME_FRAGMENT}")


def date_time(value: str) -> bool:
    """RFC 3339 `date-time`."""
    match = _DATE_TIME_RE.match(value)
    if match is None:
        return False
    if not _valid_ymd(int(match["year"]), int(match["month"]), int(match["day"])):
        return False
    return _valid_clock(match)


# --- `duration` (RFC 3339 Appendix A) ----------------------------------
#
# dur-second = 1*DIGIT "S"
# dur-minute = 1*DIGIT "M" [dur-second]
# dur-hour   = 1*DIGIT "H" [dur-minute]
# dur-time   = "T" (dur-hour / dur-minute / dur-second)
# dur-day    = 1*DIGIT "D"
# dur-week   = 1*DIGIT "W"
# dur-month  = 1*DIGIT "M" [dur-day]
# dur-year   = 1*DIGIT "Y" [dur-month]
# dur-date   = (dur-day / dur-month / dur-year) [dur-time]
# duration   = "P" (dur-date / dur-time / dur-week)
#
# This is the RFC 3339 Appendix A grammar, not general ISO 8601: no
# fractional components, no combining weeks with anything else, and a
# duration must have at least one component. The alternations mirror the
# ABNF exactly, including the two independent meanings of a bare "M"
# (month at the date position, minute inside a "T..." time position); no
# Python-side validation is needed beyond the regex.

_DUR_SECOND = r"[0-9]+S"
_DUR_MINUTE = rf"[0-9]+M(?:{_DUR_SECOND})?"
_DUR_HOUR = rf"[0-9]+H(?:{_DUR_MINUTE})?"
_DUR_TIME = rf"T(?:{_DUR_HOUR}|{_DUR_MINUTE}|{_DUR_SECOND})"
_DUR_DAY = r"[0-9]+D"
_DUR_WEEK = r"[0-9]+W"
_DUR_MONTH = rf"[0-9]+M(?:{_DUR_DAY})?"
_DUR_YEAR = rf"[0-9]+Y(?:{_DUR_MONTH})?"
_DUR_DATE = rf"(?:{_DUR_DAY}|{_DUR_MONTH}|{_DUR_YEAR})(?:{_DUR_TIME})?"
_DURATION_FRAGMENT = rf"P(?:{_DUR_DATE}|{_DUR_TIME}|{_DUR_WEEK})"
_DURATION_RE = _anchored(_DURATION_FRAGMENT)


def duration(value: str) -> bool:
    """RFC 3339 Appendix A `duration`."""
    return _DURATION_RE.match(value) is not None
