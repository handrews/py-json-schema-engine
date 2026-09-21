# Shared helper for per-keyword lowering tests (M6): a recording
# `LoweringContext` that captures the IR a keyword's `lower()` emits, with
# an optional static coverage for consumer keywords.

from collections.abc import Mapping
from dataclasses import dataclass, field

from json_schema_engine.core.dialect import KeywordBehavior
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.lowering import (
    INSTANCE,
    Expr,
    StaticCoverage,
    Stmt,
)


@dataclass(slots=True)
class RecordingContext:
    """A `LoweringContext` that records emitted statements."""

    _schema: Mapping[str, JsonValue]
    _coverage: StaticCoverage | None = None
    _tracked: bool = False
    stmts: list[Stmt] = field(default_factory=list[Stmt])
    next_binding: int = 0

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


def lower(
    behavior: KeywordBehavior,
    value: JsonValue,
    schema: Mapping[str, JsonValue] | None = None,
    coverage: StaticCoverage | None = None,
    tracked: bool = False,
) -> tuple[Stmt, ...]:
    """The IR `behavior.lower` emits for `value` inside `schema`; `tracked`
    is the planner's runtime-coverage decision for a consumer (M9)."""
    assert behavior.lower is not None, "behavior has no lower()"
    ctx = RecordingContext(schema if schema is not None else {}, coverage, tracked)
    behavior.lower(value, ctx)
    return tuple(ctx.stmts)
