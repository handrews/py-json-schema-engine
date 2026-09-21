# Bench subjects (M6 Step 5): each subject's `prepare(schema)` builds
# whatever cold artifact that subject needs (a registered jse engine, a
# compiled jse validator, an imported standalone module, a
# fastjsonschema-compiled function, a jsonschema validator instance) and
# returns a plain `validate(instance) -> bool` callable. The harness times
# `prepare` itself as the "compile" partition and the returned callable as
# the hot/valid/invalid partitions.
#
# IP POLICY (DESIGN.md D15): fastjsonschema and jsonschema are executed
# here as competitors only — never read, never ported. Their imports are
# isolated behind `# type: ignore` (neither ships inline type stubs) so
# the rest of this module, and the rest of the bench package, stays
# strictly typed.
#
# Format validation is disabled/absent for every subject here — none of
# these schemas declare a `format` assertion, and no subject opts into one.

from __future__ import annotations

import importlib.util
import itertools
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import fastjsonschema  # type: ignore[import-untyped]
import jsonschema  # type: ignore[import-untyped]

from json_schema_engine.compiler import compile_validator, emit_standalone
from json_schema_engine.core import JsonValue, create_engine

Validate = Callable[[JsonValue], bool]

_uri_counter = itertools.count()


def _fresh_uri() -> str:
    # Each `prepare` call registers into its own fresh engine, but the
    # counter still keeps every generated retrieval URI distinct across
    # calls for clarity in error messages and tracebacks.
    return f"https://bench.example/subject-{next(_uri_counter)}"


@dataclass(frozen=True, slots=True)
class Subject:
    """A competitor in the bench: `prepare(schema)` builds its cold
    artifact and returns `validate(instance) -> bool`."""

    name: str
    prepare: Callable[[JsonValue], Validate]


def _jse_interpreter_flag(schema: JsonValue) -> Validate:
    engine = create_engine()
    uri = engine.register_schema(schema, _fresh_uri())
    return lambda instance: engine.evaluate(uri, instance).valid


def _jse_compiled_flag(schema: JsonValue) -> Validate:
    engine = create_engine()
    uri = engine.register_schema(schema, _fresh_uri())
    return compile_validator(engine, uri).validate


def _jse_standalone(schema: JsonValue) -> Validate:
    """Emit a standalone module and import it from a temp file.

    May raise `StandaloneUnsupportedError` (schema needs the interpreter
    at evaluation time, or the engine's regex backend is not `re`) — the
    harness catches this and records an exclusion instead of timing the
    subject.
    """
    engine = create_engine()
    uri = engine.register_schema(schema, _fresh_uri())
    source = emit_standalone(engine, uri)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as handle:
        handle.write(source)
        module_path = Path(handle.name)
    spec = importlib.util.spec_from_file_location(
        f"json_schema_engine.bench._standalone_{next(_uri_counter)}", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load standalone module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Validate, module.validate)


def _fastjsonschema(schema: JsonValue) -> Validate:
    # fastjsonschema has no inline types; pyright's best-effort inference
    # of its `exec`-generated `compile` is worse than useless (it infers
    # nonsense unions from the generated code's local names). Go through
    # an `Any`-typed alias first so the attribute access itself is not
    # inferred (and flagged) before the cast can take effect.
    untyped: Any = fastjsonschema
    compile_fn = cast("Callable[[Any], Callable[[Any], object]]", untyped.compile)
    compiled = compile_fn(schema)
    exceptions = cast(type[Exception], untyped.JsonSchemaException)

    def validate(instance: JsonValue) -> bool:
        try:
            compiled(instance)
        except exceptions:
            return False
        return True

    return validate


def _jsonschema(schema: JsonValue) -> Validate:
    validator_cls = cast("Callable[[Any], Any]", jsonschema.Draft202012Validator)
    validator = validator_cls(schema)
    return cast(Validate, validator.is_valid)


SUBJECTS: list[Subject] = [
    Subject("jse interpreter flag", _jse_interpreter_flag),
    Subject("jse compiled flag", _jse_compiled_flag),
    Subject("jse standalone", _jse_standalone),
    Subject("fastjsonschema", _fastjsonschema),
    Subject("jsonschema", _jsonschema),
]
