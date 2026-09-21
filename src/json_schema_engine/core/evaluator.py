# The interpreter: frame-scoped record channel (DESIGN.md §4, normative),
# evaluation-path tracking with lazy materialization, cycle guard, depth
# budget (P3), dynamic scope (D8), and annotation elision (D5).
#
# Channel rules implemented here and nowhere else:
#  1. each schema application pushes a frame;
#  2. annotate() appends an annotation record (the keyword's own value) and
#     produce() a dependency record (computed data for other keywords) to
#     the current frame;
#  3. on success the frame merges into its parent, on failure it is
#     discarded;
#  4. visibility = the current frame's dependency records filtered by
#     cursor identity;
#  5. the annotation result is the root frame's annotation records filtered
#     by the annotation selection; selection never affects rule 4;
#  6. relevance (draft-03 §12.2): a keyword that accepts makes the errors of
#     its rejecting sub-evaluations irrelevant — evaluate_keyword drops them
#     (kept aside only when retention is requested, for verbose output);
#     rule 3 is the same transition for a rejecting schema object's accepting
#     sub-evaluations.
#
# Dependency direction: imports the registry, dialect, channel, cursor, ref,
# json_model, and errors modules. The engine façade imports this; keyword
# modules never do — they see only the `KeywordContext` protocol.

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from json_schema_engine.core.channel import (
    AnnotationRecord,
    DependencyRecord,
    ErrorRecord,
    Frame,
    PathNode,
)
from json_schema_engine.core.cursor import Cursor, root_cursor
from json_schema_engine.core.dialect import (
    CompiledRegex,
    DependencyView,
    DialectKeyword,
    ErrorParams,
    VisibleScope,
    unknown_keyword_id,
)
from json_schema_engine.core.errors import (
    InfiniteLoopError,
    InvalidSchemaError,
    KeywordContractError,
    MaxDepthExceededError,
    UndeclaredConsumptionError,
    UndeclaredProductionError,
    UnknownKeywordError,
)
from json_schema_engine.core.json_model import (
    JsonValue,
    escape_segment,
    is_object,
    json_type_of,
)
from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.registry import DEFAULT_MAX_DEPTH, SchemaRegistry
from json_schema_engine.core.uri import resolve, split_fragment

# Annotation elision (D5): when set, an annotation is recorded only if this
# returns true for (keyword name, vocabulary URI), and dependency records are
# recorded only for behavior ids some registered keyword consumes. `None`
# means "record everything" — the no-elision mode a trace needs.
type RecordPredicate = Callable[[str, str | None], bool]
type RegexCompiler = Callable[[str], CompiledRegex]


@dataclass(slots=True)
class EvalState:
    """Mutable state for one evaluation run.

    Frames, the relevant error list, the dynamic scope, the cycle guard, and
    the depth budget. Created per run, never shared.
    """

    registry: SchemaRegistry
    compile_regex: RegexCompiler
    should_record: RecordPredicate | None = None
    max_depth: int = DEFAULT_MAX_DEPTH
    # When true, errors made irrelevant by rule 6 are kept aside in
    # `dropped_errors` instead of being forgotten (verbose output, M5).
    retain_dropped: bool = False
    frames: list[Frame] = field(default_factory=lambda: [Frame()])
    # Relevant errors, in encounter order (rule 6).
    errors: list[ErrorRecord] = field(default_factory=list[ErrorRecord])
    dropped_errors: list[ErrorRecord] = field(default_factory=list[ErrorRecord])
    # Dynamic scope (D8): resources entered by schema application, outermost
    # first. Duplicates are fine — resolution takes the first hit.
    dynamic_scope: list[str] = field(default_factory=list[str])
    # Active schema-application nesting, bounded by `max_depth` (P3).
    depth: int = 0
    # Cycle guard: schema locations active at each cursor. Keyed by cursor
    # identity (P7): the same schema at a structurally equal but distinct
    # cursor is progress, not a loop.
    _active: dict[Cursor, set[str]] = field(default_factory=dict[Cursor, set[str]])

    @property
    def frame(self) -> Frame:
        """The innermost open frame."""
        return self.frames[-1]

    @property
    def root_annotations(self) -> list[AnnotationRecord]:
        """Annotations surviving at the root frame, before selection (rule 5)."""
        return self.frames[0].annotations

    @property
    def root_dependencies(self) -> list[DependencyRecord]:
        return self.frames[0].dependencies

    def drop_errors_from(self, mark: int) -> None:
        """Forget the errors pushed since `mark` (rule 6)."""
        if self.retain_dropped:
            self.dropped_errors.extend(self.errors[mark:])
        del self.errors[mark:]

    def enter(self, schema_ref: SchemaRef, cursor: Cursor) -> None:
        """Record entry into a schema application for cycle detection."""
        key = schema_ref.location
        active = self._active.get(cursor)
        if active is None:
            self._active[cursor] = {key}
            return
        if key in active:
            raise InfiniteLoopError(
                f"schema '{key}' re-entered at the same instance location",
                schema_location=key,
            )
        active.add(key)

    def exit(self, schema_ref: SchemaRef, cursor: Cursor) -> None:
        active = self._active[cursor]
        active.discard(schema_ref.location)
        if not active:
            del self._active[cursor]


class _KeywordContext:
    """The `KeywordContext` implementation: one instance per keyword run."""

    __slots__ = (
        "_behavior_id",
        "_cursor",
        "_name",
        "_path_node",
        "_schema_ref",
        "_state",
        "_value",
        "_vocabulary_uri",
        "reported",
    )

    def __init__(
        self,
        state: EvalState,
        schema_ref: SchemaRef,
        entry: DialectKeyword,
        value: JsonValue,
        cursor: Cursor,
        path_node: PathNode | None,
    ) -> None:
        self._state = state
        self._schema_ref = schema_ref
        self._name = entry.name
        self._behavior_id = entry.behavior.id
        self._vocabulary_uri: str | None = entry.vocabulary_uri
        self._value = value
        self._cursor = cursor
        self._path_node = path_node
        # Set once this keyword reports an error of its own: the rule 6
        # contract check in `evaluate_keyword`.
        self.reported = False

    @property
    def schema(self) -> dict[str, JsonValue]:
        node = self._schema_ref.node
        assert isinstance(node, dict)
        return node

    @property
    def cursor(self) -> Cursor:
        return self._cursor

    def apply(self, segments: Sequence[str | int], cursor: Cursor) -> bool:
        child = self._state.registry.child(self._schema_ref, segments)
        path_node = self._path_node
        for segment in segments:
            path_node = PathNode(path_node, escape_segment(str(segment)))
        return apply_schema(self._state, child, cursor, path_node)

    def resolve_ref(self, ref: str) -> SchemaRef:
        return self._state.registry.resolve_ref(ref, self._schema_ref.base_uri)

    def resolve_dynamic(self, ref: str) -> SchemaRef:
        registry = self._state.registry
        # Lexical resolution first: the initial target must exist. Rebinding
        # applies only to plain-name fragments minted by a dynamic anchor;
        # pointer fragments behave exactly like `$ref`.
        target = registry.resolve_ref(ref, self._schema_ref.base_uri)
        resource, fragment = split_fragment(resolve(self._schema_ref.base_uri, ref))
        if not fragment or fragment.startswith("/"):
            return target
        if registry.dynamic_anchor(resource, fragment) is None:
            return target
        for scope_uri in self._state.dynamic_scope:
            hit = registry.dynamic_anchor(scope_uri, fragment)
            if hit is not None:
                return hit
        return target

    def resolve_recursive(self, ref: str) -> SchemaRef:
        registry = self._state.registry
        # 2019-09: the reference is "#"; a non-empty fragment behaves like
        # `$ref`. Rebinding is all-or-nothing on the root `$recursiveAnchor`.
        target = registry.resolve_ref(ref, self._schema_ref.base_uri)
        resource, fragment = split_fragment(resolve(self._schema_ref.base_uri, ref))
        if fragment:
            return target
        if not registry.has_recursive_root(resource):
            return target
        for scope_uri in self._state.dynamic_scope:
            if registry.has_recursive_root(scope_uri):
                return registry.root_ref(scope_uri)
        return target

    def apply_resolved(self, target: SchemaRef) -> bool:
        path_node = PathNode(self._path_node, escape_segment(self._name))
        return apply_schema(self._state, target, self._cursor, path_node)

    def compile_regex(self, pattern: str) -> CompiledRegex:
        return self._state.compile_regex(pattern)

    def annotate(self) -> None:
        predicate = self._state.should_record
        if predicate is not None and not predicate(self._name, self._vocabulary_uri):
            return
        self._state.frame.annotations.append(
            AnnotationRecord(
                behavior_id=self._behavior_id,
                keyword_name=self._name,
                vocabulary_uri=self._vocabulary_uri,
                schema_ref=self._schema_ref,
                path_node=self._path_node,
                cursor=self._cursor,
                value=self._value,
            )
        )

    def produce(self, data: object) -> None:
        registry = self._state.registry
        # A producer nobody declared is invisible to elision analysis and to
        # the compiler's channel routing: fail loud, not wrong.
        if not registry.is_produced(self._behavior_id):
            raise UndeclaredProductionError(
                f"'{self._behavior_id}' produces dependency data without "
                "declaring it in analyze().produces",
                schema_location=self._schema_ref.location,
            )
        # Under elision, dependency data nobody consumes is never read.
        if self._state.should_record is not None and not registry.is_consumed(
            self._behavior_id
        ):
            return
        self._state.frame.dependencies.append(
            DependencyRecord(
                behavior_id=self._behavior_id,
                keyword_name=self._name,
                vocabulary_uri=self._vocabulary_uri,
                schema_ref=self._schema_ref,
                path_node=self._path_node,
                cursor=self._cursor,
                data=data,
            )
        )

    def visible(
        self, behavior_ids: Sequence[str], scope: VisibleScope = "all"
    ) -> list[DependencyView]:
        # Under elision, reading an id nobody declared through
        # `StaticFacts.consumes` means the records may already be gone.
        if self._state.should_record is not None:
            registry = self._state.registry
            for behavior_id in behavior_ids:
                if not registry.is_consumed(behavior_id):
                    raise UndeclaredConsumptionError(
                        f"'{self._behavior_id}' reads '{behavior_id}' without "
                        "declaring it in analyze().consumes",
                        schema_location=self._schema_ref.location,
                    )
        # Every keyword of one schema application shares its path node, so
        # identity picks out the adjacent keywords' records.
        wanted = set(behavior_ids)
        return [
            DependencyView(record.behavior_id, record.data)
            for record in self._state.frame.dependencies
            if record.cursor is self._cursor
            and record.behavior_id in wanted
            and (scope == "all" or record.path_node is self._path_node)
        ]

    def error(self, message: str, params: ErrorParams | None = None) -> None:
        self.reported = True
        self._state.errors.append(
            ErrorRecord(
                behavior_id=self._behavior_id,
                keyword_name=self._name,
                vocabulary_uri=self._vocabulary_uri,
                schema_ref=self._schema_ref,
                path_node=self._path_node,
                cursor=self._cursor,
                message=message,
                params=params,
            )
        )


def apply_schema(
    state: EvalState,
    schema_ref: SchemaRef,
    cursor: Cursor,
    path_node: PathNode | None,
) -> bool:
    """Apply one schema to one instance cursor.

    Pushes a frame, evaluates the dialect's keywords in order, and merges or
    discards the frame per §4. Raises `InfiniteLoopError` if the schema is
    already active at this cursor and `MaxDepthExceededError` past the depth
    budget.
    """
    if state.depth >= state.max_depth:
        raise MaxDepthExceededError(
            f"schema application exceeds max_depth ({state.max_depth})",
            schema_location=schema_ref.location,
        )
    state.depth += 1
    try:
        return _apply_at_depth(state, schema_ref, cursor, path_node)
    finally:
        state.depth -= 1


def _apply_at_depth(
    state: EvalState,
    schema_ref: SchemaRef,
    cursor: Cursor,
    path_node: PathNode | None,
) -> bool:
    node = schema_ref.node
    if isinstance(node, bool):
        if not node:
            state.errors.append(
                ErrorRecord(
                    behavior_id=None,
                    keyword_name=None,
                    vocabulary_uri=None,
                    schema_ref=schema_ref,
                    path_node=path_node,
                    cursor=cursor,
                    message="schema is false",
                )
            )
        return node
    # Backstop for the registration walk's eager D19 check: a position the
    # walk never saw (a `$ref` whose pointer lands inside unwalked data)
    # still fails loud when applied, never silently passes.
    if not is_object(node):
        raise InvalidSchemaError(
            f"non-schema value ({json_type_of(node).value}) applied as a schema",
            schema_location=schema_ref.location,
        )

    dialect = state.registry.dialect_for(schema_ref.base_uri)
    # draft-07/06 (D18): a `$ref` makes every sibling act as if absent.
    ref_only = dialect.ref_ignores_siblings and "$ref" in node

    state.enter(schema_ref, cursor)
    state.dynamic_scope.append(schema_ref.base_uri)
    state.frames.append(Frame())
    valid = True
    try:
        for entry in dialect.ordered:
            if ref_only and entry.name != "$ref":
                continue
            if entry.name not in node:
                continue
            if not _evaluate_keyword(state, schema_ref, entry, cursor, path_node):
                valid = False
        if not ref_only:
            for name, value in node.items():
                if name in dialect.keywords:
                    continue
                if not dialect.allow_unknown_keywords:
                    raise UnknownKeywordError(
                        f"dialect '{dialect.uri}' does not allow unknown "
                        f"keyword '{name}'",
                        schema_location=schema_ref.location,
                    )
                # Unknown keywords are collected as annotations whose value
                # is the keyword's value (spec SHOULD).
                predicate = state.should_record
                if predicate is not None and not predicate(name, None):
                    continue
                state.frame.annotations.append(
                    AnnotationRecord(
                        behavior_id=unknown_keyword_id(name),
                        keyword_name=name,
                        vocabulary_uri=None,
                        schema_ref=schema_ref,
                        path_node=path_node,
                        cursor=cursor,
                        value=value,
                    )
                )
    finally:
        frame = state.frames.pop()
        if valid:
            parent = state.frame
            parent.annotations.extend(frame.annotations)
            parent.dependencies.extend(frame.dependencies)
        state.dynamic_scope.pop()
        state.exit(schema_ref, cursor)
    return valid


def _evaluate_keyword(
    state: EvalState,
    schema_ref: SchemaRef,
    entry: DialectKeyword,
    cursor: Cursor,
    path_node: PathNode | None,
) -> bool:
    node = schema_ref.node
    assert isinstance(node, dict)
    value = node[entry.name]
    ctx = _KeywordContext(state, schema_ref, entry, value, cursor, path_node)
    mark = len(state.errors)
    ok = entry.behavior.evaluate(value, cursor, ctx)
    if ok:
        # Rule 6 keys on the keyword's verdict, so a keyword that reports
        # and still accepts would have its own error silently dropped.
        if ctx.reported:
            raise KeywordContractError(
                f"'{entry.behavior.id}' reported an error but accepted the input",
                schema_location=schema_ref.location,
            )
        if len(state.errors) > mark:
            state.drop_errors_from(mark)
    return ok


def run_evaluation(
    registry: SchemaRegistry,
    schema_uri: str,
    instance: JsonValue,
    *,
    compile_regex: RegexCompiler,
    should_record: RecordPredicate | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    retain_dropped: bool = False,
) -> tuple[bool, EvalState]:
    """Evaluate an instance against a registered root schema.

    Returns the verdict and the final state, whose root frame holds the
    surviving records. A `RecursionError` escaping the interpreter (only
    possible when `max_depth` exceeds what the runtime's stack allows) is
    reported as `MaxDepthExceededError` so callers never see an untyped
    crash (P3).
    """
    state = EvalState(
        registry,
        compile_regex,
        should_record=should_record,
        max_depth=max_depth,
        retain_dropped=retain_dropped,
    )
    try:
        valid = apply_schema(
            state, registry.root_ref(schema_uri), root_cursor(instance), None
        )
    except RecursionError:
        raise MaxDepthExceededError(
            f"evaluation exceeded the interpreter's stack (max_depth={max_depth}); "
            "reduce nesting or lower max_depth"
        ) from None
    return valid, state
