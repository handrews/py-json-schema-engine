# The instance cursor: a parent-linked position in the instance document
# (DESIGN.md §2 module table; P7 identity-keyed structures; §4 rule 4).
#
# Dependency direction: imports `json_model` only. The evaluator, the channel
# records, and the output layer all import this; it imports none of them.
#
# Cursor identity carries semantic weight and is the reason for `eq=False`.
# In-place applicators (`$ref`, `allOf`, `if`) apply subschemas to the *same*
# cursor object, while child applicators (`properties`, `items`) build child
# cursors. Channel rule 4 filters visible dependency records by that identity
# — which is what keeps a cousin schema's records invisible even when the two
# instance locations are structurally identical. A value-equality dataclass
# would make cousins visible to each other and break
# `unevaluatedProperties`; `frozen=True` alone would not help, since it adds
# value equality rather than removing it.

from dataclasses import dataclass, field

from json_schema_engine.core.json_model import JsonValue, escape_segment


@dataclass(eq=False, slots=True)
class Cursor:
    """A position in the instance document, linked to its parent.

    Two cursors over equal values at equal locations are still two distinct
    cursors, and hash and compare as such.
    """

    value: JsonValue
    parent: "Cursor | None" = None
    # `str` for an object member, `int` for an array element; `None` only at
    # the root. Keeping the two apart lets a later output layer report an
    # array index as a number without re-parsing the pointer.
    segment: str | int | None = None
    # Materialized lazily: a pointer string is only ever needed when a unit
    # escapes to output, and most cursors in a run never produce one.
    _pointer: str | None = field(default=None, init=False, repr=False)

    @property
    def pointer(self) -> str:
        """The RFC 6901 JSON Pointer for this position; `""` at the root.

        Walks to the nearest ancestor that already has a cached pointer and
        fills in the chain on the way back down, so repeated output from deep
        inside a large instance stays linear overall. Iterative rather than
        recursive: instance depth is attacker-controlled, and a cursor chain
        is not covered by the evaluator's depth budget (P3).
        """
        cached = self._pointer
        if cached is not None:
            return cached
        chain: list[Cursor] = []
        node: Cursor | None = self
        while node is not None and node._pointer is None:
            chain.append(node)
            node = node.parent
        # The loop stopped either at a cached ancestor or past the root; both
        # give a prefix the chain below extends.
        ancestor = node._pointer if node is not None else None
        pointer = ancestor if ancestor is not None else ""
        for link in reversed(chain):
            if link.parent is None:
                pointer = ""
            else:
                pointer += "/" + escape_segment(str(link.segment))
            link._pointer = pointer
        return pointer


def root_cursor(value: JsonValue) -> Cursor:
    """Create a cursor at the root of an instance document."""
    return Cursor(value)


def child_cursor(parent: Cursor, segment: str | int, value: JsonValue) -> Cursor:
    """Create a cursor for a named or indexed child of `parent`."""
    return Cursor(value, parent, segment)
