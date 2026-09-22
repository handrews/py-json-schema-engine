# Changelog

All notable changes to `json-schema-engine` (the Python engine). The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/) with the 0.x caveat that
minor versions may change public API.

## [Unreleased]

### Changed

- **Duplicate identifiers are now registration errors (DESIGN.md P12).**
  Two different schemas may no longer claim one resource URI
  (`DuplicateResourceError`), and two different schema objects may no longer
  claim one anchor name within a resource (`DuplicateAnchorError`). Both were
  silent last-write-wins, so one schema shadowed the other and a reference
  resolved to whichever the walk reached last. The anchor case was worse than
  shadowing: because a dynamic anchor is also a plain anchor, `$anchor: "n"` on
  one object and `$dynamicAnchor: "n"` on another left `$ref` and `$dynamicRef`
  resolving the same fragment to *different* schemas. **Breaking:** a document
  that registered before may now raise. Re-registering an *equal* document is
  still a no-op, and one object carrying both `$anchor` and `$dynamicAnchor`
  under one name is still fine. No case in the official test suite, the bundled
  metaschemas, or this repo's fixtures is affected.
- **Registration is now all-or-nothing (DESIGN.md P13).** A document whose
  registration raises leaves the registry exactly as it found it, so an engine
  stays usable after a caught registration error. Previously the half-indexed
  document stayed registered and evaluable, missing every anchor and
  sub-resource past the failure point, with partial contributions to the
  produced/consumed id sets that drive annotation elision — so the failure
  surfaced as a wrong answer rather than a loud one. Registration cost is
  unchanged (measured: 1.27 ms either way on the OAS 3.1 schema).
- Because a failed registration is rolled back, `Engine.locate` can no longer
  place an error from one: there is no registered document to place it
  against. The error carries `schema_source` instead (below).
- **`validate_schemas` now checks a document before registering it**, so one
  that fails its metaschema is no longer registered. Previously the check ran
  after the walk and nothing removed the document, leaving a caller who asked
  for validation, caught the typed rejection, and carried on holding an invalid
  schema that still evaluated. The option remains opt-in and off by default —
  validating the OAS 3.1 schema costs 2.0 ms against 56.8 ms, a 28× difference
  on registration. A document broken both ways at once now reports
  `SchemaValidationError` rather than `InvalidSchemaError`.
- A document-level `schema_location` is now `uri#` rather than a bare `uri`,
  so every location is a `base#pointer` (P10) that `Engine.locate` and
  `Engine.location_chain` accept. Affects `SchemaValidationError`,
  `UnknownVocabularyError`, and `FormatsRequiredError`.

### Added

- `JsonSchemaEngineError.schema_source`: the failing position seen physically
  (D17) — the document, the document-rooted pointer, and the source range when
  a loader reported one. Captured as the error leaves the engine, so it
  survives a rolled-back registration. A `SourceRange` is plain integers, so an
  error held in a log buffer keeps nothing alive.
- **Location chains (DESIGN.md P11).** A canonical `base_uri#pointer` names a
  position exactly and still may not locate it: in a bundled document the base
  may be an embedded `$id` the reader never knew was there, and a relative
  `$id` resolves to a URI that appears nowhere in their file.
  `Engine.location_chain(location)` returns the position followed by each
  enclosing resource, innermost first, with the pointer to the one below it and
  the `$id` as written; the outermost hop names the retrieval URI when it
  differs from the `$id`. Every hop's `.location` is a `$ref` value and an
  `Engine.locate` argument, so the chain composes with source positions rather
  than duplicating them. New exports: `LocationChain`, `LocationHop`,
  `format_location_chain`.
- Every error leaving `register_schema`, `load_schema`, `load`, or `evaluate`
  carries its `location_chain`, in both the interpreter and the compiled tier.
  `str(error)` appends the chain **only** past one hop, so a single-resource
  schema's message is byte-identical to before.
- `UnresolvableReferenceError` carries the resolution that failed:
  `reference` (as written in the schema), `resolved_against` (the base URI in
  force at that position), and `resolved_to` (the absolute URI the two
  produced). A relative `$ref` under an embedded `$id` resolves somewhere that
  looks unrelated to anything in the document, and previously the message named
  only the URI that came out. A pointer miss also names the failing segment and
  the prefix that matched, so `#/a/b/c/d` failing at `b` no longer reads exactly
  like the same pointer failing at `d`.

### Fixed

- **`Engine.locate` resolves an anchor fragment.** An anchor is a fragment,
  not a pointer, so `locate("urn:x#spot")` percent-decoded it into `spot` —
  a string with no leading `/` that names nothing — and returned a
  `SourceLocation` holding it. It now goes through the anchor index, as
  `Engine.location_chain` does, so both public location APIs answer the same
  question about the same string. An unknown anchor returns `None`.
- **An error raised during evaluation now carries a schema location.** The
  registration walk has always back-filled `schema_location` onto an error
  escaping a keyword's `analyze()`, but the evaluation tier had no equivalent,
  so an `UnresolvableReferenceError` from a `$ref` actually followed at
  evaluation time reached the caller with `schema_location` still `None` —
  naming neither the reference nor the schema that followed it. It now names
  the keyword's own position, encoded per P10 and accepted by `Engine.locate`.

- **A schema location is now a URI (DESIGN.md P10).** The JSON Pointer in
  `schemaLocation`, `absoluteKeywordLocation`, and the `schema_location`
  carried by a raised error is percent-encoded per RFC 3986's `fragment`
  production, so a property named `a b` is reported at
  `#/properties/a%20b` and one named `100%` at `#/properties/100%25`.
  Previously the pointer was emitted raw, which produced strings that were
  not URIs, could not be used as a `$ref`, and did not survive being handed
  back to `Engine.locate` — while the registry already percent-decoded on
  the way in. Ordinary pointers are unaffected: `/`, `:`, `@`, and the
  sub-delimiters stay literal, so `#/properties/count/type` reads exactly
  as before.
- `Engine.locate` decodes the fragment of the location it is given, and
  still returns a plain-text `pointer`.
- `evaluationPath`, `keywordLocation`, `inputLocation`, `instanceLocation`,
  and `SourceLocation.pointer` are unchanged: they are JSON Pointers, not
  URIs, and are never encoded.

### Added

- `json_schema_engine.core.uri.pointer_fragment`,
  `pointer_from_fragment`, and `schema_location`: the single pair of
  conversions between a plain-text JSON Pointer and its URI fragment form,
  plus the builder every emitted schema location goes through.

## [0.0.3] - 2026-09-21

### Added

- `compile_evaluator`: compiles a registered root schema into an evaluator
  serving every output format the interpreter does (errors, annotations,
  dropped records, the application trace), not only the verdict `flag`
  level.
- Plan-time resolution of `$dynamicRef`/`$recursiveRef`: a reference site
  whose target is the same on every path that can reach it compiles as an
  ordinary static edge instead of falling back to the interpreter;
  `explain_compilation` reports such sites through `resolved_dynamic_sites`.
- Runtime coverage tracking: an `unevaluated*` consumer whose evaluated
  coverage depends on runtime branching (an `anyOf`/`oneOf` alternative, an
  `if`'s condition) compiles directly instead of islanding, folding a
  runtime coverage channel instead of a static licence.
- Public `json_schema_engine.core.lowering`: the compiler lowering IR a
  custom keyword's `lower()` is built from, previously private to the
  engine's own keyword modules.

### Changed

- `first_duplicate_pair` returns a list.
- Compiled error messages now match the interpreter's for `oneOf`,
  `contains`, `uniqueItems`, and `type`.
- A dialect refusing unknown keywords no longer compiles those units
  silently: an unknown keyword under such a dialect now falls back to the
  interpreter like any other unlowerable case, rather than being planned
  as if the keyword were absent.

## [0.0.2] - 2026-09-21

The first functional release. Everything below is new relative to the
0.0.1 name reservation.

### Added

- `json_schema_engine.core`: the interpreter tier. Draft 2020-12 (default),
  2019-09, draft-07, and draft-06 with each draft's own semantics
  (`$dynamicRef`, `$recursiveRef`, `$ref` sibling handling); `$vocabulary`
  processing with the bundled metaschemas; loaders for remote references
  with source-position reporting (`parse_json_with_ranges`,
  `positions=True`, `Engine.locate`); metaschema validation on request
  (`validate_schemas=True`); the `flag`, `basic`, `detailed`, `verbose`,
  `list`, and `hierarchical` output formats with annotation selection,
  error params, verbose levels, and the application trace; ECMA-262
  regular expressions through `ecma-regex`, with a Python `re`
  passthrough dialect and the optional `regex` backend; the
  `reject_unsafe_regex` screen, `max_depth`, and O(n) `uniqueItems`.
- `json_schema_engine.compiler`: `compile_validator` (a verdict-only
  Python function bound to a registry snapshot, trampolining into the
  interpreter for whatever it cannot lower), `emit_standalone` (a module
  importable without the compiler), and `explain_compilation`.
- `json_schema_engine.formats`: every format the four drafts define,
  implemented from the RFCs and verified against the official
  `optional/format` suites; the `idna` extra for IDNA2008
  (`idn-hostname`, A-label checks in `hostname`); assertion opt-in through
  `create_engine(formats=..., assert_formats=...)` and the 2020-12
  format-assertion vocabulary.
- Every distribution portion ships a `py.typed` marker.

### Changed

- The distribution depends on `ecma-regex>=0.1,<0.2`.
- The sdist no longer carries the test tree, which needs the repository's
  test-kit and the suite submodule.

## [0.0.1] - 2026-09-20

Name reservation on PyPI; no functionality.
