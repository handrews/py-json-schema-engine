# json-schema-engine (Python): engineering design

**Status:** living design contract. M0–M9 complete (2026-09-21); M10 next. Derived from the
TypeScript engine's design record
([handrews/json-schema-engine `DESIGN.md`](https://github.com/handrews/json-schema-engine/blob/main/DESIGN.md)),
whose decisions were validated by a complete implementation (all official
suites for 2020-12, 2019-09, draft-07, draft-06, and draft-04 in two tiers).
This document restates those decisions for Python, marks each as carried,
amended, or not applicable, and adds Python-specific decisions (P-series).
It is self-contained: a reader of this repository never needs the TS repo.

**How to use this document:** it is the contract for implementation
sessions. A fresh session (any model) should be able to pick up one milestone
from §6 with only this file, the repo, and the referenced specs. Each
milestone names a mechanical done-signal; a milestone is not done until its
signal is green. The model-tier column is advisory routing: "patterned"
milestones follow exemplars and suit Sonnet-class sessions; "judgment"
milestones change interfaces or semantics and go to Opus/Fable-class
sessions.

**Semantic target:** the IETF draft-03 record model — exact-value
annotations separate from keyword dependency information, §12.2 relevance —
and the output model of the TS engine's ADR 0003 (formats by name, three
levels, orthogonal controls). D4–D6 and §4 state them. References:
[draft-ietf-jsonschema-json-schema-02](https://www.ietf.org/archive/id/draft-ietf-jsonschema-json-schema-02.html),
the 2020-12 spec pair, the 2019-09 / draft-07 / draft-06 / draft-04 specs,
the machines-oriented output proposal, and the
[official test suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite)
(submodule `test-suite/`).

**This is not a port.** The architecture, interfaces, and channel semantics
are the same; the code is written in Python idioms from this document and the
specs. Reading the TS source for semantics and test expectations is
permitted and encouraged; transliterating it is not the goal.

## 0. IP policy (D15, restated first because it binds every session)

Implementation from the JSON Schema specifications and the official test
suite only. Other validators — AJV, Hyperjump, python-jsonschema,
fastjsonschema, and any other — may be **executed** as correctness oracles
or benchmark subjects; their source is never read for implementation,
ported, or translated. The TS json-schema-engine is the exception: it is
this project's own prior work. Compatibility layers reproduce public API
surfaces only. **This policy binds every implementation session, including
subagents — restate it in any task prompt.**

## 1. Decision register

Each row carries the TS decision ID so the two records stay aligned.
Status: **carried** (unchanged), **amended** (Python changes the mechanism,
not the intent), **N/A** (JavaScript-only).

| #   | Decision                       | Status  | Choice for Python                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------ | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Execution model                | amended | Two tiers, one keyword registry. The interpreter (`json_schema_engine.core`) is the reference semantics. The compiler (`json_schema_engine.compiler`, M6) consumes only `analyze()` facts and each keyword's optional `lower()` IR, never keyword names. **Amendment:** the compiler emits a Python `ast` tree, never source text; injection is unrepresentable because schema data only ever becomes `ast.Constant` nodes. The trampoline into the interpreter for dynamic islands is unchanged. Delivered at M6: `core/lowering.py` (the IR), `KeywordBehavior.lower`, `StaticFacts.applications`, `evaluate_fragment`; `json_schema_engine.compiler` (planner, `ast` emitter, runtime, standalone). The trampoline is one-way: interpreted code never re-enters compiled code, so island channel flow is strictly upward. M9: the compiled tier serves every output format through `compile_evaluator`: evaluator units take the shared core `EvalState`, a real `PathNode`, and a real `Cursor`, record through core's `channel_ops` helpers, and islands run on the same state (`apply_fragment`), so their records and trace nodes need no grafting; result assembly is the interpreter's own (`assemble_evaluation`). |
| D2  | Keyword identity               | carried | Keywords identified by URI; a vocabulary is a named map of keyword URIs; a dialect is an ordered set of vocabularies; drafts are predefined dialects. All data, no privileged built-ins. `KeywordBehavior` is a frozen dataclass of callables (§3), not a class hierarchy.                                                                                                                                                                                                                        |
| D3  | Keyword interface              | carried | `analyze(value, context) -> StaticFacts` + `evaluate(value, cursor, ctx) -> bool` (§3). Applicators request subschema application through the engine; the engine owns path, scope, and frame bookkeeping in exactly one place (`evaluator.py`).                                                                                                                                                                                                                                                 |
| D4  | Keyword communication          | carried | Frame-scoped record channel (§4) with two record kinds: annotation records (the keyword's own value; output) and dependency records (computed data for other keywords; never output). Records merge to the parent frame only on success.                                                                                                                                                                                                                                                         |
| D5  | Annotation selection           | carried | `annotations=False \| True \| AnnotationSelection`: allow-lists by keyword name and vocabulary URI, deny-lists subtracted after, a `keep` predicate over the rendered unit. Internal consumers always see the channel. The interpreter elides at annotate time what the selection rules out and dependency records nothing consumes. Producers declare `produces`, consumers declare `consumes`, or `UndeclaredProductionError` / `UndeclaredConsumptionError` is raised — never a silently empty channel. Complete at M5: every suite case is evaluated under `flag` (elided) and under `hierarchical`+verbose (nothing elided) and the verdicts must agree. |
| D6  | Output                         | carried | Formats by name: `flag`, `basic`, `detailed`, `verbose` (draft-03 §13) and `list`, `hierarchical` (machines-oriented proposal); three levels (minimal, relevant, verbose); orthogonal controls `annotations`, `error_params`, `positions`, `trace`. Unsupported combinations raise `OutputOptionsError` before evaluation. Each format fixes its own document structure and field vocabulary (`basic` speaks draft-03's `keywordLocation`/`absoluteKeywordLocation`/`instanceLocation`; `list`/`hierarchical` speak the proposal's `evaluationPath`/`schemaLocation`/`instanceLocation`), while the flat `Result.errors`/`Result.annotations` surface always carries the engine's native `evaluationPath`/`schemaLocation`/`inputLocation`. Python-side option names are snake_case (P8). Complete at M5: tracing is opt-in in the evaluator (`TraceNode` per application, `KeywordTrace` per non-structural keyword); `records.to_render_node` turns the trace into the engine-free `RenderNode` tree that `output.py` renders; `verbose` (the format, or `verbose=True` on `list`/`hierarchical`) exposes `Result.dropped_errors`/`dropped_annotations`; `trace=True` renders `Result.trace` with decoded segments and `errorIndexes` into `Result.errors`. |
| D7  | Async boundary                 | amended | `evaluate` (and later `compile`) are synchronous. **Amendment (P4):** loaders are synchronous callables by default; an `AsyncEngine` façade over `asyncio` loaders is a later milestone. Registration itself never awaits.                                                                                                                                                                                                                                                                       |
| D8  | Dynamic scope                  | carried | Full 2020-12 `$dynamicRef` semantics over a stack of entered schema resources; 2019-09 `$recursiveRef`/`$recursiveAnchor` as the degenerate case. Compiler (M9, after the TS engine's ADR 0004, extended to `$recursiveRef`): a site whose target is the same on every path that can reach it resolves at plan time and compiles as a static edge (reference applications carry a `resolution` fact; the scope-independent half of resolution lives on the registry, `dynamic_reference`/`recursive_reference`, shared by both tiers; the planner runs a per-anchor forward dataflow over the unit graph in rounds); a site whose target differs by path islands with cause `dynamic`. 2020-12 census: 58 sites resolved, 1 island; the OpenAPI 3.1 schema and the 2020-12 metaschema plan with no interpreted unit.                                                                                                                                                                                                                                                                |
| D9  | Lowering catalogue             | carried | Same catalogue in intent (evaluated-set tracking, production elision, constant locations, small-set membership, lazy unit materialization, regex/format hoisting). Measured at M6 on CPython 3.12/3.14: `type(x) is T` tests (P9) run 3–4× faster than bool-guarded `isinstance` for numbers; `frozenset` membership beats an `==` chain from two members, so `InConsts` renders all-string and all-number sets as hoisted frozensets behind a type guard and everything else as a chain; binding helpers as default arguments gains nothing over globals in the exec namespace; one call level costs ~12 ns, so a single-use static child inlines unless the inline stack passes 32 or the loop nesting would pass 16 (CPython refuses more than 20 statically nested `for`/`while`/`try`/`with` blocks; `if` does not count). Consumers (D9a): static coverage when every contributor is unconditional, else runtime tracking (M9): the consumer's unit is *tracked* (owns a coverage channel it folds through core's `coverage.py`), its in-place closure is its *region* (units producing into the channel, every branch run, a failing application's productions cut at its mark, islands harvested through a coverage trampoline), and nested tracked consumers nest through their entry mark. Evaluator plans track every consumer, since a static licence models only the parent-success path. Outside regions flag code is unchanged. |
| D10 | Compiler output modes          | amended | Runtime compilation = `compile()` of an `ast.Module` (D1). Standalone emission = `ast.unparse` to a `.py` module importable without the compiler. There is no CSP; the security analogue is that only `json_schema_engine.compiler` may touch `ast`/`compile` (P5), and deployments can audit that with `sys.addaudithook`. CPython's cap on statically nested blocks means emission splits units into functions rather than nesting loops. Delivered at M6: `compile_validator` (runtime; `compile`/`exec` live only in `compiler/runtime_compile.py`, proven by `tests/test_fences.py` and an audit-hook probe) and `emit_standalone` (a module importing only `re`, core's errors, and core's pure helpers, with patterns pre-translated for `re`; refused with `StandaloneUnsupportedError` for any interpreted unit or a non-`re` backend). M9: `compile_evaluator` (runtime only; standalone stays flag-only by owner decision, and now accepts tracked schemas). Rule for a later evaluator standalone: every helper emitted code calls is a namespace global with a `json_schema_engine.core` import path, never a method on the runtime object, so that module is prologue work only. |
| D11 | Draft support                  | carried | Native in core: 2020-12, 2019-09, draft-07, draft-06 (M4), all coexisting in one registry with their own identifier syntax and `$ref` semantics (D18). draft-07/06 predate vocabularies, so their keywords live under registry-internal `urn:jse:vocab:draft-0X:*` names. draft-04 as a separately importable dialect module (`json_schema_engine.dialects.draft04`, M10), assembled through the public dialect-authoring surface.                                                                                                                                                                                                                 |
| D12 | Testing strategy               | carried | Official suite as git submodule with a pytest runner in `test_kit`; both tiers pass the identical suite with exact-count pins; differential fuzzing (Hypothesis) as the compiler's primary correctness gate; Bowtie harness from M3; releases conformance-gated. At M6 the compiled legs import the interpreter legs' parameter sets, so the pins are the same numbers; the plan census pins exact static/interpreted counts per dialect (fallback is always correct, so only a pin notices a regression); the goldens pin emitted source byte for byte. |
| D13 | Error model                    | carried | Keywords emit structured error data (keyword id, params, message) into units; rendering is presentation. Params are designed so a future compatibility adapter can reconstruct another library's error shape mechanically.                                                                                                                                                                                                                                                                       |
| D14 | Strictness                     | carried | Core is spec-clean; strict-mode hygiene is opt-in only via a lint layer or stricter metaschemas. No python-jsonschema compatibility shim in the first release (owner decision 2026-09-20).                                                                                                                                                                                                                                                                                                       |
| D15 | IP policy                      | carried | §0.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D16 | Packaging                      | amended | One repository as a uv workspace. **One published distribution `json-schema-engine`** laid out as a PEP 420 namespace package: `json_schema_engine.core`, `.compiler`, `.formats`, `.dialects.*`, so a later split into several distributions changes no import path. Unpublished workspace members: `test-kit`, later `bench`, `bowtie`. **`ecma-regex` is a separate, publishable workspace member** with no dependency on the engine (P1). No third-party runtime dependencies; optional extras only (`regex` for the alternative regex backend, `idna` for IDNA2008 in the formats package, M7). Publication shape (M8): the engine depends on a compatible `ecma-regex` range pinned in `pyproject.toml`; every portion (`core`, `compiler`, `formats`, `ecma_regex`) carries a `py.typed` marker, one per portion because a namespace package has no root to hold it; the engine sdist ships `src`, README, CHANGELOG, LICENSE, and pyproject only (its tests need the workspace-private test-kit and the suite submodule), ecma-regex's sdist keeps its self-contained tests; `scripts/install_smoke.py` proves an offline install from the built artifacts, with a strict pyright pass over a consumer file, in CI and before every publish. |
| D17 | Source-position correlation    | carried | Loaders may return `get_range(document_root_pointer)`; the registry maps resource-rooted locations to document-rooted pointers; correlation only at unit escape (`positions=True` decorates units with `source`) or via `Engine.locate()`. Zero hot-path cost. Implemented in M3. Since M8 `core/positions.py` ships `parse_json_with_ranges` as public API: a stdlib-only RFC 8259 parser whose `ParsedDocument` is a `LoadedResource` with `get_range`, so a caller gets positions without writing a parser; syntax errors are the typed `JsonSyntaxError` (also a `ValueError`) with line/column/offset.                                                                                                                                                                                                                                                                          |
| D18 | Per-dialect identifier syntax  | carried | Identifier extraction is dialect data (`IdentifierExtractor`), consumed by the registration walk and pointer navigation. `ref_ignores_siblings` for draft-07/06 is honored by the registration walk as well as the evaluator (owner ruling 2026-09-20: ignored is ignored — no identifier, subschema, or pattern beside a `$ref` is seen; pointer references into siblings still resolve).                                                                                                                                                                                                                                                                                                                                 |
| D19 | Non-schema values              | carried | Fail loud in two layers: the registration walk raises `InvalidSchemaError` for a keyword-claimed schema position holding neither object nor boolean; `apply_schema` raises the same as a lazy backstop. Keyword-value validity stays the metaschema's job.                                                                                                                                                                                                                                       |
| D20 | Resource-exhaustion bounds     | amended | Same three defenses. (1) ReDoS: the regex dialect/backend is pluggable (P1); `detect_unsafe_regex` star-height screen backs opt-in `reject_unsafe_regex` raising `UnsafeRegexError` at registration; a linear-time backend is a revisit item (neither `re` nor `regex` is linear-time). (2) `uniqueItems`: O(n) bucketing by `canonical_key`, confirmed by `json_equal`. (3) Depth: P3. Prototype-pollution defenses are N/A — Python dicts have no prototype chain; the suite's trap keys are still unit-tested to prove it. |

### Python-specific decisions

| #  | Decision                     | Choice                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Why                                                                                                                                                                                                                                                                                | Revisit trigger                                                                                                        |
| -- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| P1 | Regex dialect and backend    | `pattern`-class keywords are evaluated under a **regex dialect** (ECMA-262 by default for every current draft; Python `re` passthrough as an engine-wide override for Python-only migrations; I-Regexp later, as the default of whichever dialect the RFC defines) and a **backend** (`re` by default; the `regex` module via the `regex` extra). The ECMA-262 translator is the standalone package **`ecma-regex`** (`packages/ecma-regex`, import `ecma_regex`): one regex AST, front-ends parse into it, back-ends emit for `re`/`regex`, `search` with ECMA semantics, `star_height` for the D20 screen. It imports nothing from the engine. Untranslatable patterns fail at **registration** with a typed error carrying the schema location. Anchoring is a property of the keyword (`pattern` is search), never of the dialect. | Schemas are portable artifacts; a Python-flavoured default would disagree with every other conformant implementation and with Bowtie. The translator is an ecosystem gap worth publishing on its own (owner decision 2026-09-20). | The JSON Schema RFC adopts I-Regexp: add the front-end and flip that dialect's default. A linear-time backend appears. |
| P2 | Number and equality model    | Numeric identity is mathematical. `bool` is never a number: every type test checks `bool` before `int`, and `json_equal`/`canonical_key` distinguish `True` from `1`. `type: "integer"` accepts `int` (not `bool`) and `float` with zero fractional part (`1.0` is an integer, per spec). Python ints are unbounded, so big literals stay exact (an improvement over JS). Non-finite floats are outside the JSON model: parse boundaries (loaders, the suite runner) reject `NaN`/`Infinity`; the hot path never checks. Plain `==` on JSON values is banned in core; `json_equal` is the only equality. **`multipleOf` uses decimal semantics (M2):** each operand becomes the exact rational of its shortest round-trip `repr` (`Fraction(Decimal(repr(x)))`), so `0.0075` is a multiple of `0.0001` as the author meant, and `1e308 / 0.123456789` is simply a non-integer rather than an overflow.                                                                                                                                                                                                              | `True == 1`, `hash(True) == hash(1)`, and `{"a": 1} == {"a": True}` are all true in Python; `json.loads` accepts `NaN` by default.                                                                                                                                                | Never for bool. A schema author who needs binary-float `multipleOf` semantics (none known).                            |
| P3 | Recursion budget             | `EvalState` carries an explicit depth counter; `max_depth` (default 512) bounds both registration nesting and evaluation application nesting and raises `MaxDepthExceededError` **before** CPython's recursion limit can. `Engine.evaluate` and `SchemaRegistry.register` additionally translate a stray `RecursionError` into the same typed error. Library code never calls `sys.setrecursionlimit`.                                                                                                                                                                                                                                                                                                                                                                                                                | CPython's default limit is 1000 frames and each schema application costs several.                                                                                                                                                                                                  | Measured frames-per-application changes the safe default.                                                              |
| P4 | Loaders are sync-first       | `Loader = Callable[[str], LoadedResource \| None]` where `LoadedResource` is a Protocol (`value`, `uri`), so a loader written with no dependency on the engine satisfies it structurally; `LoadedDocument` is the engine's own concrete form. A loaded resource may also offer `get_range(document_pointer)` (D17); the engine reads it with `getattr`, so resource types without it stay valid. `None` from a loader is a miss, never an error. `Engine.register_schema` is local-only; `Engine.load_schema` drains unresolved references through the loaders synchronously. An `AsyncEngine`/async-loader façade is a later milestone; it wraps the same registry.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Most Python callers are synchronous; forcing `await` on registration would be the tail wagging the dog.                                                                                                                                                                             | A consumer needs concurrent remote loading.                                                                            |
| P5 | Packaging and import fences  | See D16. Enforced by import-linter contracts run in CI from M0: `json_schema_engine.core` never imports `json_schema_engine.compiler`, `ast`, `json_schema_engine.test_kit`, or `json_schema_engine.formats`; the compiler never imports `test_kit` or `formats` (a standalone module's predicate imports are checked by name through `importlib`); `formats` never imports the compiler or `test_kit`; `ecma_regex` never imports `json_schema_engine`; `json_schema_engine.test_kit` never imports `core`, `compiler`, or `formats` (M8), so the suite runner stays engine-independent. The builtin `compile` is not an import, so it is banned in core by a lint gate. Core depends on `ecma-regex`, so an engine release whose pin needs an `ecma-regex` version PyPI lacks publishes `ecma-regex` first (CONTRIBUTING.md § Releasing).                                                                                                                                                                                                                                                                                                                                                                                                       | The "core has no code generation in its dependency graph" invariant is the Python form of the TS ESLint fences.                                                                                                                                                                    | The compiler needs a helper that belongs in core: move it, never relax the contract.                                   |
| P6 | Records vs. units            | Engine records (`AnnotationRecord`, `DependencyRecord`, `ErrorRecord`, `PathNode`, `Frame`) are `@dataclass(eq=False, slots=True)` and never rendered directly. Output units are `TypedDict`s with the wire field names, so `json.dumps` takes them unchanged and optional keys are genuinely absent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Records need identity and lazy path materialization; units need to *be* the JSON.                                                                                                                                                                                                  | A renderer needs behaviour on units.                                                                                   |
| P7 | Identity-keyed structures    | `Cursor`, `SchemaRef`, `PathNode`, and all record types use identity equality (`eq=False`), so sets and dict keys are identity-keyed. Channel rule 4 filters dependency records by **cursor identity**; the cycle guard is keyed by (schema location, cursor identity). A `frozen=True` dataclass with default equality would silently give value semantics and break cousin invisibility.                                                                                                                                                                                                                                                                                                                                                                                                                              | Rule 4 depends on it; `dict` values are unhashable anyway.                                                                                                                                                                                                                         | Never.                                                                                                                 |
| P9 | Plain-data instance contract | Compiled artifacts test types with `type(x) is dict`/`list`/`str`/`bool`/`int`/`float` (and `x is None`): the instance is assumed to be `json.loads`-shaped data. Subclasses of the JSON types (an `OrderedDict`, an `IntEnum`, a `str` subclass) are not JSON values to the compiled tier; the interpreter, which uses `isinstance` and `is_object`, makes no such assumption and is the surface for hand-built objects. The differential fuzzer generates only plain data.                                                                                                                                                                                                                                                                                                                              | Measured 3–4× faster than the bool-guarded `isinstance` forms on the number tests, which dominate; `bool` is excluded for free because `type(True) is bool`.                                                                                                              | A caller needs subclass instances validated at compiled speed: add a normalizing copy, never `isinstance` in emitted code. |
| P8 | Naming                       | Python API: snake_case functions, options, and attributes (`register_schema`, `error_params`). JSON Schema keyword names and output-document field names are wire formats and keep their spec spelling. Module names follow the TS modules where sensible (`registry`, `dialect`, `cursor`, `output`, `result`); `json_model.py` rather than `json.py`, `evaluator.py` for the TS `engine.ts` machinery, `engine.py` for the public `Engine` façade.                                                                                                                                                                                                                                                                                                                                                                | Idiomatic Python without renaming spec concepts.                                                                                                                                                                                                                                   | —                                                                                                                      |
| P10 | Location string encoding     | A schema location is a **URI**. `SchemaRef.location` and every error's `schema_location` are built by `schema_location(base_uri, pointer)` in `core/uri.py`, which takes an RFC 6901 pointer and percent-encodes exactly what RFC 3986's `fragment` production disallows: space, `"`, `<`, `>`, `\`, `^`, `` ` ``, `{`, `|`, `}`, `#`, `%`, controls, and every non-ASCII character as UTF-8 bytes. `/ : @ ! $ & ' ( ) * + , ; = - . _ ~` stay literal, so an ordinary pointer reads unchanged. `pointer_from_fragment(fragment)` is the exact inverse and is the only way a fragment becomes a pointer (registry lookup, `Engine.locate`). Prose in error messages uses the same URI form for schema positions. `evaluationPath` and `instanceLocation` stay **plain-text** JSON Pointers, which their specs require and `$ref` never sees. | `schemaLocation`/`absoluteKeywordLocation` are specified as URIs, and callers paste them into `$ref` or feed them back to `Engine.locate`. Emitting the raw pointer made a property named `100%` come out as `#/properties/100%`, which is neither a URI nor round-trippable, while the registry already `unquote`d on the way in. Matching user-facing form to `$ref` usage is the rule wherever the spec does not fix a format. | The JSON Schema RFC adopts IRIs: widen to the IRI `ifragment` rules and leave non-ASCII literal. Until then a human-centric UI decodes for display; the engine emits the machine-round-trippable form. |
| P11 | Embedded-resource location chain | A schema location names a position exactly and still may not locate it: in a compound document the base may be an embedded `$id` the reader never knew was there, and a relative `$id` resolves to a URI that appears nowhere in their file. `SchemaRegistry.location_chain(location)` returns a `tuple[LocationHop, ...]`, innermost first: the position, then each lexically enclosing resource with the pointer to the one below it *within that resource*, ending at a root. Every hop's `.location` is a canonical schema location, so it is a `$ref` value and an `Engine.locate` argument; a hop also carries the `$id` as written (the only way to find a relative one in the text) and, on the outermost hop, the retrieval URI when it differs. The parent link rides on `DocumentLocation`, which `snapshot()` already copies, rather than a parallel map. `Engine` attaches a chain to any error leaving `register_schema` or `evaluate` — no raise site holds a registry — and `str(error)` appends it only past one hop, so a single-resource message is byte-identical to before. Side API only: no output unit gains a field. | The bundled shape (many `$id` resources in one document's `$defs`) is the common real one, and it is exactly where a canonical URI stops being actionable. Deriving at the boundary rather than at the raise site avoids coupling the regex screen, the evaluator and keyword `analyze()` to a registry, and freezes the chain at the moment of failure. Hops carry no `SourceLocation` because its range comes from a loader closure over a parse tree, and an exception that outlives it must not pin it; `Engine.locate(hop.location)` is one call. | The chain and `Engine.locate` disagree — a test composes the hops back into the flat D17 pointer to make that a failure rather than a drift. |
| P12 | Duplicate identifiers are errors | Two different schemas may not claim one resource URI, and two different schema objects may not claim one anchor name within a resource. `DuplicateResourceError` covers a single document minting an `$id` twice and a later registration rebinding a URI an earlier one bound to a *different* schema (`json_equal`, so re-registering an equal document stays a no-op). `DuplicateAnchorError` covers `$anchor`, `$dynamicAnchor`, and the draft-07/06 `$id: "#name"` form alike, keyed on the `_anchors` entry that all three write; one object carrying both anchor kinds under one name claims the same key with the same target and is allowed. Claims are scoped to one registration walk, so a re-registered resource rewrites its own anchors without a false positive, and a `$ref` sibling under draft-07/06 claims nothing because it suppresses identifiers (D18). | Both were silent last-write-wins, so one schema shadowed the other and a reference resolved to whichever the walk reached last. The anchor case was worse than shadowing: because a dynamic anchor is also a plain anchor (D8), `$anchor: "n"` on one object and `$dynamicAnchor: "n"` on another left `$ref` and `$dynamicRef` resolving the same fragment to *different* schemas. The spec is silent on duplicate `$id` and deems a duplicate anchor undefined behavior an implementation MAY reject; the owner deems rejection correct for both. Duplicate `$id` is also what made the P11 parent relation cyclic. | A schema in the wild proves a duplicate is load-bearing somewhere (none known; the vendored suite, the bundled metaschemas, and every repo fixture are clean). |
| P13 | Registration is all-or-nothing | `SchemaRegistry.register` journals every index write and undoes them if anything escapes, so a document that fails leaves the registry exactly as it found it. A `_Registration` holds `(index, key, prior)` for the seven dict indexes and `(index, member)` for the four set ones, recording only genuinely new members because `_produced_ids`/`_consumed_ids` are unions. The undo restores prior values rather than deleting keys: a walk legitimately rebinds entries an earlier registration owns, and `_documents` order is what `resources()` promises. `except BaseException`, since `_step` raises bare `KeyError`/`TypeError`, `RecursionError` can fire anywhere, and caller code runs inside the walk. Not journaled: `_reference_memo` (a derived cache, cleared on both paths), the P12 claim sets (per-walk scratch), and the regex cache (keyed by pattern, a function of a fixed dialect and backend). On the way out the registry fills the error's `location_chain` (P11) and `schema_source` (D17) *before* the undo — the only moment the indexes they derive from still exist — and `_canonical` refuses to start a lazy bundled registration while a journal is live. | The half-indexed document left behind was still evaluable, and its partial `produces`/`consumes` fed D5's elision predicate, so the failure surfaced as a wrong answer rather than a loud one. P12 added two more ways to fail mid-walk. Journaling rather than snapshotting keeps the cost O(this document's writes) with no term in registry size, which matters because every lookup may lazily register a bundled metaschema; measured, registration is unchanged (1.27 ms either way on the OAS 3.1 corpus). | A caller needs a *successful* registration undone: that wants `unregister`, and an answer for resources an earlier registration also claims. |
| P14 | Per-resource dialects | `$schema` governs the schema resource it roots, not the document (2020-12 core §8.1.1). `_walk` rebinds its `dialect` local wherever it rebinds `base_uri`, so the inner dialect supplies the keyword table, `ref_ignores_siblings`, and the identifiers minted into that resource, and `_document_dialects` records it. **The boundary is decided from the outside, the contents from the inside:** `base_id` comes from the *parent* extractor — its `$id` syntax is what decides a resource starts here at all, and a relative `$schema` has no base to resolve against until it has — while `anchors`, `dynamic_anchor` and `recursive_anchor` are re-read with the inner one. Honored under every dialect; draft-07/06 are silent on the placement rather than prohibitive. A `$schema` where no resource starts is **ignored**, not refused: the spec forbids the placement, but refusing it is strict-mode hygiene, which D14 keeps opt-in, and `{"$schema": X, "not": {"$schema": X}}` is how Bowtie spells "allows nothing" for every dialect it tests. Only the walk can discover an embedded `$schema`, and the registry holds no loaders, so it raises `UnknownDialectError` carrying `dialect_uri` and the engine assembles that dialect and registers again; P13 rollback is what makes the retry start from the state the first attempt found. Pointer navigation in `resolve_ref`/`child` refreshes its extractor at each base change through a non-raising lookup, so a base the walk never indexed falls back to the dialect in force rather than failing. | The walk threaded the document root's dialect through the whole recursion, so the bug cut both ways: a valid draft-07 resource embedded in a 2020-12 document was rejected for array-form `items`, and a 2020-12 resource embedded in a draft-07 document had `$id: "#foo"` accepted as an anchor. It also mislabeled any node reached by a pointer that crossed an `$id` under the wrong extractor as its resource's root. Evaluation and the compiler already keyed every dialect lookup on the unit's own base URI, so the walk was the only tier disagreeing — with them and with itself. | A dialect needs to *forbid* an embedded `$schema`: that wants a `Dialect` field beside `identifiers` and `ref_ignores_siblings`. A lint layer under D14 wants to flag a misplaced `$schema`, which this deliberately does not. |

## 2. System shape

```
                    ┌────────────────────────────────────────────┐
                    │                 registry                   │
                    │ documents · $id/$anchor index · dialects · │
                    │ vocabularies · keyword behaviors (by URI)  │
                    └────────────┬───────────────┬───────────────┘
                          analyze() facts   evaluate() impls
                                 │               │
                    ┌────────────▼──┐      ┌─────▼──────────────┐
   schema ──────►   │  compiler     │      │  interpreter core  │
   + selection      │  (static      │      │  ctx: eval path ·  │
   policy           │  subschemas)  │      │  lexical+dynamic   │
                    │               │─────►│  scope · channel   │
                    │ emit Python   │ tram-│  frames            │
                    │ ast with      │ po-  └─────┬──────────────┘
                    │ constant      │ line       │ records/errors
                    │ locations     │            │
                    └────────┬──────┘            │
                             ▼                   ▼
                      compiled artifact    render input ──► output renderers
                      (per schema ×        (flat units + located tree,
                       policy × config)     all formats and levels)
```

Modules of `json_schema_engine.core` (M1 set; later milestones add
`loader.py` extensions, `walk.py`, `coverage.py`, `lowering.py`):

| Module          | Responsibility                                                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `errors.py`     | One root exception; every typed error the engine raises.                                                                                    |
| `json_model.py` | `JsonValue`, `JsonType`, `json_type_of`, `is_integer_value`, `json_equal`, `canonical_key`, `code_point_length`, RFC 6901 escaping (P2).    |
| `locations.py`  | `LocationHop`/`LocationChain` and their formatter: the P11 chain type, importing only `uri` so `errors` may import it. |
| `uri.py`        | RFC 3986 §5 reference resolution and fragment splitting. Own implementation: `urllib.parse.urljoin` cannot resolve against `urn:` bases.    |
| `cursor.py`     | `Cursor`: parent-linked instance position with lazy JSON Pointer; identity-significant (P7).                                                |
| `ref.py`        | `SchemaRef`: schema node + canonical base URI + pointer.                                                                                    |
| `channel.py`    | `PathNode`, the three record kinds, `Frame`, `TraceNode` (P6).                                                                              |
| `dialect.py`    | `KeywordBehavior`, `StaticFacts`, `AnalyzeContext`, `KeywordContext` protocol, `IdentifierExtractor`, `Dialect`, `DialectRegistry` (§3).     |
| `registry.py`   | `SchemaRegistry`: registration walk over `analyze().subschemas` only, identifier index, produced/consumed unions, reference resolution.      |
| `evaluator.py`  | `EvalState`, `apply_schema`, `evaluate_keyword`, the `KeywordContext` implementation: the only home of §4.                                  |
| `regex.py`      | Thin adapter over `ecma_regex`: dialect selection, `RegexCache`, error mapping, `detect_unsafe_regex` (P1, D20).                            |
| `records.py`    | Records → located units and `RenderInput`.                                                                                                  |
| `output.py`     | Units, `AnnotationSelection`, `make_record_predicate`, the format renderers. Engine-free.                                                   |
| `result.py`     | `OutputFormat`, `EvaluateOptions`, `resolve_output_demand`, `assemble_result`, `Result`.                                                    |
| `loader.py`     | `LoadedDocument`, `Loader` protocol (P4).                                                                                                   |
| `positions.py`  | `parse_json_with_ranges`, `ParsedDocument`: the positions-reporting JSON parser, public since M8 (D17).                                     |
| `coverage.py`   | `fold_name_coverage`/`fold_index_coverage`: the evaluated-coverage folds both tiers use (M9).                                               |
| `channel_ops.py`| The record, mark/cut, and trace operations a compiled evaluator performs on a shared `EvalState` (M9); every name a runtime helper.         |
| `engine.py`     | `Engine`, `create_engine`: the public façade.                                                                                               |
| `lowering.py`   | The compiler IR (data only) and the `LoweringContext` protocol; keyword modules describe their compiled form through it (D1, M6).           |
| `formats.py`    | `FormatDefinition`/`FormatTable`: the format contract the `format` keyword, the compiler's runtime, and the formats package share (M7).       |
| `keywords/`     | One module per keyword class: `core.py`, `validation.py`, `applicator.py`, `unevaluated.py`, `format.py`; `dialect2020.py` assembles.       |

Modules of `json_schema_engine.formats` (M7; core never imports it, a
caller injects a table with `create_engine(formats=...)`):

| Module         | Responsibility                                                                                                        |
| -------------- | --------------------------------------------------------------------------------------------------------------------- |
| `__init__.py`  | `FORMATS_2020_12` (= 2019-09), `FORMATS_DRAFT_07`, `FORMATS_DRAFT_06`, `format_table_for`, `anchored`; the conventions. |
| `_abnf.py`     | RFC 3986/3987 fragments shared by the URI family.                                                                     |
| `datetime_.py` | `date`, `time`, `date_time`, `duration` (RFC 3339 §5.6, Appendix A).                                                  |
| `net.py`       | `ipv4`, `ipv6` (`ipaddress`), `hostname` (RFC 1123, A-labels via `idna_`), `email` (RFC 5321), `idn_email` (RFC 6531). |
| `uri.py`       | `uri`, `uri_reference`, `iri`, `iri_reference`, `uri_template` (RFC 3986/3987/6570).                                   |
| `pointer.py`   | `json_pointer` (RFC 6901), `relative_json_pointer`.                                                                   |
| `misc.py`      | `uuid` (RFC 4122), `regex` (ECMA-262 syntax through `ecma_regex.parse`).                                              |
| `idna_.py`     | IDNA2008 through the optional `idna` package: `a_label_ok`, `idn_hostname`; documented degradation without the extra.  |

Modules of `json_schema_engine.compiler` (M6):

| Module               | Responsibility                                                                                                                     |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `plan.py`            | `build_plan`: static vs interpreted units from `analyze()` facts alone; plan-time dynamic-reference resolution in rounds; coverage licensing or tracking (tracked/region units); cycle islanding; `explain_compilation`. |
| `emit.py`            | The gated `ast` builder: minted identifier vocabulary, `const()` as the only data entry point, node helpers, hoists.                |
| `serialize/`         | `units.py` (lower a unit to IR), `body.py` (IR → `ast`: expressions, statements, applications, inlining), `__init__` (assembly).    |
| `runtime.py`         | The exec namespace: core's helpers, the pattern table, the depth budget, the one-way trampolines (`frag`, `frag_cov` harvesting coverage, `frag_eval` on the shared state). |
| `runtime_compile.py` | The only `compile`/`exec` site (D10, P5).                                                                                          |
| `standalone.py`      | `emit_standalone`: the same module with a stdlib-plus-core prologue; refuses anything needing the interpreter.                    |
| `__init__.py`        | `compile_validator`, `CompiledValidator`, `compile_evaluator`, `CompiledEvaluator`, `emit_standalone`, `build_plan`, `explain_compilation`. |

## 3. Keyword behavior interface (normative for M1+)

```python
@dataclass(frozen=True, slots=True)
class StaticFacts:
    subschemas: tuple[tuple[str | int, ...], ...] = ()  # child schema positions, relative to the keyword value
    references: tuple[str, ...] = ()                    # reference URIs in the value (transitive loading)
    produces: tuple[str, ...] = ()                      # behavior ids this keyword may ctx.produce() under
    consumes: tuple[str, ...] = ()                      # behavior ids this keyword reads via ctx.visible()
    regexes: tuple[str, ...] = ()                       # pattern values, screened by reject_unsafe_regex
    formats: tuple[str, ...] = ()                       # format names needing a table entry
    dynamic_scope_sensitive: bool = False               # $dynamicRef and friends (D8)
    evaluates_names: NameCoverage | None = None         # D9a static contribution to evaluated properties
    evaluates_indexes: IndexCoverage | None = None      # D9a static contribution to evaluated items
    applications: tuple[SubschemaApplication, ...] = () # M6: how subschemas are applied (planner edges)

@dataclass(frozen=True, slots=True)
class SubschemaApplication:                             # M6
    path: SubschemaPath                                 # relative to the keyword value; () is the value itself
    mode: Literal["in_place", "child_by_key", "child_by_index", "child_sweep", "property_name"]
    conditional: bool                                   # depends on runtime branching, not instance shape
    asserts: bool                                       # its verdict feeds the keyword's verdict
    sibling: str | None = None                          # if -> then/else
    ref: str | None = None                              # reference keywords; path ignored
    inverted: bool = False                              # not: coverage analysis skips the edge
    resolution: Literal["dynamic", "recursive"] | None = None  # M9: a scope-dependent reference the planner resolves or islands

@dataclass(frozen=True, slots=True)
class AnalyzeContext:
    schema: Mapping[str, JsonValue]   # the containing schema object, for sibling-dependent facts

class Phase(IntEnum):
    ASSERT = 0        # every keyword unless stated otherwise
    UNEVALUATED = 1   # runs after all phase-0 keywords of the same object have merged

@dataclass(frozen=True, slots=True)
class KeywordBehavior:
    id: str                                   # keyword URI (D2)
    evaluate: Callable[[JsonValue, Cursor, KeywordContext], bool]   # interpreter semantics, sync
    analyze: Callable[[JsonValue, AnalyzeContext], StaticFacts] | None = None   # pure static facts
    phase: Phase = Phase.ASSERT
    structural: bool = False                  # identifier/reserved keyword: never an output unit
    lower: LowerFn | None = None              # M6 compiler IR (core/lowering.py); absent means "interpreted unit", never a failure
```

`KeywordBehavior` is data (D2): vocabularies are `dict[str, KeywordBehavior]`
and factories (`structural(id)`, `annotation_only(id)`, `assertion(...)`)
return instances. Callables stored as dataclass fields are instance
attributes, not methods: `behavior.evaluate(value, cursor, ctx)` never
receives `self`.

Engine-owned context services, the only path to descent, locations, and the
channel — this is what makes D1's compiler contract enforceable:

```python
class KeywordContext(Protocol):
    schema: Mapping[str, JsonValue]
    cursor: Cursor
    def apply(self, segments: Sequence[str | int], cursor: Cursor) -> bool: ...
    def resolve_ref(self, ref: str) -> SchemaRef: ...
    def resolve_dynamic(self, ref: str) -> SchemaRef: ...        # D8, M3
    def apply_resolved(self, target: SchemaRef) -> bool: ...
    def compile_regex(self, pattern: str) -> CompiledRegex: ...
    def annotate(self) -> None: ...                              # own value, current cursor (rule 2)
    def produce(self, data: object) -> None: ...                 # dependency data (rule 2, rule 6)
    def visible(self, behavior_ids: Sequence[str], scope: Literal["all", "adjacent"] = "all") -> Sequence[DependencyView]: ...
    def error(self, message: str, params: Mapping[str, JsonValue] | None = None) -> None: ...
```

Exemplars of each keyword class, promoted to production form in M1:
assertion (`pattern`), in-place applicator (`anyOf`), child applicator
(`properties`), channel consumer (`unevaluatedProperties`), annotation-only
(unknown-keyword handling and `annotation_only()`), reference (`$ref`).

## 4. Channel semantics (normative)

Carried verbatim from the TS design; these rules are language-independent.

1. Each schema application pushes a frame.
2. `ctx.annotate()` appends an annotation record `{keyword, evaluationPath,
   schemaLocation, instanceLocation, value}` to the current frame, where
   `value` is the keyword's own value (draft-03 §12.9). `ctx.produce(data)`
   appends a dependency record `{keyword, evaluationPath, schemaLocation,
   instanceLocation, data}`: computed information for other keywords, never
   output (draft-03 Appendix D). A producer declares its own id in
   `analyze().produces`; an undeclared producer throws
   `UndeclaredProductionError`.
3. On application **success**, the frame's records merge into the parent
   frame; on **failure**, they are discarded. No other visibility rule exists.
4. `ctx.visible(ids)` filters the current frame's dependency records by
   instance location — thereby seeing own-schema records and merged records
   from successful in-place child applications, and _not_ seeing cousins or
   failed branches. (`unevaluatedProperties/Items` correctness in the suite is
   the regression test for this rule.)
5. The annotation result of an evaluation is the root frame's surviving
   annotation records filtered by the annotation selection (D5). Selection
   never affects rule 4. `$comment` is structural and never annotates.
6. Relevance (draft-03 §12.2): a keyword that accepts makes the errors of
   its rejecting sub-evaluations irrelevant — the engine drops them from the
   error list when the keyword returns (kept aside only when tracing, for
   verbose output). Rule 3 is the same transition for a rejecting schema
   object's accepting sub-evaluations. A keyword that reports an error must
   reject (`KeywordContractError` otherwise). Dependency data is produced
   only by an accepting keyword (Appendix D); `contains` reports its matched
   positions, every other producer reports nothing when it rejects. `if`
   produces its subschema's outcome and always accepts; `then`/`else` consume
   it through `ctx.visible(ids, "adjacent")` (a same-scope dependency, §12.3)
   and report their own subschema's verdict.
7. Short-circuiting (draft-03 §12) is permitted only when no annotation
   could be produced, no dependency communication could be affected, and no
   verbose output is requested. The interpreter never short-circuits; the
   compiler short-circuits `anyOf`/`oneOf` exactly in verdict-only regions
   (flag output, nothing consumes per `StaticFacts`, no retainable
   annotation — D9b), and list output runs every branch. M9: inside a
   tracked region (D9a) and in every evaluator artifact, every branch runs.

### Compiled-tier contracts (normative, M9)

- **Channels.** A compiled evaluator writes to one shared core
  `EvalState`. Errors are flat and truncate only on keyword acceptance
  (rule 6; an `if` condition's immediately). Annotations live in the root
  frame and are cut at every application boundary (rule 3: compiled
  applications nest, so a failed one's records are a contiguous suffix).
  Runtime coverage (`ev`) is a per-region list of `(behavior_id, data)`
  pairs cut at every in-place boundary; a tracked unit folds only what
  its own region produced (`ev[mark:]`). The evaluator cuts the root
  frame when the root fails.
- **Trampoline.** Still one-way. A resolved dynamic site is a static edge,
  not code inside an island. `frag_eval` runs an island on the shared
  state with the caller's cursor and path node; `frag_cov` harvests a
  flag-mode island's root-frame productions at its cursor into the
  region's channel.
- **Emitted code semantics live in core.** Every helper an artifact
  calls is a core function bound under a fixed name (`channel_ops`,
  `coverage`, `json_model`, `cursor`, `channel`), so the evaluator's
  records are `ErrorRecord`/`AnnotationRecord`/`TraceNode` objects and
  the interpreter's renderers run unchanged.
- **The annotation selection is an artifact property.** Ruled-out
  annotations are never emitted (their values never reach the module);
  `keep` runs at evaluation. Every other output control is per call, and
  `resolve_output_demand` rejects combinations exactly as the engine does.
- **Messages are one builder.** A keyword's `Fail`/`CombineCheck`/
  `CountRange` carries the message and params `evaluate` reports, with
  runtime values as bindings; the evaluator suite legs and the whole-result
  fuzz are the referee.

In Python terms: "instance location" in rule 4 is **cursor identity** (P7),
and "throws" is "raises".

## 5. Carry-over findings that must not be relearned

From the TS build (language-independent):

- Registration must walk **schema positions only**: `$id`/`$anchor` inside
  `enum` or `const` data are not identifiers, and a keyword name inside data
  is not a keyword. Pointer navigation must track `$id`-induced base changes.
- A `$ref` cycle guard is required from M1: a seen-set keyed by (schema
  location, instance identity); the suite's `infinite-loop-detection.json`
  is the test.
- Annotation cost is proportional to retention; elision at annotate time is
  the interpreter's win. All-errors unit materialization is the untuned spot.
- Bundled metaschemas must be resolvable without loaders; the suite's
  metaschema-`$ref` cases silently error-skip otherwise. Pin exact run counts.
- The compiler's differential gate must be able to detect a planted
  divergence; test the gate, not only the code.

Python-specific (measured 2026-09-20 on CPython 3.14):

- `urllib.parse.urljoin("urn:uuid:…", "#/$defs/x")` returns the fragment
  alone; `urldefrag` cannot distinguish an absent fragment from an empty one
  (`$ref: "#"`). `uri.py` implements RFC 3986 §5 itself.
- `isinstance(True, int)`, `1 == True == 1.0`, `hash(1) == hash(True)`.
  See P2. `json.loads` accepts `NaN`/`Infinity`/`-Infinity` by default and
  keeps the last of duplicate keys.
- Non-optional suite files (`pattern.json`, `patternProperties.json`) use
  `\p{Letter}`; stdlib `re` rejects `\p`. The ECMA front-end must handle
  property escapes from M1 (expanding to explicit ranges under `re`).
- ECMA vs `re` divergences that silently change verdicts: `$` matches before
  a trailing newline in `re`; `.` in `re` excludes only `\n` (ECMA excludes
  `\r`, ` `, ` ` too); `\d`, `\w`, `\b` are Unicode-aware in `re`
  and ASCII in ECMA; `\s` differs in membership. Translate, do not flag.
- Default recursion limit is 1000 frames (P3). `list.extend` has no
  argument-count ceiling, so the TS chunked-append workaround is unnecessary.
- Python dicts have no prototype chain: `name in instance` is complete where
  TS needed `Object.hasOwn`. The suite's `__proto__`/`constructor`/`toString`
  property names are still unit-tested so the absence of the hazard is
  proven rather than assumed.
- A PEP 420 namespace breaks the moment anyone adds
  `src/json_schema_engine/__init__.py`; CI asserts `__file__ is None`.
- One implementation per keyword class, many dialects: `unevaluated*` and
  `contains` are factories parameterized by producer ids and sibling
  bounds, so 2019-09 and draft-07/06 wire their own instances without
  duplicating the fold.
- Bundled metaschemas register lazily on first reference, so `create_engine()`
  stays cheap for the suite and Bowtie, which build one engine per case;
  eager registration of eight documents would have doubled the suite's time.
- `repr(float)` is the shortest round-trip form, so `Decimal(repr(x))`
  recovers the decimal a schema author wrote; exact binary rationals
  (`Fraction(x)` directly) would make `0.0075` a non-multiple of `0.0001`.
- Records attribute to tree nodes by path-node **identity**, never by path
  string: two applications of one keyword (`items` over an array) share
  the evaluation-path string but each mints its own `PathNode`, and a
  string-keyed attribution would merge their records. `to_render_node`
  keys on `id(path_node)`, which is safe because the state keeps every
  record and trace node alive until the tree is built.
- A `NotRequired` unit field whose value may be JSON `null` (`annotation`,
  a `default` of `null`) is tested by key presence, never by `.get() is
  None`; the renderers' condensation rule keys on presence.
- CPython's "too many statically nested blocks" limit (20) counts loops,
  `try`, and `with`, not `if`: the emitter tracks loop nesting and refuses
  to inline past 16, which is the hoist — the child keeps its own function.
- `ast.unparse` renders a set constant in hash order: emitted sets are
  `frozenset((...))` over sorted members, never a set display, or goldens
  would depend on the hash seed.
- The interpreter's five frames per application trip CPython's default
  recursion limit near 200 nested applications, before `max_depth` 512;
  compiled units cost one frame and reach the counter. Depth parity is by
  exception class (`MaxDepthExceededError` from either path), never by
  the exact depth.
- Importing any `json_schema_engine.core` submodule executes the package
  `__init__`, which imports the regex adapter and therefore `ecma_regex`;
  a standalone module cannot avoid that import even though it never
  references it. "Importable without the compiler" is the contract, and
  it is proven by `sys.modules` in a subprocess.
- Format predicates (M7): `datetime.fromisoformat`, `uuid.UUID`,
  `email.utils`, and `urllib.parse` are wrong in both directions against
  the official fixtures (lenient on week dates, comma fractions, braces,
  Bengali digits via `int()`; strict on lowercase `t`/`z` and leap
  seconds); `ipaddress` is exact for both IP formats once IPv6 zone ids
  are rejected. ABNF regexes anchored `\A…\Z` are the tool: `$` matches
  before a trailing newline and `\d`/`\w`/`\s` are Unicode-aware, and
  the suite has a case for each trap.
- A leap second needs no table: the suite requires `:60` valid exactly
  when the UTC-equivalent wall clock is 23:59, on any date.
- Predicates never lazy-import: a standalone module's validation must
  raise no `exec` audit event, and a first `import idna` inside a
  predicate would be one. The optional import happens at module load.
- `ruff format` rewrites `\uXXXX` escapes in string literals to the
  characters themselves, which `RUF001` then flags as ambiguous; named
  escapes (`\N{FULLWIDTH FULL STOP}`) survive formatting.
- The interpreter's loop order is part of parity (M9): `patternProperties`
  sweeps patterns outermost, so its lowering must too, or error order
  differs. Whole-`Result` equality is the gate that notices.
- A boolean subschema in an evaluator artifact is never folded to a
  literal: the interpreter opens a trace node and, for `false`, records
  an error, so the artifact calls `apply_true`/`apply_false`.
- A dialect that refuses unknown keywords raises at evaluation in the
  interpreter; a compiled unit holding one must island, or flag mode
  silently accepts what the interpreter rejects.
- Site identities (behavior id, keyword, vocabulary, `SchemaRef`) cannot
  be `ast.Constant`s: they are hoisted from a namespace tuple, one `xN`
  per keyword occurrence.
- Publication (M8): a PEP 420 namespace package has nowhere to put one
  `py.typed`, so each portion carries its own, and only a strict pyright
  run against the installed wheel (not the source tree) proves they work.
  Hatchling normalizes specifier order in wheel metadata
  (`>=0.1,<0.2` becomes `<0.2,>=0.1`), so a check compares clauses, not
  strings; `uv build --out-dir` also writes a `.gitignore` into the
  output directory.

## 6. Milestones

| M    | Deliverable                                                                                                                                                                                                                                                                                                                                             | Tier                                   | Done-signal (mechanical)                                                                                                                                                                       |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M0   | Workspace scaffolding (D16/P5): uv workspace with `test-kit` and `ecma-regex` members, suite submodule, ruff/pyright-strict/import-linter, CI matrix 3.12–3.14, pytest suite runner in `test_kit` (schema-position skip scan, exact-count pins, remotes loader)                                                                                                                                          | patterned                              | All gates green on an empty core; runner self-tests green                                                                                                                                      |
| M1   | `core` interpreter: JSON model, URI resolution, cursor, registry with registration walk, dialect registry, channel + evaluator with cycle guard and depth budget, flag/basic/list output, `Engine` façade; the six §3 exemplars plus `type`, `required`, and annotation-only `format`/`content*`; `ecma_regex` front-end and `re` backend sufficient for the suite's non-optional patterns | judgment                               | Ported channel/relevance unit tests green; draft2020-12 leg over the M1 file list green at an exact pin (0 failures, 0 errors, every skip naming an unimplemented keyword); `refRemote.json` leg green |
| M2   | Keyword fan-out: full 2020-12 assertion/applicator/annotation set, per exemplar patterns                                                                                                                                                                                                                                                                | patterned                              | Full draft2020-12 suite green except `dynamicRef`, `vocabulary`; each keyword lands with its suite file; pins updated                                                                            |
| M3   | References hardened: `$dynamicRef`/dynamic scope (D8), `$vocabulary` processing, bundled metaschemas, loaders incl. D17 positions, metaschema validation policy, Bowtie harness (native Python)                                                                                                                                                         | judgment                               | The whole draft2020-12 leg green with one loader-backed pin, plus an optional leg; local Bowtie 2020-12 = 100% at the same count                                                              |
| M4   | Dialects: 2019-09 (incl. `$recursiveRef`), draft-07, draft-06 (D18)                                                                                                                                                                                                                                                                                     | patterned (+ judgment for D18 hooks)   | Those suites green, zero skips; Bowtie 100% per dialect                                                                                                                                        |
| M5   | Output completion: `detailed`/`verbose`/`hierarchical`, official output-tests, goldens, D5 elision, D20 security baseline (`reject_unsafe_regex`, O(n) `uniqueItems`, depth adversarial suite)                                                                                                                                                          | patterned (+ judgment for elision)     | Renderer goldens green; official output-tests green; adversarial suite within budget                                                                                                           |
| M6   | `compiler`: StaticFacts v2 and `lower()` IR in core, planner, `ast` emission, runtime and standalone modes, trampoline, Hypothesis differential fuzz, injection corpus, lowering fan-out, legacy-dialect lowering                                                                                                                                         | judgment (contracts) + patterned (fan-out) | Full suites green through the compiled tier with identical pins; fuzz clean; standalone module imports without the compiler; bench vs fastjsonschema recorded                                    |
| M7   | `formats`: all standard formats from their RFCs, `idna` extra for IDNA2008                                                                                                                                                                                                                                                                              | patterned                              | `optional/format` legs green per dialect; `format-assertion` green                                                                                                                             |
| M8   | Bench harness, docs, publication readiness (`ecma-regex` published first)                                                                                                                                                                                                                                                                               | patterned                              | Bench reproducible; `uv build` + offline install smoke; README audited                                                                                                                         |
| M9   | Compiled output beyond the verdict: annotation and dependency records in emitted code, runtime coverage tracking and channel regions for `unevaluated*` (the M6 planner islands those consumers), `compile_list`/`compile_evaluator` reusing the M5 renderers, a compiled Bowtie variant                                                                  | judgment (contracts) + patterned         | Compiled `list`/`hierarchical` documents equal the interpreter's over every suite; the M6 census's `unlowerable` consumers become static; fuzz clean over full results                            |
| M10  | `dialects.draft04` through the public dialect-authoring surface                                                                                                                                                                                                                                                                                         | patterned                              | draft4 suite green, coexisting with 2020-12 in one registry                                                                                                                                    |

Session protocol for a milestone: read this file §0–§5 + the milestone row;
run the done-signal first (red); implement; done-signal green; every
previously green gate stays green; restate §0 in any subagent prompt. Keep
changes within the milestone — interface changes (§3–§4, P-decisions)
require a judgment-tier session and an update to this file.

**Status note (M0/M1, completed 2026-09-20):** all M0 gates green (ruff,
pyright strict over `src` and `packages`, four import-linter contracts,
build, namespace check; CI matrix 3.12–3.14). M1: the evaluator-level channel
gate (25 tests over a hand-written vocabulary) and its real-keyword port (11
tests) green; draft2020-12 leg over `boolean_schema`, `content`, `format`,
`pattern`, `required`, `type`, `ref`, `unevaluatedProperties`, `properties`,
`anyOf`, `anchor` pinned at **418 run / 123 skipped**, every skip naming an
unimplemented keyword except one `ref` group that needs the bundled
metaschema (M3); `refRemote` leg pinned at **25 run / 6 skipped**. `defs.json`
waits for M3 for the same reason. M1 shipped more than the six exemplars:
`type`, `required`, `allOf`, the meta-data annotations, `format` as
annotation-only, and `content*`. `ecma-regex` (104 tests; 4 more with the
`regex` extra) handles every pattern in the suite's non-optional files,
including `\p{Letter}`. Submodule pinned at `ab079cc2` (1301 draft2020-12
cases in total).

**Status note (M2, completed 2026-09-20):** every 2020-12 keyword except
`$dynamicRef` is bound. The applicator vocabulary spans three modules by
keyword class (in-place, object, array). draft2020-12 leg over 41 files
pinned at **1213 run / 6 skipped** (four `$dynamicRef` groups, the `ref`
metaschema group); `refRemote` leg **31 / 0**. `dynamicRef.json`,
`vocabulary.json`, and `defs.json` stay out of the leg until M3 bundles the
metaschemas and implements dynamic scope. `multipleOf` uses decimal
semantics (P2); `uniqueItems` buckets by canonical key (D20).

**Status note (M3, completed 2026-09-20):** `$dynamicRef` with full D8
scope resolution; the eight 2020-12 metaschemas bundled as package data and
registered lazily; `$vocabulary`-assembled dialects (unknown required →
`UnknownVocabularyError`, unknown optional skipped, none → the default
dialect); `validate_schemas`; D17 source positions end to end. The suite is
one loader-backed leg over every top-level draft2020-12 file, pinned at
**1301 run / 0 skipped**, plus an optional leg (`anchor`, `dynamicRef`,
`id`, `no-schema`, `unknownKeyword`, `refOfUnknownKeyword`) at **25 / 0**.
Bowtie (harness in `bowtie/`, `scripts/bowtie_check.py`, CI job): 2020-12
**1301 tests, 0 failed/errored/skipped/mismatched**, run locally against
the podman machine and in CI. The public bowtie.report listing is the
owner's submission.

**Status note (M4, completed 2026-09-20):** 2019-09, draft-07, and draft-06
are built in. New keywords: `$recursiveRef`/`$recursiveAnchor`,
tuple-or-schema `items`, `additionalItems`, `dependencies`, `definitions`,
a sibling-free `contains`; `unevaluated*` and `contains` are factories.
Nine more bundled metaschemas (17 total). In `$ref`-ignoring dialects the
registration walk skips a `$ref` node's siblings entirely. Suite legs, all
loader-backed, zero skips: draft2020-12 **1301**, draft2019-09 **1261**,
draft7 **929**, draft6 **841**; optional legs 26, 26, 12, 10. Bowtie, all
four dialects: the same counts, zero failures, errors, skips, or
mismatches.

**Status note (M5, completed 2026-09-20):** every output format renders
from one located tree: opt-in tracing in the evaluator, `to_render_node`
attributing records by path-node identity, and engine-free renderers for
`hierarchical`, `list`, the draft-03 `detailed` (built, then condensed per
§13.4.3) and `verbose`, and the public `trace`. The option matrix is
complete; `Result` carries `dropped_errors`/`dropped_annotations` at the
verbose level. Goldens: the TS engine's fourteen documents, byte-identical
apart from error text. Official output-tests: draft2020-12 **4**,
draft2019-09 **4** (`basic`, validated against each release's
output-schema), `v1` **3** (`list`). The D5 differential runs in every
suite leg (flag vs. hierarchical+verbose, verdicts equal). Security
baseline (`tests/core/test_security.py`): 100k-element `uniqueItems`, 5000-deep
schema and instance nesting, the `RecursionError` backstop, `reject_unsafe_regex`,
the star-height table, reserved names, wide instances, undeclared-* errors
under tree output — all within budget.

**Status note (M6, completed 2026-09-21):** the compiled flag validator.
Core gained the lowering IR, `KeywordBehavior.lower`,
`StaticFacts.applications`, the `evaluate_fragment` seam, registry
snapshots, and the P5 fences (ruff `S102`/`S307`, an AST walk, and an
audit-hook proof of exactly one `compile` and one `exec` per artifact).
`json_schema_engine.compiler` plans from `analyze()` facts alone, emits
an `ast.Module` of flat unit functions, inlines single-use children up to
CPython's loop-nesting cap, short-circuits `anyOf`/`oneOf`/`contains` only
where the plan proves the region verdict-only, threads the dynamic scope
only toward islands, and trampolines one way into the interpreter. Every
built-in keyword lowers except `$dynamicRef`/`$recursiveRef`. Compiled
suite legs at the interpreter's pins in both optimization settings:
draft2020-12 **1301**, draft2019-09 **1261**, draft7 **929**, draft6
**841** (optional 26/26/12/10). Plan census: 2020-12 **1206** units, **79**
interpreted (59 dynamic, 20 consumers with runtime-conditional coverage);
2019-09 **1184**/**65**; draft7 **762**/0; draft6 **680**/0. Goldens for
five fixtures. Hypothesis differential over **1248** suite groups: `ci`
profile 300 examples per dialect in the matrix, `deep` profile 20 000 per
dialect clean in 76 s, planted-divergence self-test green; injection
corpus 27 hostile strings × 7 shapes with the structural identifier
proof. Standalone: every static 2020-12 group imported with the compiler
absent, no code generated while validating. Bench (`packages/bench`,
report-only, 250 ms per task on this machine): compiled flag mode 80–300×
the interpreter and 1.6–5.9× fastjsonschema; fastjsonschema excluded on
`event` for disagreeing with the oracle on `unevaluatedProperties`.


**Status note (M7, completed 2026-09-21):** the formats package.
`json_schema_engine.formats` implements the nineteen defined formats from
their RFCs (ABNF transcriptions anchored `\A…\Z`; `ipaddress` for the
IP formats; `ecma_regex.parse` for `regex`; the `idna` extra for
IDNA2008, executed through its public API); tables per dialect (2020-12
= 2019-09 19, draft-07 17, draft-06 9). Core gained the
`FormatDefinition`/`FormatTable` contract, `asserting_format` in two
postures (the 2020-12 format-assertion vocabulary refusing unknown
names; `assert_formats=True` best effort in every standard dialect),
`create_engine(formats=..., assert_formats=...)`, `FormatsRequiredError`
for a table-less engine meeting the format-assertion vocabulary or
`assert_formats`, `FormatUnavailableError` for an entry whose extra is
missing, and the bundled `meta/format-assertion`. The compiler gained
`FormatTest`, `plan.formats`, hoisted `fmtN` predicates, and standalone
modules import predicates by the table entry's import path. `optional/
format` legs, on the interpreter, both compiled settings, and standalone:
draft2020-12 **866**, draft2019-09 **866**, draft7 **785**, draft6 **407**,
`format-assertion` **4**; the mandatory `format.json` legs unchanged
(annotation-only default); the plan census unchanged under
`assert_formats`. Without the extra: `idn-hostname` is unavailable
(loud at registration) and `hostname` accepts a well-formed `xn--` label
unchecked. The differential fuzz gained a corpus over every
`optional/format` case (**2928** entries, one per suite instance; the
`deep` profile's 20 000 examples clean in 17 s), and a 217-row
edge-case matrix pins the leap-second, digit, newline, and IDNA traps on
the interpreter, both compiled settings, and standalone together.

**Status note (M8, completed 2026-09-21):** publication readiness. The
release commits carry `ecma-regex` **0.1.0** and the engine **0.0.2**
(`ecma-regex>=0.1,<0.2`), `py.typed` in every portion, an engine sdist
without the test tree, CHANGELOGs, and `scripts/install_smoke.py`: an
offline install of both built artifacts into a fresh venv, probed from
inside (imports, private packages absent, evaluate, compile, standalone,
formats, 18 bundled metaschemas, versions) and type-checked strictly
from a consumer file; CI and the publish workflow run it. The
positions-reporting parser moved from the test-kit into core as
`parse_json_with_ranges` (D17), and a ninth import-linter contract keeps
the test-kit engine-free. Documentation: a user guide of eleven pages
plus an index under `docs/guide/`, `docs/reference.md` covering all
**115** exports (core 67, compiler 12, formats 6, ecma_regex 30),
`CONTRIBUTING.md`, and audited READMEs; `tests/test_docs.py` executes
every `python` block on every page in one namespace per page, and
`tests/test_reference.py` holds the reference to every `__all__` name.
Bench: seven corpora (`oas-document` and `api-payload` added), results
carrying machine, commit, and subject versions, `--compare`. On
`oas-document` the compiled flag validator runs at **0.67×** the
interpreter: the root's `anyOf` beside `unevaluatedProperties` leaves
coverage runtime-conditional, so the whole root is interpreted through
the trampoline and the artifact only pays overhead; that is the M9
target (runtime coverage tracking makes those consumers static). Public
lowering of custom keywords (the IR in `core.lowering` is not exported)
is likewise deferred to M9. Suite **15447** tests; Bowtie unchanged.

**Status note (M9, completed 2026-09-21):** the compiled tier beyond the
verdict, in three steps. (1) Plan-time resolution of `$dynamicRef` and
`$recursiveRef` (the TS engine's ADR 0004, extended to 2019-09): the
2020-12 census's dynamic islands fell 59 → **1** (58 sites resolved),
2019-09's 49 → **2** (47 resolved); the 2020-12 metaschema and the
OpenAPI 3.1 schema plan with no interpreted unit, and a seed corpus of
stable and unstable shapes runs on every surface and in the fuzz.
(2) Runtime coverage tracking: no `unlowerable` consumer island remains
(census 2020-12 **1371** units / 1 interpreted; 2019-09 **1300** / 2);
the OpenAPI schema compiles as 368 static units (8 tracked, 68 in
regions), emits a standalone module, and its compiled flag validator
runs at **220×** the interpreter (was 0.67×), 286× jsonschema. Flag
goldens outside regions stayed byte-identical. (3) `compile_evaluator`:
the four evaluator suite legs compare five demands under both
optimization settings at the interpreter's pins (**1328/1288/942/852**)
with zero divergence, the official output-tests pass through the
artifact, the fuzz compares whole `Result`s (list and hierarchical,
relevant and verbose, with traces; a planted-divergence self-test proves
the comparison sees a corrupted param and a dropped annotation; the
`deep` profile's 20 000 examples clean in 19 s), goldens pin every
fixture in both modes (16), evaluator census pins add tracked/region
counts (2020-12: 85/73), and the evaluator tier costs 2–3.5× the
interpreter's own `list` output on the bench. Bowtie now runs both
tiers at the same pins (1301/1261/929/841, zero failures). The lowering
IR is public (`json_schema_engine.core.lowering`, 73 names, documented
with a lowering guide). The compiled evaluator deviates from the plan in
one place, on purpose: only the annotation selection is fixed at compile
time; `error_params`, `verbose`, `trace`, and `positions` are per call,
since the emitted code is the same for every level.

## 7. Open items (owner decisions)

1. **Releases** — the owner decides when to release, and tags and merges;
   nothing is pushed by automation. The procedure is CONTRIBUTING.md
   § Releasing: bump the version, date the changelog entry, release
   `ecma-regex` first when the engine's pin needs a version PyPI lacks, and
   tag — `publish.yml` refuses a tag that does not match `pyproject.toml`.
   This item names no version on purpose, so it needs no edit per release;
   the record of what shipped is the changelogs and the tags.
2. **Regex default for a future RFC dialect** — I-Regexp with search
   semantics is the expected answer; confirm when the RFC text settles.
3. **Async façade timing** (P4) — after M3 unless a consumer needs it earlier.
4. **Bowtie image publication** — the harness image is built locally by
   `scripts/bowtie_check.py` (both tiers since M9); publishing it (ghcr.io)
   and listing the implementation with Bowtie are owner-controlled.
5. **Per-site dispatch for unstable dynamic sites** — compile one target
   per possible resolution and select by the first declaring scope entry;
   deferred until a real schema needs it (the suite's "multiple dynamic
   paths" groups are the only known cases).
6. **Evaluator standalone emission** — prologue-only work under D10's
   helper convention; deferred (owner decision, M9).
7. **Per-resource metaschema validation** — `validate_schemas` checks a
   document against its *root* dialect's metaschema only, so an embedded
   resource on another dialect is checked by the wrong one. P14 supplies the
   per-resource dialect and P11 the per-resource location, so the data is
   there; the obstacle is ordering. The check deliberately runs *before* the
   walk so an invalid document never registers, but only the walk discovers
   embedded resources. It needs either a walk-free enumeration pass (the
   two-phase read factored out of `_walk`) or a walk-validate-roll-back mode
   reusing P13's journal — more attractive now that P14's retry loop has
   already made that journal load-bearing on a success path. It also needs a
   ruling on whether an embedded resource whose metaschema is unavailable is
   skipped, as the root case is today.

8. **Pointer navigation reads identifiers in non-schema positions** —
   `resolve_ref`'s pointer walk and `child` apply the dialect's identifier
   extractor to every object they step onto, including one that is *data*.
   A pointer into `enum`/`const` therefore rebases onto an `$id` written
   there, minting a resource identity the registration walk correctly never
   indexed (§5: schema positions only). Reachable from an ordinary schema,
   and the error names a URI that was never an identifier:

   ```python
   {"$id": "https://r/", "$ref": "#/enum/0/properties/a",
    "enum": [{"$id": "https://ghost/", "properties": {"a": {"type": "string"}}}]}
   # evaluate -> UnresolvableReferenceError: unknown schema 'https://ghost/'
   ```

   It also makes `child` raise on the evaluation hot path. Not a quick fix:
   navigation cannot tell a schema position from data without running each
   keyword's `analyze()`, which is the walk. Options are to carry the walk's
   knowledge (only rebase onto a base `_document_dialects` knows), or to
   refuse a pointer that leaves schema positions at all. P14's
   `_dialect_after` already takes the first approach for the *dialect*
   lookup, so the shape exists; the base itself is what still drifts.

9. **A stale range lookup survives a re-registration** — `_document_ranges`
   is written only when `get_range` is supplied, so registering a document
   with ranges and then registering it again without them leaves the first
   lookup in place, and `Engine.locate` keeps reporting offsets from the
   earlier text. P12 means the second document must be `json_equal` to the
   first, but equal JSON can come from differently formatted text, so the
   positions can point at the wrong characters. Minor, and the fix is
   probably to drop the entry when a re-registration supplies no lookup —
   the question is whether that is a surprise for a caller who registered
   twice deliberately.


10. **P12 has three gaps where an identifier still shadows silently** — all
    found reviewing P12, none covered by its tests:

    - An embedded `$id` equal to another document's *retrieval URI* is
      claimed and then unreachable. `_claim_resource` checks `_documents`
      only, while `_canonical` prefers `_aliases`, so
      `{"$id": "https://a/", ...}` registered as `https://r/` followed by a
      document embedding `{"$id": "https://r/", "type": "string"}` registers
      cleanly and every lookup of `https://r/` answers the first document.
      Measured: `$ref: "https://r/"` validates a number, not a string.
    - Claiming a bundled metaschema's URI is order-dependent. On a fresh
      engine `register_schema({"$id": DIALECT_2020_12, ...})` succeeds and
      shadows the bundled document (`_canonical` sees it in `_documents` and
      never lazily registers the real one); after any evaluation that
      touched the metaschema, the same call raises `DuplicateResourceError`.
      Either answer may be right — a caller overriding a metaschema is a
      real use — but it must be the same answer both times.
    - A retrieval-URI alias is still last-write-wins: registering a second
      document with a *different* `$id` under a retrieval URI an earlier one
      used silently repoints `_aliases[retrieval]`. Not a resource
      collision, so P12 does not see it, but it is the same shadowing shape.

11. **A root `$id` is not checked the way an embedded one is.** Under
    2020-12 and 2019-09 an `$id` may end in an empty fragment (a bare `#`),
    which it SHOULD NOT, and may not carry a non-empty one (the metaschemas'
    `^[^#]*#?$`). That rule is the same at a document root and at an
    embedded resource, but only the embedded position enforces the part
    that is a MUST:

    - **Non-empty fragment** — refused in an embedded `$id`
      (`InvalidIdentifierError`), but at a document root `identify` resolves
      the `$id` unchecked and `_resource_of` strips the fragment, so
      `{"$id": "https://x.example/s#frag"}` registers as
      `https://x.example/s` and the fragment silently vanishes; a root
      `{"$id": "#foo"}` lands on the retrieval URI the same way. Fix: give
      the root the same check as `_check_embedded_id`.
    - **Empty fragment** — accepted at both positions and stripped, as the
      spec allows. Correct today; no change.
    - **`""` and `"#"`** — not a fragment question. At a root they mean the
      retrieval URI, which is legal and correct. Embedded, they resolve to
      the *enclosing* resource's own URI, so refusing them there is P12's
      "two resources, one URI" rule rather than a syntax rule — which is why
      it applies only below the root. An earlier wording of this item
      counted root `""` as a problem; it is not.

    **Owner decision (2026-09-23):** keep the 2020-12/2019-09 behavior as
    the default, empty fragment allowed, and add an opt-in engine option that
    forbids *any* fragment, empty included, in an `$id` that sets a base URI.
    It is a forward-compatibility aid: IETF draft-03 makes that a MUST NOT,
    but draft-03 cannot currently be selected through a metaschema. Opt-in
    keeps it within D14. Scope it to `$id` as a base URI, so draft-07/06
    `#name` anchors — an anchor, not a base — are untouched. The dialects
    guide currently says a base URI "cannot carry a fragment"; it should say
    *non-empty* fragment, and mention the option once it exists.

14. **No way to replace a registered document.** P12 turns a modified
    re-registration under the same URI into `DuplicateResourceError`, and
    nothing unregisters. The edit-and-re-register loop (a REPL, a test that
    mutates a fixture, an editor integration re-validating on save) now
    needs a fresh engine per edit, which also discards every other
    registration and any compiled artifact's snapshot lineage. P13's
    revisit names `unregister`; this promotes it: decide the API
    (`unregister(uri)`, or `register(..., replace=True)`), and what happens
    to a resource an earlier registration also claims ("P12 has three gaps …" above), to
    anchors the old document minted, and to `_produced_ids`/`_consumed_ids`
    contributions that nothing else re-derives.


15. **`UnknownDialectError.dialect_uri` never reaches a caller.** P14 added
    it so the registry could ask the engine for a dialect an embedded
    resource declared, and the engine consumes it to assemble and retry.
    When assembly then fails, `_register_assembling_dialects` raises
    assembly's own error, carrying the location, chain and source across but
    not the URI — so through `Engine` the attribute is always `None`, and a
    caller who wants to supply the missing metaschema has to parse the
    message. The fix is one line: carry `dialect_uri` over with the rest.
    Worth deciding at the same time whether a document-root `$schema`
    failure should set it too, so the attribute means "the dialect that
    could not be found or assembled" wherever it is raised. Once it does,
    the `dialect_uri` notes in `docs/reference.md` and the changelog, which
    currently say it arrives `None`, need rewriting.

### Resolved (owner, 2026-09-23)

- "`compile_validator` drops the location chain": the flag artifact's
  `validate` is the emitted function itself, so rather than wrap it — one
  more frame on every call of the tier that exists to be fast — the chain is
  attached in the two interpreter trampolines (`frag`, `frag_cov`), the only
  exits from it that carry a location. `attach_location_chain` moved to
  `registry` so the compiled runtime can reach it without importing the
  engine.
- "One document-level location is still a bare URI": a root
  `DuplicateResourceError` now names `uri#`. The error-path hazard filed
  with it is closed too: `attach_location_chain` treats a failure while
  building the chain as "no chain" rather than letting it replace the error
  being reported, the same rule `_register` applies around `_describe`.

### Resolved (owner, 2026-09-22)

- `$schema` governs the resource it roots, not the document (P14).
- Registration is atomic (P13), answering the open item this section held.
- Location chains (P11), answering the four questions this section held:
  (a) derived by the registry and attached by `Engine`'s entry points, since no
  raise site holds a registry; (b) `Engine.locate` is untouched and composes
  with the chain rather than being subsumed by it, so `positions=True` pays
  nothing; (c) `str(error)` appends a chain only past one hop, leaving
  single-resource messages byte-identical; (d) `UnresolvableReferenceError`
  also carries `reference`, `resolved_against` and `resolved_to`.
- Duplicate `$id`s and duplicate anchors are registration errors (P12).

### Resolved (owner, 2026-09-20)

- One distribution with namespace layout, not a family (D16).
- Python floor 3.12.
- ECMA-262 is the default regex dialect; switchable (P1).
- No python-jsonschema compatibility shim in the first release (D14).
- The ECMA-262 translator is a separate package, `ecma-regex` (P1).
