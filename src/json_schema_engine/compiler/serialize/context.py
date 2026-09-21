# Serializer state (M6): the module being assembled (requested unit
# functions, hoisted regexes and constants), the function being emitted
# (loop nesting, inline stack, whether it calls a unit), and the unit body
# being serialized (its instance variable, object guard, binding names, and
# its planned edges keyed the way an `Apply` names them).
#
# Dependency direction: imports the planner, `emit`, and core's IR types.
# The other serializer modules import this.

import ast
from collections.abc import Mapping
from dataclasses import dataclass, field

from json_schema_engine.compiler.emit import (
    DEPTH_ERROR,
    H_DEEP,
    H_DUP,
    H_EQ,
    H_FRAG,
    H_MAXD,
    H_MOF,
    RUNTIME,
    TARGETS,
    Names,
)
from json_schema_engine.compiler.plan import CompilationPlan, PlannedUnit
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.registry import SchemaRegistry


class SerializeError(Exception):
    """A plan/lowering mismatch the serializer refuses to paper over."""


@dataclass(frozen=True, slots=True)
class Flags:
    """Emitter optimizations; `conservative` artifacts turn them off so the
    differential fuzzer referees both configurations."""

    inline: bool = True
    specialize_sets: bool = True
    inline_stack_cap: int = 32
    # CPython refuses more than 20 statically nested blocks (`for`/`while`/
    # `try`/`with`; `if` does not count). Inlining stops short of it.
    loop_cap: int = 16


type EdgeKey = tuple[str, str | None, str | None, tuple[str | int, ...]]


@dataclass(slots=True)
class ModuleContext:
    plan: CompilationPlan
    registry: SchemaRegistry
    flags: Flags
    names: Names = field(default_factory=Names)
    # unit key -> function name, in request order (root first).
    functions: dict[str, str] = field(default_factory=dict[str, str])
    pending: list[str] = field(default_factory=list[str])
    # regex source -> hoisted name
    regexes: dict[str, str] = field(default_factory=dict[str, str])
    # format name -> hoisted name (M7)
    formats: dict[str, str] = field(default_factory=dict[str, str])
    # hoisted constant containers and sets: name -> expression
    constants: list[tuple[str, ast.expr]] = field(
        default_factory=list[tuple[str, ast.expr]]
    )
    inlined: set[str] = field(default_factory=set[str])

    def __post_init__(self) -> None:
        for fixed in (
            H_EQ,
            H_MOF,
            H_DUP,
            H_FRAG,
            H_DEEP,
            H_MAXD,
            RUNTIME,
            TARGETS,
            DEPTH_ERROR,
        ):
            self.names.name(fixed)

    def function_name(self, key: str) -> str:
        """The function emitted for a static unit, requested on first use."""
        name = self.functions.get(key)
        if name is None:
            name = self.names.fresh("u")
            self.functions[key] = name
            self.pending.append(key)
        return name

    def regex_name(self, source: str) -> str:
        name = self.regexes.get(source)
        if name is None:
            name = self.names.fresh("r")
            self.regexes[source] = name
        return name

    def format_name(self, name: str) -> str:
        hoisted = self.formats.get(name)
        if hoisted is None:
            hoisted = self.names.fresh("fmt")
            self.formats[name] = hoisted
        return hoisted

    def hoist(self, expr: ast.expr) -> str:
        name = self.names.fresh("k")
        self.constants.append((name, expr))
        return name

    def target_slot(self, key: str) -> int:
        for index, unit in enumerate(self.plan.targets):
            if unit.key == key:
                return index
        raise SerializeError(f"no target slot for interpreted unit {key}")


@dataclass(slots=True)
class FunctionContext:
    module: ModuleContext
    unit: PlannedUnit
    loop_depth: int = 0
    inline_stack: list[str] = field(default_factory=list[str])
    # Set when the body calls a unit function or the trampoline: only such
    # functions can recurse and need the depth guard.
    called_unit: bool = False


@dataclass(slots=True)
class BodyContext:
    """One unit's body inside one function: its own for a unit function,
    an inlined child's for an inline site."""

    fn: FunctionContext
    unit: PlannedUnit
    schema: Mapping[str, JsonValue]
    # The variable holding this body's instance.
    value: str
    edges: dict[EdgeKey, str]
    # Object-guard variable for `value`, when the body tests it.
    guard: str | None = None
    # local binding id -> emitted name
    bindings: dict[int, str] = field(default_factory=dict[int, str])
    # Bindings introduced by a key sweep (always strings: no type guard needed).
    key_bindings: set[int] = field(default_factory=set[int])
    # The keyword whose statements are being serialized (edge lookup).
    keyword: str = ""

    def binding_name(self, binding: int) -> str:
        name = self.bindings.get(binding)
        if name is None:
            name = self.fn.module.names.fresh("b")
            self.bindings[binding] = name
        return name
