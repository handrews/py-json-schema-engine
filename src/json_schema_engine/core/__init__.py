"""json-schema-engine: a spec-complete, annotation-first JSON Schema engine.

The interpreter tier (DESIGN.md D1). Create an engine, register or load a
schema, evaluate an instance::

    from json_schema_engine.core import create_engine

    engine = create_engine()
    uri = engine.register_schema({"type": "object"}, "https://example.com/s")
    result = engine.evaluate(uri, {})
    assert result.valid
"""

from json_schema_engine.core.dialect import (
    AnalyzeContext,
    DependencyView,
    Dialect,
    DialectRegistry,
    KeywordBehavior,
    KeywordContext,
    Phase,
    StaticFacts,
)
from json_schema_engine.core.engine import Engine, create_engine
from json_schema_engine.core.errors import (
    InfiniteLoopError,
    InvalidSchemaError,
    JsonSchemaEngineError,
    KeywordContractError,
    MaxDepthExceededError,
    OutputOptionsError,
    UndeclaredConsumptionError,
    UndeclaredProductionError,
    UnknownDialectError,
    UnknownKeywordError,
    UnresolvableReferenceError,
    UnsafeRegexError,
    UnsupportedPatternError,
)
from json_schema_engine.core.json_model import JsonType, JsonValue, json_equal
from json_schema_engine.core.keywords._ids import DIALECT_2020_12
from json_schema_engine.core.loader import LoadedDocument, Loader
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationsOption,
    AnnotationUnit,
    BasicOutputDocument,
    ErrorUnit,
    ListOutputDocument,
    OutputUnit,
)
from json_schema_engine.core.regex import (
    RegexBackend,
    RegexDialect,
    UnsafeRegexReport,
    detect_unsafe_regex,
)
from json_schema_engine.core.result import OutputFormat, Result

__all__ = [
    "DIALECT_2020_12",
    "AnalyzeContext",
    "AnnotationSelection",
    "AnnotationUnit",
    "AnnotationsOption",
    "BasicOutputDocument",
    "DependencyView",
    "Dialect",
    "DialectRegistry",
    "Engine",
    "ErrorUnit",
    "InfiniteLoopError",
    "InvalidSchemaError",
    "JsonSchemaEngineError",
    "JsonType",
    "JsonValue",
    "KeywordBehavior",
    "KeywordContext",
    "KeywordContractError",
    "ListOutputDocument",
    "LoadedDocument",
    "Loader",
    "MaxDepthExceededError",
    "OutputFormat",
    "OutputOptionsError",
    "OutputUnit",
    "Phase",
    "RegexBackend",
    "RegexDialect",
    "Result",
    "StaticFacts",
    "UndeclaredConsumptionError",
    "UndeclaredProductionError",
    "UnknownDialectError",
    "UnknownKeywordError",
    "UnresolvableReferenceError",
    "UnsafeRegexError",
    "UnsafeRegexReport",
    "UnsupportedPatternError",
    "create_engine",
    "detect_unsafe_regex",
    "json_equal",
]
