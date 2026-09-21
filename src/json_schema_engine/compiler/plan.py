# The compilation planner (DESIGN.md D1, D8, D9; M6): classifies every
# schema node reachable from a root as a static (compilable) or interpreted
# (trampoline) unit, using only public core APIs and `analyze()` facts —
# never keyword names. Conservative by design: anything uncertain falls
# back to the interpreter, which is always correct.
#
# Dependency direction: imports core's registry/dialect/ref/errors and the
# engine façade's type. The serializer and the public API import this.

from collections.abc import Mapping
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
"""Why a unit is interpreted: a `$dynamicRef`-class keyword; a keyword
without `lower()`, an unresolvable edge, or a consumer without static
coverage; a possible in-place cycle; a reference into non-schema data
(the interpreter's D19 backstop reports it)."""


@dataclass(frozen=True, slots=True)
class PlannedApplication:
    """One application edge out of a unit, resolved at plan time."""

    keyword: str
    app: SubschemaApplication
    target_key: str


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
    # Interpreted units in stable order; index = target-table slot.
    targets: tuple[PlannedUnit, ...]


def unit_key(ref: SchemaRef) -> str:
    return ref.location


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
) -> tuple[_NameHalf | None, _IndexHalf | None]:
    """The evaluated coverage a schema node contributes at its own cursor
    (D9a), including — transitively — unconditional asserting in-place
    applications. `None` means statically unknowable.

    `exclude_consumers` is true only for the licensing node itself: a
    consumer's own coverage fact describes the state after it runs. Facts
    come from `analyze()` alone, so contribution is independent of which
    tier evaluates the target.
    """
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
            if facts.dynamic_scope_sensitive:
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
                try:
                    target = _edge_target(registry, ref, entry.name, app)
                except UnresolvableReferenceError:
                    return None, None
                sub_names, sub_indexes = coverage_halves(
                    registry, target, visiting, False
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


def _edge_target(
    registry: SchemaRegistry, ref: SchemaRef, keyword: str, app: SubschemaApplication
) -> SchemaRef:
    if app.ref is not None:
        return registry.resolve_ref(app.ref, ref.base_uri)
    head = app.sibling if app.sibling is not None else keyword
    return registry.child(ref, [head, *app.path])


def edge_target(
    registry: SchemaRegistry, ref: SchemaRef, keyword: str, app: SubschemaApplication
) -> SchemaRef:
    """The schema position an application edge lands on."""
    return _edge_target(registry, ref, keyword, app)


def _is_coverage_consumer(facts: StaticFacts) -> bool:
    # A coverage consumer (`unevaluated*`) declares `consumes` and an
    # evaluated-coverage fact; a keyword consuming other dependency data
    # (`then`/`else` reading `if`'s outcome) needs no coverage.
    return len(facts.consumes) > 0 and (
        facts.evaluates_names is not None or facts.evaluates_indexes is not None
    )


def build_plan(engine: Engine, schema_uri: str) -> CompilationPlan:
    """Plan the compilation of one registered root schema.

    The walk mirrors the registration walk's position logic by
    construction: descent uses the same `analyze()` facts and the same
    `registry.child` pointer navigation. `registry` may be a snapshot.
    """
    return build_plan_over(engine.schemas, schema_uri)


def build_plan_over(registry: SchemaRegistry, schema_uri: str) -> CompilationPlan:
    units: dict[str, PlannedUnit] = {}
    patterns: dict[str, None] = {}

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
            if facts.dynamic_scope_sensitive:
                unit.interpret("dynamic")
                return unit
            if entry.behavior.lower is None:
                unit.interpret("unlowerable")
                return unit
            if _is_coverage_consumer(facts):
                consumer_present = True
            for regex in facts.regexes:
                patterns[regex] = None
            present.append((entry.name, facts))
        # Unknown keywords are annotations: nothing to assert in flag mode.

        # Consumer licensing (D9a): a consumer lowers only when the coverage
        # half it needs is statically known — from this object's own
        # contributors plus, transitively, unconditional asserting in-place
        # applications. Anything runtime-conditional makes the coverage
        # dynamic and (in M6, without runtime tracking) the node interpreted.
        if consumer_present:
            name_half, index_half = coverage_halves(registry, ref, set(), True)
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

        # Resolve application edges; plan children.
        for name, facts in present:
            for app in facts.applications:
                try:
                    target = _edge_target(registry, ref, name, app)
                except UnresolvableReferenceError:
                    # Lazy-failure parity: the interpreter raises only when
                    # the reference is followed, so the whole node falls back.
                    unit.interpret("unlowerable")
                    return unit
                target_key = unit_key(target)
                if app.mode == "in_place":
                    if target_key in in_place_chain or target_key == key:
                        # In-place cycle: same-cursor re-entry. The
                        # interpreter's cycle guard gives exact
                        # `InfiniteLoopError` parity.
                        cyclic = units.get(target_key) or plan(
                            target, (*in_place_chain, key)
                        )
                        cyclic.interpret("cycle")
                        if cyclic is unit:
                            return unit
                        unit.edges.append(PlannedApplication(name, app, target_key))
                        continue
                    plan(target, (*in_place_chain, key))
                else:
                    plan(target, ())
                unit.edges.append(PlannedApplication(name, app, target_key))
        return unit

    root = plan(registry.root_ref(schema_uri), ())

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
    return CompilationPlan(root.key, units, tuple(patterns), targets)


@dataclass(frozen=True, slots=True)
class CompilationExplanation:
    """A read-only projection of a plan for census gates and diagnostics."""

    total_units: int
    static_units: int
    interpreted_units: int
    causes: Mapping[FallbackCause, int]
    interpreted_keys: tuple[str, ...]
    reaches_interpreted: int


def explain_compilation(plan: CompilationPlan) -> CompilationExplanation:
    causes: dict[FallbackCause, int] = {}
    interpreted: list[str] = []
    reaching = 0
    for unit in plan.units.values():
        if unit.kind == "interpreted":
            interpreted.append(unit.key)
            assert unit.cause is not None
            causes[unit.cause] = causes.get(unit.cause, 0) + 1
        elif unit.reaches_interpreted:
            reaching += 1
    return CompilationExplanation(
        total_units=len(plan.units),
        static_units=len(plan.units) - len(interpreted),
        interpreted_units=len(interpreted),
        causes=dict(sorted(causes.items())),
        interpreted_keys=tuple(sorted(interpreted)),
        reaches_interpreted=reaching,
    )


def schema_value(ref: SchemaRef) -> Mapping[str, JsonValue]:
    """The object node of a static, non-boolean unit."""
    node = ref.node
    assert is_object(node)
    return node
