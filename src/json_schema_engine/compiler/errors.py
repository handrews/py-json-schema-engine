# The compiler tier's own errors (M6), rooted in core's exception so callers
# catching `JsonSchemaEngineError` see them too.
#
# Dependency direction: imports core's errors only.

from json_schema_engine.core.errors import JsonSchemaEngineError


class StandaloneUnsupportedError(JsonSchemaEngineError):
    """`emit_standalone` refused: the schema needs the interpreter at
    evaluation time, or the engine's regex backend cannot be emitted."""
