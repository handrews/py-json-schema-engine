# A schema position: the node plus its canonical location (DESIGN.md §2
# module table; P7 identity-keyed structures).
#
# Dependency direction: imports `json_model` only. The dialect layer, the
# registry, the evaluator, and the records all build on it; it knows about
# none of them.

from dataclasses import dataclass

from json_schema_engine.core.json_model import JsonValue


@dataclass(frozen=True, eq=False, slots=True)
class SchemaRef:
    """A schema node together with where it lives.

    `frozen` because a resolved position is a fact that must not drift under
    a caller holding it; `eq=False` because identity is what the cycle guard
    and the record channel key on (P7), and because a value-equality
    dataclass over a `dict` node would be unhashable anyway.
    """

    node: JsonValue
    # Canonical and fragment-free: the `$id` in force at this position, with
    # every enclosing `$id` already resolved into it.
    base_uri: str
    # JSON Pointer from the root schema of `base_uri`'s resource — not from
    # the document root, which may differ once an embedded `$id` starts a new
    # resource.
    pointer: str

    @property
    def location(self) -> str:
        """The canonical `schemaLocation` string for output units (D6)."""
        return f"{self.base_uri}#{self.pointer}"
