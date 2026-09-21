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
# graph, so the plan is built in rounds under the current site decisions;
# decisions move only unknown → resolved → unstable, which bounds the loop.
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
resolve (its target differs by path, or the keyword declares no
resolution fact); a keyword without `lower()`, an unresolvable edge, or a
consumer without static coverage; a possible in-place cycle; a reference
into non-schema data (the interpreter's D19 backstop reports it)."""


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
    """One schema node in the plan, keyed by its canonical location."""

    key: str
    ref: SchemaRef
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

    def interpret(self, cause: FallbackCause) -> None:
        self.kind = "interpreted"
        self.cause = cause
        self.edges = []


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


def unit_key(ref: SchemaRef) -> str:
    return ref.location


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
class _PendingSite:
    """A site met during a round with no decision yet."""

    key: SiteKey
    unit_key: str
    kind: Literal["dynamic", "recursive"]
    anchor: str
    lexical: SchemaRef


@dataclass(frozen=True, slots=True)
class _Resolved:
    target: SchemaRef
    dynamic: DynamicResolution | None = None


@dataclass(frozen=True, slots=True)
class _Pending:
    site: _PendingSite


type _EdgeResolution = _Resolved | _Pending | Literal["unresolvable", "unstable"]

# The 2019-09 rebinding has no anchor name; one sentinel keys its dataflow.
_RECURSIVE_ANCHOR = "$recursiveAnchor"


def _resolve_edge(
    registry: SchemaRegistry,
    ref: SchemaRef,
    keyword: str,
    app: SubschemaApplication,
    sites: SiteDecisions,
) -> _EdgeResolution:
    """Where an application edge lands, under the current site decisions."""
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
    key: SiteKey = (unit_key(ref), keyword, app.ref)
    state = sites.get(key)
    if state is None:
        return _Pending(
            _PendingSite(key, unit_key(ref), app.resolution, anchor, lexical)
        )
    if state == "unstable":
        return "unstable"
    return _Resolved(state.target, DynamicResolution(state.winner))


def edge_target(
    registry: SchemaRegistry, ref: SchemaRef, keyword: str, app: SubschemaApplication
) -> SchemaRef:
    """The schema position a scope-independent application edge lands on.

    Raises `UnresolvableReferenceError` for a missing target and
    `ValueError` for a dynamic site (whose target is a plan decision).
    """
    resolution = _resolve_edge(registry, ref, keyword, app, {})
    match resolution:
        case _Resolved(target):
            return target
        case "unresolvable":
            raise UnresolvableReferenceError(f"unresolvable reference {app.ref!r}")
        case _:
            raise ValueError("a dynamic-reference site has no plan-independent target")


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
    visiting: set[str],
    exclude_consumers: bool,
    sites: SiteDecisions | None = None,
) -> tuple[_NameHalf | None, _IndexHalf | None]:
    """The evaluated coverage a schema node contributes at its own cursor
    (D9a), including — transitively — unconditional asserting in-place
    applications. `None` means statically unknowable.

    `exclude_consumers` is true only for the licensing node itself: a
    consumer's own coverage fact describes the state after it runs. Facts
    come from `analyze()` alone, so contribution is independent of which
    tier evaluates the target. Dynamic-reference edges resolve through
    `sites`; a pending or unstable site is unknowable, exactly like an
    unresolvable `$ref`.
    """
    if sites is None:
        sites = {}
    key = unit_key(ref)
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
                resolution = _resolve_edge(registry, ref, entry.name, app, sites)
                if not isinstance(resolution, _Resolved):
                    return None, None
                sub_names, sub_indexes = coverage_halves(
                    registry, resolution.target, visiting, False, sites
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


def build_plan(engine: Engine, schema_uri: str) -> CompilationPlan:
    """Plan the compilation of one registered root schema.

    The walk mirrors the registration walk's position logic by
    construction: descent uses the same `analyze()` facts and the same
    `registry.child` pointer navigation. `registry` may be a snapshot.
    """
    return build_plan_over(engine.schemas, schema_uri)


@dataclass(slots=True)
class _Round:
    units: dict[str, PlannedUnit]
    patterns: dict[str, None]
    formats: dict[str, None]
    pending: dict[SiteKey, _PendingSite]
    root: PlannedUnit


@dataclass(frozen=True, slots=True)
class _Edge:
    keyword: str
    app: SubschemaApplication
    target: SchemaRef
    dynamic: DynamicResolution | None


def _plan_round(
    registry: SchemaRegistry, root_ref: SchemaRef, sites: SiteDecisions
) -> _Round:
    units: dict[str, PlannedUnit] = {}
    patterns: dict[str, None] = {}
    formats: dict[str, None] = {}
    pending: dict[SiteKey, _PendingSite] = {}

    def plan(ref: SchemaRef, in_place_chain: tuple[str, ...]) -> PlannedUnit:
        key = unit_key(ref)
        existing = units.get(key)
        if existing is not None:
            return existing
        unit = PlannedUnit(key, ref)
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
        # Unknown keywords are annotations: nothing to assert in flag mode.

        # Resolve every edge before any child is planned, so a unit that
        # islands never leaves half-planned children behind.
        edges: list[_Edge] = []
        for name, facts in present:
            for app in facts.applications:
                resolution = _resolve_edge(registry, ref, name, app, sites)
                match resolution:
                    case _Resolved(target, dynamic):
                        edges.append(_Edge(name, app, target, dynamic))
                    case _Pending(site):
                        # No edge this round; the round settles the site.
                        pending.setdefault(site.key, site)
                    case "unstable":
                        unit.interpret("dynamic")
                        return unit
                    case "unresolvable":
                        # Lazy-failure parity: the interpreter raises only
                        # when the reference is followed, so the whole node
                        # falls back.
                        unit.interpret("unlowerable")
                        return unit

        # Consumer licensing (D9a): a consumer lowers only when the coverage
        # half it needs is statically known — from this object's own
        # contributors plus, transitively, unconditional asserting in-place
        # applications. Anything runtime-conditional makes the coverage
        # dynamic and (in M6, without runtime tracking) the node interpreted.
        if consumer_present:
            name_half, index_half = coverage_halves(registry, ref, set(), True, sites)
            needs_names = any(
                len(f.consumes) > 0 and f.evaluates_names is not None
                for _, f in present
            )
            needs_indexes = any(
                len(f.consumes) > 0 and f.evaluates_indexes is not None
                for _, f in present
            )
            if (needs_names and name_half is None) or (
                needs_indexes and index_half is None
            ):
                unit.interpret("unlowerable")
                return unit
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
            target_key = unit_key(edge.target)
            planned = PlannedApplication(
                edge.keyword, edge.app, target_key, edge.dynamic
            )
            if edge.app.mode == "in_place":
                if target_key in in_place_chain or target_key == key:
                    # In-place cycle: same-cursor re-entry. The interpreter's
                    # cycle guard gives exact `InfiniteLoopError` parity.
                    cyclic = units.get(target_key) or plan(
                        edge.target, (*in_place_chain, key)
                    )
                    cyclic.interpret("cycle")
                    if cyclic is unit:
                        return unit
                    unit.edges.append(planned)
                    continue
                plan(edge.target, (*in_place_chain, key))
            else:
                plan(edge.target, ())
            unit.edges.append(planned)
        return unit

    root = plan(root_ref, ())
    return _Round(units, patterns, formats, pending, root)


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
    resource binds if it declares), joined by union, to a fixpoint.
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


def _settle_sites(
    registry: SchemaRegistry, round_: _Round, sites: SiteDecisions
) -> bool:
    """Decide every pending site of a round; True when a decision changed."""
    changed = False
    by_anchor: dict[tuple[str, str], list[_PendingSite]] = {}
    for site in round_.pending.values():
        by_anchor.setdefault((site.kind, site.anchor), []).append(site)
    for (kind, anchor), group in by_anchor.items():
        if kind == "dynamic":

            def declares(resource: str, anchor: str = anchor) -> bool:
                return registry.dynamic_anchor(resource, anchor) is not None

            def target_of(winner: str, anchor: str = anchor) -> SchemaRef:
                hit = registry.dynamic_anchor(winner, anchor)
                assert hit is not None
                return hit

        else:

            def declares(resource: str, anchor: str = anchor) -> bool:
                return registry.has_recursive_root(resource)

            def target_of(winner: str, anchor: str = anchor) -> SchemaRef:
                return registry.root_ref(winner)

        arrival = _outermost_declarers(round_.units, round_.root.key, declares)
        for site in group:
            winners = arrival.get(site.unit_key)
            if not winners:
                # Unreachable from the root this round (only through an
                # island): the interpreter resolves it there.
                continue
            targets: dict[str, tuple[SchemaRef, str | None]] = {}
            for winner in sorted(winners, key=lambda w: (w is not None, w or "")):
                target = site.lexical if winner is None else target_of(winner)
                targets.setdefault(unit_key(target), (target, winner))
            previous = sites.get(site.key)
            if len(targets) == 1:
                ((target, winner),) = targets.values()
                if previous is None:
                    sites[site.key] = ResolvedSite(target, winner)
                    changed = True
                elif previous != "unstable" and unit_key(previous.target) != unit_key(
                    target
                ):
                    sites[site.key] = "unstable"
                    changed = True
            elif previous != "unstable":
                sites[site.key] = "unstable"
                changed = True
    return changed


def build_plan_over(registry: SchemaRegistry, schema_uri: str) -> CompilationPlan:
    root_ref = registry.root_ref(schema_uri)
    sites: SiteDecisions = {}
    while True:
        round_ = _plan_round(registry, root_ref, sites)
        if not _settle_sites(registry, round_, sites):
            break
    units = round_.units

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
    return CompilationPlan(
        round_.root.key, units, tuple(round_.patterns), tuple(round_.formats), targets
    )


# --- explanation -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedDynamicSite:
    """A dynamic-reference site the plan compiled as a static edge."""

    unit: str
    keyword: str
    ref: str
    target: str
    winner: str | None


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


def explain_compilation(plan: CompilationPlan) -> CompilationExplanation:
    causes: dict[FallbackCause, int] = {}
    interpreted: list[str] = []
    reaching = 0
    resolved: list[ResolvedDynamicSite] = []
    for unit in plan.units.values():
        if unit.kind == "interpreted":
            interpreted.append(unit.key)
            assert unit.cause is not None
            causes[unit.cause] = causes.get(unit.cause, 0) + 1
            continue
        if unit.reaches_interpreted:
            reaching += 1
        for edge in unit.edges:
            if edge.dynamic is not None and edge.app.ref is not None:
                resolved.append(
                    ResolvedDynamicSite(
                        unit.key,
                        edge.keyword,
                        edge.app.ref,
                        edge.target_key,
                        edge.dynamic.winner,
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
    )


def schema_value(ref: SchemaRef) -> Mapping[str, JsonValue]:
    """The object node of a static, non-boolean unit."""
    node = ref.node
    assert is_object(node)
    return node
