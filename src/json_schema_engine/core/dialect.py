# The keyword behavior interface and the dialect/vocabulary registry
# (DESIGN.md D2, D18, §3). Keywords are identified by URI, a vocabulary is a
# named map of keyword behaviors, a dialect is an ordered set of
# vocabularies. Built-in drafts and user extensions use the same mechanism;
# nothing here is privileged.
#
# Dependency direction: imports `cursor`, `ref`, `json_model`, `errors`, and
# `lowering` (the compiler IR's type vocabulary, for the `lower` slot). The
# registry and the evaluator build on this; keyword modules import it and
# never the engine.

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal, Protocol

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.errors import ReadOnlyRegistryError, UnknownDialectError
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.lowering import LowerFn
from json_schema_engine.core.ref import SchemaRef

# --- Static facts --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NamesCoverage:
    """A fixed set of property names this keyword evaluates (D9a)."""

    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PatternsCoverage:
    """Property names matching any of these patterns (D9a)."""

    patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AllNames:
    """Every property name (D9a): `additionalProperties`-class sweeps."""


@dataclass(frozen=True, slots=True)
class DynamicNames:
    """Coverage only knowable at runtime (D9a): forces evaluated-set tracking."""


type NameCoverage = NamesCoverage | PatternsCoverage | AllNames | DynamicNames


@dataclass(frozen=True, slots=True)
class PrefixIndexes:
    """The first `count` array indexes (D9a): `prefixItems`."""

    count: int


@dataclass(frozen=True, slots=True)
class IndexesFrom:
    """Every index from `start` onward (D9a): 2020-12 `items`."""

    start: int


@dataclass(frozen=True, slots=True)
class AllIndexes:
    """Every array index (D9a)."""


@dataclass(frozen=True, slots=True)
class DynamicIndexes:
    """Index coverage only knowable at runtime (D9a)."""


type IndexCoverage = PrefixIndexes | IndexesFrom | AllIndexes | DynamicIndexes

type SubschemaPath = tuple[str | int, ...]

type ApplyMode = Literal[
    "in_place",  # same cursor: allOf/anyOf/oneOf/not/if/$ref
    "child_by_key",  # a fixed property name: properties entries
    "child_by_index",  # a fixed array index: prefixItems entries
    "child_sweep",  # runtime-determined children: items, *Properties sweeps
    "property_name",  # applied to the property NAME as the instance
]


type Resolution = Literal["dynamic", "recursive"]


@dataclass(frozen=True, slots=True)
class SubschemaApplication:
    """How one keyword applies one subschema (D1, M6): the planner's edge.

    `path` is relative to the keyword's value; `()` is the value itself. A
    sibling keyword's value (`if` → `then`/`else`) is named by `sibling`
    instead; a reference keyword sets `ref`, resolved at plan time against
    the lexical base (then `path` is ignored). `conditional` means the
    application depends on runtime branching (`anyOf` alternatives, an
    `if`-guarded `then`), not merely on instance shape; `asserts` means the
    subschema's verdict feeds this keyword's verdict (false for `if`'s
    condition role and `contains`' per-item probes); `inverted` means it
    feeds negated (`not`), so its records never survive the parent-success
    path and coverage analysis skips the edge. `resolution` marks a
    reference whose target depends on the dynamic scope (D8): `"dynamic"`
    for `$dynamicRef`, `"recursive"` for `$recursiveRef`. The planner
    resolves such a site at plan time when every path reaching it agrees
    on the target, and islands it otherwise (M9).
    """

    path: SubschemaPath
    mode: ApplyMode
    conditional: bool
    asserts: bool
    sibling: str | None = None
    ref: str | None = None
    inverted: bool = False
    resolution: Resolution | None = None


@dataclass(frozen=True, slots=True)
class StaticFacts:
    """What one keyword occurrence says about itself from its value alone.

    This is the compiler tier's entire window into keyword semantics (D1),
    and it drives the registry's schema-position walk: only the positions a
    keyword claims in `subschemas` are treated as schemas, which is what
    keeps an `$id` inside `enum` data from becoming an identifier.
    """

    # Paths to child schemas, relative to the keyword's value.
    subschemas: tuple[SubschemaPath, ...] = ()
    # Reference URIs in the value, relative to the lexical base; they drive
    # transitive loading (P4).
    references: tuple[str, ...] = ()
    # Behavior ids this keyword may `produce()` dependency data under —
    # normally its own id. An undeclared producer is refused (§4 rule 2).
    produces: tuple[str, ...] = ()
    # Behavior ids this keyword reads through `visible()` (D5).
    consumes: tuple[str, ...] = ()
    # Regular expressions the keyword compiles; screened by
    # `reject_unsafe_regex` at registration (D20).
    regexes: tuple[str, ...] = ()
    # Format names the keyword needs a table entry for (M7).
    formats: tuple[str, ...] = ()
    # Participates in dynamic-scope resolution (D8).
    dynamic_scope_sensitive: bool = False
    evaluates_names: NameCoverage | None = None
    evaluates_indexes: IndexCoverage | None = None
    # How the keyword applies its subschemas (M6): the planner's edges and
    # the coverage analysis's transitive contributors. `subschemas` remains
    # the registration walk's position list.
    applications: tuple[SubschemaApplication, ...] = ()


EMPTY_FACTS = StaticFacts()


@dataclass(frozen=True, slots=True)
class AnalyzeContext:
    """The keyword's containing schema object, for sibling-dependent facts.

    The same sibling reads `evaluate()` performs through `ctx.schema`:
    `items` starts after `prefixItems`, `if` declares edges for `then`.
    """

    schema: Mapping[str, JsonValue]


# --- The evaluation-time context -----------------------------------------


class CompiledRegex(Protocol):
    """What a keyword needs from a compiled pattern: an unanchored test."""

    def search(self, text: str, /) -> bool: ...


@dataclass(frozen=True, slots=True)
class DependencyView:
    """A consumer's view of one dependency record: who produced it and what."""

    behavior_id: str
    data: object


type VisibleScope = Literal["all", "adjacent"]
type ErrorParams = Mapping[str, JsonValue]


class KeywordContext(Protocol):
    """The engine services available to one keyword application.

    This is the only path to subschema application, the channel, and error
    reporting. The engine owns path, scope, and frame bookkeeping in exactly
    one place (§3), which is what lets locations become compile-time
    constants in the compiler tier.
    """

    @property
    def schema(self) -> Mapping[str, JsonValue]:
        """The current schema object, this keyword's siblings included."""
        ...

    @property
    def cursor(self) -> Cursor: ...

    def apply(self, segments: Sequence[str | int], cursor: Cursor) -> bool:
        """Apply the subschema at `segments` (relative to the schema object)."""
        ...

    def resolve_ref(self, ref: str) -> SchemaRef:
        """Resolve a reference against the current lexical base."""
        ...

    def resolve_dynamic(self, ref: str) -> SchemaRef:
        """Resolve a `$dynamicRef`-class reference with rebinding (D8)."""
        ...

    def resolve_recursive(self, ref: str) -> SchemaRef:
        """Resolve a 2019-09 `$recursiveRef`, D8's degenerate case."""
        ...

    def apply_resolved(self, target: SchemaRef) -> bool:
        """Apply a resolved reference target at the current cursor."""
        ...

    def compile_regex(self, pattern: str) -> CompiledRegex:
        """Compile through the engine's regex dialect, backend, and cache."""
        ...

    def annotate(self) -> None:
        """Record this keyword's own value as an annotation (§4 rule 2)."""
        ...

    def produce(self, data: object) -> None:
        """Communicate dependency data to other keywords; never output."""
        ...

    def visible(
        self, behavior_ids: Sequence[str], scope: VisibleScope = "all"
    ) -> Sequence[DependencyView]:
        """Dependency records visible at the current cursor (§4 rule 4).

        `"all"` sees this schema object's keywords plus records merged from
        successful in-place sub-applications, which is what `unevaluated*`
        needs; `"adjacent"` sees only this schema object's own keywords,
        which is what `then`/`else` need from `if` (draft-03 §12.3).
        """
        ...

    def error(self, message: str, params: ErrorParams | None = None) -> None:
        """Report an assertion failure with optional structured params (D13)."""
        ...


# --- Keyword behavior ----------------------------------------------------

type AnalyzeFn = Callable[[JsonValue, AnalyzeContext], StaticFacts]
type EvaluateFn = Callable[[JsonValue, Cursor, KeywordContext], bool]


class Phase(IntEnum):
    """Evaluation order within one schema object.

    Phase 1 keywords (`unevaluated*`) run after every phase 0 keyword of the
    same object has merged its records, so their `visible()` sees the whole
    object's dependency data.
    """

    ASSERT = 0
    UNEVALUATED = 1


@dataclass(frozen=True, slots=True)
class KeywordBehavior:
    """A keyword's static analysis and evaluation semantics (D2, §3).

    Keywords are data: vocabularies are plain mappings of these, and the
    factories in `keywords/core.py` return instances. The callables are
    dataclass *fields*, so they are looked up on the instance and never bound
    as methods; `behavior.evaluate(value, cursor, ctx)` passes exactly those
    three arguments.
    """

    # The keyword URI: its stable identity, independent of its name in any
    # dialect.
    id: str
    # Interpreter semantics, synchronous (D7). A keyword that reports an
    # error through `ctx.error()` must return False (§4 rule 6).
    evaluate: EvaluateFn
    # Static facts; also drives the registration walk's descent. Absent
    # means "no facts": no subschemas, no productions, nothing to screen.
    analyze: AnalyzeFn | None = None
    phase: Phase = Phase.ASSERT
    # An identifier or reserved-location keyword (`$id`, `$defs`,
    # `$comment`): it evaluates to nothing and appears in no output unit.
    structural: bool = False
    # Compiled form as lowering IR (D1, M6). Absent means a schema object
    # containing this keyword becomes an interpreted unit (the trampoline
    # fallback), never a failure.
    lower: LowerFn | None = None

    def facts(self, value: JsonValue, schema: Mapping[str, JsonValue]) -> StaticFacts:
        """The keyword's static facts for one occurrence, empty if it has none."""
        if self.analyze is None:
            return EMPTY_FACTS
        return self.analyze(value, AnalyzeContext(schema))


# --- Dialects ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdentifierFacts:
    """Identifiers found in one schema object, per the dialect's syntax (D18)."""

    # Changes the lexical base and starts a schema resource.
    base_id: str | None = None
    # Plain-name anchors minted at this schema object.
    anchors: tuple[str, ...] = ()
    # Anchor participating in `$dynamicRef` rebinding (D8).
    dynamic_anchor: str | None = None
    # 2019-09 `$recursiveAnchor`, effective at a resource root.
    recursive_anchor: bool = False


NO_IDENTIFIERS = IdentifierFacts()

type IdentifierExtractor = Callable[[Mapping[str, JsonValue]], IdentifierFacts]


def identifiers_2020(node: Mapping[str, JsonValue]) -> IdentifierFacts:
    """2020-12 identifier syntax: `$id`, `$anchor`, `$dynamicAnchor`."""
    base_id = node.get("$id")
    anchor = node.get("$anchor")
    dynamic = node.get("$dynamicAnchor")
    return IdentifierFacts(
        base_id=base_id if isinstance(base_id, str) else None,
        anchors=(anchor,) if isinstance(anchor, str) else (),
        dynamic_anchor=dynamic if isinstance(dynamic, str) else None,
    )


def identifiers_2019(node: Mapping[str, JsonValue]) -> IdentifierFacts:
    """2019-09 identifier syntax: `$id`, `$anchor`, boolean `$recursiveAnchor`."""
    base_id = node.get("$id")
    anchor = node.get("$anchor")
    return IdentifierFacts(
        base_id=base_id if isinstance(base_id, str) else None,
        anchors=(anchor,) if isinstance(anchor, str) else (),
        recursive_anchor=node.get("$recursiveAnchor") is True,
    )


def identifiers_legacy(node: Mapping[str, JsonValue]) -> IdentifierFacts:
    """draft-07/06 identifier syntax.

    A schema object containing `$ref` has no identifiers at all (the suite's
    "`$ref` prevents a sibling `$id` from changing the base uri"), and a
    plain-fragment `$id` mints an anchor rather than changing the base.
    """
    if "$ref" in node:
        return NO_IDENTIFIERS
    base_id = node.get("$id")
    if not isinstance(base_id, str):
        return NO_IDENTIFIERS
    if base_id.startswith("#"):
        return (
            IdentifierFacts(anchors=(base_id[1:],))
            if len(base_id) > 1
            else NO_IDENTIFIERS
        )
    return IdentifierFacts(base_id=base_id)


@dataclass(frozen=True, slots=True)
class DialectKeyword:
    """A keyword's binding within one dialect: its name there and its owner."""

    name: str
    behavior: KeywordBehavior
    vocabulary_uri: str


@dataclass(frozen=True, slots=True)
class Dialect:
    """An ordered set of vocabularies with identifier and `$ref` semantics."""

    uri: str
    keywords: Mapping[str, DialectKeyword]
    # Evaluation order: every phase 0 entry, then every phase 1 entry, each
    # group in vocabulary-then-declaration order.
    ordered: tuple[DialectKeyword, ...]
    vocabulary_uris: tuple[str, ...]
    # Unknown keywords are collected as annotations (spec SHOULD) when true,
    # and raise `UnknownKeywordError` when false.
    allow_unknown_keywords: bool
    identifiers: IdentifierExtractor
    # draft-07/06: a schema object with `$ref` evaluates only `$ref`.
    ref_ignores_siblings: bool

    def identifiers_of(self, node: JsonValue) -> IdentifierFacts:
        """Identifier facts for a node, none for a boolean schema."""
        return self.identifiers(node) if is_object(node) else NO_IDENTIFIERS


class DialectRegistry:
    """Registry of vocabularies and the dialects assembled from them (D2)."""

    def __init__(self) -> None:
        self._vocabularies: dict[str, Mapping[str, KeywordBehavior]] = {}
        self._dialects: dict[str, Dialect] = {}
        self._read_only = False

    def register_vocabulary(
        self, uri: str, keywords: Mapping[str, KeywordBehavior]
    ) -> None:
        """Register a vocabulary's keyword behaviors under its URI."""
        self._check_writable()
        self._vocabularies[uri] = dict(keywords)

    def register_dialect(
        self,
        uri: str,
        vocabulary_uris: Sequence[str],
        *,
        allow_unknown_keywords: bool = True,
        identifiers: IdentifierExtractor = identifiers_2020,
        ref_ignores_siblings: bool = False,
    ) -> Dialect:
        """Assemble a dialect from already-registered vocabularies.

        A later vocabulary rebinding a name replaces the earlier binding, so
        a dialect author can override a built-in keyword by listing an
        extension vocabulary after the standard one.
        """
        self._check_writable()
        keywords: dict[str, DialectKeyword] = {}
        for vocabulary_uri in vocabulary_uris:
            vocabulary = self._vocabularies.get(vocabulary_uri)
            if vocabulary is None:
                raise UnknownDialectError(
                    f"dialect '{uri}' requires unregistered vocabulary "
                    f"'{vocabulary_uri}'"
                )
            for name, behavior in vocabulary.items():
                keywords[name] = DialectKeyword(name, behavior, vocabulary_uri)
        entries = list(keywords.values())
        ordered = tuple(
            [e for e in entries if e.behavior.phase is Phase.ASSERT]
            + [e for e in entries if e.behavior.phase is Phase.UNEVALUATED]
        )
        dialect = Dialect(
            uri=uri,
            keywords=keywords,
            ordered=ordered,
            vocabulary_uris=tuple(vocabulary_uris),
            allow_unknown_keywords=allow_unknown_keywords,
            identifiers=identifiers,
            ref_ignores_siblings=ref_ignores_siblings,
        )
        self._dialects[uri] = dialect
        return dialect

    def snapshot(self) -> "DialectRegistry":
        """A frozen copy: the same vocabularies and dialects, no registration.

        A compiled artifact binds to a snapshot (M6), so a dialect registered
        after compilation cannot change what an artifact's islands resolve.
        """
        copy = DialectRegistry()
        copy._vocabularies = dict(self._vocabularies)
        copy._dialects = dict(self._dialects)
        copy._read_only = True
        return copy

    def _check_writable(self) -> None:
        if self._read_only:
            raise ReadOnlyRegistryError(
                "this dialect registry is a compiled artifact's snapshot"
            )

    def get_dialect(self, uri: str) -> Dialect:
        """Look up a registered dialect; raises `UnknownDialectError`."""
        try:
            return self._dialects[uri]
        except KeyError:
            raise UnknownDialectError(f"unknown dialect '{uri}'") from None

    def has_dialect(self, uri: str) -> bool:
        return uri in self._dialects

    def has_vocabulary(self, uri: str) -> bool:
        return uri in self._vocabularies


def unknown_keyword_id(name: str) -> str:
    """Behavior id for annotations from keywords the dialect does not know."""
    return f"urn:jse:keyword:unknown#{name}"
