# The gated `ast` builder (DESIGN.md D1 amendment, D10, D20; M6): the only
# way the serializer produces Python code. Schema-derived data enters
# through `const()` and becomes `ast.Constant` nodes (or containers of
# them) and nothing else; identifiers come from a fixed, machine-minted
# vocabulary that `Names` records, so a test can prove every name in an
# emitted module is one the compiler chose. No module here ever sees
# source text: `ast.unparse` runs once, in the public API, for diagnostics
# and standalone emission.
#
# Dependency direction: imports `ast`, `keyword`, `math`, and core's
# `JsonValue`. The serializer builds on this.

import ast
import keyword
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from json_schema_engine.core.json_model import JsonValue

# Fixed helper vocabulary (the exec namespace and the standalone prologue
# define exactly these; `Names.vocabulary` records them on first use).
H_EQ = "H_EQ"  # json_equal
H_MOF = "H_MOF"  # is_multiple_of
H_DUP = "H_DUP"  # has_duplicate_items
H_FRAG = "H_FRAG"  # trampoline into the interpreter
H_DEEP = "H_DEEP"  # raise MaxDepthExceededError
H_MAXD = "H_MAXD"  # the depth budget
TARGETS = "T"  # interpreted-unit table
RUNTIME = "R"  # the runtime object (regex table)
DEPTH_ERROR = "MaxDepthExceededError"
VALIDATE = "validate"
VALUE = "v"
DEPTH = "d"
SCOPE = "s"

BUILTINS_USED = frozenset(
    {
        "type",
        "len",
        "range",
        "frozenset",
        "dict",
        "list",
        "str",
        "int",
        "float",
        "bool",
        "RecursionError",
    }
)


class EmitError(Exception):
    """A serializer invariant was violated (a compiler bug, never schema data)."""


@dataclass(slots=True)
class Names:
    """Minted identifiers: unit functions, bindings, temps, guards, counters,
    regexes, hoisted constants. Every name passes `name()`, which rejects
    anything that is not a plain identifier or that shadows a keyword, and
    records it so the injection corpus can audit the emitted module."""

    vocabulary: set[str] = field(default_factory=set[str])
    _counters: dict[str, int] = field(default_factory=dict[str, int])

    def name(self, text: str) -> str:
        if not text.isidentifier() or keyword.iskeyword(text):
            raise EmitError(f"not an identifier: {text!r}")
        self.vocabulary.add(text)
        return text

    def fresh(self, prefix: str) -> str:
        count = self._counters.get(prefix, 0)
        self._counters[prefix] = count + 1
        return self.name(f"{prefix}{count}")


def load(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Load())


def store(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Store())


def const(value: JsonValue) -> ast.expr:
    """A JSON constant as an `ast` literal: the only data entry point."""
    if isinstance(value, bool | int | str) or value is None:
        return ast.Constant(value=value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise EmitError("non-finite number in schema data")
        return ast.Constant(value=value)
    if isinstance(value, list):
        return ast.List(elts=[const(v) for v in value], ctx=ast.Load())
    return ast.Dict(
        keys=[ast.Constant(value=k) for k in value],
        values=[const(v) for v in value.values()],
    )


def call(func: ast.expr, *args: ast.expr) -> ast.Call:
    return ast.Call(func=func, args=list(args), keywords=[])


def attr(value: ast.expr, name: str) -> ast.Attribute:
    return ast.Attribute(value=value, attr=name, ctx=ast.Load())


def subscript(value: ast.expr, index: ast.expr) -> ast.Subscript:
    return ast.Subscript(value=value, slice=index, ctx=ast.Load())


def compare(left: ast.expr, op: ast.cmpop, right: ast.expr) -> ast.Compare:
    return ast.Compare(left=left, ops=[op], comparators=[right])


def is_(left: ast.expr, right: ast.expr) -> ast.Compare:
    return compare(left, ast.Is(), right)


def is_not(left: ast.expr, right: ast.expr) -> ast.Compare:
    return compare(left, ast.IsNot(), right)


def in_(left: ast.expr, right: ast.expr) -> ast.Compare:
    return compare(left, ast.In(), right)


def not_in(left: ast.expr, right: ast.expr) -> ast.Compare:
    return compare(left, ast.NotIn(), right)


_NEGATED_OPS: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}


def not_(expr: ast.expr) -> ast.expr:
    # Double negation folds; identity and membership tests flip their
    # operator (`x is not None` rather than `not x is None`).
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return expr.operand
    if isinstance(expr, ast.Constant) and isinstance(expr.value, bool):
        return ast.Constant(value=not expr.value)
    if isinstance(expr, ast.Compare) and len(expr.ops) == 1:
        flipped = _NEGATED_OPS.get(type(expr.ops[0]))
        if flipped is not None:
            return ast.Compare(
                left=expr.left, ops=[flipped()], comparators=expr.comparators
            )
    return ast.UnaryOp(op=ast.Not(), operand=expr)


def _boolop(op: ast.boolop, parts: Sequence[ast.expr], unit: bool) -> ast.expr:
    flat: list[ast.expr] = []
    for part in parts:
        if isinstance(part, ast.BoolOp) and type(part.op) is type(op):
            flat.extend(part.values)
        elif isinstance(part, ast.Constant) and isinstance(part.value, bool):
            if part.value is unit:
                continue  # the identity element
            return ast.Constant(value=not unit)  # the absorbing element
        else:
            flat.append(part)
    if not flat:
        return ast.Constant(value=unit)
    if len(flat) == 1:
        return flat[0]
    return ast.BoolOp(op=op, values=flat)


def and_(*parts: ast.expr) -> ast.expr:
    return _boolop(ast.And(), parts, True)


def or_(*parts: ast.expr) -> ast.expr:
    return _boolop(ast.Or(), parts, False)


def type_is(value: ast.expr, type_name: str) -> ast.Compare:
    """`type(value) is <type_name>`: the plain-data discipline (P9)."""
    return is_(call(load("type"), value), load(type_name))


def assign(name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(targets=[store(name)], value=value)


def aug_add(name: str, value: ast.expr) -> ast.AugAssign:
    return ast.AugAssign(target=store(name), op=ast.Add(), value=value)


def if_(
    test: ast.expr, body: Sequence[ast.stmt], orelse: Sequence[ast.stmt] = ()
) -> ast.If:
    return ast.If(test=test, body=list(body), orelse=list(orelse))


def for_(target: str, iterable: ast.expr, body: Sequence[ast.stmt]) -> ast.For:
    return ast.For(target=store(target), iter=iterable, body=list(body), orelse=[])


def return_(value: ast.expr) -> ast.Return:
    return ast.Return(value=value)


def expr_stmt(value: ast.expr) -> ast.Expr:
    return ast.Expr(value=value)


def function(
    name: str, params: Sequence[str], body: Sequence[ast.stmt]
) -> ast.FunctionDef:
    return ast.FunctionDef(
        name=name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=list(body),
        decorator_list=[],
        returns=None,
        type_params=[],
    )


def tuple_(elts: Iterable[ast.expr]) -> ast.Tuple:
    return ast.Tuple(elts=list(elts), ctx=ast.Load())


def starred_append(name: str, value: ast.expr) -> ast.Tuple:
    """`(*name, value)`: the dynamic-scope tuple extended by one entry."""
    return ast.Tuple(
        elts=[ast.Starred(value=load(name), ctx=ast.Load()), value], ctx=ast.Load()
    )


def module(body: Sequence[ast.stmt]) -> ast.Module:
    tree = ast.Module(body=list(body), type_ignores=[])
    return ast.fix_missing_locations(tree)


def frozenset_literal(values: Sequence[JsonValue]) -> ast.expr:
    """`frozenset((...))` over sorted members: never a set display, whose
    unparsed order would depend on the hash seed."""
    return call(load("frozenset"), tuple_(const(v) for v in values))
