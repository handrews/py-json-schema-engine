# json-schema-engine (Python): engineering design

**Status:** living design contract. M0–M3 complete (2026-09-20); M4 next. Derived from the
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
| D1  | Execution model                | amended | Two tiers, one keyword registry. The interpreter (`json_schema_engine.core`) is the reference semantics. The compiler (`json_schema_engine.compiler`, M6) consumes only `analyze()` facts and each keyword's optional `lower()` IR, never keyword names. **Amendment:** the compiler emits a Python `ast` tree, never source text; injection is unrepresentable because schema data only ever becomes `ast.Constant` nodes. The trampoline into the interpreter for dynamic islands is unchanged. |
| D2  | Keyword identity               | carried | Keywords identified by URI; a vocabulary is a named map of keyword URIs; a dialect is an ordered set of vocabularies; drafts are predefined dialects. All data, no privileged built-ins. `KeywordBehavior` is a frozen dataclass of callables (§3), not a class hierarchy.                                                                                                                                                                                                                        |
| D3  | Keyword interface              | carried | `analyze(value, context) -> StaticFacts` + `evaluate(value, cursor, ctx) -> bool` (§3). Applicators request subschema application through the engine; the engine owns path, scope, and frame bookkeeping in exactly one place (`evaluator.py`).                                                                                                                                                                                                                                                 |
| D4  | Keyword communication          | carried | Frame-scoped record channel (§4) with two record kinds: annotation records (the keyword's own value; output) and dependency records (computed data for other keywords; never output). Records merge to the parent frame only on success.                                                                                                                                                                                                                                                         |
| D5  | Annotation selection           | carried | `annotations=False \| True \| AnnotationSelection`: allow-lists by keyword name and vocabulary URI, deny-lists subtracted after, a `keep` predicate over the rendered unit. Internal consumers always see the channel. The interpreter elides at annotate time what the selection rules out and dependency records nothing consumes. Producers declare `produces`, consumers declare `consumes`, or `UndeclaredProductionError` / `UndeclaredConsumptionError` is raised — never a silently empty channel. |
| D6  | Output                         | carried | Formats by name: `flag`, `basic`, `detailed`, `verbose` (draft-03 §13) and `list`, `hierarchical` (machines-oriented proposal); three levels (minimal, relevant, verbose); orthogonal controls `annotations`, `error_params`, `positions`, `trace`. Unsupported combinations raise `OutputOptionsError` before evaluation. Each format fixes its own document structure and field vocabulary (`basic` speaks draft-03's `keywordLocation`/`absoluteKeywordLocation`/`instanceLocation`; `list`/`hierarchical` speak the proposal's `evaluationPath`/`schemaLocation`/`instanceLocation`), while the flat `Result.errors`/`Result.annotations` surface always carries the engine's native `evaluationPath`/`schemaLocation`/`inputLocation`. Python-side option names are snake_case (P8).      |
| D7  | Async boundary                 | amended | `evaluate` (and later `compile`) are synchronous. **Amendment (P4):** loaders are synchronous callables by default; an `AsyncEngine` façade over `asyncio` loaders is a later milestone. Registration itself never awaits.                                                                                                                                                                                                                                                                       |
| D8  | Dynamic scope                  | carried | Full 2020-12 `$dynamicRef` semantics over a stack of entered schema resources; 2019-09 `$recursiveRef`/`$recursiveAnchor` as the degenerate case. Compiler marks dynamically reachable scope as an island → interpreter trampoline.                                                                                                                                                                                                                                                                |
| D9  | Lowering catalogue             | carried | Same catalogue in intent (evaluated-set tracking, production elision, constant locations, small-set membership, lazy unit materialization, regex/format hoisting). Thresholds and mechanisms (`frozenset` vs equality chains, etc.) are re-measured against CPython at M6, not assumed from V8.                                                                                                                                                                                                  |
| D10 | Compiler output modes          | amended | Runtime compilation = `compile()` of an `ast.Module` (D1). Standalone emission = `ast.unparse` to a `.py` module importable without the compiler. There is no CSP; the security analogue is that only `json_schema_engine.compiler` may touch `ast`/`compile` (P5), and deployments can audit that with `sys.addaudithook`. CPython's cap on statically nested blocks means emission splits units into functions rather than nesting loops.                                                     |
| D11 | Draft support                  | carried | Native in core: 2020-12, IETF drafts, 2019-09, draft-07, draft-06. draft-04 as a separately importable dialect module (`json_schema_engine.dialects.draft04`, M10), assembled through the public dialect-authoring surface and coexisting with every other draft in one registry.                                                                                                                                                                                                                 |
| D12 | Testing strategy               | carried | Official suite as git submodule with a pytest runner in `test_kit`; both tiers pass the identical suite with exact-count pins; differential fuzzing (Hypothesis) as the compiler's primary correctness gate; Bowtie harness from M3; releases conformance-gated.                                                                                                                                                                                                                                  |
| D13 | Error model                    | carried | Keywords emit structured error data (keyword id, params, message) into units; rendering is presentation. Params are designed so a future compatibility adapter can reconstruct another library's error shape mechanically.                                                                                                                                                                                                                                                                       |
| D14 | Strictness                     | carried | Core is spec-clean; strict-mode hygiene is opt-in only via a lint layer or stricter metaschemas. No python-jsonschema compatibility shim in the first release (owner decision 2026-09-20).                                                                                                                                                                                                                                                                                                       |
| D15 | IP policy                      | carried | §0.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| D16 | Packaging                      | amended | One repository as a uv workspace. **One published distribution `json-schema-engine`** laid out as a PEP 420 namespace package: `json_schema_engine.core`, `.compiler`, `.formats`, `.dialects.*`, so a later split into several distributions changes no import path. Unpublished workspace members: `test-kit`, later `bench`, `bowtie`. **`ecma-regex` is a separate, publishable workspace member** with no dependency on the engine (P1). No third-party runtime dependencies.  |
| D17 | Source-position correlation    | carried | Loaders may return `get_range(document_root_pointer)`; the registry maps resource-rooted locations to document-rooted pointers; correlation only at unit escape (`positions=True` decorates units with `source`) or via `Engine.locate()`. Zero hot-path cost. Implemented in M3; the test-kit's `parse_json_with_ranges` is the reference loader.                                                                                                                                                                                                                                                                          |
| D18 | Per-dialect identifier syntax  | carried | Identifier extraction is dialect data (`IdentifierExtractor`), consumed by the registration walk and pointer navigation. `ref_ignores_siblings` for draft-07/06.                                                                                                                                                                                                                                                                                                                                 |
| D19 | Non-schema values              | carried | Fail loud in two layers: the registration walk raises `InvalidSchemaError` for a keyword-claimed schema position holding neither object nor boolean; `apply_schema` raises the same as a lazy backstop. Keyword-value validity stays the metaschema's job.                                                                                                                                                                                                                                       |
| D20 | Resource-exhaustion bounds     | amended | Same three defenses. (1) ReDoS: the regex dialect/backend is pluggable (P1); `detect_unsafe_regex` star-height screen backs opt-in `reject_unsafe_regex` raising `UnsafeRegexError` at registration; a linear-time backend is a revisit item (neither `re` nor `regex` is linear-time). (2) `uniqueItems`: O(n) bucketing by `canonical_key`, confirmed by `json_equal`. (3) Depth: P3. Prototype-pollution defenses are N/A — Python dicts have no prototype chain; the suite's trap keys are still unit-tested to prove it. |

### Python-specific decisions

| #  | Decision                     | Choice                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Why                                                                                                                                                                                                                                                                                | Revisit trigger                                                                                                        |
| -- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| P1 | Regex dialect and backend    | `pattern`-class keywords are evaluated under a **regex dialect** (ECMA-262 by default for every current draft; Python `re` passthrough as an engine-wide override for Python-only migrations; I-Regexp later, as the default of whichever dialect the RFC defines) and a **backend** (`re` by default; the `regex` module via the `regex` extra). The ECMA-262 translator is the standalone package **`ecma-regex`** (`packages/ecma-regex`, import `ecma_regex`): one regex AST, front-ends parse into it, back-ends emit for `re`/`regex`, `search` with ECMA semantics, `star_height` for the D20 screen. It imports nothing from the engine. Untranslatable patterns fail at **registration** with a typed error carrying the schema location. Anchoring is a property of the keyword (`pattern` is search), never of the dialect. | Schemas are portable artifacts; a Python-flavoured default would disagree with every other conformant implementation and with Bowtie. The translator is an ecosystem gap worth publishing on its own (owner decision 2026-09-20). | The JSON Schema RFC adopts I-Regexp: add the front-end and flip that dialect's default. A linear-time backend appears. |
| P2 | Number and equality model    | Numeric identity is mathematical. `bool` is never a number: every type test checks `bool` before `int`, and `json_equal`/`canonical_key` distinguish `True` from `1`. `type: "integer"` accepts `int` (not `bool`) and `float` with zero fractional part (`1.0` is an integer, per spec). Python ints are unbounded, so big literals stay exact (an improvement over JS). Non-finite floats are outside the JSON model: parse boundaries (loaders, the suite runner) reject `NaN`/`Infinity`; the hot path never checks. Plain `==` on JSON values is banned in core; `json_equal` is the only equality. **`multipleOf` uses decimal semantics (M2):** each operand becomes the exact rational of its shortest round-trip `repr` (`Fraction(Decimal(repr(x)))`), so `0.0075` is a multiple of `0.0001` as the author meant, and `1e308 / 0.123456789` is simply a non-integer rather than an overflow.                                                                                                                                                                                                              | `True == 1`, `hash(True) == hash(1)`, and `{"a": 1} == {"a": True}` are all true in Python; `json.loads` accepts `NaN` by default.                                                                                                                                                | Never for bool. A schema author who needs binary-float `multipleOf` semantics (none known).                            |
| P3 | Recursion budget             | `EvalState` carries an explicit depth counter; `max_depth` (default 512) bounds both registration nesting and evaluation application nesting and raises `MaxDepthExceededError` **before** CPython's recursion limit can. `Engine.evaluate` and `SchemaRegistry.register` additionally translate a stray `RecursionError` into the same typed error. Library code never calls `sys.setrecursionlimit`.                                                                                                                                                                                                                                                                                                                                                                                                                | CPython's default limit is 1000 frames and each schema application costs several.                                                                                                                                                                                                  | Measured frames-per-application changes the safe default.                                                              |
| P4 | Loaders are sync-first       | `Loader = Callable[[str], LoadedResource \| None]` where `LoadedResource` is a Protocol (`value`, `uri`), so a loader written with no dependency on the engine satisfies it structurally; `LoadedDocument` is the engine's own concrete form. A loaded resource may also offer `get_range(document_pointer)` (D17); the engine reads it with `getattr`, so resource types without it stay valid. `None` from a loader is a miss, never an error. `Engine.register_schema` is local-only; `Engine.load_schema` drains unresolved references through the loaders synchronously. An `AsyncEngine`/async-loader façade is a later milestone; it wraps the same registry.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Most Python callers are synchronous; forcing `await` on registration would be the tail wagging the dog.                                                                                                                                                                             | A consumer needs concurrent remote loading.                                                                            |
| P5 | Packaging and import fences  | See D16. Enforced by import-linter contracts run in CI from M0: `json_schema_engine.core` never imports `json_schema_engine.compiler`, `ast`, or `json_schema_engine.test_kit`; `ecma_regex` never imports `json_schema_engine`. The builtin `compile` is not an import, so it is banned in core by a lint gate. The engine's next release must publish `ecma-regex` first (or wait), since core depends on it.                                                                                                                                                                                                                                                                                                                                                                                                       | The "core has no code generation in its dependency graph" invariant is the Python form of the TS ESLint fences.                                                                                                                                                                    | The compiler needs a helper that belongs in core: move it, never relax the contract.                                   |
| P6 | Records vs. units            | Engine records (`AnnotationRecord`, `DependencyRecord`, `ErrorRecord`, `PathNode`, `Frame`) are `@dataclass(eq=False, slots=True)` and never rendered directly. Output units are `TypedDict`s with the wire field names, so `json.dumps` takes them unchanged and optional keys are genuinely absent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Records need identity and lazy path materialization; units need to *be* the JSON.                                                                                                                                                                                                  | A renderer needs behaviour on units.                                                                                   |
| P7 | Identity-keyed structures    | `Cursor`, `SchemaRef`, `PathNode`, and all record types use identity equality (`eq=False`), so sets and dict keys are identity-keyed. Channel rule 4 filters dependency records by **cursor identity**; the cycle guard is keyed by (schema location, cursor identity). A `frozen=True` dataclass with default equality would silently give value semantics and break cousin invisibility.                                                                                                                                                                                                                                                                                                                                                                                                                              | Rule 4 depends on it; `dict` values are unhashable anyway.                                                                                                                                                                                                                         | Never.                                                                                                                 |
| P8 | Naming                       | Python API: snake_case functions, options, and attributes (`register_schema`, `error_params`). JSON Schema keyword names and output-document field names are wire formats and keep their spec spelling. Module names follow the TS modules where sensible (`registry`, `dialect`, `cursor`, `output`, `result`); `json_model.py` rather than `json.py`, `evaluator.py` for the TS `engine.ts` machinery, `engine.py` for the public `Engine` façade.                                                                                                                                                                                                                                                                                                                                                                | Idiomatic Python without renaming spec concepts.                                                                                                                                                                                                                                   | —                                                                                                                      |

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
| `engine.py`     | `Engine`, `create_engine`: the public façade.                                                                                               |
| `keywords/`     | One module per keyword class: `core.py`, `validation.py`, `applicator.py`, `unevaluated.py`, `format.py`; `dialect2020.py` assembles.       |

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
    # lower: added at M6 (compiler IR); absent means "interpreted unit", never a failure
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
   annotation — D9b), and list output runs every branch.

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
- Bundled metaschemas register lazily on first reference, so `create_engine()`
  stays cheap for the suite and Bowtie, which build one engine per case;
  eager registration of eight documents would have doubled the suite's time.
- `repr(float)` is the shortest round-trip form, so `Decimal(repr(x))`
  recovers the decimal a schema author wrote; exact binary rationals
  (`Fraction(x)` directly) would make `0.0075` a non-multiple of `0.0001`.

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


## 7. Open items (owner decisions)

1. **`ecma-regex` PyPI reservation** — the name was free on 2026-09-20; the
   engine's next release depends on it being published.
2. **Regex default for a future RFC dialect** — I-Regexp with search
   semantics is the expected answer; confirm when the RFC text settles.
3. **Async façade timing** (P4) — after M3 unless a consumer needs it earlier.

### Resolved (owner, 2026-09-20)

- One distribution with namespace layout, not a family (D16).
- Python floor 3.12.
- ECMA-262 is the default regex dialect; switchable (P1).
- No python-jsonschema compatibility shim in the first release (D14).
- The ECMA-262 translator is a separate package, `ecma-regex` (P1).
