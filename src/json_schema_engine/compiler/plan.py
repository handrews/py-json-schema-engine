# The compilation planner (DESIGN.md D1, D8, D9; M6, M9): classifies every
# schema node reachable from a root as a static (compilable) or interpreted
# (trampoline) unit, using only public core APIs and `analyze()` facts —
# never keyword names. Conservative by design: anything uncertain falls
# back to the interpreter, which is always correct.
#
# Dynamic references (M9, after the TS engine's ADR 0004): a `$dynamicRef`
# or `$recursiveRef` site is resolved at plan time when every path that can
# reach it yields the same target, and compiled as an ordinary static edge.
# The dynamic scope at a compiled site is the chain of resource URIs from
# the artifact root (the trampoline is one-way, so a compiled site is
# reached only through compiled ancestors), and the interpreter's rule is
# "the outermost scope entry that declares the anchor wins". Per anchor, a
# forward dataflow over the unit graph computes, for each unit, the set of
# resources that can be the outermost declarer on arrival; the graph
# over-approximates real paths, so the analysis errs only toward islanding.
# A resolved site adds its target's subtree — and so new paths — to the
# graph, so the plan is built in rounds under the current site decisions,
# and every decision is re-derived each round from the grown graph.
#
# Specialization: a site whose target differs by path is not islanded at
# once. The winner is the first resource on the path that declares the
# anchor, so the planner *splits* the anchor: from then on a unit's
# identity is (location, dynamic context), the context being the first
# declarer bound so far for every split anchor, and a site of a split
# anchor resolves exactly from its unit's context. Units below a declaring
# resource are cloned per winner; every clone is an ordinary static unit
# that reports the location it shares with its siblings. Decisions move
# only unknown → resolved → unstable per site and unsplit → split → capped
# per anchor, which bounds the rounds. `max_dynamic_winners` bounds the
# declarers a split anchor may bind (0 never splits); beyond it the anchor
# is capped and its unstable sites island with cause "dynamic" as before.
#
# Dependency direction: imports core's registry/dialect/ref/errors and the
# engine façade's type. The serializer and the public API import this.

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from json_schema_engine.core.dialect import (
    AllIndexes,
    AllNames,
    DynamicIndexes,
    DynamicNames,
    IndexesFrom,
    NamesCoverage,
    PatternsCoverage,
    PrefixIndexes,
    StaticFacts,
    SubschemaApplication,
)
from json_schema_engine.core.engine import Engine
from json_schema_engine.core.errors import UnresolvableReferenceError
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.lowering import StaticCoverage
from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.registry import SchemaRegistry

type FallbackCause = Literal["dynamic", "unlowerable", "cycle", "non_schema"]
"""Why a unit is interpreted: a dynamic-reference site the plan cannot
resolve (its anchor binds more declarers than `max_dynamic_winners` allows
it to specialize, or the keyword declares no resolution fact); a keyword
without `lower()`, an unresolvable edge, or a consumer without static
coverage; a possible in-place cycle; a reference into non-schema data (the
interpreter's D19 backstop reports it)."""

type AnchorKind = Literal["dynamic", "recursive"]
"""Which rebinding a site performs: 2020-12 `$dynamicRef` (keyed by anchor
name) or 2019-09 `$recursiveRef` (one shared dataflow)."""

type AnchorKey = tuple[AnchorKind, str]

type DynamicContext = tuple[tuple[AnchorKind, str, str], ...]
"""Sorted `(kind, anchor, winner)` triples: for every split anchor whose
winner is bound on the path so far, the first declaring resource. Empty
when nothing is split, so unit keys are then plain locations."""

DEFAULT_MAX_DYNAMIC_WINNERS = 16
"""Declaring resources a split anchor may bind before it is capped."""

# The 2019-09 rebinding has no anchor name; one sentinel keys its dataflow.
_RECURSIVE_ANCHOR = "$recursiveAnchor"


@dataclass(frozen=True, slots=True)
class DynamicResolution:
    """How a dynamic-reference edge was resolved at plan time: the resource
    whose anchor won (`None` when the reference behaved like `$ref`)."""

    winner: str | None


@dataclass(frozen=True, slots=True)
class PlannedApplication:
    """One application edge out of a unit, resolved at plan time."""

    keyword: str
    app: SubschemaApplication
    target_key: str
    dynamic: DynamicResolution | None = None


@dataclass(slots=True)
class PlannedUnit:
    """One schema node in the plan, keyed by its canonical location plus,
    once the plan has split an anchor, its dynamic context."""

    key: str
    ref: SchemaRef
    # The first declarer bound for every split anchor on the way here.
    context: DynamicContext = ()
    kind: Literal["static", "interpreted"] = "static"
    cause: FallbackCause | None = None
    # Resolved outgoing edges, in keyword order (static units only).
    edges: list[PlannedApplication] = field(default_factory=list[PlannedApplication])
    # Static evaluated coverage licensed for this object's consumers (D9a).
    coverage: StaticCoverage | None = None
    # True when some apply path from here can reach an interpreted unit:
    # the dynamic scope must be threaded through, and inlining is off.
    reaches_interpreted: bool = False
    # Planned edges targeting this unit (D9c inline licensing).
    use_count: int = 0
    # M9 runtime coverage tracking: a tracked unit owns a coverage channel
    # its consumers fold at runtime (no static licence); a region unit is
    # reachable in place from a tracked unit and produces into the channel
    # it is handed. Both take the channel as a parameter and never inline.
    tracked: bool = False
    in_region: bool = False

    @property
    def takes_channel(self) -> bool:
        return self.tracked or self.in_region

    def interpret(self, cause: FallbackCause) -> None:
        self.kind = "interpreted"
        self.cause = cause
        self.edges = []


@dataclass(frozen=True, slots=True)
class SplitAnchor:
    """An anchor the plan specialized: its sites resolve per unit context,
    and `winners` are the declaring resources some unit bound."""

    kind: AnchorKind
    anchor: str
    winners: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompilationPlan:
    root_key: str
    # Insertion order is planning order: deterministic function numbering.
    units: dict[str, PlannedUnit]
    # Every regex source any static unit tests (patterns plus coverage).
    patterns: tuple[str, ...]
    # Every format name any static unit asserts (M7).
    formats: tuple[str, ...]
    # Interpreted units in stable order; index = target-table slot.
    targets: tuple[PlannedUnit, ...]
    # Producer ids some tracked consumer reads (M9): only their productions
    # are recorded on a channel.
    coverage_ids: frozenset[str] = frozenset()
    # Anchors whose sites were specialized per dynamic context.
    split_anchors: tuple[SplitAnchor, ...] = ()


def unit_key(ref: SchemaRef, context: DynamicContext = ()) -> str:
    """A unit's identity: its canonical location, suffixed with its dynamic
    context once an anchor is split. `|` cannot appear raw in a URI, so the
    suffix never collides with a location; the kind prefix keeps the
    recursive sentinel apart from a dynamic anchor of the same name."""
    if not context:
        return ref.location
    return ref.location + "".join(
        f"|{kind}:{anchor}={winner}" if kind == "dynamic" else f"|{kind}={winner}"
        for kind, anchor, winner in context
    )


# --- dynamic-reference sites -----------------------------------------------

# (unit key, keyword, reference value): one decision per site.
type SiteKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ResolvedSite:
    target: SchemaRef
    winner: str | None


# A site's decision; `"unstable"` is permanent.
type SiteState = ResolvedSite | Literal["unstable"]
type SiteDecisions = dict[SiteKey, SiteState]


@dataclass(frozen=True, slots=True)
class _AnchorRules:
    """How one anchor binds: whether a resource declares it, and where a
    winner's declaration lands."""

    declares: Callable[[str], bool]
    target_of: Callable[[str], SchemaRef]


def _anchor_rules(registry: SchemaRegistry, key: AnchorKey) -> _AnchorRules:
    kind, anchor = key
    if kind == "dynamic":

        def declares(resource: str) -> bool:
            return registry.dynamic_anchor(resource, anchor) is not None

        def target_of(winner: str) -> SchemaRef:
            hit = registry.dynamic_anchor(winner, anchor)
            assert hit is not None
            return hit

        return _AnchorRules(declares, target_of)
    return _AnchorRules(registry.has_recursive_root, registry.root_ref)


@dataclass(slots=True)
class _Splits:
    """Plan-wide anchor decisions, owned by `build_plan_over`: an anchor is
    unsplit (its sites are decided one by one), split (its sites resolve
    from the unit context), or capped (never to be split). Each step is
    permanent."""

    cap: int
    rules: dict[AnchorKey, _AnchorRules] = field(
        default_factory=dict[AnchorKey, _AnchorRules]
    )
    capped: set[AnchorKey] = field(default_factory=set[AnchorKey])


def _bound(context: DynamicContext, key: AnchorKey) -> str | None:
    for kind, anchor, winner in context:
        if (kind, anchor) == key:
            return winner
    return None


def _enter(context: DynamicContext, ref: SchemaRef, splits: _Splits) -> DynamicContext:
    """The context inside `ref`: the outermost-first rule applied forward —
    every split anchor still unbound binds to this unit's resource if that
    resource declares it."""
    if not splits.rules:
        return context
    added: list[tuple[AnchorKind, str, str]] = [
        (kind, anchor, ref.base_uri)
        for (kind, anchor), rules in splits.rules.items()
        if _bound(context, (kind, anchor)) is None and rules.declares(ref.base_uri)
    ]
    if not added:
        return context
    return tuple(sorted((*context, *added)))


@dataclass(frozen=True, slots=True)
class _DynamicSite:
    """A site of an unsplit anchor met during a round, decided or not."""

    key: SiteKey
    unit_key: str
    kind: AnchorKind
    anchor: str
    lexical: SchemaRef


@dataclass(frozen=True, slots=True)
class _Resolved:
    target: SchemaRef
    dynamic: DynamicResolution | None = None


@dataclass(frozen=True, slots=True)
class _Dynamic:
    site: _DynamicSite
    # The current decision; `None` until the round settles it.
    state: SiteState | None


type _EdgeResolution = _Resolved | _Dynamic | Literal["unresolvable"]


def _resolve_edge(
    registry: SchemaRegistry,
    ref: SchemaRef,
    context: DynamicContext,
    keyword: str,
    app: SubschemaApplication,
    sites: SiteDecisions,
    splits: _Splits,
) -> _EdgeResolution:
    """Where an application edge lands, under the current decisions."""
    if app.ref is None:
        head = app.sibling if app.sibling is not None else keyword
        return _Resolved(registry.child(ref, [head, *app.path]))
    try:
        if app.resolution is None:
            return _Resolved(registry.resolve_ref(app.ref, ref.base_uri))
        if app.resolution == "dynamic":
            dynamic = registry.dynamic_reference(app.ref, ref.base_uri)
            if dynamic.anchor is None:
                return _Resolved(dynamic.lexical, DynamicResolution(None))
            anchor = dynamic.anchor
            lexical = dynamic.lexical
        else:
            recursive = registry.recursive_reference(app.ref, ref.base_uri)
            if not recursive.recursive:
                return _Resolved(recursive.lexical, DynamicResolution(None))
            anchor = _RECURSIVE_ANCHOR
            lexical = recursive.lexical
    except UnresolvableReferenceError:
        return "unresolvable"
    anchor_key: AnchorKey = (app.resolution, anchor)
    rules = splits.rules.get(anchor_key)
    if rules is not None:
        # A split anchor: the context names the winner exactly.
        winner = _bound(context, anchor_key)
        target = lexical if winner is None else rules.target_of(winner)
        return _Resolved(target, DynamicResolution(winner))
    key: SiteKey = (unit_key(ref, context), keyword, app.ref)
    site = _DynamicSite(key, key[0], app.resolution, anchor, lexical)
    return _Dynamic(site, sites.get(key))


# --- coverage licensing ------------------------------------------------------


@dataclass(slots=True)
class _NameHalf:
    names: set[str] = field(default_factory=set[str])
    patterns: list[str] = field(default_factory=list[str])
    all: bool = False


@dataclass(slots=True)
class _IndexHalf:
    prefix: int = 0
    all: bool = False


def coverage_halves(
    registry: SchemaRegistry,
    ref: SchemaRef,
    context: DynamicContext,
    visiting: set[str],
    exclude_consumers: bool,
    sites: SiteDecisions | None = None,
    splits: _Splits | None = None,
) -> tuple[_NameHalf | None, _IndexHalf | None]:
    """The evaluated coverage a schema node contributes at its own cursor
    (D9a), including — transitively — unconditional asserting in-place
    applications. `None` means statically unknowable.

    `exclude_consumers` is true only for the licensing node itself: a
    consumer's own coverage fact describes the state after it runs. Facts
    come from `analyze()` alone, so contribution is independent of which
    tier evaluates the target. Dynamic-reference edges resolve through
    `sites`, or from `context` for a split anchor; an undecided or
    unstable site is unknowable, exactly like an unresolvable `$ref`.
    """
    if sites is None:
        sites = {}
    if splits is None:
        splits = _Splits(0)
    key = unit_key(ref, context)
    if key in visiting:
        return None, None
    visiting.add(key)
    try:
        node = ref.node
        if isinstance(node, bool):
            # Contributes nothing; `false` fails the parent, making coverage moot.
            return _NameHalf(), _IndexHalf()
        if not is_object(node):
            return None, None
        dialect = registry.dialect_for(ref.base_uri)
        ref_only = dialect.ref_ignores_siblings and "$ref" in node
        name_half: _NameHalf | None = _NameHalf()
        index_half: _IndexHalf | None = _IndexHalf()
        for entry in dialect.ordered:
            if ref_only and entry.name != "$ref":
                continue
            if entry.name not in node:
                continue
            facts = entry.behavior.facts(node[entry.name], node)
            if facts.dynamic_scope_sensitive and not any(
                app.resolution is not None for app in facts.applications
            ):
                return None, None
            is_consumer = len(facts.consumes) > 0
            if not (exclude_consumers and is_consumer):
                name_half = _fold_names(name_half, facts)
                index_half = _fold_indexes(index_half, facts)
            for app in facts.applications:
                if app.mode != "in_place" or app.inverted:
                    continue
                if app.conditional or not app.asserts:
                    return None, None
                resolution = _resolve_edge(
                    registry, ref, context, entry.name, app, sites, splits
                )
                if isinstance(resolution, _Resolved):
                    target = resolution.target
                elif isinstance(resolution, _Dynamic) and isinstance(
                    resolution.state, ResolvedSite
                ):
                    target = resolution.state.target
                else:
                    return None, None
                sub_names, sub_indexes = coverage_halves(
                    registry,
                    target,
                    _enter(context, target, splits),
                    visiting,
                    False,
                    sites,
                    splits,
                )
                if name_half is not None:
                    if sub_names is None:
                        name_half = None
                    else:
                        name_half.names |= sub_names.names
                        name_half.patterns.extend(sub_names.patterns)
                        name_half.all = name_half.all or sub_names.all
                if index_half is not None:
                    if sub_indexes is None:
                        index_half = None
                    else:
                        index_half.prefix = max(index_half.prefix, sub_indexes.prefix)
                        index_half.all = index_half.all or sub_indexes.all
            if name_half is None and index_half is None:
                return None, None
        return name_half, index_half
    finally:
        visiting.discard(key)


def _fold_names(half: _NameHalf | None, facts: StaticFacts) -> _NameHalf | None:
    if half is None or facts.evaluates_names is None:
        return half
    match facts.evaluates_names:
        case NamesCoverage(names):
            half.names.update(names)
        case PatternsCoverage(patterns):
            half.patterns.extend(patterns)
        case AllNames():
            half.all = True
        case DynamicNames():
            return None
    return half


def _fold_indexes(half: _IndexHalf | None, facts: StaticFacts) -> _IndexHalf | None:
    if half is None or facts.evaluates_indexes is None:
        return half
    match facts.evaluates_indexes:
        case PrefixIndexes(count):
            half.prefix = max(half.prefix, count)
        case IndexesFrom():
            # The start is bounded by this node's own prefix contribution
            # (`items` starts after sibling `prefixItems`), so the per-node
            # union covers everything from there on.
            half.all = True
        case AllIndexes():
            half.all = True
        case DynamicIndexes():
            return None
    return half


def _is_coverage_consumer(facts: StaticFacts) -> bool:
    # A coverage consumer (`unevaluated*`) declares `consumes` and an
    # evaluated-coverage fact; a keyword consuming other dependency data
    # (`then`/`else` reading `if`'s outcome) needs no coverage.
    return len(facts.consumes) > 0 and (
        facts.evaluates_names is not None or facts.evaluates_indexes is not None
    )


# --- planning ----------------------------------------------------------------


def build_plan(
    engine: Engine,
    schema_uri: str,
    *,
    max_dynamic_winners: int = DEFAULT_MAX_DYNAMIC_WINNERS,
) -> CompilationPlan:
    """Plan the compilation of one registered root schema.

    The walk mirrors the registration walk's position logic by
    construction: descent uses the same `analyze()` facts and the same
    `registry.child` pointer navigation. `registry` may be a snapshot.
    """
    return build_plan_over(
        engine.schemas, schema_uri, max_dynamic_winners=max_dynamic_winners
    )


@dataclass(slots=True)
class _Round:
    units: dict[str, PlannedUnit]
    patterns: dict[str, None]
    formats: dict[str, None]
    # Every site of an unsplit anchor met this round, decided or not.
    met: dict[SiteKey, _DynamicSite]
    root: PlannedUnit
    coverage_ids: set[str]


@dataclass(frozen=True, slots=True)
class _Edge:
    keyword: str
    app: SubschemaApplication
    target: SchemaRef
    dynamic: DynamicResolution | None


def _plan_round(
    registry: SchemaRegistry,
    root_ref: SchemaRef,
    sites: SiteDecisions,
    splits: _Splits,
    track_all: bool,
) -> _Round:
    units: dict[str, PlannedUnit] = {}
    patterns: dict[str, None] = {}
    formats: dict[str, None] = {}
    met: dict[SiteKey, _DynamicSite] = {}
    coverage_ids: set[str] = set()
    # One `SchemaRef` per location, shared by every clone of it.
    refs: dict[str, SchemaRef] = {}

    def plan(
        ref: SchemaRef, context: DynamicContext, chain: Mapping[str, str]
    ) -> PlannedUnit:
        # `context` is the entry context (the caller applied `_enter`);
        # `chain` maps the locations of the same-cursor in-place ancestors
        # on this path to their unit keys.
        ref = refs.setdefault(ref.location, ref)
        key = unit_key(ref, context)
        existing = units.get(key)
        if existing is not None:
            return existing
        unit = PlannedUnit(key, ref, context)
        units[key] = unit
        node = ref.node
        if isinstance(node, bool):
            return unit
        if not is_object(node):
            unit.interpret("non_schema")
            return unit

        # No dialect allowlist: a dialect compiles exactly when every present
        # keyword lowers. The one dialect-level semantic mirrored here is
        # `ref_ignores_siblings` (draft-07/06: plan and lower only `$ref`).
        dialect = registry.dialect_for(ref.base_uri)
        ref_only = dialect.ref_ignores_siblings and "$ref" in node
        present: list[tuple[str, StaticFacts]] = []
        consumer_present = False
        for entry in dialect.ordered:
            if ref_only and entry.name != "$ref":
                continue
            if entry.name not in node:
                continue
            facts = entry.behavior.facts(node[entry.name], node)
            if facts.dynamic_scope_sensitive and not any(
                app.resolution is not None for app in facts.applications
            ):
                # A dynamic keyword the planner cannot discharge.
                unit.interpret("dynamic")
                return unit
            if entry.behavior.lower is None:
                unit.interpret("unlowerable")
                return unit
            if _is_coverage_consumer(facts):
                consumer_present = True
            for regex in facts.regexes:
                patterns[regex] = None
            for format_name in facts.formats:
                formats[format_name] = None
            present.append((entry.name, facts))
        # Unknown keywords are annotations (recorded by the evaluator tier);
        # a dialect that refuses them raises at evaluation time in the
        # interpreter, which only the interpreter can reproduce.
        if (
            not ref_only
            and not dialect.allow_unknown_keywords
            and any(name not in dialect.keywords for name in node)
        ):
            unit.interpret("unlowerable")
            return unit

        # Resolve every edge before any child is planned, so a unit that
        # islands never leaves half-planned children behind.
        edges: list[_Edge] = []
        for name, facts in present:
            for app in facts.applications:
                resolution = _resolve_edge(
                    registry, ref, context, name, app, sites, splits
                )
                match resolution:
                    case _Resolved(target, dynamic):
                        edges.append(_Edge(name, app, target, dynamic))
                    case _Dynamic(site, state):
                        # Recorded whether decided or not: the round re-derives
                        # every decision from the grown graph.
                        met.setdefault(site.key, site)
                        if state is None:
                            # No edge this round; the round settles the site.
                            continue
                        if not isinstance(state, ResolvedSite):
                            unit.interpret("dynamic")
                            return unit
                        edges.append(
                            _Edge(
                                name, app, state.target, DynamicResolution(state.winner)
                            )
                        )
                    case "unresolvable":
                        # Lazy-failure parity: the interpreter raises only
                        # when the reference is followed, so the whole node
                        # falls back.
                        unit.interpret("unlowerable")
                        return unit

        # Consumer licensing (D9a): a consumer lowers against a static
        # coverage when the half it needs is statically known — from this
        # object's own contributors plus, transitively, unconditional
        # asserting in-place applications. Anything runtime-conditional
        # makes the coverage dynamic, and the unit is then tracked (M9):
        # its consumers fold a runtime channel instead. A static licence
        # models only the parent-success path, so a plan that must observe
        # failed siblings (`track_all`, the evaluator) tracks every consumer.
        if consumer_present:
            consumers = [f for _, f in present if _is_coverage_consumer(f)]
            name_half, index_half = (
                (None, None)
                if track_all
                else coverage_halves(registry, ref, context, set(), True, sites, splits)
            )
            needs_names = any(f.evaluates_names is not None for f in consumers)
            needs_indexes = any(f.evaluates_indexes is not None for f in consumers)
            if (needs_names and name_half is None) or (
                needs_indexes and index_half is None
            ):
                unit.tracked = True
                for f in consumers:
                    coverage_ids.update(f.consumes)
            else:
                unit.coverage = StaticCoverage(
                    names=frozenset(name_half.names) if name_half else frozenset(),
                    patterns=tuple(name_half.patterns) if name_half else (),
                    covers_all_names=name_half.all if name_half else False,
                    prefix_count=index_half.prefix if index_half else 0,
                    covers_all_indexes=index_half.all if index_half else False,
                )
                for regex in unit.coverage.patterns:
                    patterns[regex] = None

        # Plan children.
        for edge in edges:
            target_context = _enter(context, edge.target, splits)
            target_key = unit_key(edge.target, target_context)
            if edge.app.mode == "in_place":
                location = edge.target.location
                if location in chain or location == ref.location:
                    # In-place cycle: same-cursor re-entry of a location on
                    # this path, whatever its context (the interpreter's
                    # guard keys on location). Islanding the ancestor that
                    # is actually on the path keeps its `InfiniteLoopError`
                    # parity even when a short-circuiting parent would
                    # never reach a clone islanded further down.
                    cyclic = units[chain.get(location, key)]
                    cyclic.interpret("cycle")
                    if cyclic is unit:
                        return unit
                    unit.edges.append(
                        PlannedApplication(
                            edge.keyword, edge.app, cyclic.key, edge.dynamic
                        )
                    )
                    continue
                plan(edge.target, target_context, {**chain, ref.location: key})
            else:
                plan(edge.target, target_context, {})
            unit.edges.append(
                PlannedApplication(edge.keyword, edge.app, target_key, edge.dynamic)
            )
        return unit

    root = plan(root_ref, _enter((), root_ref, splits), {})
    return _Round(units, patterns, formats, met, root, coverage_ids)


def _outermost_declarers(
    units: Mapping[str, PlannedUnit],
    root_key: str,
    declares: Callable[[str], bool],
) -> dict[str, set[str | None]]:
    """Per unit, the resources that can be the outermost declarer of one
    anchor when evaluation arrives there (`None`: no declarer yet).

    Seeded at the root, propagated along every planned edge of every
    static unit — in-place or child, conditional or not — with the
    outermost-first rule (a bound winner sticks; otherwise the unit's own
    resource binds if it declares), joined by union, to a fixpoint. Over a
    graph with clones, each clone has its own arrival set.
    """

    def own(unit: PlannedUnit, winner: str | None) -> str | None:
        if winner is not None:
            return winner
        return unit.ref.base_uri if declares(unit.ref.base_uri) else None

    arrival: dict[str, set[str | None]] = {root_key: {own(units[root_key], None)}}
    worklist = [root_key]
    while worklist:
        key = worklist.pop()
        unit = units[key]
        if unit.kind != "static":
            continue
        for edge in unit.edges:
            target = units[edge.target_key]
            state = arrival.setdefault(edge.target_key, set())
            before = len(state)
            state.update(own(target, winner) for winner in arrival[key])
            if len(state) != before:
                worklist.append(edge.target_key)
    return arrival


def _bound_winners(units: Mapping[str, PlannedUnit]) -> dict[AnchorKey, set[str]]:
    """Per split anchor, every declarer some unit's context binds."""
    bound: dict[AnchorKey, set[str]] = {}
    for unit in units.values():
        for kind, anchor, winner in unit.context:
            bound.setdefault((kind, anchor), set()).add(winner)
    return bound


def _split(
    splits: _Splits,
    anchor_key: AnchorKey,
    rules: _AnchorRules,
    winners: set[str | None],
) -> bool:
    """Specialize an anchor whose site has several targets, unless the cap
    forbids it — then the anchor is capped for good."""
    distinct = {winner for winner in winners if winner is not None}
    if anchor_key in splits.capped or len(distinct) > splits.cap:
        splits.capped.add(anchor_key)
        return False
    splits.rules[anchor_key] = rules
    return True


def _settle_sites(
    registry: SchemaRegistry, round_: _Round, sites: SiteDecisions, splits: _Splits
) -> bool:
    """Re-derive every site met in a round from the round's graph; True
    when a decision or an anchor's state changed."""
    changed = False
    by_anchor: dict[AnchorKey, list[_DynamicSite]] = {}
    for site in round_.met.values():
        by_anchor.setdefault((site.kind, site.anchor), []).append(site)
    for anchor_key, group in by_anchor.items():
        rules = _anchor_rules(registry, anchor_key)
        arrival = _outermost_declarers(round_.units, round_.root.key, rules.declares)
        for site in group:
            winners = arrival.get(site.unit_key)
            if not winners:
                # Unreachable from the root this round (only through an
                # island): the interpreter resolves it there.
                continue
            targets: dict[str, tuple[SchemaRef, str | None]] = {}
            for winner in sorted(winners, key=lambda w: (w is not None, w or "")):
                target = site.lexical if winner is None else rules.target_of(winner)
                targets.setdefault(target.location, (target, winner))
            previous = sites.get(site.key)
            if previous == "unstable":
                continue
            if len(targets) == 1:
                ((target, winner),) = targets.values()
                if previous is None:
                    sites[site.key] = ResolvedSite(target, winner)
                    changed = True
                    continue
                if previous.target.location == target.location:
                    continue
            # Several targets, or a decision whose target moved as the graph
            # grew: specialize the anchor, or island the site.
            if _split(splits, anchor_key, rules, winners):
                for other in group:
                    sites.pop(other.key, None)
                changed = True
                break
            sites[site.key] = "unstable"
            changed = True
    # The cap holds across rounds: an anchor split on one site's winners
    # may bind more declarers once its clones are planned.
    bound = _bound_winners(round_.units)
    for anchor_key in list(splits.rules):
        if len(bound.get(anchor_key, ())) > splits.cap:
            del splits.rules[anchor_key]
            splits.capped.add(anchor_key)
            changed = True
    return changed


def build_plan_over(
    registry: SchemaRegistry,
    schema_uri: str,
    *,
    track_all: bool = False,
    max_dynamic_winners: int = DEFAULT_MAX_DYNAMIC_WINNERS,
) -> CompilationPlan:
    """Plan over a registry (normally a snapshot). `track_all` tracks every
    coverage consumer at runtime instead of licensing static coverage
    (the evaluator's plans, whose units continue past a failed sibling).
    `max_dynamic_winners` caps the declaring resources a split anchor may
    bind; `0` never specializes, so every path-dependent site islands."""
    if max_dynamic_winners < 0:
        raise ValueError("max_dynamic_winners must be >= 0")
    root_ref = registry.root_ref(schema_uri)
    sites: SiteDecisions = {}
    splits = _Splits(max_dynamic_winners)
    while True:
        round_ = _plan_round(registry, root_ref, sites, splits, track_all)
        if not _settle_sites(registry, round_, sites, splits):
            break
    units = round_.units

    # Region fixpoint (M9): every static, non-boolean unit reachable in
    # place from a tracked unit produces into that unit's channel. Every
    # in-place edge counts — inverted (`not`) and non-asserting (`if`'s
    # condition) ones too, since a passing negated or conditional
    # subschema's records are visible to the consumer — and a tracked unit
    # inside a region nests through its own entry mark.
    worklist = [u.key for u in units.values() if u.tracked]
    while worklist:
        unit = units[worklist.pop()]
        for edge in unit.edges:
            target = units[edge.target_key]
            if (
                edge.app.mode != "in_place"
                or target.kind != "static"
                or isinstance(target.ref.node, bool)
                or target.in_region
            ):
                continue
            target.in_region = True
            worklist.append(target.key)

    # `reaches_interpreted` fixpoint over the edge graph.
    changed = True
    while changed:
        changed = False
        for unit in units.values():
            if unit.kind == "interpreted" or unit.reaches_interpreted:
                continue
            for edge in unit.edges:
                target = units[edge.target_key]
                if target.kind == "interpreted" or target.reaches_interpreted:
                    unit.reaches_interpreted = True
                    changed = True
                    break

    for unit in units.values():
        if unit.kind != "static":
            continue
        for edge in unit.edges:
            units[edge.target_key].use_count += 1

    targets = tuple(u for u in units.values() if u.kind == "interpreted")
    bound = _bound_winners(units)
    split_anchors = tuple(
        SplitAnchor(kind, anchor, tuple(sorted(bound.get((kind, anchor), ()))))
        for kind, anchor in sorted(splits.rules)
    )
    return CompilationPlan(
        round_.root.key,
        units,
        tuple(round_.patterns),
        tuple(round_.formats),
        targets,
        frozenset(round_.coverage_ids),
        split_anchors,
    )


# --- explanation -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedDynamicSite:
    """A dynamic-reference site the plan compiled as a static edge. `unit`
    and `target` are unit keys; `location` and `target_location` the
    schema locations they report."""

    unit: str
    keyword: str
    ref: str
    target: str
    winner: str | None
    location: str
    target_location: str


@dataclass(frozen=True, slots=True)
class CompilationExplanation:
    """A read-only projection of a plan for census gates and diagnostics."""

    total_units: int
    static_units: int
    interpreted_units: int
    causes: Mapping[FallbackCause, int]
    interpreted_keys: tuple[str, ...]
    reaches_interpreted: int
    resolved_dynamic_sites: tuple[ResolvedDynamicSite, ...] = ()
    # M9: consumers tracked at runtime, and the units in their regions.
    tracked_units: int = 0
    region_units: int = 0
    # Anchors specialized per dynamic context, and the units cloned for it.
    split_anchors: tuple[SplitAnchor, ...] = ()
    specialized_units: int = 0


def explain_compilation(plan: CompilationPlan) -> CompilationExplanation:
    causes: dict[FallbackCause, int] = {}
    interpreted: list[str] = []
    reaching = tracked = region = specialized = 0
    resolved: list[ResolvedDynamicSite] = []
    for unit in plan.units.values():
        specialized += bool(unit.context)
        if unit.kind == "interpreted":
            interpreted.append(unit.key)
            assert unit.cause is not None
            causes[unit.cause] = causes.get(unit.cause, 0) + 1
            continue
        if unit.reaches_interpreted:
            reaching += 1
        tracked += unit.tracked
        region += unit.in_region
        for edge in unit.edges:
            if edge.dynamic is not None and edge.app.ref is not None:
                resolved.append(
                    ResolvedDynamicSite(
                        unit.key,
                        edge.keyword,
                        edge.app.ref,
                        edge.target_key,
                        edge.dynamic.winner,
                        unit.ref.location,
                        plan.units[edge.target_key].ref.location,
                    )
                )
    return CompilationExplanation(
        total_units=len(plan.units),
        static_units=len(plan.units) - len(interpreted),
        interpreted_units=len(interpreted),
        causes=dict(sorted(causes.items())),
        interpreted_keys=tuple(sorted(interpreted)),
        reaches_interpreted=reaching,
        resolved_dynamic_sites=tuple(
            sorted(resolved, key=lambda s: (s.unit, s.keyword, s.ref))
        ),
        tracked_units=tracked,
        region_units=region,
        split_anchors=plan.split_anchors,
        specialized_units=specialized,
    )


def schema_value(ref: SchemaRef) -> Mapping[str, JsonValue]:
    """The object node of a static, non-boolean unit."""
    node = ref.node
    assert is_object(node)
    return node
