# The compiled artifact's runtime (M6, D1, D8, P3): the objects the exec
# namespace binds under the emitter's fixed helper names — core's own
# helper functions (never re-implemented), the compiled-pattern table, the
# depth budget, and the one-way trampoline into the interpreter.
#
# Dependency direction: imports core's evaluator seam, cursor, json_model,
# errors, regex, registry, and `emit`'s name constants. The public API
# imports this; the serializer never does.

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn, Protocol

from json_schema_engine.compiler import emit as e
from json_schema_engine.core.cursor import root_cursor
from json_schema_engine.core.errors import MaxDepthExceededError
from json_schema_engine.core.evaluator import evaluate_fragment
from json_schema_engine.core.json_model import (
    JsonValue,
    has_duplicate_items,
    is_multiple_of,
    json_equal,
)
from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.regex import RegexCache
from json_schema_engine.core.registry import SchemaRegistry


class Searchable(Protocol):
    """The backend pattern object emitted code calls directly."""

    def search(self, string: str, /) -> object | None: ...


type Fragment = Callable[[SchemaRef, JsonValue, tuple[str, ...], int], bool]


@dataclass(frozen=True, slots=True)
class Runtime:
    re: Mapping[str, Searchable]
    max_depth: int
    frag: Fragment
    too_deep: Callable[[], NoReturn]


def _record_nothing(keyword_name: str, vocabulary_uri: str | None) -> bool:
    return False


def make_runtime(
    registry: SchemaRegistry,
    regex_cache: RegexCache,
    patterns: Sequence[str],
    max_depth: int,
) -> Runtime:
    """Bind an artifact's runtime to a registry (normally a snapshot)."""
    table: dict[str, Searchable] = {
        source: regex_cache.compile(source).compiled for source in patterns
    }
    compile_regex = regex_cache.compile

    def frag(
        target: SchemaRef, value: JsonValue, scope: tuple[str, ...], depth: int
    ) -> bool:
        # Verdict only: the flag tier records nothing, and the interpreter
        # still sees consumed dependency data inside the fragment.
        return evaluate_fragment(
            registry,
            target,
            root_cursor(value),
            compile_regex=compile_regex,
            dynamic_scope=scope,
            depth=depth,
            max_depth=max_depth,
            should_record=_record_nothing,
        ).valid

    def too_deep() -> NoReturn:
        raise MaxDepthExceededError(
            f"schema application exceeds max_depth ({max_depth})"
        )

    return Runtime(table, max_depth, frag, too_deep)


def make_namespace(runtime: Runtime, targets: Sequence[SchemaRef]) -> dict[str, object]:
    """The globals an emitted module executes in."""
    return {
        e.RUNTIME: runtime,
        e.TARGETS: tuple(targets),
        e.H_EQ: json_equal,
        e.H_MOF: is_multiple_of,
        e.H_DUP: has_duplicate_items,
        e.H_FRAG: runtime.frag,
        e.H_DEEP: runtime.too_deep,
        e.H_MAXD: runtime.max_depth,
        e.DEPTH_ERROR: MaxDepthExceededError,
    }
