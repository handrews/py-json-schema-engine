# The format table contract (DESIGN.md D16 `.formats`; M7): what a format
# is to the engine — a predicate plus the instance types it constrains —
# and the table shape the `format` keyword, the compiler's runtime, and
# the `json_schema_engine.formats` package all share. Core defines the
# contract and never imports a table (P5): a caller injects one through
# `create_engine(formats=...)`, exactly as the regex cache is injected.
#
# Dependency direction: imports `json_model` and `lowering` (for
# `TypeName`) only. A leaf, like `errors.py`.

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from json_schema_engine.core.json_model import JsonValue, is_integer_value, json_type_of
from json_schema_engine.core.lowering import TypeName

type FormatPredicate = Callable[[Any], bool]
"""A format's test. It runs only on instances of the definition's `types`
(the keyword guards first), so a string format may take `str`."""


@dataclass(frozen=True, slots=True)
class FormatDefinition:
    """One format: its predicate and the instance types it applies to.

    An instance of a type not listed is vacuously valid (the spec's
    "format applies to strings" rule, generalized so a custom table can
    constrain numbers). `unavailable` marks an entry that exists in the
    table but cannot run in this environment (an optional extra is
    missing); asserting it fails loudly at registration rather than
    silently passing. `import_path` (`module:attribute`) lets a
    standalone module import the predicate by name; an entry without one
    can only be used by runtime compilation.
    """

    test: FormatPredicate
    types: tuple[TypeName, ...] = ("string",)
    unavailable: str | None = None
    import_path: str | None = None


type FormatTable = Mapping[str, FormatDefinition]


def applies_to(types: tuple[TypeName, ...], value: JsonValue) -> bool:
    """Whether a format constrains `value` (P2: a bool is never a number)."""
    if "integer" in types and is_integer_value(value):
        return True
    return json_type_of(value).value in types
