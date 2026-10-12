# A schema position: the node plus its canonical location (DESIGN.md §2
# module table; P7 identity-keyed structures).
#
# Dependency direction: imports `json_model` and `uri` only. The dialect
# layer, the registry, the evaluator, and the records all build on it; it
# knows about none of them.

from dataclasses import dataclass, field

from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.uri import schema_location


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
    # `location`, built on first read: the renderers ask every record and
    # the trace node of an application for it, and the interpreter's cycle
    # guard asks on entry and exit. Derived from the fields above, so the
    # ref stays frozen and the fill goes through `object.__setattr__`, as
    # `PathNode._path` does.
    _location: str | None = field(default=None, init=False, repr=False)

    @property
    def location(self) -> str:
        """The canonical `schemaLocation` string for output units (D6).

        A URI: the pointer is fragment-encoded on the way out (P10), so the
        result can be pasted into a `$ref` or handed back to
        `Engine.locate` even when a member name holds a space or a `%`.
        """
        cached = self._location
        if cached is None:
            cached = schema_location(self.base_uri, self.pointer)
            object.__setattr__(self, "_location", cached)
        return cached
