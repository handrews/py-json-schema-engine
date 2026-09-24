# API reference

This page lists every name each public package exports through `__all__`, with
its exact signature and a short description. `tests/test_reference.py` checks
that every export of every package below appears here, so the page cannot
silently fall behind a new export.

Import paths:

- `json_schema_engine.core`: the interpreter tier: `Engine`, `create_engine`,
  results, output units, the keyword extension surface.
- `json_schema_engine.compiler`: the ahead-of-time compiler: plans a registered
  schema into a Python `ast` module, either run in-process
  (`compile_validator`) or emitted as a standalone file (`emit_standalone`).
- `json_schema_engine.formats`: the standard `format` predicate tables for the
  built-in dialects.
- `ecma_regex`: a standalone package (no dependency on the engine) that parses,
  translates, and matches ECMA-262 regular expressions.

Any name not listed on this page, including everything under a package's
private submodules, is an implementation detail and may change without notice.

## `json_schema_engine.core`

### Engine and creation

`create_engine(*, default_dialect=DIALECT_2020_12, loaders=(),
regex_dialect="ecma262", regex_backend="re", reject_unsafe_regex=False,
max_depth=512, validate_schemas=False, formats=None, assert_formats=False,
reject_id_fragments=False) -> Engine`: builds an `Engine` with the built-in
dialects (2020-12, 2019-09, draft-07, draft-06) registered. `formats` (e.g.
`json_schema_engine.formats.FORMATS_2020_12`) enables the 2020-12
format-assertion vocabulary; `assert_formats=True` additionally makes `format`
assert, best effort, in every standard dialect. Without either, `format` only
annotates. `reject_id_fragments=True` makes an empty trailing fragment in an
`$id` that sets a base URI (`"https://x.example/s#"`) an
`InvalidIdentifierError`: 2020-12 and 2019-09 allow it, IETF draft-03 does not,
so this is a forward-compatibility check. draft-07/06 `$id: "#name"` is an
anchor, not a base URI, and is unaffected, as are the bundled metaschemas. This
is the normal entry point; `Engine()` is equivalent but less discoverable.

`Engine`: a JSON Schema engine: dialect registry, schema registry, regex cache,
and evaluation. Construct through `create_engine`; the constructor takes the
same keyword-only parameters. Registration is synchronous and local;
`load_schema` additionally drains external references through the loaders (P4).

- `Engine.dialects`: the engine's `DialectRegistry`: every registered
  vocabulary and assembled dialect.
- `Engine.schemas`: the engine's schema registry (internal type; registration,
  reference resolution, and dialect lookup for registered documents all go
  through it).
- `Engine.formats -> FormatTable | None`: the format table this engine asserts
  through, if any (M7).
- `Engine.max_depth -> int`: the schema-application depth budget (P3).
- `Engine.regex_cache -> RegexCache`: the engine's pattern cache (dialect,
  backend, compiled patterns; internal type, exposed read-only).
- `Engine.register_schema(schema, retrieval_uri, dialect_uri=None,
  get_range=None) -> str`: registers a schema document locally and returns its
  canonical URI. The document's dialect must exist or be assemblable from a
  registered or bundled metaschema; `$ref` targets are not followed (use
  `load_schema` for that). `get_range` is the D17 position capability for this
  document.
- `Engine.unregister_schema(uri) -> None`: removes a registered document and
  everything its registration claimed: embedded `$id` resources, anchors and
  dynamic anchors, recursive roots, dialect and location entries, its range
  lookup, and every retrieval alias for it (P15). `uri` is the document's
  canonical or retrieval URI. A resource that an equal copy in a later document
  has since taken over stays with that document. Unregister then
  `register_schema` is how a document is replaced. Compiled artifacts keep what
  they were compiled against, and a dialect assembled from an unregistered
  metaschema stays registered. Raises `UnresolvableReferenceError` for a URI
  that names no document root (including a resource embedded in another
  document, which the message names), and `ReadOnlyRegistryError` for a
  bundled metaschema.
- `Engine.load_schema(schema, retrieval_uri, dialect_uri=None, get_range=None)
  -> str`: registers a document and loads every resource it references (P4).
- `Engine.load(uri) -> str`: loads and registers a resource by URI through the
  configured loaders.
- `Engine.locate(schema_location) -> SourceLocation | None`: translates a
  canonical schema location back to its document: the containing document, the
  document-rooted pointer, and the source range when that document's loader
  reported positions. Returns `None` for a resource the registry never saw.
  Zero cost on the evaluation path; nothing calls this unless asked. The
  argument is a URI, as every `schemaLocation` the engine emits is; its
  fragment is decoded back into a plain-text pointer, and the
  `SourceLocation.pointer` returned is plain text too. An anchor-shaped
  fragment is resolved through the anchor index, so `#spot` and the pointer
  naming the same node give the same answer; an unknown anchor gives `None`.
- `Engine.location_chain(schema_location) -> LocationChain`: the enclosing
  `$id` resources of a schema location (P11), innermost first, ending at a root
  resource. Empty for a resource this engine never saw. A position in a plain
  single-resource document gives one hop. This is the *identity* question —
  which resource, inside which — where `locate` is the *physical* one; they
  compose, since every hop's `.location` is a `locate` argument.
- `Engine.evaluate(schema_uri, instance, *, output=OutputFormat.FLAG,
  annotations=False, error_params=False, verbose=None, trace=False,
  positions=False) -> Result`: evaluates `instance` against a registered schema
  (D6). `output` names the format; `annotations` selects which annotations
  reach output (D5); `error_params` adds keyword identity and structured params
  to the flat error units (D13); `verbose` asks for the verbose level of
  `list`/`hierarchical`; `trace` renders the application tree into
  `Result.trace`; `positions` decorates the flat units with schema-side source
  positions (D17). An unsupported combination raises `OutputOptionsError`
  before evaluating.

### Evaluation results and output units

`Result`: the result of an evaluation (D6): a frozen dataclass with fields
`valid: bool`, `errors: list[ErrorUnit] | None`, `annotations:
list[AnnotationUnit] | None`, `output_document: OutputDocument | None`,
`dropped_errors: list[ErrorUnit] | None = None`, `dropped_annotations:
list[AnnotationUnit] | None = None`, and `trace: TraceUnit | None = None`.
Presence rules: `errors` iff invalid; `annotations` iff valid and annotations
were selected; the dropped pair at the verbose level; `trace` when requested;
`output_document` is `None` for `flag`, which carries nothing beyond `valid`.

`OutputDocument`: the document type each non-flag `OutputFormat` renders:
`BasicOutputDocument | DetailedOutputUnit | ListOutputDocument | OutputUnit |
dict[str, bool]`. `basic` renders `BasicOutputDocument`; `detailed`/`verbose`
render `DetailedOutputUnit`; `list` renders `ListOutputDocument`;
`hierarchical` renders `OutputUnit`.

Location spelling (P10) is uniform across every unit and document type
below: a **schema** location (`schemaLocation`, `absoluteKeywordLocation`) is
a URI whose fragment is a percent-encoded JSON Pointer, while an
**evaluation** or **instance** location (`evaluationPath`, `keywordLocation`,
`inputLocation`, `instanceLocation`, `SourceLocation.pointer`) is a
plain-text JSON Pointer. Only a name containing a character RFC 3986 keeps
out of a fragment makes the two differ.

`ErrorUnit`: a `TypedDict` for one rendered assertion failure, native field
names (D6, D13): `evaluationPath: str`, `schemaLocation: str`, `inputLocation:
str`, `error: str`, `keyword: NotRequired[str]`, `vocabulary:
NotRequired[str]`, `params: NotRequired[dict[str, JsonValue]]`, `source:
NotRequired[SourceLocation]`. `keyword`/`vocabulary`/`params` appear only with
the `error_params` control; `keyword`/`vocabulary` are additionally absent for
a boolean `false` schema's error, which names no keyword; `source` appears with
the `positions` control.

`AnnotationUnit`: a `TypedDict` for one rendered annotation (a keyword's own
value at a location): `evaluationPath: str`, `schemaLocation: str`,
`inputLocation: str`, `keyword: str`, `annotation: JsonValue`, `vocabulary:
NotRequired[str]`, `source: NotRequired[SourceLocation]`.

`BasicOutputDocument`: a `TypedDict` for the IETF draft-03 §13.4.2 `basic`
document: `valid: bool`, `keywordLocation: str`, `absoluteKeywordLocation:
str`, `instanceLocation: str`, `errors: NotRequired[list[...]]` (each
`{keywordLocation, absoluteKeywordLocation, instanceLocation, error}`),
`annotations: NotRequired[list[...]]` (each with `annotation` in place of
`error`). `errors` appears only on an invalid result, `annotations` only on a
valid one, never both.

`DetailedOutputUnit`: a `TypedDict` for one node of the `detailed`/`verbose`
keyword-level tree (IETF draft-03 §13.3): `valid: bool`, `keywordLocation:
str`, `absoluteKeywordLocation: str`, `instanceLocation: str`, `error:
NotRequired[str]`, `annotation: NotRequired[JsonValue]`, `errors:
NotRequired[list[DetailedOutputUnit]]`, `annotations:
NotRequired[list[DetailedOutputUnit]]`. Nested results key on the node's own
result: `errors` for a failing node, `annotations` for a passing one.

`ListOutputDocument`: a `TypedDict` for the `list` document (the
machines-oriented output proposal): `valid: bool`, `details: list[OutputUnit]`,
one unit per schema application in pre-order.

`OutputUnit`: a `TypedDict` for one schema application in the
`list`/`hierarchical` documents: `valid: bool`, `evaluationPath: str`,
`schemaLocation: str`, `instanceLocation: str`, `errors: NotRequired[dict[str,
str]]`, `annotations: NotRequired[dict[str, JsonValue]]`, `droppedErrors:
NotRequired[dict[str, str]]`, `droppedAnnotations: NotRequired[dict[str,
JsonValue]]`, `details: NotRequired[list[OutputUnit]]` (nested
sub-applications, `hierarchical` only). At the verbose level `droppedErrors`/
`droppedAnnotations` mark irrelevant records.

`TraceUnit`: a `TypedDict` for one schema application from a traced evaluation
(`Result.trace`): `segments: list[str]` (evaluation-path segments below the
parent, decoded; the first is the applying keyword), `schemaLocation: str`,
`inputLocation: str`, `valid: bool`, `errorIndexes: list[int]` (indexing
`Result.errors` of the same run, populated only when the evaluation failed),
`children: list[TraceUnit]`.

### Output options

`AnnotationsOption`: a type alias, `bool | AnnotationSelection`: `False`
(nothing), `True` (everything), or a filtered `AnnotationSelection`. Passed as
`Engine.evaluate`'s `annotations` argument.

`AnnotationSelection`: which annotations reach output (D5), independent of
format and level: a frozen dataclass with fields `keywords: frozenset[str] |
None = None`, `vocabularies: frozenset[str] | None = None`, `exclude_keywords:
frozenset[str] = frozenset()`, `exclude_vocabularies: frozenset[str] =
frozenset()`, `keep: Callable[[AnnotationUnit], bool] | None = None`. The
allow-lists (`keywords`, `vocabularies`) are OR'd together; when both are
`None` every keyword is allowed. The deny-lists subtract from that result.
`keep` runs last, over the fully rendered `AnnotationUnit`.

`OutputFormat`: a `StrEnum` of output format names (D6), each fixing its own
document structure and field vocabulary: `FLAG = "flag"`, `BASIC = "basic"`,
`DETAILED = "detailed"`, `VERBOSE = "verbose"`, `LIST = "list"`, `HIERARCHICAL
= "hierarchical"`. `flag`/`basic`/`detailed`/`verbose` are IETF draft-03 §13;
`list`/`hierarchical` are the machines-oriented output proposal.

### Errors

Every error below is a `JsonSchemaEngineError` (directly or through another
error in this list); `schema_location: str | None` lives on the root and is
populated when the error concerns a specific schema position.

`JsonSchemaEngineError(message, *, schema_location=None)`: root of every error
this engine raises. Catch this to see everything the library raises without
also swallowing bugs (`TypeError`, `KeyError`). Besides `schema_location` it
carries two things a raise site cannot work out for itself, both filled in by
the engine on the way out and both `None` when unavailable:
`location_chain: LocationChain | None`, the position's enclosing `$id`
resources (P11), and `schema_source: SourceLocation | None`, the same position
seen physically (D17) — the document, the document-rooted pointer, and the
source range when a loader reported one. `schema_source` is captured rather
than looked up because a failed registration is rolled back, so there is no
longer a registered document for `Engine.locate` to find.

`JsonSyntaxError(message, *, line, column, offset)`: `parse_json_with_ranges`
met text that is not an RFC 8259 document. Also a `ValueError`. Carries the
1-based `line: int` and `column: int` and the 0-based `offset: int` of the
first offending character.

`InvalidSchemaError`: a keyword-claimed schema position holds neither an object
nor a boolean (D19). Raised by the registration walk and, as a lazy backstop,
by schema application.

`InvalidIdentifierError`: an `$id` cannot identify the resource it claims to
start — either it carries a non-empty fragment (under 2019-09/2020-12 an `$id`
sets a base URI, and a base URI cannot carry one; the plain-name form is
`$anchor`), at a document root or below one; or it is an embedded `""` or
`"#"` and so resolves to the enclosing resource, identifying nothing new. At a
document root `""` and `"#"` are legal and mean the retrieval URI. Per dialect:
draft-07/06 read `#name` as an anchor and never reach the first rule, so the
same document is legal there. Distinct from `DuplicateResourceError`, which is
about two positions claiming one URI.

`DuplicateResourceError`: two different schemas claim one resource URI (P12) —
either a single document minting the same `$id` twice, or a later registration
that would rebind a URI an earlier one bound to a different schema.
Re-registering an *equal* document is not a duplicate. A retrieval URI is a
claim too (P15): an `$id` equal to another document's retrieval URI, and a
retrieval URI that already names a resource or aliases a different one, are
refused, since one of the two would be unreachable. A bundled metaschema's URI
is reserved for content equal to the bundled document, whether or not that
metaschema has been used yet; a custom metaschema goes under a URI of its own.

`DuplicateAnchorError`: two different schema objects claim one anchor name
within a resource (P12). Covers `$anchor`, `$dynamicAnchor`, and the
draft-07/06 `$id: "#name"` form alike, including a name claimed by an
`$anchor` on one object and a `$dynamicAnchor` on another — which would
otherwise leave `$ref` and `$dynamicRef` resolving the same fragment to
different schemas. A single object carrying both under one name is fine.

Registration is all-or-nothing (P13): a document whose registration raises
leaves the registry exactly as it found it, so an engine stays usable after a
caught registration error. Because the document is gone, `Engine.locate` cannot
place such an error afterwards — the error carries its own `schema_source`,
captured before the rollback.

`ReadOnlyRegistryError`: a registry, or an entry in one, cannot be modified:
registration or unregistration on a compiled artifact's registry snapshot,
unregistering from caller code running inside a registration, or unregistering
a bundled metaschema (P15).

`UnknownDialectError`: a schema names a `$schema` dialect URI that no
registered dialect claims, or that cannot be assembled. `dialect_uri: str |
None` is the dialect that could not be found or assembled — the URI a loader
would have to provide a metaschema for. When a metaschema's own `$schema` is
the missing one, it names that inner dialect, since that is what is actually
needed. For an *embedded* resource's `$schema` (P14), `schema_location` names
the resource that asked for it. `Engine.register_schema` assembles an
embedded dialect from a metaschema and registers again before giving up, so
an error reaching you means that assembly failed too.

`UnknownKeywordError`: a schema uses a keyword its dialect does not define and
does not permit unknown keywords for. Only dialects built with
`allow_unknown_keywords=False` raise this; the default treats an unknown
keyword as annotation-only.

`UndeclaredProductionError`: a keyword called `ctx.produce()` without declaring
its id in `StaticFacts.produces`. See "Dialects and keywords" below and
`guide/custom-keywords.md`.

`UndeclaredConsumptionError`: a keyword called `ctx.visible()` for an id absent
from its `StaticFacts.consumes`. The mirror of `UndeclaredProductionError`.

`KeywordContractError`: a keyword reported an error through `ctx.error()` yet
accepted the input. Relevance drops the errors of accepting evaluations, so
such an error would otherwise vanish; the contract violation is reported
instead of the phantom error.

`InfiniteLoopError`: a schema was re-entered at the same instance location
without progress (the `$ref` cycle guard, keyed by schema location and cursor
identity).

`MaxDepthExceededError`: registration or evaluation nested deeper than
`max_depth` allows (P3), raised before CPython's own recursion limit can fire.

`OutputOptionsError`: the requested combination of output format, level, and
controls is invalid. Raised by `Engine.evaluate` before evaluation (D6), so a
caller never pays for a run whose result it cannot be given.

`UnsupportedPatternError`: a regex could not be translated into the configured
backend's dialect. Raised at registration (P1), never on the hot path.

`UnsafeRegexError`: a regex failed the star-height screen while
`reject_unsafe_regex` is on (D20 ReDoS defense).

`UnresolvableReferenceError`: a reference could not be resolved to a schema: it
does not form a usable absolute URI, its target document was never registered
and no loader supplied it, or a pointer or anchor names nothing in an otherwise
known resource. Beyond `schema_location`, which says where the failure was, it
carries what was attempted: `reference: str | None` (the reference exactly as
written), `resolved_against: str | None` (the base URI in force there, which may
be an embedded `$id` a reader never knew was present), and `resolved_to: str |
None` (the absolute URI the two produced). All three are `None` when no
reference was in play, such as a resource a caller named directly. A pointer
miss additionally names the failing segment and the prefix that did match.

`UnknownVocabularyError`: a metaschema's `$vocabulary` requires a vocabulary
nobody registered. Only a vocabulary marked `true` (required) raises; an
unknown optional vocabulary is skipped.

`UnknownFormatError`: a `format` names a format the engine's table lacks, under
the format-assertion vocabulary (which promised assertion for every name).

`FormatUnavailableError`: a `format` names a table entry that cannot run in
this environment (an optional extra is missing); asserting it is refused at
registration.

`FormatsRequiredError`: a format table is needed but none was configured:
`assert_formats=True` without `formats=`, or a metaschema declaring the
format-assertion vocabulary on an engine without a table.

`SchemaValidationError(message, errors, *, schema_location=None)`: a registered
document fails its own metaschema (`create_engine(validate_schemas=True)`).
`errors: list[object]` are the list-format units of the failed evaluation. The
check is per dialect region (P17). The root is checked against its dialect's
metaschema, and so is every embedded resource whose `$schema` names a
different dialect from its parent's, with any region nested inside it masked
out. `schema_location` is `uri#` of the region's resource, and the error
carries that resource's `location_chain` and `schema_source`. A region whose
metaschema is unavailable is skipped. The check walks the document once
before registering it, so a validated registration walks it twice.

### Dialects and keywords (the extension surface)

These are the types a custom keyword or dialect is written against; see
`guide/custom-keywords.md` for a worked example.

`KeywordBehavior`: a keyword's static analysis and evaluation semantics (D2), a
frozen dataclass. Keywords are data: vocabularies are plain mappings of these,
looked up on the instance and never bound as methods. Fields:

- `id: str`: the keyword URI: its stable identity, independent of its name in
  any dialect.
- `evaluate: EvaluateFn` (`Callable[[JsonValue, Cursor, KeywordContext],
  bool]`): interpreter semantics, synchronous (D7). A keyword that reports an
  error through `ctx.error()` must return `False`.
- `analyze: AnalyzeFn | None = None` (`Callable[[JsonValue, AnalyzeContext],
  StaticFacts] | None`): static facts; also drives the registration walk's
  descent. `None` means no facts: no subschemas, no productions, nothing to
  screen.
- `phase: Phase = Phase.ASSERT`: evaluation order within one schema object.
- `structural: bool = False`: an identifier or reserved-location keyword
  (`$id`, `$defs`, `$comment`): it evaluates to nothing and appears in no
  output unit.
- `lower: LowerFn | None = None`: compiled form as lowering IR (M6). `None`
  means a schema object containing this keyword becomes an interpreted unit
  (the trampoline fallback), never a failure.
- `KeywordBehavior.facts(value, schema) -> StaticFacts`: the keyword's static
  facts for one occurrence, `StaticFacts()` (empty) if `analyze` is `None`.

`KeywordContext`: a `Protocol`: the engine services available to one keyword
application, the only path to subschema application, the channel, and error
reporting. The engine owns path, scope, and frame bookkeeping in exactly one
place, which is what lets locations become compile-time constants in the
compiler tier.

- `KeywordContext.schema -> Mapping[str, JsonValue]`: the current schema
  object, this keyword's siblings included.
- `KeywordContext.cursor -> Cursor`: the current instance position (internal
  type: a parent-linked, identity-compared position).
- `KeywordContext.apply(segments, cursor) -> bool`: applies the subschema at
  `segments` (relative to the schema object).
- `KeywordContext.resolve_ref(ref) -> SchemaRef`: resolves a reference against
  the current lexical base.
- `KeywordContext.resolve_dynamic(ref) -> SchemaRef`: resolves a
  `$dynamicRef`-class reference with rebinding (D8).
- `KeywordContext.resolve_recursive(ref) -> SchemaRef`: resolves a 2019-09
  `$recursiveRef`, D8's degenerate case.
- `KeywordContext.apply_resolved(target) -> bool`: applies a resolved reference
  target at the current cursor.
- `KeywordContext.compile_regex(pattern) -> CompiledRegex`: compiles through
  the engine's regex dialect, backend, and cache.
- `KeywordContext.annotate() -> None`: records this keyword's own value as an
  annotation.
- `KeywordContext.produce(data) -> None`: communicates dependency data to other
  keywords; never output.
- `KeywordContext.visible(behavior_ids, scope="all") ->
  Sequence[DependencyView]`: dependency records visible at the current cursor.
  `"all"` sees this schema object's keywords plus records merged from
  successful in-place sub-applications (what `unevaluated*` needs);
  `"adjacent"` sees only this schema object's own keywords (what `then`/`else`
  need from `if`).
- `KeywordContext.error(message, params=None) -> None`: reports an assertion
  failure with optional structured params (D13).

`StaticFacts`: what one keyword occurrence says about itself from its value
alone (a frozen dataclass); the compiler tier's entire window into keyword
semantics, and it drives the registry's schema-position walk: only the
positions a keyword claims in `subschemas` are treated as schemas. Fields, all
defaulting to empty/`None`:

- `subschemas: tuple[SubschemaPath, ...] = ()`: paths to child schemas,
  relative to the keyword's value.
- `references: tuple[str, ...] = ()`: reference URIs in the value, relative to
  the lexical base; drive transitive loading (P4).
- `produces: tuple[str, ...] = ()`: behavior ids this keyword may `produce()`
  dependency data under, normally its own id. An undeclared producer raises
  `UndeclaredProductionError`.
- `consumes: tuple[str, ...] = ()`: behavior ids this keyword reads through
  `visible()` (D5).
- `regexes: tuple[str, ...] = ()`: regular expressions the keyword compiles;
  screened by `reject_unsafe_regex` at registration (D20).
- `formats: tuple[str, ...] = ()`: format names the keyword needs a table entry
  for (M7).
- `dynamic_scope_sensitive: bool = False`: participates in dynamic-scope
  resolution (D8); forces the compiler to fall back to the interpreter.
- `evaluates_names: NameCoverage | None = None`: property-name coverage this
  occurrence contributes (D9a); `None` means none.
- `evaluates_indexes: IndexCoverage | None = None`: array-index coverage this
  occurrence contributes (D9a); `None` means none.
- `applications: tuple[SubschemaApplication, ...] = ()`: how the keyword
  applies its subschemas (M6): the planner's edges and the coverage analysis's
  transitive contributors. `SubschemaApplication` (internal type) fields:
  `path: SubschemaPath`, `mode: ApplyMode`, `conditional: bool`, `asserts:
  bool`, `sibling: str | None = None`, `ref: str | None = None`, `inverted:
  bool = False`, `resolution: Literal["dynamic", "recursive"] | None = None`
  (M9: marks a reference whose target depends on the dynamic scope — the
  planner resolves such a site at plan time when every path reaching it
  agrees on the target, and islands it otherwise).

`AnalyzeContext`: a frozen dataclass wrapping `schema: Mapping[str,
JsonValue]`, the keyword's containing schema object, for sibling-dependent
facts (e.g. `items` starting after `prefixItems`, `if` declaring edges for
`then`).

`DependencyView`: a frozen dataclass, a consumer's view of one dependency
record: `behavior_id: str` (who produced it) and `data: object` (what).
Returned by `KeywordContext.visible`.

`Dialect`: an ordered set of vocabularies with identifier and `$ref` semantics,
a frozen dataclass. Fields: `uri: str`; `keywords: Mapping[str,
DialectKeyword]`; `ordered: tuple[DialectKeyword, ...]` (every phase-0 entry,
then every phase-1 entry, each group in vocabulary-then-declaration order);
`vocabulary_uris: tuple[str, ...]`; `allow_unknown_keywords: bool` (unknown
keywords collected as annotations when true, `UnknownKeywordError` when false);
`identifiers: IdentifierExtractor`; `ref_ignores_siblings: bool` (draft-07/06:
a schema object with `$ref` evaluates only `$ref`). Method
`Dialect.identifiers_of(node) -> IdentifierFacts`: identifier facts for a node,
none for a boolean schema.

`DialectRegistry`: the registry of vocabularies and the dialects assembled from
them (D2). Construct with `DialectRegistry()`.

- `DialectRegistry.register_vocabulary(uri, keywords) -> None`: registers a
  vocabulary's keyword behaviors (`Mapping[str, KeywordBehavior]`) under its
  URI.
- `DialectRegistry.register_dialect(uri, vocabulary_uris, *,
  allow_unknown_keywords=True, identifiers=identifiers_2020,
  ref_ignores_siblings=False) -> Dialect`: assembles a dialect from
  already-registered vocabularies. A later vocabulary rebinding a name replaces
  the earlier binding, so a dialect author can override a built-in keyword by
  listing an extension vocabulary after the standard one.
- `DialectRegistry.snapshot() -> DialectRegistry`: a frozen copy: the same
  vocabularies and dialects, read-only. A compiled artifact binds to a snapshot
  (M6).
- `DialectRegistry.get_dialect(uri) -> Dialect`: looks up a registered dialect;
  raises `UnknownDialectError`.
- `DialectRegistry.has_dialect(uri) -> bool`
- `DialectRegistry.has_vocabulary(uri) -> bool`

`Phase`: an `IntEnum` of evaluation order within one schema object: `ASSERT =
0`, `UNEVALUATED = 1`. Phase 1 keywords (`unevaluated*`) run after every phase
0 keyword of the same object has merged its records, so their `visible()` sees
the whole object's dependency data.

### Loaders and source positions

`Loader`: a type alias, `Callable[[str], LoadedResource | None]`. Returns
`None` for a URI it does not know: a miss is not an error, since the next
loader may know it.

`LoadedResource`: a `Protocol`: what the engine needs from a loader's result.
`LoadedResource.value -> JsonValue` and `LoadedResource.uri -> str` (the URI to
register the document under; a loader that followed a redirect reports where
the document actually lives).

`LoadedDocument`: a frozen dataclass, the engine's own concrete
`LoadedResource`: `value: JsonValue`, `uri: str`, `get_range: RangeLookup |
None = None` (the optional D17 position capability).

`RangeLookup`: a type alias, `Callable[[str], SourceRange | None]`: a loader's
position capability, the range of a document-rooted JSON Pointer, or `None`
when it does not know.

`SourceLocation`: a `TypedDict` for a schema location translated back to its
document (D17): `documentUri: str`, `pointer: str` (document-rooted, unlike a
`schemaLocation`), `range: NotRequired[SourceRange]` (present when the
document's loader reported positions).

`SourcePosition`: a `TypedDict` for a point in source text: `line: int`
(1-based), `column: int` (1-based), `offset: int` (0-based).

`LocationHop`: a frozen dataclass, one resource on the path from a position out
to its document (P11). `resource_uri: str` (canonical, fragment-free);
`pointer: str` (plain text, from this resource's root to whatever the hop
*below* names — for the first hop, the position itself); `declared_id: str |
None` (the `$id` exactly as written, which is the only way to find a relative
one in the source text); `retrieval_uri: str | None` (set on the outermost hop
only, when the document was fetched under a name other than its `$id`). The
`LocationHop.location -> str` property is the hop's own canonical schema
location, so it can be pasted into a `$ref` or handed to `Engine.locate`.

`LocationChain`: a type alias, `tuple[LocationHop, ...]`, innermost first.

`format_location_chain(chain, *, message=None) -> str`: renders a chain for a
person. A one-hop chain formats to exactly `chain[0].location`, so the common
single-resource case reads as it always did; beyond one hop each enclosing
resource gets an indented line, and the `$id` as written is shown only when it
differs from the URI it produced.

`SourceRange`: a `TypedDict` for where a value sits in its document: `value:
SourceSpan`, `key: NotRequired[SourceSpan]` (present for an object member:
diagnostics about a missing or extra property point at the key, those about a
value at the value).

`SourceSpan`: a `TypedDict`: `start: SourcePosition`, `end: SourcePosition`.

`ParsedDocument`: a frozen dataclass returned by `parse_json_with_ranges`,
satisfying `LoadedResource` with the D17 extension: `value: JsonValue`, `uri:
str`, `get_range: Callable[[str], SourceRange | None]`.

`parse_json_with_ranges(text, uri) -> ParsedDocument`: parses `text` as JSON,
returning the value plus a source-position lookup by document-rooted JSON
Pointer (RFC 6901). Raises `JsonSyntaxError` (also a `ValueError`) on any
syntax error, including trailing content and the non-JSON extensions
`NaN`/`Infinity`. The reference loader for D17 positions; a loader can return
the result directly since `evaluate(..., positions=True)` and `Engine.locate`
read its `get_range`.

### Formats contract

`FormatDefinition`: one format: its predicate and the instance types it applies
to. A frozen dataclass: `test: FormatPredicate`, `types: tuple[TypeName, ...] =
("string",)` (an instance of a type not listed is vacuously valid),
`unavailable: str | None = None` (marks an entry that exists but cannot run in
this environment; asserting it fails loudly at registration), `import_path: str
| None = None` (`module:attribute`, lets a standalone module import the
predicate by name).

`FormatPredicate`: a type alias, `Callable[[Any], bool]`. Runs only on
instances of the definition's `types`; the `format` keyword guards the instance
type first.

`FormatTable`: a type alias, `Mapping[str, FormatDefinition]`. Injected into
`create_engine(formats=...)`; core never imports a table itself.

### JSON model

`JsonType`: a `StrEnum` of the seven JSON Schema primitive type names, spelled
as the spec spells them: `NULL = "null"`, `BOOLEAN = "boolean"`, `OBJECT =
"object"`, `ARRAY = "array"`, `NUMBER = "number"`, `STRING = "string"`,
`INTEGER = "integer"`.

`JsonValue`: a type alias for a JSON-representable value: `bool | int | float |
str | list[JsonValue] | dict[str, JsonValue] | None`. Non-finite floats (`NaN`,
`Infinity`) are outside this model even though `float` admits them; parse
boundaries reject them.

`json_equal(a, b) -> bool`: whether two JSON values are equal per the spec:
same type and same value, object member order insignificant, array order
significant, numeric equality mathematical (`1 == 1.0`). The only equality core
uses between `JsonValue`s; plain `==` conflates `True` with `1`.

### Regex

`RegexDialect`: a type alias, `Literal["ecma262", "python"]`. `ecma262` is the
default for every current draft; `python` hands the pattern to `re` untouched,
for callers migrating schemas that only ever ran under Python.

`RegexBackend`: a type alias, `Literal["re", "regex"]`.

`UnsafeRegexReport`: a frozen dataclass: `safe: bool`, `reason: str | None =
None`.

`detect_unsafe_regex(pattern) -> UnsafeRegexReport`: a conservative ReDoS
screen: nested unbounded quantifiers (D20). Necessary, not sufficient, so it
over-reports. Backs the opt-in `reject_unsafe_regex` engine option.

### Constants

`DIALECT_2019_09`: `"https://json-schema.org/draft/2019-09/schema"`.

`DIALECT_2020_12`: `"https://json-schema.org/draft/2020-12/schema"`.

`DIALECT_DRAFT_06`: `"http://json-schema.org/draft-06/schema"`.

`DIALECT_DRAFT_07`: `"http://json-schema.org/draft-07/schema"`.

`VOCAB_FORMAT_ASSERTION`:
`"https://json-schema.org/draft/2020-12/vocab/format-assertion"`.

## `json_schema_engine.core.lowering`

The vocabulary a keyword behavior's `lower()` emits, and the service the
compiler implements as `LoweringContext` (D1, D9; M6, M9). Public API since
M9: a custom keyword builds its compiled form from these names alone,
never from a private compiler module. See
[Lowering a custom keyword](guide/custom-keywords.md#lowering-a-custom-keyword)
for a worked example.

### Expressions

`Instance`: a frozen dataclass, no fields: the instance value under
evaluation at the lowering site. The module constant `INSTANCE` is the one
value every keyword shares.

`Const`: a frozen dataclass: `value: JsonValue` — a schema-derived JSON
constant; the emitter's only data entry point.

`Member`: a frozen dataclass: `target: Expr`, `key: str` — object member
access by a schema-derived key.

`Item`: a frozen dataclass: `target: Expr`, `index: Expr` — array element
access.

`Binding`: a frozen dataclass: `id: int` — a loop binding introduced by
`ForEachKey`/`ForEachIndex`/`CountRange`.

`TypeIs`: a frozen dataclass: `target: Expr`, `types: tuple[TypeName, ...]`
— a JSON type test, including the `integer` refinement (P2 discipline).

`HasKey`: a frozen dataclass: `target: Expr`, `key: Expr | str` — object
membership test: the key is a constant or a swept binding.

`Cmp`: a frozen dataclass: `op: CmpOp`, `left: Expr`, `right: Expr` —
numeric or string comparison of two expressions.

`Helper`: a frozen dataclass: `name: HelperName`, `args: tuple[Expr, ...]`
— a call into the closed helper set (core's own functions, never
re-implemented by emitted code).

`InConsts`: a frozen dataclass: `target: Expr`, `values: tuple[JsonValue,
...]` — `json_equal(target, v)` for some `v` in `values` (D9d); the
keyword states the membership, the emitter chooses the mechanism.

`RegexTest`: a frozen dataclass: `source: str`, `target: Expr` — an
unanchored search with a hoisted pattern, compiled through the engine's
`RegexCache`.

`FormatTest`: a frozen dataclass: `name: str`, `target: Expr` — a format
predicate applied to `target`, hoisted like a regex and resolved by `name`
from the engine's format table (M7).

`Not`: a frozen dataclass: `expr: Expr`.

`Logic`: a frozen dataclass: `op: Literal["and", "or"]`, `parts:
tuple[Expr, ...]`.

`ApplyExpr`: a frozen dataclass: `apply: LowerApply` — a subschema
application used for its verdict as a value (`if`'s condition, `not`'s
negated apply, `contains`' per-item probe); a bare use carries
`fold="discard"`.

`Cond`: a frozen dataclass: `test: Expr`, `then: Expr`, `orelse: Expr` —
`then` when `test` holds, else `orelse`.

`Covers`: a frozen dataclass: `fold: int`, `target: Expr` — whether the
coverage bound by a `CoverageFold` covers `target` (a swept name or
index).

### Cursors and applications

`Here`: a frozen dataclass, no fields — the current instance position. The
module constant `HERE` is the shared value.

`Child`: a frozen dataclass: `of: LowerCursor`, `segment: Expr | str |
int` — a child of a cursor: a constant member/index or a swept binding.

`Key`: a frozen dataclass: `binding: int` — `propertyNames`: the swept key
string itself is the instance.

`LowerApply`: a frozen dataclass: how a keyword's lowered body applies one
subschema. Fields: `path: tuple[str | int, ...]` (relative to the
keyword's value; loop bindings never appear in a path), `cursor:
LowerCursor`, `fold: Fold`, `sibling: str | None = None` (a sibling
keyword's value applied instead, e.g. `if` → `then`/`else`), `ref: str |
None = None` (a reference resolved at plan time against the unit's
lexical base; then `path` is ignored), `message: LowerMessage | None =
None`, `params: LowerParams | None = None`, `resolution: Literal[
"dynamic", "recursive"] | None = None` (marks a reference the plan
resolved against the dynamic scope, D8; carried only so the serializer can
find the planner's edge — the target is the plan's decision, never the
IR's).

### Statements

`If`: a frozen dataclass: `cond: Expr`, `then: tuple[Stmt, ...]`, `orelse:
tuple[Stmt, ...] = ()`.

`ForEachKey`: a frozen dataclass: `target: Expr`, `binding: int`, `body:
tuple[Stmt, ...]` — iterate an object's member names, binding each.

`ForEachIndex`: a frozen dataclass: `target: Expr`, `binding: int`, `body:
tuple[Stmt, ...]`, `start: int = 0` — iterate array indexes from `start`,
binding each.

`Fail`: a frozen dataclass: `message: LowerMessage`, `params: LowerParams
| None = None` — this keyword's assertion failure at the current cursor.

`Apply`: a frozen dataclass: `apply: LowerApply` — apply a subschema and
fold its verdict per `apply.fold`.

`CombineCheck`: a frozen dataclass: `message: LowerMessage`, `params:
LowerParams | None = None`, `count: int | None = None`, `passing: int |
None = None` — closes the immediately preceding run of
`any_may_pass`/`exactly_one` applies: the keyword fails with `message`
when the run's combined verdict fails. `count`/`passing` are bindings the
message and params may reference.

`CountRange`: a frozen dataclass: `target: Expr`, `binding: int`,
`count_when: Expr`, `minimum: int`, `maximum: int | None`, `message:
LowerMessage`, `params: LowerParams | None = None`, `matched: int | None =
None`, `count: int | None = None` — `contains`' shape: probe every index,
count the matches, fail when the count falls outside `[minimum, maximum]`
(`None` = unbounded); `matched`, when set, is a list binding that collects
the matching indexes.

`Collect`: a frozen dataclass: `binding: int` — bind an empty list to
accumulate dependency data.

`Append`: a frozen dataclass: `binding: int`, `value: Expr`, `unique: bool
= False` — append `value` to a `Collect` binding.

`Produce`: a frozen dataclass: `value: Expr` — the keyword's dependency
data at the current cursor: the value `ctx.produce()` would carry.
Reached only along the keyword's accepting path; elided unless a tracked
consumer reads it.

`CoverageFold`: a frozen dataclass: `binding: int`, `half: Literal["names",
"indexes"]`, `consumes: tuple[str, ...]`, `contains_id: str | None =
None`, `prefix_id: str | None = None` — bind the runtime evaluated
coverage a tracked consumer reads: the region channel's productions from
the producers in `consumes`, folded by core's coverage folds.

`Annotate`: a frozen dataclass, no fields — the keyword's own value as an
annotation at the current cursor (§4 rule 2); elided when the artifact's
selection rules the keyword out.

### The lowering service

`StaticCoverage`: a frozen dataclass: `names: frozenset[str]`, `patterns:
tuple[str, ...]`, `covers_all_names: bool`, `prefix_count: int`,
`covers_all_indexes: bool` — the statically known evaluated coverage of a
schema object (D9a), for `unevaluated*` lowerings.

`LoweringContext`: a `Protocol`: services available to one keyword's
`lower()` (the plan-time mirror of `KeywordContext`, D3), implemented by
the compiler.

- `LoweringContext.instance -> Expr`: the instance expression at this
  lowering site.
- `LoweringContext.schema -> Mapping[str, JsonValue]`: the keyword's
  containing schema object.
- `LoweringContext.static_coverage() -> StaticCoverage | None`: the
  planner's static coverage for this schema object; `None` means the
  planner did not license a static consumer here (tracked at runtime
  instead, `runtime_coverage()`).
- `LoweringContext.runtime_coverage() -> bool`: whether the planner tracks
  this schema object's consumers at runtime (M9): the consumer folds the
  region channel instead of a static coverage. Exactly one of this and
  `static_coverage()` is available to a consumer; neither means a planner
  bug.
- `LoweringContext.emit(*stmts) -> None`: appends statements to the
  keyword's lowered body.
- `LoweringContext.binding() -> int`: allocates a loop binding id.

`LowerFn`: a type alias, `Callable[[JsonValue, LoweringContext], None]` —
the shape of `KeywordBehavior.lower`.

`lower_nothing(_value, _ctx) -> None`: the lowering of a keyword that
asserts nothing (structural, annotation-only, and sibling-driven
keywords).

### Constructors

Shorthands the built-in keyword modules use to build IR nodes without
naming the dataclasses directly; a custom keyword's `lower()` reaches for
the same names.

`INSTANCE`: the shared `Instance()` value.

`HERE`: the shared `Here()` value.

`const(value) -> Const`

`type_is(target, *types) -> TypeIs`

`has_key(target, key) -> HasKey`

`cmp(op, left, right) -> Cmp`

`helper(name, *args) -> Helper`

`in_consts(target, values) -> InConsts`

`regex_test(source, target) -> RegexTest`

`format_test(name, target) -> FormatTest`

`not_(expr) -> Not`

`and_(*parts) -> Logic` (`op="and"`)

`or_(*parts) -> Logic` (`op="or"`)

`child(of, segment) -> Child`

`key(binding) -> Key`

`when(cond, then, orelse=()) -> If`

`fail(message, params=None) -> Fail`

`apply(path, cursor, fold="all_must_pass", *, sibling=None, ref=None,
message=None, params=None, resolution=None) -> Apply`

`apply_expr(path, cursor, fold="discard", *, sibling=None, ref=None) ->
ApplyExpr`

`combine_check(message, params=None, *, count=None, passing=None) ->
CombineCheck`

`annotate() -> Annotate`

`cond(test, then, orelse) -> Cond`

`covers(fold, target) -> Covers`

`collect(binding) -> Collect`

`append(binding, value, *, unique=False) -> Append`

`produce(value) -> Produce`

`coverage_fold(binding, half, consumes, *, contains_id=None, prefix_id=None)
-> CoverageFold`

### Type aliases

`TypeName`: `Literal["null", "boolean", "object", "array", "number",
"string", "integer"]` — the spec's type names plus the `integer`
refinement.

`HelperName`: `Literal["json_equal", "is_multiple_of",
"has_duplicate_items", "first_duplicate_pair", "length_of",
"code_point_length", "json_type_name"]` — the closed helper set `Helper`
may name.

`CmpOp`: `Literal["<", "<=", ">", ">=", "==", "!="]`.

`Expr`: the union of every expression node: `Instance | Const | Member |
Item | Binding | TypeIs | HasKey | Cmp | Helper | InConsts | RegexTest |
FormatTest | Not | Logic | ApplyExpr | Cond | Covers`.

`LowerCursor`: `Here | Child | Key`.

`Fold`: `Literal["all_must_pass", "any_may_pass", "exactly_one", "negate",
"discard"]` — how an apply's verdict folds into its keyword's verdict.

`LowerMessage`: `tuple[str | Expr, ...]` — an error message built from
literal text and runtime-computed parts, exactly as `evaluate` reports it.

`LowerParams`: `Mapping[str, Expr]` — structured error params, exactly as
`evaluate` reports them.

`Stmt`: the union of every statement: `If | ForEachKey | ForEachIndex |
Fail | Apply | CombineCheck | CountRange | Collect | Append | Produce |
CoverageFold | Annotate`.

## `json_schema_engine.compiler`

Consumes only `analyze()` facts and each keyword's optional `lower()` IR from
`json_schema_engine.core`, never keyword names (D1). Anything the compiler
cannot lower trampolines to the interpreter, so an artifact is exactly as
correct as `Engine.evaluate` and never less complete: tier choice is a
performance decision, not a semantic one. Compile only after registration on
the engine is complete; an artifact binds a snapshot of the schema and dialect
registries taken at compile time.

### Functions

`build_plan(engine, schema_uri, *, max_dynamic_winners=16) -> CompilationPlan`:
plans the compilation of one registered root schema: classifies every reachable
schema node as a static (compilable) or interpreted (trampoline) unit.
Conservative by design; anything uncertain falls back to the interpreter.
`max_dynamic_winners` caps how many declaring resources a `$dynamicRef`/
`$recursiveRef` anchor whose target differs by path may be specialized for
(the units below each declarer are compiled once per declarer, so every copy's
site is a static edge); `0` never specializes, and such sites island. Negative
values raise `ValueError`.

`compile_evaluator(engine, schema_uri, *, annotations=False, max_depth=None,
conservative=False, max_dynamic_winners=16) -> CompiledEvaluator`: compiles a registered root schema
into an evaluator serving every output format but `flag` (M9). The
annotation selection is fixed at compile time (ruled-out annotations are
never recorded); every consumer is tracked at runtime and every branch
runs, so the errors, annotations, dropped records, output document, and
trace equal `Engine.evaluate`'s. Interpreted islands run on the same
state.

`CompiledEvaluator`: a frozen dataclass: `evaluate(instance, *,
output="list", error_params=False, verbose=None, trace=False,
positions=False) -> Result` (the engine's own output controls, rejected the
same way with `OutputOptionsError`), `plan: CompilationPlan`, `module:
ast.Module`, `source: str`, `annotations: AnnotationsOption`.

`compile_validator(engine, schema_uri, *, max_depth=None, conservative=False,
max_dynamic_winners=16) -> CompiledValidator`: compiles a registered root schema
into a verdict-only validator. `max_depth` defaults to the engine's;
`conservative=True` turns the emitter's optimizations off (no inlining, no set
specialization): the differential fuzzer referees both configurations;
`max_dynamic_winners` is the planner's specialization cap (see `build_plan`).

`emit_standalone(engine, schema_uri, *, max_depth=None, max_dynamic_winners=16)
-> str`: emits a
registered root schema as a self-contained validator module: source text whose
`validate(instance) -> bool` agrees with `Engine.evaluate` on every instance,
importable without the compiler package. Raises `StandaloneUnsupportedError`
when the plan has any interpreted unit or the engine's regex backend is not
`"re"`.

`explain_compilation(plan) -> CompilationExplanation`: a read-only projection
of a plan for census gates and diagnostics: counts of static versus interpreted
units, grouped by `FallbackCause`, the dynamic sites resolved at plan time, and
the anchors specialized per dynamic context.

### Artifacts and plan types

`CompiledValidator`: a frozen dataclass: the compiled flag validator. Fields:
`validate: Callable[[JsonValue], bool]`, `plan: CompilationPlan`, `module:
ast.Module` (the emitted module), `source: str` (`ast.unparse(module)`, for
diagnostics and goldens).

`CompilationPlan`: a frozen dataclass: `root_key: str`, `units: dict[str,
PlannedUnit]` (insertion order is planning order, deterministic function
numbering), `patterns: tuple[str, ...]` (every regex source any static unit
tests), `formats: tuple[str, ...]` (every format name any static unit asserts,
M7), `targets: tuple[PlannedUnit, ...]` (interpreted units in stable order;
index = target-table slot), `coverage_ids: frozenset[str] = frozenset()` (M9:
producer ids some tracked consumer reads; only their productions are recorded
on a channel), `split_anchors: tuple[SplitAnchor, ...] = ()` (anchors whose
sites were specialized per dynamic context).

`PlannedUnit`: a mutable, slotted dataclass: one schema node in the plan, keyed
by its canonical location plus, once the plan has split an anchor, its dynamic
context (the key is then the location followed by `|dynamic:<anchor>=<winner>`
or `|recursive=<winner>` per bound anchor; `|` cannot appear raw in a URI).
Copies of one location share one `SchemaRef` and report the same location.
Fields: `key: str`, `ref: SchemaRef` (internal type), `context: tuple[tuple[str,
str, str], ...] = ()` (sorted `(kind, anchor, winner)` triples: the first
declaring resource bound on the path for each split anchor), `kind:
Literal["static", "interpreted"] = "static"`, `cause:
FallbackCause | None = None`, `edges: list[PlannedApplication] = []` (resolved
outgoing edges, in keyword order, static units only), `coverage: StaticCoverage
| None = None` (static evaluated coverage licensed for this object's consumers,
D9a; internal type), `reaches_interpreted: bool = False` (true when some apply
path from here can reach an interpreted unit), `use_count: int = 0` (planned
edges targeting this unit), `tracked: bool = False` (M9: this unit owns a
coverage channel its consumers fold at runtime, no static licence), `in_region:
bool = False` (M9: reachable in place from a tracked unit, and produces into
the channel it is handed). Property `PlannedUnit.takes_channel -> bool`:
`tracked or in_region` — both take the channel as a parameter and never
inline. Method `PlannedUnit.interpret(cause) -> None`: marks the unit
interpreted with the given `FallbackCause` and clears its edges.

`PlannedApplication`: a frozen dataclass: one application edge out of a unit,
resolved at plan time. Fields: `keyword: str`, `app: SubschemaApplication`
(from `json_schema_engine.core.dialect`), `target_key: str`, `dynamic:
DynamicResolution | None = None` (set on a dynamic-reference edge the plan
resolved).

`DynamicResolution`: a frozen dataclass: how a `$dynamicRef`/`$recursiveRef`
edge was resolved at plan time. Field: `winner: str | None`, the resource
whose anchor won, or `None` when the reference behaved like `$ref`.

`FallbackCause`: a type alias, `Literal["dynamic", "unlowerable", "cycle",
"non_schema"]`: why a unit is interpreted: a dynamic-reference site whose
anchor binds more declaring resources than `max_dynamic_winners` allows the
plan to specialize for (or a dynamic keyword without a resolution fact); a
keyword without `lower()`, an unresolvable edge, or a consumer without static
coverage; a possible in-place cycle; or a reference into non-schema data.

`CompilationExplanation`: a frozen dataclass: `total_units: int`,
`static_units: int`, `interpreted_units: int`, `causes: Mapping[FallbackCause,
int]`, `interpreted_keys: tuple[str, ...]`, `reaches_interpreted: int`,
`resolved_dynamic_sites: tuple[ResolvedDynamicSite, ...] = ()`, `tracked_units:
int = 0` (M9: consumers tracked at runtime), `region_units: int = 0` (M9: units
reachable in place from a tracked consumer's region), `split_anchors:
tuple[SplitAnchor, ...] = ()` (the plan's specialized anchors),
`specialized_units: int = 0` (units carrying a non-empty dynamic context).

`ResolvedDynamicSite`: a frozen dataclass: a dynamic-reference site the plan
compiled as a static edge. Fields: `unit: str` (the site's unit key),
`keyword: str`, `ref: str`, `target: str` (the target's unit key), `winner:
str | None`, `location: str` and `target_location: str` (the schema locations
the two units report; copies of one location share them).

`SplitAnchor`: a frozen dataclass: an anchor the plan specialized per dynamic
context. Fields: `kind: Literal["dynamic", "recursive"]`, `anchor: str` (for
the recursive kind, the sentinel `"$recursiveAnchor"`), `winners: tuple[str,
...]` (the declaring resources some unit bound, sorted).

### Errors

`FormatTableError(JsonSchemaEngineError)`: a compiled artifact asserts a format
the engine's table cannot serve.

`StandaloneUnsupportedError(JsonSchemaEngineError)`: `emit_standalone` refused:
the schema needs the interpreter at evaluation time, or the engine's regex
backend cannot be emitted.

## `json_schema_engine.formats`

One table per built-in dialect, each entry a predicate implemented from the
format's RFC and verified against the official test suite. Core never imports
this package; inject a table with `create_engine(formats=...)`.

### Tables

`FORMATS_2020_12`: a `FormatTable` with the nineteen formats 2020-12 §7.3
defines: `date-time`, `date`, `time`, `duration`, `email`, `idn-email`,
`hostname`, `idn-hostname` (unavailable without the `idna` extra), `ipv4`,
`ipv6`, `uri`, `uri-reference`, `iri`, `iri-reference`, `uuid`, `uri-template`,
`json-pointer`, `relative-json-pointer`, `regex`.

`FORMATS_2019_09`: the same `FormatTable` object as `FORMATS_2020_12`; 2019-09
§7.3 names the same nineteen formats.

`FORMATS_DRAFT_07`: `FORMATS_2020_12` minus `uuid` and `duration` (draft-07
§7.3).

`FORMATS_DRAFT_06`: `FORMATS_2020_12` restricted to `date-time`, `email`,
`hostname`, `ipv4`, `ipv6`, `uri`, `uri-reference`, `uri-template`,
`json-pointer` (draft-06 §8.3).

### Lookup

`format_table_for(dialect_uri) -> FormatTable`: the standard table for a
built-in dialect URI (fragment ignored). Raises `ValueError` for any other URI.

### Shared helper

`anchored(fragment) -> re.Pattern[str]`: compiles an ABNF fragment as a
whole-string match (`\A(?:fragment)\Z`); used by every predicate module in this
package and available for a caller building a compatible format.

## `ecma_regex`

A standalone package with no dependency on `json_schema_engine` (P1): one regex
AST, a front-end parser, back-ends that emit for `re`/`regex`, and a
`search`-only matcher with ECMA-262 `u`-mode semantics. Untranslatable patterns
raise at translation, not on the hot path.

### `compile` and the pattern object

`compile(pattern, *, flags="", backend="re") -> EcmaRegex`: parses, translates,
and compiles `pattern` in one step. Raises `EcmaRegexSyntaxError` for an
invalid pattern and `UnsupportedPatternError` for a valid pattern the backend
cannot express.

`EcmaRegex`: a frozen dataclass: an ECMA-262 pattern compiled for a Python
backend. Fields: `pattern: str` (the original source), `flags: str` (the
original flag string), `translated: str` (the backend pattern that was
compiled), `backend: BackendName`, `compiled: CompiledPattern` (the underlying
`re.Pattern` or `regex` equivalent). Method `EcmaRegex.search(string) -> bool`:
whether the pattern matches anywhere in `string` (`RegExp.prototype.test`
semantics: unanchored, yes/no only). Nothing here is cached; build one per
pattern and hold on to it, or cache in front of `compile`.

`CompiledPattern`: a `Protocol`: the slice of a compiled backend pattern this
package relies on, `search(string, /) -> object | None`.

`Pattern`: a frozen dataclass: a parsed pattern, `root: Node` and `flags:
Flags`. Returned by `parse`.

`Flags`: a frozen dataclass, the subset of ECMA-262 `RegExp` flags this package
models: `ignore_case: bool = False`, `multiline: bool = False`, `dot_all: bool
= False`, `unicode: bool = True` (always true; only `u`-mode is implemented).
Property `Flags.source -> str`: the flags as an ECMA-262 flag string, in
canonical order (`s`, `i`, `m`, `u`).

### Lower-level functions

`parse(pattern, *, flags="") -> Pattern`: parses `pattern` as an ECMA-262
pattern under `u`-mode semantics. `flags` is an ECMA-262 flag string; `i`, `m`,
`s`, `u` are accepted (`u` is implied). Raises `EcmaRegexSyntaxError` for an
invalid pattern and `UnsupportedPatternError` for a flag this package does not
model.

`translate(pattern, *, backend="re") -> str`: emits a backend pattern string
with ECMA-262 semantics, meant to be compiled with the flags `translate_flags`
returns. Raises `UnsupportedPatternError` when the chosen backend cannot
express the pattern (a variable-width lookbehind on `re`, or an uncomputable
Unicode property).

`translate_flags(pattern) -> int`: backend compile flags that cannot be
expressed in the pattern text. Only `re.IGNORECASE` is ever returned: `m` and
`s` are spelled out in the translated pattern, because Python's own
`MULTILINE`/`DOTALL` use a narrower line-terminator set than ECMA-262.

`star_height(pattern) -> int`: the nesting depth of unbounded quantifiers (`a`
is 0, `a+` is 1, `(a+)+` is 2; bounded quantifiers like `a{2,3}` do not count,
`a{2,}` does). A star height of 2 or more is the classic necessary (not
sufficient) screen for catastrophic backtracking.

`width(node) -> tuple[int, int | None]`: the `(minimum, maximum)` number of
code points `node` consumes; `maximum` is `None` when unbounded or not
statically known (a backreference).

`BackendName`: a type alias, `Literal["re", "regex"]`.

### AST and errors

`Node`: a type alias for any pattern AST node: the union of every node type
below except `Pattern` itself.

`Alternation`: a frozen dataclass: `options: tuple[Node, ...]` (`a|b|c`).

`Concatenation`: a frozen dataclass: `parts: tuple[Node, ...]`, a sequence of
terms; an empty tuple is the empty alternative.

`Literal`: a frozen dataclass: `code_point: int`, a single code point matched
literally.

`Dot`: a frozen dataclass with no fields: `.`, every code point except a line
terminator unless the `s` flag is set.

`Anchor`: a frozen dataclass: `kind: Literal["start", "end"]` (`^` or `$`).

`WordBoundary`: a frozen dataclass: `negated: bool` (`\b` when `False`, `\B`
when `True`).

`Group`: a frozen dataclass: `body: Node`, `capturing: bool`, `index: int |
None = None` (one-based capture index, `None` when non-capturing), `name: str |
None = None`.

`Backreference`: a frozen dataclass: `index: int | None = None` (`\1`), `name:
str | None = None` (`\k<name>`).

`Lookaround`: a frozen dataclass: `body: Node`, `direction: Literal["ahead",
"behind"]`, `negated: bool`.

`Quantifier`: a frozen dataclass: `target: Node`, `min: int`, `max: int | None`
(`None` for unbounded), `greedy: bool`.

`CharClass`: a frozen dataclass: `negated: bool`, `items: tuple[ClassItem,
...]` (`[...]` or `[^...]`).

`ClassEscape`: a frozen dataclass: `kind: Literal["d", "D", "w", "W", "s",
"S"]` (`\d`, `\D`, `\w`, `\W`, `\s`, or `\S`).

`ClassRange`: a frozen dataclass: `low: int`, `high: int`, an inclusive
code-point range inside a character class.

`ClassItem`: a type alias, `Literal | ClassRange | ClassEscape |
PropertyEscape` (the AST node types, not `typing.Literal`): one member of a
character class.

`PropertyEscape`: a frozen dataclass: `name: str` (`General_Category`,
`Script`, `Script_Extensions`, or a binary property name), `value: str | None`
(the property value for `name=value` form, `None` for the lone-name form),
`negated: bool` (`\p{...}` / `\P{...}`).

`EcmaRegexError(message, position)`: base class for every error this package
raises. `position` is a zero-based index into the source pattern (or, for flag
errors, into the flag string).

`EcmaRegexSyntaxError`: a subclass of `EcmaRegexError`: the pattern is not a
valid ECMA-262 pattern under `u` semantics.

`UnsupportedPatternError`: a subclass of `EcmaRegexError`: the pattern is valid
ECMA-262 but cannot be translated faithfully by the chosen backend (e.g. a
variable-width lookbehind on `re`, or an uncomputable Unicode property).

