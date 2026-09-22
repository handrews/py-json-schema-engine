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
    Site,
)
from json_schema_engine.compiler.serialize.units import lower_unit, uses_object_test
from json_schema_engine.core.output import RecordPredicate
from json_schema_engine.core.registry import SchemaRegistry

__all__ = ["Flags", "SerializeError", "Serialized", "Site", "serialize_plan"]


@dataclass(frozen=True, slots=True)
class Serialized:
    """The emitted functions and hoists, before a mode-specific prologue."""

    # `rN = ...` bindings the prologue must provide, in name order.
    regexes: tuple[tuple[str, str], ...]  # (name, source)
    # `fmtN = ...` bindings, in name order (M7).
    formats: tuple[tuple[str, str], ...]  # (name, format name)
    constants: tuple[tuple[str, ast.expr], ...]
    functions: tuple[ast.FunctionDef, ...]
    # The entry function: `validate(v)` for a flag artifact, `evaluate(v, st)`
    # for an evaluator (M9).
    validate: ast.FunctionDef
    vocabulary: frozenset[str]
    # `xN = X[N]` bindings the evaluator prologue must provide (M9).
    sites: tuple[tuple[str, Site], ...] = ()


DEFAULT_FLAGS = Flags()


def serialize_plan(
    plan: CompilationPlan,
    registry: SchemaRegistry,
    flags: Flags = DEFAULT_FLAGS,
    *,
    record: RecordPredicate | None = None,
) -> Serialized:
    """Serialize a plan. `record` (evaluator mode) is the artifact's
    annotation selection, applied statically: a ruled-out annotation is
    never emitted."""
    module = ModuleContext(plan, registry, flags, record=record)
    root = plan.units[plan.root_key]
    functions: list[ast.FunctionDef] = []
    evaluator = module.evaluator

    root_call: ast.expr
    if evaluator:
        located = [ast.Constant(value=None), e.call(e.load(e.H_ROOT), e.load(e.VALUE))]
        if root.kind == "interpreted":
            root_call = e.call(
                e.load(e.H_FRAGE),
                e.load(e.STATE),
                e.subscript(e.load(e.TARGETS), e.const(module.target_slot(root.key))),
                e.tuple_(()),
                e.const(0),
                *located,
                ast.Constant(value=None),
            )
        elif isinstance(root.ref.node, bool):
            root_call = e.call(
                e.load(e.H_TRUE if root.ref.node else e.H_FALSE),
                e.load(e.STATE),
                e.load(module.site_name(root.key, None, (None, None, None, root.ref))),
                *located,
            )
        else:
            root_call = e.call(
                e.load(module.function_name(root.key)),
                e.load(e.VALUE),
                e.const(0),
                e.tuple_(()),
                e.load(e.STATE),
                *located,
                *((e.list_literal(),) if root.takes_channel else ()),
            )
    elif root.kind == "interpreted":
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
            *((e.list_literal(),) if root.takes_channel else ()),
        )
    while module.pending:
        key = module.pending.pop(0)
        functions.append(_emit_function(module, plan.units[key]))
    validate = e.function(
        module.names.name(e.EVALUATE if evaluator else e.VALIDATE),
        [e.VALUE, e.STATE] if evaluator else [e.VALUE],
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
        formats=tuple(
            sorted(((n, f) for f, n in module.formats.items()), key=lambda p: p[0])
        ),
        constants=tuple(module.constants),
        functions=tuple(functions),
        validate=validate,
        vocabulary=frozenset(module.names.vocabulary),
        sites=tuple(module.sites),
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
    if unit.takes_channel:
        body.channel = e.CHANNEL
    if unit.tracked:
        # The unit folds only what its own region produces (M9).
        body.channel_mark = module.names.fresh("m")
        stmts.append(
            e.assign(body.channel_mark, e.call(e.load("len"), e.load(e.CHANNEL)))
        )
    trace_node: str | None = None
    if module.evaluator:
        # Evaluator mode (M9): open the application's trace node first, so
        # islands and children nest under it.
        trace_node = module.names.fresh("t")
        stmts.append(
            e.assign(
                trace_node,
                e.call(
                    e.load(e.H_ENTER),
                    e.load(e.STATE),
                    e.load(
                        module.site_name(unit.key, None, (None, None, None, unit.ref))
                    ),
                    e.load(e.PATH),
                    e.load(e.CURSOR),
                ),
            )
        )
    if uses_object_test(ir):
        body.guard = module.names.fresh("g")
        stmts.append(e.assign(body.guard, e.type_is(e.load(e.VALUE), "dict")))
    stmts.extend(unit_statements(body, ir))
    if module.evaluator:
        assert trace_node is not None
        verdict = module.names.fresh("w")
        stmts.append(
            e.assign(verdict, e.and_(*(e.load(slot) for slot in body.slots.values())))
        )
        pairs: list[ast.expr] = []
        for keyword in ir.keywords:
            if keyword.structural:
                continue
            slot = body.slots.get(keyword.name)
            pairs.append(e.const(keyword.name))
            pairs.append(e.load(slot) if slot else ast.Constant(value=True))
        for name in ir.unknown:
            pairs.append(e.const(name))
            pairs.append(ast.Constant(value=True))
        stmts.append(e.expr_stmt(e.call(e.load(e.H_KWS), e.load(trace_node), *pairs)))
        stmts.append(
            e.expr_stmt(
                e.call(
                    e.load(e.H_EXIT),
                    e.load(e.STATE),
                    e.load(trace_node),
                    e.load(verdict),
                )
            )
        )
        stmts.append(e.return_(e.load(verdict)))
    else:
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
    params = [e.VALUE, e.DEPTH, e.SCOPE]
    if module.evaluator:
        params += [e.STATE, e.PATH, e.CURSOR]
    if unit.takes_channel:
        params.append(e.CHANNEL)
    return e.function(module.functions[unit.key], params, stmts)


def assemble(prologue: Sequence[ast.stmt], serialized: Serialized) -> ast.Module:
    """A complete module: the mode's prologue, hoisted constants, the unit
    functions, and `validate`."""
    body: list[ast.stmt] = [*prologue]
    body.extend(e.assign(name, expr) for name, expr in serialized.constants)
    body.extend(serialized.functions)
    body.append(serialized.validate)
    return e.module(body)
