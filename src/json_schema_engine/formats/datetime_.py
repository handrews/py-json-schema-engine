# Date and time formats (M7): `date`, `time`, `date-time` (RFC 3339 §5.6)
# and `duration` (RFC 3339 Appendix A). Step 1 (agent A) implements these.
#
# Dependency direction: standard library and this package's `anchored`.


def date(value: str) -> bool:
    """RFC 3339 `full-date`."""
    raise NotImplementedError


def time(value: str) -> bool:
    """RFC 3339 `full-time`."""
    raise NotImplementedError


def date_time(value: str) -> bool:
    """RFC 3339 `date-time`."""
    raise NotImplementedError


def duration(value: str) -> bool:
    """RFC 3339 Appendix A `duration`."""
    raise NotImplementedError
