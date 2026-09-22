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
from json_schema_engine.compiler.runtime_compile import instantiate, instantiate_entry
from json_schema_engine.compiler.serialize import Flags, assemble, serialize_plan
from json_schema_engine.compiler.standalone import emit_standalone
from json_schema_engine.core.channel_ops import cut_annotations
from json_schema_engine.core.engine import Engine, assemble_evaluation
from json_schema_engine.core.evaluator import EvalState
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.output import AnnotationsOption, make_record_predicate
from json_schema_engine.core.result import OutputFormat, Result, resolve_output_demand

__all__ = [
    "CompilationExplanation",
    "CompilationPlan",
    "CompiledEvaluator",
    "CompiledValidator",
    "DynamicResolution",
    "FallbackCause",
    "FormatTableError",
    "PlannedApplication",
    "PlannedUnit",
    "ResolvedDynamicSite",
    "StandaloneUnsupportedError",
    "build_plan",
    "compile_evaluator",
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


def _record_nothing(keyword_name: str, vocabulary_uri: str | None) -> bool:
    return False


@dataclass(frozen=True, slots=True)
class CompiledEvaluator:
    """A compiled evaluator (M9): `evaluate(instance, *, output, error_params,
    verbose, trace, positions) -> Result`, the same result `Engine.evaluate`
    returns for that demand. The annotation selection is fixed at compile
    time (ruled-out annotations are never recorded); every other output
    control is chosen per evaluation. Records and the application trace
    are written to a core `EvalState` the artifact shares with any
    interpreted island, and rendered by the interpreter's own renderers.
    """

    evaluate: Callable[..., Result]
    plan: CompilationPlan
    module: ast.Module
    source: str
    annotations: AnnotationsOption


def compile_evaluator(
    engine: Engine,
    schema_uri: str,
    *,
    annotations: AnnotationsOption = False,
    max_depth: int | None = None,
    conservative: bool = False,
) -> CompiledEvaluator:
    """Compile a registered root schema into an evaluator serving every
    output format but the verdict-only `flag`.

    Every consumer is tracked at runtime (a static coverage models only
    the parent-success path, and an evaluator continues past a failed
    sibling), nothing inlines, and every branch runs (§4 rule 7), so the
    errors, annotations, dropped records, and trace equal the interpreter's.
    """
    registry = engine.schemas.snapshot()
    plan = build_plan_over(registry, schema_uri, track_all=True)
    flags = Flags(inline=False, specialize_sets=not conservative, mode="evaluator")
    record = make_record_predicate(annotations)
    serialized = serialize_plan(plan, registry, flags, record=record)
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
    prologue.extend(
        e.assign(name, e.subscript(e.load(e.SITES), e.const(index)))
        for index, (name, _) in enumerate(serialized.sites)
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
    entry = instantiate_entry(
        module,
        make_namespace(
            runtime,
            [t.ref for t in plan.targets],
            [site for _, site in serialized.sites],
        ),
        e.EVALUATE,
    )
    root_location = registry.root_ref(schema_uri).location
    compile_regex = engine.regex_cache.compile
    should_record = record if record is not None else _record_nothing

    def evaluate(
        instance: JsonValue,
        *,
        output: str | OutputFormat = OutputFormat.LIST,
        error_params: bool = False,
        verbose: bool | None = None,
        trace: bool = False,
        positions: bool = False,
    ) -> Result:
        demand = resolve_output_demand(
            output=output,
            annotations=annotations,
            error_params=error_params,
            verbose=verbose,
            trace=trace,
            positions=positions,
        )
        state = EvalState(
            registry,
            compile_regex,
            should_record=should_record,
            max_depth=budget,
            tracing=demand.tracing,
        )
        valid = bool(entry(instance, state))
        if not valid:
            # The root application's records never merge (rule 3).
            cut_annotations(state, 0)
        return assemble_evaluation(
            state,
            valid,
            demand,
            annotations,
            root_location,
            trace,
            locate=engine.locate if positions else None,
        )

    return CompiledEvaluator(evaluate, plan, module, ast.unparse(module), annotations)
