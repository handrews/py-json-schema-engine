# The record channel's data: evaluation-path nodes, the three record kinds,
# the frame, and the trace tree (DESIGN.md §4 normative channel semantics;
# D6 tracing; P6 records vs. units; P7 identity-keyed structures).
#
# Dependency direction: imports `cursor`, `ref`, `json_model`, `lowering`
# and `messages` (to realize a deferred error description). The evaluator
# (which owns §4's rules) and the renderers import this; this module holds
# no behavior beyond path materialization and that realization, so it never
# imports them back.
#
# These are records, not output units (P6): they are mutable, identity-keyed,
# and hold live `Cursor`/`SchemaRef` objects plus an unmaterialized path.
# Output units are `TypedDict`s with wire-format field names, produced from
# these only when something escapes to a caller — which is what makes
# annotation elision (D5) a matter of not creating a record at all.

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.lowering import LowerMessage, LowerParams
from json_schema_engine.core.messages import realize
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


# A deferred error description in lowering IR (P18): called at most once,
# when the record is first rendered, and realized against the record's own
# cursor value.
type MessageBuilder = Callable[[], tuple[LowerMessage, LowerParams | None]]


class ErrorRecord:
    """One assertion failure (D13).

    `behavior_id` and `keyword_name` are `None` when the schema itself
    rejected rather than a keyword — the boolean `false` schema, which has no
    keyword to name.

    `params` is structured error data, kept separate from `message` so that
    rendering stays presentation and a future compatibility adapter can
    rebuild another library's error shape from the parts.

    `message` may be a `MessageBuilder` rather than text (P18): the
    interpreter defers building and realizing a description until the
    record is rendered, since most records never are — a verdict-only
    evaluation renders none, and an error under a losing `anyOf` branch or
    an `if` condition is dropped. `message` and `params` realize it on first
    read, so a reader never sees the difference.

    Not a dataclass because of that laziness: a dataclass field and a
    property cannot share the name `message`, and `cached_property` needs
    the `__dict__` that slots forbid. The record keeps the description and
    nothing else per error, so a deferred error gives the garbage collector
    no more to walk than an eager one.
    """

    __slots__ = (
        "_builder",
        "_message",
        "_params",
        "behavior_id",
        "cursor",
        "keyword_name",
        "path_node",
        "schema_ref",
        "vocabulary_uri",
    )

    def __init__(
        self,
        behavior_id: str | None,
        keyword_name: str | None,
        vocabulary_uri: str | None,
        schema_ref: SchemaRef,
        path_node: PathNode | None,
        cursor: Cursor,
        message: str | MessageBuilder,
        params: Mapping[str, JsonValue] | None = None,
    ) -> None:
        self.behavior_id = behavior_id
        self.keyword_name = keyword_name
        self.vocabulary_uri = vocabulary_uri
        self.schema_ref = schema_ref
        self.path_node = path_node
        self.cursor = cursor
        if isinstance(message, str):
            self._builder: MessageBuilder | None = None
            self._message = message
            self._params = params
        else:
            self._builder = message
            self._message = ""
            self._params = None

    def _realize(self) -> None:
        builder = self._builder
        if builder is not None:
            self._builder = None
            self._message, self._params = realize(*builder(), self.cursor.value)

    @property
    def message(self) -> str:
        self._realize()
        return self._message

    @property
    def params(self) -> Mapping[str, JsonValue] | None:
        self._realize()
        return self._params

    def __repr__(self) -> str:
        return (
            f"ErrorRecord(keyword_name={self.keyword_name!r}, "
            f"cursor={self.cursor.pointer!r}, message={self.message!r})"
        )


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
