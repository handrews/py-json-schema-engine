# Module assembly (M6): one flat function per reachable static unit,
# `u{N}(v, d, s)`, closing over the exec namespace's runtime; hoisted
# regexes and constants first; `validate(v)` last. Only functions that
# something calls are emitted (an inlined unit has none), so the module is
# exactly the reachable static graph.
#
# Dependency direction: imports `emit`, `context`, `units`, `body`, and the
# planner. The public API and the standalone emitter import this.

import ast
from collections.abc import Sequence
from dataclasses import dataclass

from json_schema_engine.compiler import emit as e
from json_schema_engine.compiler.plan import CompilationPlan, PlannedUnit, schema_value
from json_schema_engine.compiler.serialize.body import edges_of, unit_statements
from json_schema_engine.compiler.serialize.context import (
    BodyContext,
    Flags,
    FunctionContext,
    ModuleContext,
    SerializeError,
)
from json_schema_engine.compiler.serialize.units import lower_unit, uses_object_test
from json_schema_engine.core.registry import SchemaRegistry

__all__ = ["Flags", "SerializeError", "Serialized", "serialize_plan"]


@dataclass(frozen=True, slots=True)
class Serialized:
    """The emitted functions and hoists, before a mode-specific prologue."""

    # `rN = ...` bindings the prologue must provide, in name order.
    regexes: tuple[tuple[str, str], ...]  # (name, source)
    constants: tuple[tuple[str, ast.expr], ...]
    functions: tuple[ast.FunctionDef, ...]
    validate: ast.FunctionDef
    vocabulary: frozenset[str]


DEFAULT_FLAGS = Flags()


def serialize_plan(
    plan: CompilationPlan, registry: SchemaRegistry, flags: Flags = DEFAULT_FLAGS
) -> Serialized:
    module = ModuleContext(plan, registry, flags)
    root = plan.units[plan.root_key]
    functions: list[ast.FunctionDef] = []

    root_call: ast.expr
    if root.kind == "interpreted":
        root_call = e.call(
            e.load(e.H_FRAG),
            e.subscript(e.load(e.TARGETS), e.const(module.target_slot(root.key))),
            e.load(e.VALUE),
            e.tuple_(()),
            e.const(0),
        )
    elif isinstance(root.ref.node, bool):
        root_call = ast.Constant(value=root.ref.node)
    else:
        root_call = e.call(
            e.load(module.function_name(root.key)),
            e.load(e.VALUE),
            e.const(0),
            e.tuple_(()),
        )
    while module.pending:
        key = module.pending.pop(0)
        functions.append(_emit_function(module, plan.units[key]))
    validate = e.function(
        module.names.name(e.VALIDATE),
        [e.VALUE],
        [
            ast.Try(
                body=[e.return_(root_call)],
                handlers=[
                    ast.ExceptHandler(
                        type=e.load("RecursionError"),
                        name=None,
                        body=[
                            ast.Raise(
                                exc=e.call(
                                    e.load(e.DEPTH_ERROR),
                                    e.const(
                                        "compiled evaluation exceeded the "
                                        "interpreter's stack; reduce nesting or "
                                        "lower max_depth"
                                    ),
                                ),
                                cause=ast.Constant(value=None),
                            )
                        ],
                    )
                ],
                orelse=[],
                finalbody=[],
            )
        ],
    )
    for name in (
        "RecursionError",
        "len",
        "range",
        "type",
        "frozenset",
        "dict",
        "list",
        "str",
        "int",
        "float",
        "bool",
    ):
        module.names.name(name)
    return Serialized(
        regexes=tuple(
            sorted(((n, s) for s, n in module.regexes.items()), key=lambda p: p[0])
        ),
        constants=tuple(module.constants),
        functions=tuple(functions),
        validate=validate,
        vocabulary=frozenset(module.names.vocabulary),
    )


def _emit_function(module: ModuleContext, unit: PlannedUnit) -> ast.FunctionDef:
    if unit.kind != "static" or isinstance(unit.ref.node, bool):
        raise SerializeError(f"no function for a non-static unit {unit.key}")
    fn = FunctionContext(module, unit)
    body = BodyContext(fn, unit, schema_value(unit.ref), e.VALUE, edges_of(unit))
    ir = lower_unit(module.registry, unit)
    stmts: list[ast.stmt] = []
    if unit.reaches_interpreted:
        # Dynamic scope (D8): only units on a path to an island thread it.
        stmts.append(
            e.assign(e.SCOPE, e.starred_append(e.SCOPE, e.const(unit.ref.base_uri)))
        )
    if uses_object_test(ir):
        body.guard = module.names.fresh("g")
        stmts.append(e.assign(body.guard, e.type_is(e.load(e.VALUE), "dict")))
    stmts.extend(unit_statements(body, ir))
    stmts.append(e.return_(ast.Constant(value=True)))
    if fn.called_unit:
        # A function that calls no unit or fragment cannot recurse.
        stmts = [
            e.if_(
                e.compare(e.load(e.DEPTH), ast.GtE(), e.load(e.H_MAXD)),
                [e.expr_stmt(e.call(e.load(e.H_DEEP)))],
            ),
            e.aug_add(e.DEPTH, e.const(1)),
            *stmts,
        ]
    return e.function(module.functions[unit.key], [e.VALUE, e.DEPTH, e.SCOPE], stmts)


def assemble(prologue: Sequence[ast.stmt], serialized: Serialized) -> ast.Module:
    """A complete module: the mode's prologue, hoisted constants, the unit
    functions, and `validate`."""
    body: list[ast.stmt] = [*prologue]
    body.extend(e.assign(name, expr) for name, expr in serialized.constants)
    body.extend(serialized.functions)
    body.append(serialized.validate)
    return e.module(body)
