# The standard formats (DESIGN.md D16 `.formats`; M7): one table per
# built-in dialect, each entry a predicate implemented from the format's
# RFC and verified against the official suite. Core never imports this
# package; a caller injects a table with `create_engine(formats=...)`.
#
# Conventions for every predicate module in this package:
# - a predicate is a plain module-level `def name(value: str) -> bool`
#   (the keyword guards the instance type first; the standalone emitter
#   imports predicates by `module:name`, so they must be top-level);
# - regexes are ABNF transcriptions built from named string fragments and
#   compiled once with `anchored()`; never `$` (it matches before a
#   trailing newline), never `\d`/`\w`/`\s` (Unicode-aware in `re`: the
#   suite's Bengali-digit cases), always explicit ASCII classes;
# - no lazy imports (a standalone module's validation must generate no
#   code and import nothing after load) and no raising on instance data;
# - imports limited to the standard library, `ecma_regex`, and core's
#   `formats`, `errors`, and `json_model` leaves (P5).
#
# Dependency direction: imports the sibling predicate modules and core's
# `formats` contract and dialect URIs. Nothing in `json_schema_engine.core`
# or `.compiler` imports this package.

from collections.abc import Mapping
from types import MappingProxyType

from json_schema_engine.core.formats import (
    FormatDefinition,
    FormatPredicate,
    FormatTable,
)
from json_schema_engine.core.keywords._ids import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
)
from json_schema_engine.formats import datetime_, idna_, misc, net, pointer, uri
from json_schema_engine.formats._abnf import anchored

__all__ = [
    "FORMATS_2019_09",
    "FORMATS_2020_12",
    "FORMATS_DRAFT_06",
    "FORMATS_DRAFT_07",
    "anchored",
    "format_table_for",
]


def _entry(
    predicate: FormatPredicate, *, unavailable: str | None = None
) -> FormatDefinition:
    """A table entry for a module-level predicate, with its import path."""
    return FormatDefinition(
        predicate,
        unavailable=unavailable,
        import_path=f"{predicate.__module__}:{predicate.__name__}",
    )


def _table(entries: Mapping[str, FormatDefinition]) -> FormatTable:
    return MappingProxyType(dict(entries))


def _subset(table: FormatTable, omit: frozenset[str]) -> FormatTable:
    return _table({name: entry for name, entry in table.items() if name not in omit})


# 2020-12 §7.3: the nineteen defined formats.
FORMATS_2020_12: FormatTable = _table(
    {
        "date-time": _entry(datetime_.date_time),
        "date": _entry(datetime_.date),
        "time": _entry(datetime_.time),
        "duration": _entry(datetime_.duration),
        "email": _entry(net.email),
        "idn-email": _entry(net.idn_email),
        "hostname": _entry(net.hostname),
        "idn-hostname": _entry(
            idna_.idn_hostname,
            unavailable=None if idna_.HAVE_IDNA else idna_.IDNA_EXTRA,
        ),
        "ipv4": _entry(net.ipv4),
        "ipv6": _entry(net.ipv6),
        "uri": _entry(uri.uri),
        "uri-reference": _entry(uri.uri_reference),
        "iri": _entry(uri.iri),
        "iri-reference": _entry(uri.iri_reference),
        "uuid": _entry(misc.uuid),
        "uri-template": _entry(uri.uri_template),
        "json-pointer": _entry(pointer.json_pointer),
        "relative-json-pointer": _entry(pointer.relative_json_pointer),
        "regex": _entry(misc.regex),
    }
)
# 2019-09 §7.3 names the same nineteen formats.
FORMATS_2019_09: FormatTable = FORMATS_2020_12
# draft-07 §7.3: no `uuid`, no `duration`.
FORMATS_DRAFT_07: FormatTable = _subset(
    FORMATS_2020_12, frozenset({"uuid", "duration"})
)
# draft-06 §8.3: date-time, email, hostname, ipv4, ipv6, uri, uri-reference,
# uri-template, json-pointer.
_DRAFT_06_NAMES = frozenset(
    {
        "date-time",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "uri",
        "uri-reference",
        "uri-template",
        "json-pointer",
    }
)
FORMATS_DRAFT_06: FormatTable = _table(
    {name: entry for name, entry in FORMATS_2020_12.items() if name in _DRAFT_06_NAMES}
)

_BY_DIALECT: Mapping[str, FormatTable] = {
    DIALECT_2020_12: FORMATS_2020_12,
    DIALECT_2019_09: FORMATS_2019_09,
    DIALECT_DRAFT_07: FORMATS_DRAFT_07,
    DIALECT_DRAFT_06: FORMATS_DRAFT_06,
}


def format_table_for(dialect_uri: str) -> FormatTable:
    """The standard table for a built-in dialect URI (fragment ignored)."""
    try:
        return _BY_DIALECT[dialect_uri.rstrip("#")]
    except KeyError:
        raise ValueError(
            f"no standard format table for dialect {dialect_uri!r}"
        ) from None
