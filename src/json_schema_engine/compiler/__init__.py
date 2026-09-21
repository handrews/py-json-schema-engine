# The compiler tier's public surface (DESIGN.md D1, D9, D10; M6): compile a
# registered schema into a flag validator, or emit it as a standalone
# module. The interpreter is the reference semantics; any subschema the
# compiler cannot emit trampolines back into it, so an artifact is exactly
# as correct as `Engine.evaluate` and never less complete — tier choice is
# a performance decision, not a semantic one.
#
# An artifact binds a snapshot of the schema and dialect registries taken
# at compile time: compile after registration is complete.
#
# Dependency direction: imports the planner, serializer, runtime, and
# instantiation modules, plus core's engine façade. `json_schema_engine.core`
# never imports this package (P5).

import ast
from collections.abc import Callable
from dataclasses import dataclass

from json_schema_engine.compiler import emit as e
from json_schema_engine.compiler.errors import (
    FormatTableError,
    StandaloneUnsupportedError,
)
from json_schema_engine.compiler.plan import (
    CompilationExplanation,
    CompilationPlan,
    DynamicResolution,
    FallbackCause,
    PlannedApplication,
    PlannedUnit,
    ResolvedDynamicSite,
    build_plan,
    build_plan_over,
    explain_compilation,
)
from json_schema_engine.compiler.runtime import make_namespace, make_runtime
from json_schema_engine.compiler.runtime_compile import instantiate
from json_schema_engine.compiler.serialize import Flags, assemble, serialize_plan
from json_schema_engine.compiler.standalone import emit_standalone
from json_schema_engine.core.engine import Engine
from json_schema_engine.core.json_model import JsonValue

__all__ = [
    "CompilationExplanation",
    "CompilationPlan",
    "CompiledValidator",
    "DynamicResolution",
    "FallbackCause",
    "FormatTableError",
    "PlannedApplication",
    "PlannedUnit",
    "ResolvedDynamicSite",
    "StandaloneUnsupportedError",
    "build_plan",
    "compile_validator",
    "emit_standalone",
    "explain_compilation",
]


@dataclass(frozen=True, slots=True)
class CompiledValidator:
    """A compiled flag validator: `validate(instance) -> bool`, the plan it
    was built from, the emitted module, and its source (for diagnostics
    and goldens; `ast.unparse` of `module`)."""

    validate: Callable[[JsonValue], bool]
    plan: CompilationPlan
    module: ast.Module
    source: str


def compile_validator(
    engine: Engine,
    schema_uri: str,
    *,
    max_depth: int | None = None,
    conservative: bool = False,
) -> CompiledValidator:
    """Compile a registered root schema into a verdict-only validator.

    `max_depth` defaults to the engine's; `conservative` turns the
    emitter's optimizations off (no inlining, no set specialization) — the
    differential fuzzer referees both configurations.
    """
    registry = engine.schemas.snapshot()
    plan = build_plan_over(registry, schema_uri)
    flags = Flags(inline=not conservative, specialize_sets=not conservative)
    serialized = serialize_plan(plan, registry, flags)
    prologue = [
        e.assign(
            name,
            e.subscript(e.attr(e.load(e.RUNTIME), "re"), e.const(source)),
        )
        for name, source in serialized.regexes
    ]
    prologue.extend(
        e.assign(
            name,
            e.subscript(e.attr(e.load(e.RUNTIME), "formats"), e.const(format_name)),
        )
        for name, format_name in serialized.formats
    )
    module = assemble(prologue, serialized)
    budget = engine.max_depth if max_depth is None else max_depth
    runtime = make_runtime(
        registry,
        engine.regex_cache,
        plan.patterns,
        budget,
        formats=plan.formats,
        format_table=engine.formats,
        coverage_ids=plan.coverage_ids,
    )
    validate = instantiate(
        module, make_namespace(runtime, [t.ref for t in plan.targets])
    )
    return CompiledValidator(validate, plan, module, ast.unparse(module))
