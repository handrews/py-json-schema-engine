# Compiler lowering IR (DESIGN.md D1, D9; M6): the vocabulary a keyword
# behavior uses to describe its compiled form through `KeywordBehavior.lower`,
# and the `LoweringContext` service the compiler implements. Data only —
# core carries no compiler runtime, and keyword modules depend on this
# module, never on `json_schema_engine.compiler`, so keyword knowledge
# stays in exactly one module per keyword.
#
# Public API (M9): every name in `__all__` below is documented under
# `json_schema_engine.core.lowering` in docs/reference.md, so a custom
# keyword can give itself a `lower` form without reaching into a private
# module.
#
# Dependency direction: imports only `json_model`. `dialect.py` imports
# this for the `lower` slot's type; the compiler package consumes it.
#
# Two properties are load-bearing:
#
# 1. No IR node carries Python source text. Schema-derived data enters only
#    as data nodes (`Const`, member keys, regex sources, `InConsts` values),
#    which the compiler turns into `ast.Constant` nodes and nothing else.
#    Injection is unrepresentable upstream of the emitter (D1, D20).
#
# 2. Application folds are EAGER by contract: every applied subschema is
#    evaluated, then the verdicts fold (§4 rule 6). A short-circuit is a
#    licensed emitter optimization in verdict-only regions (§4 rule 7),
#    never an IR semantic.
#
# Runtime coverage tracking (M9): a producer keyword describes the
# dependency data it would `ctx.produce()` with `Produce` (the same value
# shapes: name lists, `True`, an index), collected on the way with
# `Collect`/`Append`; a consumer that the planner tracks at runtime (no
# static licence) folds the region's channel once with `CoverageFold` and
# tests membership with `Covers`. Outside a tracked region the emitter
# elides all of them, so flag code there is unchanged. `Fail` keeps its
# message and params although flag emission ignores them, so a keyword
# shares one message builder between `evaluate` and `lower` from the
# start and evaluator-mode parity is mechanical.

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from json_schema_engine.core.json_model import JsonValue

__all__ = [
    "HERE",
    "INSTANCE",
    "Annotate",
    "Append",
    "Apply",
    "ApplyExpr",
    "Binding",
    "Child",
    "Cmp",
    "CmpOp",
    "Collect",
    "CombineCheck",
    "Cond",
    "Const",
    "CountRange",
    "CoverageFold",
    "Covers",
    "Expr",
    "Fail",
    "Fold",
    "ForEachIndex",
    "ForEachKey",
    "FormatTest",
    "HasKey",
    "Helper",
    "HelperName",
    "Here",
    "If",
    "InConsts",
    "Instance",
    "Item",
    "Key",
    "Logic",
    "LowerApply",
    "LowerCursor",
    "LowerFn",
    "LowerMessage",
    "LowerParams",
    "LoweringContext",
    "Member",
    "Not",
    "Produce",
    "RegexTest",
    "StaticCoverage",
    "Stmt",
    "TypeIs",
    "TypeName",
    "and_",
    "annotate",
    "append",
    "apply",
    "apply_expr",
    "child",
    "cmp",
    "collect",
    "combine_check",
    "cond",
    "const",
    "coverage_fold",
    "covers",
    "fail",
    "format_test",
    "has_key",
    "helper",
    "in_consts",
    "key",
    "lower_nothing",
    "not_",
    "or_",
    "produce",
    "regex_test",
    "type_is",
    "when",
]

# --- expressions -----------------------------------------------------------

# The spec's type names as plain strings (the values of `JsonType`), plus
# the `integer` refinement, so keyword modules and the emitter never juggle
# the enum.
type TypeName = Literal[
    "null", "boolean", "object", "array", "number", "string", "integer"
]
type HelperName = Literal[
    "json_equal",
    "is_multiple_of",
    "has_duplicate_items",
    "first_duplicate_pair",
    "length_of",
    "code_point_length",
    "json_type_name",
]
type CmpOp = Literal["<", "<=", ">", ">=", "==", "!="]


@dataclass(frozen=True, slots=True)
class Instance:
    """The instance value under evaluation at the lowering site."""


@dataclass(frozen=True, slots=True)
class Const:
    """A schema-derived JSON constant; the emitter's only data entry point."""

    value: JsonValue


@dataclass(frozen=True, slots=True)
class Member:
    """Object member access by a schema-derived key."""

    target: "Expr"
    key: str


@dataclass(frozen=True, slots=True)
class Item:
    """Array element access."""

    target: "Expr"
    index: "Expr"


@dataclass(frozen=True, slots=True)
class Binding:
    """A loop binding introduced by `ForEachKey`/`ForEachIndex`/`CountRange`."""

    id: int


@dataclass(frozen=True, slots=True)
class TypeIs:
    """JSON type test, including the `integer` refinement (P2 discipline)."""

    target: "Expr"
    types: tuple[TypeName, ...]


@dataclass(frozen=True, slots=True)
class HasKey:
    """Object membership test: the key is a constant or a swept binding."""

    target: "Expr"
    key: "Expr | str"


@dataclass(frozen=True, slots=True)
class Cmp:
    """Numeric or string comparison of two expressions."""

    op: CmpOp
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True, slots=True)
class Helper:
    """A call into the closed helper set (core's own functions, never
    re-implemented by emitted code)."""

    name: HelperName
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class InConsts:
    """`json_equal(target, v)` for some `v` in `values` (D9d).

    The keyword states the membership; the emitter chooses the mechanism
    (a hoisted `frozenset`, an equality chain) from measurements.
    """

    target: "Expr"
    values: tuple[JsonValue, ...]


@dataclass(frozen=True, slots=True)
class RegexTest:
    """An unanchored search with a hoisted pattern (compiled through the
    engine's `RegexCache`)."""

    source: str
    target: "Expr"


@dataclass(frozen=True, slots=True)
class FormatTest:
    """A format predicate applied to `target`, hoisted like a regex and
    resolved by `name` from the engine's format table (M7)."""

    name: str
    target: "Expr"


@dataclass(frozen=True, slots=True)
class Not:
    expr: "Expr"


@dataclass(frozen=True, slots=True)
class Logic:
    op: Literal["and", "or"]
    parts: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class ApplyExpr:
    """A subschema application used for its verdict as a value: `if`'s
    condition, `not`'s negated apply, `contains`' per-item probe. A bare
    `ApplyExpr` used purely for its value carries `fold="discard"`."""

    apply: "LowerApply"


@dataclass(frozen=True, slots=True)
class Cond:
    """A conditional expression: `then` when `test` holds, else `orelse`."""

    test: "Expr"
    then: "Expr"
    orelse: "Expr"


@dataclass(frozen=True, slots=True)
class Covers:
    """Whether the coverage bound by a `CoverageFold` covers `target` (a
    swept name or index)."""

    fold: int
    target: "Expr"


type Expr = (
    Instance
    | Const
    | Member
    | Item
    | Binding
    | TypeIs
    | HasKey
    | Cmp
    | Helper
    | InConsts
    | RegexTest
    | FormatTest
    | Not
    | Logic
    | ApplyExpr
    | Cond
    | Covers
)

# --- cursors and applications ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Here:
    """The current instance position."""


@dataclass(frozen=True, slots=True)
class Child:
    """A child of a cursor: a constant member/index or a swept binding."""

    of: "LowerCursor"
    segment: Expr | str | int


@dataclass(frozen=True, slots=True)
class Key:
    """`propertyNames`: the swept key string itself is the instance."""

    binding: int


type LowerCursor = Here | Child | Key

type Fold = Literal["all_must_pass", "any_may_pass", "exactly_one", "negate", "discard"]
type LowerMessage = tuple[str | Expr, ...]
type LowerParams = Mapping[str, Expr]


@dataclass(frozen=True, slots=True)
class LowerApply:
    """How a keyword's lowered body applies one subschema.

    `path` is the subschema position relative to the keyword's value (loop
    bindings never appear in a path: a swept child's position is
    `path=()` with the binding in the cursor). `sibling` names a sibling
    keyword whose value is applied (`if` → `then`/`else`); `ref` is a
    reference value resolved at plan time against the unit's lexical base
    (then `path` is ignored); `resolution` marks a reference the plan
    resolved against the dynamic scope (`"dynamic"`/`"recursive"`, D8),
    which the lowered apply carries only so the serializer can find the
    planner's edge — the target is the plan's decision, never the IR's.
    `fold` says how the verdict folds into the keyword's verdict;
    `message`/`params` accompany folds that report their own failure
    (`negate`).
    """

    path: tuple[str | int, ...]
    cursor: LowerCursor
    fold: Fold
    sibling: str | None = None
    ref: str | None = None
    message: LowerMessage | None = None
    params: LowerParams | None = None
    resolution: Literal["dynamic", "recursive"] | None = None


# --- statements ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class If:
    cond: Expr
    then: tuple["Stmt", ...]
    orelse: tuple["Stmt", ...] = ()


@dataclass(frozen=True, slots=True)
class ForEachKey:
    """Iterate an object's member names, binding each."""

    target: Expr
    binding: int
    body: tuple["Stmt", ...]


@dataclass(frozen=True, slots=True)
class ForEachIndex:
    """Iterate array indexes from `start`, binding each."""

    target: Expr
    binding: int
    body: tuple["Stmt", ...]
    start: int = 0


@dataclass(frozen=True, slots=True)
class Fail:
    """This keyword's assertion failure at the current cursor."""

    message: LowerMessage
    params: LowerParams | None = None


@dataclass(frozen=True, slots=True)
class Apply:
    """Apply a subschema and fold its verdict per `apply.fold`."""

    apply: LowerApply


@dataclass(frozen=True, slots=True)
class CombineCheck:
    """Closes the immediately preceding run of `any_may_pass`/`exactly_one`
    applies: the keyword fails with `message` when the run's combined
    verdict fails. Emitted by the keyword so failure text stays keyword
    knowledge (D1). `count`/`passing` are bindings the message and params
    may reference: the number of passing branches and their indexes."""

    message: LowerMessage
    params: LowerParams | None = None
    count: int | None = None
    passing: int | None = None


@dataclass(frozen=True, slots=True)
class CountRange:
    """`contains`' shape: probe every index, count the matches, fail when
    the count falls outside `[minimum, maximum]` (`None` = unbounded).
    `matched`, when set, is a list binding that collects the matching
    indexes (the keyword's dependency data)."""

    target: Expr
    binding: int
    count_when: Expr
    minimum: int
    maximum: int | None
    message: LowerMessage
    params: LowerParams | None = None
    matched: int | None = None
    # A binding the message and params may reference: the match count.
    count: int | None = None


@dataclass(frozen=True, slots=True)
class Annotate:
    """The keyword's own value as an annotation at the current cursor (§4
    rule 2). Elided when the artifact's selection rules the keyword out."""


@dataclass(frozen=True, slots=True)
class Collect:
    """Bind an empty list to accumulate dependency data."""

    binding: int


@dataclass(frozen=True, slots=True)
class Append:
    """Append `value` to a `Collect` binding (`unique`: only when absent)."""

    binding: int
    value: Expr
    unique: bool = False


@dataclass(frozen=True, slots=True)
class Produce:
    """The keyword's dependency data at the current cursor (§4 rule 2):
    the value `ctx.produce()` would carry. Reached only along the keyword's
    accepting path (rule 6). Elided unless a tracked consumer reads it."""

    value: Expr


@dataclass(frozen=True, slots=True)
class CoverageFold:
    """Bind the runtime evaluated coverage a tracked consumer reads: the
    region channel's productions from the producers in `consumes`, folded
    by core's coverage folds (`half` selects names or indexes)."""

    binding: int
    half: Literal["names", "indexes"]
    consumes: tuple[str, ...]
    contains_id: str | None = None
    prefix_id: str | None = None


type Stmt = (
    If
    | ForEachKey
    | ForEachIndex
    | Fail
    | Apply
    | CombineCheck
    | CountRange
    | Collect
    | Append
    | Produce
    | CoverageFold
    | Annotate
)

# --- the lowering service --------------------------------------------------


@dataclass(frozen=True, slots=True)
class StaticCoverage:
    """The statically known evaluated coverage of a schema object (D9a),
    for `unevaluated*` lowerings: names and patterns covered, whether every
    name is, the covered index prefix, and whether every index is."""

    names: frozenset[str]
    patterns: tuple[str, ...]
    covers_all_names: bool
    prefix_count: int
    covers_all_indexes: bool


class LoweringContext(Protocol):
    """Services available to one keyword's `lower()` (the plan-time mirror
    of `KeywordContext`, D3). Implemented by the compiler; defined here so
    keyword modules never import it."""

    @property
    def instance(self) -> Expr:
        """The instance expression at this lowering site."""
        ...

    @property
    def schema(self) -> Mapping[str, JsonValue]:
        """The keyword's containing schema object."""
        ...

    def static_coverage(self) -> StaticCoverage | None:
        """The planner's static coverage for this schema object; `None`
        means the planner did not license a static consumer here (it is
        then tracked at runtime, `runtime_coverage()`)."""
        ...

    def runtime_coverage(self) -> bool:
        """Whether the planner tracks this schema object's consumers at
        runtime (M9): the consumer folds the region channel instead of a
        static coverage. Exactly one of this and `static_coverage()` is
        available to a consumer; neither means a planner bug."""
        ...

    def emit(self, *stmts: Stmt) -> None:
        """Append statements to the keyword's lowered body."""
        ...

    def binding(self) -> int:
        """Allocate a loop binding id."""
        ...


type LowerFn = Callable[[JsonValue, LoweringContext], None]


def lower_nothing(_value: JsonValue, _ctx: LoweringContext) -> None:
    """The lowering of a keyword that asserts nothing (structural,
    annotation-only, and sibling-driven keywords)."""


# --- constructor shorthands ------------------------------------------------

INSTANCE = Instance()
HERE = Here()


def const(value: JsonValue) -> Const:
    return Const(value)


def type_is(target: Expr, *types: TypeName) -> TypeIs:
    return TypeIs(target, types)


def has_key(target: Expr, key: Expr | str) -> HasKey:
    return HasKey(target, key)


def cmp(op: CmpOp, left: Expr, right: Expr) -> Cmp:
    return Cmp(op, left, right)


def helper(name: HelperName, *args: Expr) -> Helper:
    return Helper(name, args)


def in_consts(target: Expr, values: tuple[JsonValue, ...]) -> InConsts:
    return InConsts(target, values)


def regex_test(source: str, target: Expr) -> RegexTest:
    return RegexTest(source, target)


def format_test(name: str, target: Expr) -> FormatTest:
    return FormatTest(name, target)


def not_(expr: Expr) -> Not:
    return Not(expr)


def and_(*parts: Expr) -> Logic:
    return Logic("and", parts)


def or_(*parts: Expr) -> Logic:
    return Logic("or", parts)


def child(of: LowerCursor, segment: Expr | str | int) -> Child:
    return Child(of, segment)


def key(binding: int) -> Key:
    return Key(binding)


def when(cond: Expr, then: tuple[Stmt, ...], orelse: tuple[Stmt, ...] = ()) -> If:
    return If(cond, then, orelse)


def fail(message: LowerMessage, params: LowerParams | None = None) -> Fail:
    return Fail(message, params)


def apply(
    path: tuple[str | int, ...],
    cursor: LowerCursor,
    fold: Fold = "all_must_pass",
    *,
    sibling: str | None = None,
    ref: str | None = None,
    message: LowerMessage | None = None,
    params: LowerParams | None = None,
    resolution: Literal["dynamic", "recursive"] | None = None,
) -> Apply:
    return Apply(
        LowerApply(path, cursor, fold, sibling, ref, message, params, resolution)
    )


def apply_expr(
    path: tuple[str | int, ...],
    cursor: LowerCursor,
    fold: Fold = "discard",
    *,
    sibling: str | None = None,
    ref: str | None = None,
) -> ApplyExpr:
    return ApplyExpr(LowerApply(path, cursor, fold, sibling, ref))


def combine_check(
    message: LowerMessage,
    params: LowerParams | None = None,
    *,
    count: int | None = None,
    passing: int | None = None,
) -> CombineCheck:
    return CombineCheck(message, params, count, passing)


def annotate() -> Annotate:
    return Annotate()


def cond(test: Expr, then: Expr, orelse: Expr) -> Cond:
    return Cond(test, then, orelse)


def covers(fold: int, target: Expr) -> Covers:
    return Covers(fold, target)


def collect(binding: int) -> Collect:
    return Collect(binding)


def append(binding: int, value: Expr, *, unique: bool = False) -> Append:
    return Append(binding, value, unique)


def produce(value: Expr) -> Produce:
    return Produce(value)


def coverage_fold(
    binding: int,
    half: Literal["names", "indexes"],
    consumes: tuple[str, ...],
    *,
    contains_id: str | None = None,
    prefix_id: str | None = None,
) -> CoverageFold:
    return CoverageFold(binding, half, consumes, contains_id, prefix_id)
