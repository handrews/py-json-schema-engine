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
from typing import Literal

from json_schema_engine.compiler.emit import (
    CHANNEL,
    CURSOR,
    DEPTH_ERROR,
    EVALUATOR_NAMES,
    H_COVI,
    H_COVN,
    H_DEEP,
    H_DUP,
    H_EQ,
    H_FRAG,
    H_FRAGC,
    H_MAXD,
    H_MOF,
    PATH,
    RUNTIME,
    TARGETS,
    Names,
)
from json_schema_engine.compiler.plan import CompilationPlan, PlannedUnit
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.output import RecordPredicate
from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.registry import SchemaRegistry

# (behavior_id, keyword_name, vocabulary_uri, schema_ref): a record's
# identity, hoisted once per keyword occurrence in evaluator mode (M9).
type Site = tuple[str | None, str | None, str | None, SchemaRef]


class SerializeError(Exception):
    """A plan/lowering mismatch the serializer refuses to paper over."""


@dataclass(frozen=True, slots=True)
class Flags:
    """Emitter optimizations; `conservative` artifacts turn them off so the
    differential fuzzer referees both configurations. `mode` selects the
    flag validator (verdict only) or the evaluator (records and trace on a
    shared `EvalState`, M9), which never inlines."""

    inline: bool = True
    specialize_sets: bool = True
    mode: Literal["flag", "evaluator"] = "flag"
    inline_stack_cap: int = 32
    # CPython refuses more than 20 statically nested blocks (`for`/`while`/
    # `try`/`with`; `if` does not count). Inlining stops short of it.
    loop_cap: int = 16


# (keyword, sibling, ref, resolution, path): the join between a keyword's
# `analyze()` applications and its lowered applies. `resolution` keeps a
# `$dynamicRef` and a `$ref` with the same string apart.
type EdgeKey = tuple[str, str | None, str | None, str | None, tuple[str | int, ...]]


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
    # Evaluator mode (M9): the record-time selection (static elision of
    # ruled-out annotations; `None` records nothing) and the site table.
    record: RecordPredicate | None = None
    sites: list[tuple[str, Site]] = field(default_factory=list[tuple[str, Site]])
    _site_names: dict[tuple[str, str | None], str] = field(
        default_factory=dict[tuple[str, str | None], str]
    )

    @property
    def evaluator(self) -> bool:
        return self.flags.mode == "evaluator"

    def site_name(self, unit_key: str, keyword: str | None, site: Site) -> str:
        """The hoisted `xN` holding a keyword occurrence's (or unit's) site."""
        key = (unit_key, keyword)
        name = self._site_names.get(key)
        if name is None:
            name = self.names.fresh("x")
            self._site_names[key] = name
            self.sites.append((name, site))
        return name

    def __post_init__(self) -> None:
        for fixed in (
            H_EQ,
            H_MOF,
            H_DUP,
            H_FRAG,
            H_FRAGC,
            H_COVN,
            H_COVI,
            H_DEEP,
            H_MAXD,
            RUNTIME,
            TARGETS,
            DEPTH_ERROR,
            CHANNEL,
            *EVALUATOR_NAMES,
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
    # Its behavior id: the producer identity a `Produce` records under.
    behavior_id: str = ""
    # The coverage channel variable when this body's function takes one
    # (a tracked or region unit, M9); `None` elides every production.
    channel: str | None = None
    # A tracked unit's entry mark: it folds only what its own region
    # produced (`ev[mark:]`), so nesting inside another region is sound.
    channel_mark: str | None = None
    # Coverage-fold bindings rendered so far -> which half they hold.
    folds: dict[int, str] = field(default_factory=dict[int, str])
    # Evaluator mode (M9): the variables holding this body's path node and
    # cursor, the current keyword's hoisted site, and one verdict slot per
    # non-structural present keyword (a sibling apply writes its sibling's).
    path: str = PATH
    cursor: str = CURSOR
    site: str = ""
    slots: dict[str, str] = field(default_factory=dict[str, str])

    @property
    def evaluator(self) -> bool:
        return self.fn.module.evaluator

    @property
    def produce_live(self) -> bool:
        """Whether the current keyword's productions reach a consumer."""
        return (
            self.channel is not None
            and self.behavior_id in self.fn.module.plan.coverage_ids
        )

    def binding_name(self, binding: int) -> str:
        name = self.bindings.get(binding)
        if name is None:
            name = self.fn.module.names.fresh("b")
            self.bindings[binding] = name
        return name
