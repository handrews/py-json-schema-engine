# Applicators with a `false` subschema (DESIGN.md D13, P18).
#
# A `false` subschema fails everything it is applied to and explains
# nothing: its only error is "schema is false", once per child, while the
# useful fact -- which properties were additional, which indexes were past
# the prefix -- is the applicator's. So an applicator does not apply a
# `false` subschema at all. It names the keys it would have applied it to
# and reports them in one error of its own, built here so the wording is
# shared across keywords and both tiers.
#
# Dependency direction: imports `json_model` and `lowering`; keyword
# modules import this.

from collections.abc import Mapping, Sequence

from json_schema_engine.core.dialect import KeywordContext
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.lowering import (
    HERE,
    Binding,
    Const,
    Expr,
    Item,
    LoweringContext,
    LowerMessage,
    LowerParams,
    Stmt,
    apply,
    child,
    collect,
    helper,
    reject,
    reject_check,
)
from json_schema_engine.core.messages import realize


def is_false(value: JsonValue) -> bool:
    """The boolean schema `false`: `value is False`, never a falsy value."""
    return value is False


def names_rejected(
    prefix: str, suffix: str, names: Expr, extra: Mapping[str, Expr] | None = None
) -> tuple[LowerMessage, LowerParams]:
    """`additional properties "b", "c" not allowed`, params `properties`."""
    return (
        (
            prefix,
            helper("labeled_names", names, Const("property"), Const("properties")),
            suffix,
        ),
        {"properties": names, **(extra or {})},
    )


def tail_rejected(
    noun: str, start: int, indexes: Expr
) -> tuple[LowerMessage, LowerParams]:
    """`items not allowed from index 1: 1-4`: every index from `start`."""
    return (
        (f"{noun} not allowed from index {start}: ", helper("index_ranges", indexes)),
        {"start": Const(start), "failed": helper("ranges", indexes)},
    )


def positions_rejected(indexes: Expr) -> tuple[LowerMessage, LowerParams]:
    """`items not allowed at 1, 3`: the positions a tuple forbids."""
    return (
        ("items not allowed at ", helper("index_ranges", indexes)),
        {"failed": helper("ranges", indexes)},
    )


def unevaluated_rejected(indexes: Expr) -> tuple[LowerMessage, LowerParams]:
    """`unevaluated items not allowed, first at index 2: 2, 3, 6`."""
    first = Item(indexes, Const(0))
    return (
        (
            "unevaluated items not allowed, first at index ",
            first,
            ": ",
            helper("index_ranges", indexes),
        ),
        {"start": first, "failed": helper("ranges", indexes)},
    )


def tail_sweep(
    noun: str, value: JsonValue, start: int, binding: int, lctx: LoweringContext
) -> tuple[tuple[Stmt, ...], Stmt, tuple[Stmt, ...]]:
    """The head, per-index step and tail of an `items`-like sweep from
    `start`: apply the subschema, or, when it is `false`, reject the index
    and report the tail once."""
    if not is_false(value):
        return (), apply((), child(HERE, Binding(binding))), ()
    r = lctx.binding()
    return (
        (collect(r, errors=True),),
        reject(r, Binding(binding)),
        (reject_check(r, *tail_rejected(noun, start, Binding(r))),),
    )


def tail_evaluate(
    noun: str, start: int, instance: list[JsonValue], ctx: KeywordContext
) -> bool:
    """`evaluate`'s side of `tail_sweep` for a `false` subschema."""
    if len(instance) <= start:
        return True
    rejected: list[JsonValue] = list(range(start, len(instance)))
    ctx.error(*realize(*tail_rejected(noun, start, Const(rejected)), instance))
    return False


def positions_sweep(
    value: Sequence[JsonValue], lctx: LoweringContext
) -> tuple[tuple[Stmt, ...], tuple[Stmt, ...], int]:
    """Head and tail around a tuple sweep whose members may be `false`, and
    the binding a member's `reject` names (allocated, and meaningful, only
    when some member is `false`)."""
    if not any(is_false(schema) for schema in value):
        return (), (), -1
    r = lctx.binding()
    return (
        (collect(r, errors=True),),
        (reject_check(r, *positions_rejected(Binding(r))),),
        r,
    )
