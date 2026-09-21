# The public façade (DESIGN.md §2, D6, D7/P4, D20, P3): one `Engine` owns a
# dialect registry, a schema registry, and a regex cache, and turns
# evaluation options into a `Result`.
#
# Dependency direction: imports everything below it in `core`. Nothing in
# `core` imports this module.

from collections.abc import Sequence

from json_schema_engine.core.dialect import (
    DialectRegistry,
    identifiers_2019,
    identifiers_2020,
)
from json_schema_engine.core.errors import (
    MaxDepthExceededError,
    SchemaValidationError,
    UnknownDialectError,
    UnknownVocabularyError,
)
from json_schema_engine.core.evaluator import run_evaluation
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import DIALECT_2020_12, VOCAB_CORE_2019
from json_schema_engine.core.keywords.dialect2020 import register_standard_dialects
from json_schema_engine.core.loader import Loader
from json_schema_engine.core.metaschemas import bundled_metaschemas
from json_schema_engine.core.output import AnnotationsOption, RenderInput
from json_schema_engine.core.records import render_annotation, render_error
from json_schema_engine.core.regex import (
    RegexBackend,
    RegexCache,
    RegexDialect,
)
from json_schema_engine.core.regex import reject_unsafe_regex as _screen_unsafe
from json_schema_engine.core.registry import (
    DEFAULT_MAX_DEPTH,
    SchemaRegistry,
    effective_dialect_uri,
)
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
        validate_schemas: bool = False,
    ) -> None:
        self.dialects = DialectRegistry()
        register_standard_dialects(self.dialects)
        self.schemas = SchemaRegistry(
            self.dialects,
            default_dialect,
            max_depth=max_depth,
            bundled=bundled_metaschemas(),
        )
        self._default_dialect = default_dialect
        self._loaders = tuple(loaders)
        self._validate_schemas = validate_schemas
        # Metaschemas whose dialect is being assembled right now: a
        # metaschema naming itself (or a chain) as its own dialect would
        # otherwise recurse forever.
        self._assembling: set[str] = set()
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

        The document's dialect must exist or be assemblable from a
        registered or bundled metaschema; `$ref` targets are not followed
        (use `load_schema` for that).
        """
        self._ensure_dialect_for(schema, retrieval_uri, dialect_uri)
        try:
            uri = self.schemas.register(schema, retrieval_uri, dialect_uri)
        except RecursionError:
            raise MaxDepthExceededError(
                "schema nesting exceeded the interpreter's stack "
                f"(max_depth={self._max_depth})"
            ) from None
        self._maybe_validate(uri)
        return uri

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

    # --- dialects --------------------------------------------------------

    def _ensure_dialect_for(
        self, schema: JsonValue, retrieval_uri: str, dialect_uri: str | None
    ) -> None:
        """Make the document's dialect exist before registration.

        A known dialect passes through. Otherwise the `$schema` target is
        loaded as a metaschema (bundled or through the loaders) and a
        dialect is assembled from its `$vocabulary` (2020-12 core §8.1).
        """
        effective = effective_dialect_uri(
            schema, retrieval_uri, dialect_uri, self._default_dialect
        )
        if self.dialects.has_dialect(effective):
            return
        if effective in self._assembling:
            raise UnknownDialectError(f"metaschema cycle at '{effective}'")
        self._assembling.add(effective)
        try:
            if not self.schemas.has(effective):
                self._fetch(effective)
            meta = self.schemas.document(effective)
            if meta is None:
                raise UnknownDialectError(
                    f"dialect '{effective}' is not registered and no loader "
                    "provides its metaschema"
                )
            self._assemble_dialect(effective, meta)
        finally:
            self._assembling.discard(effective)

    def _assemble_dialect(self, uri: str, meta: JsonValue) -> None:
        declared = meta.get("$vocabulary") if is_object(meta) else None
        if not is_object(declared):
            # The spec leaves a `$vocabulary`-less metaschema open; the
            # least-surprise reading is the default dialect's vocabularies.
            base = self.dialects.get_dialect(self._default_dialect)
            self.dialects.register_dialect(
                uri,
                base.vocabulary_uris,
                allow_unknown_keywords=base.allow_unknown_keywords,
                identifiers=base.identifiers,
                ref_ignores_siblings=base.ref_ignores_siblings,
            )
            return
        uris: list[str] = []
        for vocabulary_uri, required in declared.items():
            if self.dialects.has_vocabulary(vocabulary_uri):
                uris.append(vocabulary_uri)
            elif required is True:
                raise UnknownVocabularyError(
                    f"dialect '{uri}' requires unknown vocabulary '{vocabulary_uri}'",
                    schema_location=uri,
                )
            # An unknown optional vocabulary is skipped; its keywords fall
            # to unknown-keyword annotation handling (spec MUST for false).
        # Identifier syntax travels with the core vocabulary (D18).
        self.dialects.register_dialect(
            uri,
            uris,
            identifiers=identifiers_2019
            if VOCAB_CORE_2019 in uris
            else identifiers_2020,
        )

    def _maybe_validate(self, base_uri: str) -> None:
        """The `validate_schemas` policy: a document must satisfy its dialect.

        Skipped when the metaschema is unavailable ("cannot check", not
        failure). Bundled resources never reach this path, since the
        registry registers them itself.
        """
        if not self._validate_schemas:
            return
        dialect_uri = self.schemas.dialect_uri_for(base_uri)
        if not self.schemas.has(dialect_uri):
            return
        document = self.schemas.document(base_uri)
        result = self.evaluate(dialect_uri, document, output="list")
        if not result.valid:
            raise SchemaValidationError(
                f"schema '{base_uri}' fails its metaschema '{dialect_uri}'",
                list(result.errors or []),
                schema_location=base_uri,
            )

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
    validate_schemas: bool = False,
) -> Engine:
    """Create an engine with the built-in dialects registered."""
    return Engine(
        default_dialect=default_dialect,
        loaders=loaders,
        regex_dialect=regex_dialect,
        regex_backend=regex_backend,
        reject_unsafe_regex=reject_unsafe_regex,
        max_depth=max_depth,
        validate_schemas=validate_schemas,
    )
