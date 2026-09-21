# The public façade (DESIGN.md §2, D6, D7/P4, D20, P3): one `Engine` owns a
# dialect registry, a schema registry, and a regex cache, and turns
# evaluation options into a `Result`.
#
# Dependency direction: imports everything below it in `core`. Nothing in
# `core` imports this module.

from collections.abc import Sequence

from json_schema_engine.core.dialect import DialectRegistry
from json_schema_engine.core.errors import MaxDepthExceededError
from json_schema_engine.core.evaluator import run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import DIALECT_2020_12
from json_schema_engine.core.keywords.dialect2020 import register_standard_dialects
from json_schema_engine.core.loader import Loader
from json_schema_engine.core.output import AnnotationsOption, RenderInput
from json_schema_engine.core.records import render_annotation, render_error
from json_schema_engine.core.regex import (
    RegexBackend,
    RegexCache,
    RegexDialect,
)
from json_schema_engine.core.regex import reject_unsafe_regex as _screen_unsafe
from json_schema_engine.core.registry import DEFAULT_MAX_DEPTH, SchemaRegistry
from json_schema_engine.core.result import (
    OutputFormat,
    Result,
    assemble_result,
    resolve_output_demand,
)


def _record_nothing(keyword_name: str, vocabulary_uri: str | None) -> bool:
    return False


class Engine:
    """A JSON Schema engine: registries, evaluation, and output (D6).

    Construct through `create_engine`. Registration is synchronous and
    local; `load_schema` additionally drains external references through
    the loaders (P4).
    """

    def __init__(
        self,
        *,
        default_dialect: str = DIALECT_2020_12,
        loaders: Sequence[Loader] = (),
        regex_dialect: RegexDialect = "ecma262",
        regex_backend: RegexBackend = "re",
        reject_unsafe_regex: bool = False,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.dialects = DialectRegistry()
        register_standard_dialects(self.dialects)
        self.schemas = SchemaRegistry(
            self.dialects, default_dialect, max_depth=max_depth
        )
        self._loaders = tuple(loaders)
        self._regex = RegexCache(regex_dialect, regex_backend)
        self._max_depth = max_depth
        # Installed after the trusted built-ins register (there are none in
        # M1, but the order is the D20 contract): every pattern a caller's
        # schema declares is compiled here, so an untranslatable or unsafe
        # one fails at registration with its location.
        should_reject = reject_unsafe_regex

        def screen(pattern: str, location: str) -> None:
            self._regex.compile(pattern, schema_location=location)
            if should_reject:
                _screen_unsafe(pattern, location)

        self.schemas.on_regex = screen

    # --- registration ----------------------------------------------------

    def register_schema(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None = None,
    ) -> str:
        """Register a schema document locally and return its canonical URI.

        No references are followed; use `load_schema` for that.
        """
        try:
            return self.schemas.register(schema, retrieval_uri, dialect_uri)
        except RecursionError:
            raise MaxDepthExceededError(
                "schema nesting exceeded the interpreter's stack "
                f"(max_depth={self._max_depth})"
            ) from None

    def load_schema(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None = None,
    ) -> str:
        """Register a document and load every resource it references (P4)."""
        uri = self.register_schema(schema, retrieval_uri, dialect_uri)
        self._drain()
        return uri

    def load(self, uri: str) -> str:
        """Load and register a resource by URI through the loaders."""
        if not self.schemas.has(uri):
            self._fetch(uri)
        self._drain()
        return uri

    def _drain(self) -> None:
        # Each registration may reveal new references; a miss is left for
        # evaluation to report if the reference is actually followed.
        while missing := self.schemas.take_unresolved():
            for uri in missing:
                self._fetch(uri)

    def _fetch(self, uri: str) -> bool:
        for loader in self._loaders:
            loaded = loader(uri)
            if loaded is not None:
                self.register_schema(loaded.value, loaded.uri)
                return True
        return False

    # --- evaluation ------------------------------------------------------

    def evaluate(
        self,
        schema_uri: str,
        instance: JsonValue,
        *,
        output: str | OutputFormat = OutputFormat.FLAG,
        annotations: AnnotationsOption = False,
        error_params: bool = False,
        verbose: bool = False,
        trace: bool = False,
        positions: bool = False,
    ) -> Result:
        """Evaluate `instance` against a registered schema (D6)."""
        demand = resolve_output_demand(
            output=output,
            annotations=annotations,
            error_params=error_params,
            verbose=verbose,
            trace=trace,
            positions=positions,
        )
        # The demand's predicate is the record-time gate (D5); `None` there
        # means nothing was selected, which the evaluator spells as a
        # predicate that refuses everything (its own `None` is "no elision",
        # reserved for tracing).
        should_record = (
            demand.annotations if demand.annotations is not None else _record_nothing
        )
        valid, state = run_evaluation(
            self.schemas,
            schema_uri,
            instance,
            compile_regex=self._regex.compile,
            should_record=should_record,
            max_depth=self._max_depth,
        )
        if demand.format is OutputFormat.FLAG:
            return Result(valid, None, None, None)

        errors = [
            render_error(e, error_params=demand.error_params) for e in state.errors
        ]
        annotation_records = state.root_annotations if valid else []
        render_input = RenderInput(
            valid=valid,
            errors=errors,
            annotations=[render_annotation(a) for a in annotation_records],
            root_location=self.schemas.root_ref(schema_uri).location,
            error_keywords=[e.keyword_name for e in state.errors],
            annotation_keywords=[a.keyword_name for a in annotation_records],
        )
        return assemble_result(demand, render_input, annotations)


def create_engine(
    *,
    default_dialect: str = DIALECT_2020_12,
    loaders: Sequence[Loader] = (),
    regex_dialect: RegexDialect = "ecma262",
    regex_backend: RegexBackend = "re",
    reject_unsafe_regex: bool = False,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Engine:
    """Create an engine with the built-in dialects registered."""
    return Engine(
        default_dialect=default_dialect,
        loaders=loaders,
        regex_dialect=regex_dialect,
        regex_backend=regex_backend,
        reject_unsafe_regex=reject_unsafe_regex,
        max_depth=max_depth,
    )
