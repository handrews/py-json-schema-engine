# The record channel's data: evaluation-path nodes, the three record kinds,
# the frame, and the trace tree (DESIGN.md §4 normative channel semantics;
# D6 tracing; P6 records vs. units; P7 identity-keyed structures).
#
# Dependency direction: imports `cursor`, `ref`, and `json_model`. The
# evaluator (which owns §4's rules) and the renderers import this; this
# module holds no behavior beyond path materialization, so it never imports
# them back.
#
# These are records, not output units (P6): they are mutable, identity-keyed,
# and hold live `Cursor`/`SchemaRef` objects plus an unmaterialized path.
# Output units are `TypedDict`s with wire-format field names, produced from
# these only when something escapes to a caller — which is what makes
# annotation elision (D5) a matter of not creating a record at all.

from collections.abc import Mapping
from dataclasses import dataclass, field

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.ref import SchemaRef


@dataclass(frozen=True, eq=False, slots=True)
class PathNode:
    """One segment of the evaluation path, linked to its parent.

    The chain is built on descent and materialized into a pointer string only
    when a unit escapes to output: most applications produce no output at
    all, so building strings eagerly would charge every schema application
    for work the flag format never uses.
    """

    parent: "PathNode | None"
    # Already RFC 6901 escaped. Escaping at construction keeps it off the
    # materialization path, which may run once per emitted unit, and the
    # producers (keyword names, array indices) know their own segment's form.
    segment: str

    def materialize(self) -> str:
        """The evaluation path as a JSON Pointer string."""
        return materialize_path(self)


def materialize_path(node: PathNode | None) -> str:
    """Walk a path chain to the root and join it; the root path is `""`.

    Takes `PathNode | None` because the root application has no node at all,
    and `""` is the pointer it needs.
    """
    segments: list[str] = []
    current = node
    while current is not None:
        segments.append(current.segment)
        current = current.parent
    segments.reverse()
    return "".join("/" + segment for segment in segments)


@dataclass(eq=False, slots=True)
class AnnotationRecord:
    """A keyword's annotation: its own value at an instance location (§4 rule 2).

    The value is the keyword's own value (draft-03 §12.9), not a derived
    summary — that is what `DependencyRecord` is for. Annotations are the
    only record kind a renderer ever sees.
    """

    behavior_id: str
    keyword_name: str
    # `None` for an unknown keyword, which annotates but belongs to no
    # vocabulary; the annotation selection (D5) filters on both.
    vocabulary_uri: str | None
    schema_ref: SchemaRef
    # The path of the schema object; the keyword's own segment is appended at
    # render time, so sibling keywords share one node.
    path_node: PathNode | None
    cursor: Cursor
    value: JsonValue


@dataclass(eq=False, slots=True)
class DependencyRecord:
    """Computed data one keyword sends to another (§4 rule 2; draft-03 App. D).

    Never rendered. `ctx.visible()` filters these by cursor identity (rule
    4), so the producing cursor object — not a pointer string — is what
    decides who can see this record.
    """

    behavior_id: str
    keyword_name: str
    vocabulary_uri: str | None
    schema_ref: SchemaRef
    path_node: PathNode | None
    cursor: Cursor
    # `object`, not `JsonValue`: dependency data is internal and may be a
    # `set[str]` of evaluated property names or any other Python structure.
    # Only the producing and consuming keywords interpret it.
    data: object


@dataclass(eq=False, slots=True)
class ErrorRecord:
    """One assertion failure (D13).

    `behavior_id` and `keyword_name` are `None` when the schema itself
    rejected rather than a keyword — the boolean `false` schema, which has no
    keyword to name.

    `params` is structured error data, kept separate from `message` so that
    rendering stays presentation and a future compatibility adapter can
    rebuild another library's error shape from the parts.
    """

    behavior_id: str | None
    keyword_name: str | None
    vocabulary_uri: str | None
    schema_ref: SchemaRef
    path_node: PathNode | None
    cursor: Cursor
    message: str
    params: Mapping[str, JsonValue] | None = None


@dataclass(slots=True)
class Frame:
    """The records of one in-flight schema application (§4 rule 1).

    On success the lists merge into the parent frame, on failure they are
    discarded (rule 3). No other visibility rule exists, which is why a frame
    needs no validity flag or parent link of its own: the evaluator holds the
    stack.

    The one record type with value semantics, since a frame is a mutable
    accumulator that nothing keys on.
    """

    annotations: list[AnnotationRecord] = field(default_factory=list[AnnotationRecord])
    dependencies: list[DependencyRecord] = field(default_factory=list[DependencyRecord])


@dataclass(frozen=True, slots=True)
class KeywordTrace:
    """One keyword evaluation within a traced schema application.

    Structural keywords (`$id`, `$schema`, `$defs`, ...) evaluate to nothing
    and never appear here (draft-03 §12.6, §12.10); an unknown keyword
    appears as valid, since it annotates and asserts nothing.
    """

    name: str
    valid: bool


@dataclass(eq=False, slots=True)
class TraceNode:
    """One schema application, recorded only when tracing (D6).

    The structured renderers need application boundaries, per-branch
    validity, and each keyword's verdict in evaluation order (draft-03
    `verbose` renders one node per keyword), which the flat error list
    cannot reconstruct. `valid` is settled when the application ends;
    `keywords` and `children` grow in evaluation order.
    """

    schema_ref: SchemaRef
    path_node: PathNode | None
    cursor: Cursor
    valid: bool = True
    keywords: list[KeywordTrace] = field(default_factory=list[KeywordTrace])
    children: list["TraceNode"] = field(default_factory=list["TraceNode"])
