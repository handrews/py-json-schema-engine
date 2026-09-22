# The public façade (DESIGN.md §2, D6, D7/P4, D20, P3): one `Engine` owns a
# dialect registry, a schema registry, and a regex cache, and turns
# evaluation options into a `Result`.
#
# Dependency direction: imports everything below it in `core`. Nothing in
# `core` imports this module.

from collections.abc import Callable, Sequence

from json_schema_engine.core.channel import AnnotationRecord
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    identifiers_2019,
    identifiers_2020,
)
from json_schema_engine.core.errors import (
    FormatsRequiredError,
    JsonSchemaEngineError,
    MaxDepthExceededError,
    SchemaValidationError,
    UnknownDialectError,
    UnknownVocabularyError,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.formats import FormatTable
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import (
    DIALECT_2020_12,
    VOCAB_CORE_2019,
    VOCAB_FORMAT_ASSERTION,
)
from json_schema_engine.core.keywords.dialects import register_standard_dialects
from json_schema_engine.core.keywords.format import (
    asserting_format,
    format_assertion_vocabulary,
)
from json_schema_engine.core.loader import Loader, RangeLookup, SourceLocation
from json_schema_engine.core.locations import LocationChain
from json_schema_engine.core.metaschemas import bundled_metaschemas
from json_schema_engine.core.output import (
    AnnotationsOption,
    AnnotationUnit,
    ErrorUnit,
)
from json_schema_engine.core.records import (
    RecordSets,
    render_error,
    render_selected,
    to_render_node,
)
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
    OutputDemand,
    OutputFormat,
    Result,
    UnitSets,
    assemble_result,
    resolve_output_demand,
)
from json_schema_engine.core.uri import (
    schema_location,
)


def _record_nothing(keyword_name: str, vocabulary_uri: str | None) -> bool:
    return False


def attach_location_chain(
    registry: SchemaRegistry, error: JsonSchemaEngineError
) -> None:
    """Fill in an error's `location_chain` as it leaves the engine (P11).

    Only a registry can build a chain, and no raise site has one — the
    evaluator, the regex screen and a keyword's `analyze()` all hold a
    location and nothing else. Doing it here instead of threading a
    registry into all of them also fixes the chain at the moment of
    failure, rather than whenever someone later thinks to ask.

    A no-op without a location, or when an inner frame already attached
    one, so nesting these is harmless: `load_schema` and `_fetch` route
    through `register_schema`, and `_maybe_validate` through `evaluate`.

    A free function rather than a method because the compiled tier needs
    the same behavior and already imports from this module.
    """
    if error.location_chain is not None or error.schema_location is None:
        return
    chain = registry.location_chain(error.schema_location)
    if chain:
        error.location_chain = chain


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
        formats: FormatTable | None = None,
        assert_formats: bool = False,
    ) -> None:
        if assert_formats and formats is None:
            raise FormatsRequiredError(
                "assert_formats=True requires a format table: "
                "create_engine(formats=FORMATS_2020_12, assert_formats=True)"
            )
        self._formats = formats
        self.dialects = DialectRegistry()
        if assert_formats and formats is not None:
            table = formats

            def best_effort(behavior_id: str) -> KeywordBehavior:
                return asserting_format(behavior_id, table, refuse_unknown=False)

            register_standard_dialects(self.dialects, format_behavior=best_effort)
        else:
            register_standard_dialects(self.dialects)
        if formats is not None:
            # A table makes the 2020-12 format-assertion vocabulary available
            # to `$vocabulary`-assembled dialects (M7).
            self.dialects.register_vocabulary(
                VOCAB_FORMAT_ASSERTION, format_assertion_vocabulary(formats)
            )
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

    @property
    def regex_cache(self) -> RegexCache:
        """The engine's pattern cache (dialect, backend, compiled patterns)."""
        return self._regex

    @property
    def max_depth(self) -> int:
        """The schema-application depth budget (P3)."""
        return self._max_depth

    @property
    def formats(self) -> FormatTable | None:
        """The format table this engine asserts through, if any (M7)."""
        return self._formats

    # --- registration ----------------------------------------------------

    def register_schema(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None = None,
        get_range: RangeLookup | None = None,
    ) -> str:
        """Register a schema document locally and return its canonical URI.

        The document's dialect must exist or be assemblable from a
        registered or bundled metaschema; `$ref` targets are not followed
        (use `load_schema` for that). `get_range` is the D17 position
        capability for this document.
        """
        try:
            self._ensure_dialect_for(schema, retrieval_uri, dialect_uri)
            # Before the walk, not after: a document that fails its
            # metaschema must not be registered at all. Nothing needs to be
            # registered to check it — the metaschema sees the document as
            # plain data — and skipping the walk makes the failure cheaper.
            self._maybe_validate(schema, retrieval_uri, dialect_uri)
            try:
                uri = self.schemas.register(
                    schema, retrieval_uri, dialect_uri, get_range
                )
            except RecursionError:
                raise MaxDepthExceededError(
                    "schema nesting exceeded the interpreter's stack "
                    f"(max_depth={self._max_depth})"
                ) from None
        except JsonSchemaEngineError as error:
            attach_location_chain(self.schemas, error)
            raise
        return uri

    def load_schema(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None = None,
        get_range: RangeLookup | None = None,
    ) -> str:
        """Register a document and load every resource it references (P4)."""
        uri = self.register_schema(schema, retrieval_uri, dialect_uri, get_range)
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
                # A resource type that never heard of positions is still a
                # valid loaded resource (P4); the capability is optional.
                get_range: RangeLookup | None = getattr(loaded, "get_range", None)
                self.register_schema(loaded.value, loaded.uri, None, get_range)
                return True
        return False

    # --- positions (D17) -------------------------------------------------

    def locate(self, schema_location: str) -> SourceLocation | None:
        """Translate a canonical schema location back to its document.

        Returns the containing document, the document-rooted pointer, and
        the source range when that document's loader reported positions;
        None for a resource the registry never saw. Zero cost on the
        evaluation path: nothing calls this unless asked.

        `schema_location` is a URI, so its fragment is decoded back into a
        plain-text pointer before it is joined to the document-rooted one
        (P10) — the ranges a loader reports are keyed by plain pointers,
        and the locations the engine emits are the argument this is
        expected to be given. An anchor-shaped fragment is resolved through
        the anchor index first, since an anchor is a fragment rather than a
        pointer and decoding one yields a string no pointer walk can use.

        A location from a *failed* registration has no document to find,
        since the registration was rolled back (§7); the error carries its
        own `schema_source`, captured before the undo.
        """
        return self.schemas.source_of(schema_location)

    def location_chain(self, schema_location: str) -> LocationChain:
        """The enclosing `$id` resources of a schema location (P11).

        Innermost first, ending at a root resource; empty for a resource
        this engine never saw. A position in a plain single-resource
        document gives one hop.

        This is the identity question — which resource, inside which — and
        `locate` is the physical one. They compose rather than overlap:
        every hop's `.location` is a `locate` argument, which is how a
        caller gets a source range for a hop.
        """
        return self.schemas.location_chain(schema_location)

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
            elif vocabulary_uri == VOCAB_FORMAT_ASSERTION:
                # Present only when a table was given; with or without the
                # boolean, a caller using this vocabulary expects assertion.
                raise FormatsRequiredError(
                    f"metaschema '{uri}' declares the format-assertion "
                    "vocabulary but the engine has no format table; pass "
                    "formats= (e.g. create_engine(formats=FORMATS_2020_12))",
                    schema_location=schema_location(uri, ""),
                )
            elif required is True:
                raise UnknownVocabularyError(
                    f"dialect '{uri}' requires unknown vocabulary '{vocabulary_uri}'",
                    schema_location=schema_location(uri, ""),
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

    def _maybe_validate(
        self, schema: JsonValue, retrieval_uri: str, dialect_uri: str | None
    ) -> None:
        """The `validate_schemas` policy: a document must satisfy its dialect.

        Runs *before* registration, so a document that fails is never
        registered — which is what the option has always been documented to
        mean. `identify` names the resource and dialect the registration
        would have used, so the message and location are the same either
        way.

        Skipped when the metaschema is unavailable ("cannot check", not
        failure). Bundled resources never reach this path, since the
        registry registers them itself.
        """
        if not self._validate_schemas:
            return
        identity = self.schemas.identify(schema, retrieval_uri, dialect_uri)
        if not self.schemas.has(identity.dialect_uri):
            return
        result = self.evaluate(identity.dialect_uri, schema, output="basic")
        if not result.valid:
            raise SchemaValidationError(
                f"schema '{identity.base_uri}' fails its metaschema "
                f"'{identity.dialect_uri}'",
                list(result.errors or []),
                schema_location=schema_location(identity.base_uri, ""),
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
        verbose: bool | None = None,
        trace: bool = False,
        positions: bool = False,
    ) -> Result:
        """Evaluate `instance` against a registered schema (D6).

        `output` names the format; `annotations` selects which annotations
        reach output (D5); `error_params` adds keyword identity and
        structured params to the flat error units (D13); `verbose` asks
        for the verbose level of `list`/`hierarchical`; `trace` renders the
        application tree into `Result.trace`; `positions` decorates the
        flat units with schema-side source positions (D17). An unsupported
        combination raises `OutputOptionsError` before evaluating.
        """
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
        try:
            valid, state = run_evaluation(
                self.schemas,
                schema_uri,
                instance,
                compile_regex=self._regex.compile,
                should_record=should_record,
                max_depth=self._max_depth,
                tracing=demand.tracing,
            )
        except JsonSchemaEngineError as error:
            attach_location_chain(self.schemas, error)
            raise
        return assemble_evaluation(
            state,
            valid,
            demand,
            annotations,
            self.schemas.root_ref(schema_uri).location,
            trace,
            locate=self.locate if positions else None,
        )


def assemble_evaluation(
    state: EvalState,
    valid: bool,
    demand: OutputDemand,
    annotations: AnnotationsOption,
    root_location: str,
    trace: bool,
    *,
    locate: Callable[[str], SourceLocation | None] | None = None,
) -> Result:
    """Turn a finished evaluation state into a `Result` for `demand`: the
    interpreter's own assembly, shared with the compiled evaluator (M9),
    whose artifacts run on the same `EvalState`. `locate` decorates the
    flat units with source positions when given (D17)."""
    if demand.format is OutputFormat.FLAG:
        return Result(valid, None, None, None)

    # The flat surface first; its record lists stay paired with the unit
    # lists so the located tree can index the units.
    params = demand.error_params
    units = UnitSets(
        errors=[render_error(e, error_params=params) for e in state.errors]
    )
    records = RecordSets(errors=state.errors)
    if valid and demand.annotations is not None:
        selected = render_selected(state.root_annotations, annotations)
        units.annotations.extend(selected.units)
        records = RecordSets(errors=state.errors, annotations=selected.records)
    if demand.verbose:
        units.dropped_errors.extend(
            render_error(e, error_params=params) for e in state.dropped_errors
        )
        dropped_records: list[AnnotationRecord] = []
        if demand.annotations is not None:
            # The relevant annotations are a valid run's root survivors;
            # an invalid run has none (draft-03 §12.2). Identity, not
            # equality: two keywords may record equal-looking values.
            relevant = {id(a) for a in (state.root_annotations if valid else ())}
            candidates = [
                a for a in state.all_annotations or () if id(a) not in relevant
            ]
            selected = render_selected(candidates, annotations)
            units.dropped_annotations.extend(selected.units)
            dropped_records = selected.records
        records = RecordSets(
            errors=state.errors,
            dropped_errors=state.dropped_errors,
            annotations=records.annotations,
            dropped_annotations=dropped_records,
        )
    root = None
    if demand.tracing:
        assert state.trace_root is not None
        root = to_render_node(state.trace_root, records)
    result = assemble_result(demand, valid, units, root, root_location, trace)
    if locate is not None:
        for unit_list in (
            result.errors,
            result.annotations,
            result.dropped_errors,
            result.dropped_annotations,
        ):
            _decorate_units(unit_list, locate)
    return result


def _decorate_units(
    units: list[ErrorUnit] | list[AnnotationUnit] | None,
    locate: Callable[[str], SourceLocation | None],
) -> None:
    for unit in units or []:
        source = locate(unit["schemaLocation"])
        if source is not None:
            unit["source"] = source


def create_engine(
    *,
    default_dialect: str = DIALECT_2020_12,
    loaders: Sequence[Loader] = (),
    regex_dialect: RegexDialect = "ecma262",
    regex_backend: RegexBackend = "re",
    reject_unsafe_regex: bool = False,
    max_depth: int = DEFAULT_MAX_DEPTH,
    validate_schemas: bool = False,
    formats: FormatTable | None = None,
    assert_formats: bool = False,
) -> Engine:
    """Create an engine with the built-in dialects registered.

    `formats` (a `FormatTable`, e.g. `json_schema_engine.formats.FORMATS_2020_12`)
    enables the 2020-12 format-assertion vocabulary; `assert_formats=True`
    additionally makes `format` assert, best effort, in every standard
    dialect. Without either, `format` only annotates.
    """
    return Engine(
        default_dialect=default_dialect,
        loaders=loaders,
        regex_dialect=regex_dialect,
        regex_backend=regex_backend,
        reject_unsafe_regex=reject_unsafe_regex,
        max_depth=max_depth,
        validate_schemas=validate_schemas,
        formats=formats,
        assert_formats=assert_formats,
    )
