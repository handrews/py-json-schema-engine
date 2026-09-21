# Unit lowering (M6): run each present keyword's `lower()` in dialect
# order against a recording `LoweringContext`, yielding the unit's IR; plus
# the pure IR analyses the emitter needs (object-guard use, loop height).
# Binding ids are local to one lowering; the serializer names them.
#
# Dependency direction: imports the planner, `context`, and core's IR. The
# body serializer imports this (for inlining); nothing here imports it.

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from json_schema_engine.compiler.plan import PlannedUnit, schema_value
from json_schema_engine.compiler.serialize.context import SerializeError
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.lowering import (
    INSTANCE,
    Append,
    Cmp,
    Cond,
    CountRange,
    Covers,
    Expr,
    ForEachIndex,
    ForEachKey,
    FormatTest,
    HasKey,
    Helper,
    If,
    InConsts,
    Instance,
    Item,
    Logic,
    Member,
    Not,
    Produce,
    RegexTest,
    StaticCoverage,
    Stmt,
    TypeIs,
)
from json_schema_engine.core.registry import SchemaRegistry


@dataclass(slots=True)
class _Lowering:
    """The `LoweringContext` given to one keyword's `lower()`."""

    _schema: Mapping[str, JsonValue]
    _coverage: StaticCoverage | None
    _tracked: bool
    next_binding: int
    stmts: list[Stmt] = field(default_factory=list[Stmt])

    @property
    def instance(self) -> Expr:
        return INSTANCE

    @property
    def schema(self) -> Mapping[str, JsonValue]:
        return self._schema

    def static_coverage(self) -> StaticCoverage | None:
        return self._coverage

    def runtime_coverage(self) -> bool:
        return self._tracked

    def emit(self, *stmts: Stmt) -> None:
        self.stmts.extend(stmts)

    def binding(self) -> int:
        binding = self.next_binding
        self.next_binding += 1
        return binding


@dataclass(frozen=True, slots=True)
class KeywordIR:
    """One present keyword's lowered statements and its behavior id."""

    name: str
    behavior_id: str
    stmts: tuple[Stmt, ...]


@dataclass(frozen=True, slots=True)
class UnitIR:
    """A unit's lowered body: one statement list per present keyword, in
    dialect evaluation order."""

    keywords: tuple[KeywordIR, ...]


def lower_unit(registry: SchemaRegistry, unit: PlannedUnit) -> UnitIR:
    """Lower every present keyword of a static, non-boolean unit."""
    node = schema_value(unit.ref)
    dialect = registry.dialect_for(unit.ref.base_uri)
    ref_only = dialect.ref_ignores_siblings and "$ref" in node
    next_binding = 0
    keywords: list[KeywordIR] = []
    for entry in dialect.ordered:
        if ref_only and entry.name != "$ref":
            continue
        if entry.name not in node:
            continue
        lower = entry.behavior.lower
        if lower is None:
            raise SerializeError(f"unlowerable keyword {entry.name!r} in a static unit")
        ctx = _Lowering(node, unit.coverage, unit.tracked, next_binding)
        lower(node[entry.name], ctx)
        next_binding = ctx.next_binding
        keywords.append(KeywordIR(entry.name, entry.behavior.id, tuple(ctx.stmts)))
    return UnitIR(tuple(keywords))


def _exprs_of(expr: Expr) -> Iterator[Expr]:
    yield expr
    match expr:
        case (
            Member(target, _)
            | TypeIs(target, _)
            | InConsts(target, _)
            | RegexTest(_, target)
            | FormatTest(_, target)
        ):
            yield from _exprs_of(target)
        case Item(target, index):
            yield from _exprs_of(target)
            yield from _exprs_of(index)
        case HasKey(target, key):
            yield from _exprs_of(target)
            if not isinstance(key, str):
                yield from _exprs_of(key)
        case Cmp(_, left, right):
            yield from _exprs_of(left)
            yield from _exprs_of(right)
        case Helper(_, args) | Logic(_, args):
            for arg in args:
                yield from _exprs_of(arg)
        case Not(inner):
            yield from _exprs_of(inner)
        case Cond(test, then, orelse):
            yield from _exprs_of(test)
            yield from _exprs_of(then)
            yield from _exprs_of(orelse)
        case Covers(_, target):
            yield from _exprs_of(target)
        case _:
            # `Instance`, `Const`, `Binding`, and `ApplyExpr` (whose cursor
            # segments are bindings, never type tests) contribute nothing.
            pass


def _stmt_exprs(stmt: Stmt) -> Iterator[Expr]:
    match stmt:
        case If(cond, then, orelse):
            yield from _exprs_of(cond)
            for inner in (*then, *orelse):
                yield from _stmt_exprs(inner)
        case ForEachKey(target, _, body) | ForEachIndex(target, _, body, _):
            yield from _exprs_of(target)
            for inner in body:
                yield from _stmt_exprs(inner)
        case CountRange(target=target, count_when=count_when):
            yield from _exprs_of(target)
            yield from _exprs_of(count_when)
        case Append(_, value) | Produce(value):
            yield from _exprs_of(value)
        case _:
            pass


def uses_object_test(ir: UnitIR) -> bool:
    """Whether the body tests its own instance for object-ness (the guard
    is then hoisted once per body, D9)."""
    for keyword in ir.keywords:
        for stmt in keyword.stmts:
            for expr in _stmt_exprs(stmt):
                if (
                    isinstance(expr, TypeIs)
                    and isinstance(expr.target, Instance)
                    and "object" in expr.types
                ):
                    return True
    return False


def loop_height(stmts: tuple[Stmt, ...]) -> int:
    """The deepest loop nesting in a statement list (statically nested
    blocks toward CPython's cap)."""
    deepest = 0
    for stmt in stmts:
        match stmt:
            case If(_, then, orelse):
                deepest = max(deepest, loop_height(then), loop_height(orelse))
            case ForEachKey(_, _, body) | ForEachIndex(_, _, body, _):
                deepest = max(deepest, 1 + loop_height(body))
            case CountRange():
                deepest = max(deepest, 1)
            case _:
                pass
    return deepest


def ir_loop_height(ir: UnitIR) -> int:
    return max((loop_height(k.stmts) for k in ir.keywords), default=0)
