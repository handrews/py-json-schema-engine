# json-schema-engine (Python)

A JSON Schema implementation for Python that aims to be both spec-complete
and built for speed: an interpreter that is the reference semantics, a
compiler tier for hot paths, full annotation collection, and every standard
output format. It is the Python counterpart of
[handrews/json-schema-engine](https://github.com/handrews/json-schema-engine)
and shares its architecture: two tiers, one keyword registry, a frame-scoped
record channel, and the new (2026)
[IETF working group draft-03](https://www.ietf.org/archive/id/draft-ietf-jsonschema-json-schema-03.html)
relevance model.

Produced by Henry Andrews via Claude Code.

**`[json-schema-engine](https://pypi.org/project/json-schema-engine/)` and
`[ecma-regex](https://pypi.org/project/ecma-regex/)` are published on PyPI.

**Status: The `0.0.x` line is functionally complete but experimental.**

See [CHANGELOG.md](CHANGELOG.md) for the current release's contents.
[DESIGN.md](DESIGN.md) is the design contract and carries the milestone
status.

All features are expected to work, but have not been tested beyond
what the CI tests, including Bowtie, cover.  Additional testing
and CI enhancements are in progress.

Aside from the functionality, during the `0.0.x` release line,
the exact shape of the function or method calls and any exceptions
they raise may change to improve developer experience.  This release
line also has AI-written documentation.  Promotion to `0.1.0` will
occur when the interface is believed to have solid developer UX and
the documentation has been human-audited.

Promotion to `1.0.0` will occur when real-world usage indicates
production-readiness.

The regular-expression translator lives in its own package,
[`ecma-regex`](https://pypi.org/project/ecma-regex/) (`0.1.0`):
ECMA-262 patterns
for Python, with JavaScript semantics, no dependency on this engine.

## Install

```sh
pip install json-schema-engine
```

Python 3.12+. Extras: `[idna]` for IDNA2008 support (`idn-hostname`, and the
`xn--` label check inside `hostname`); `[regex]` to swap in the `regex`
package as the pattern backend.

## Use

```python
from json_schema_engine.core import create_engine

engine = create_engine()
uri = engine.register_schema(
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
    "https://example.com/person",
)
assert engine.evaluate(uri, {"name": "Ada"}).valid
result = engine.evaluate(uri, {}, output="list")
assert result.errors is not None and result.errors[0]["evaluationPath"] == "/required"
```

Four drafts are built in: 2020-12 (the default), 2019-09, draft-07, and
draft-06. A document's `$schema` selects its dialect; `create_engine(
default_dialect=DIALECT_DRAFT_07)` sets the dialect for documents without
one. Each keeps its own semantics, so a draft-07 `$ref` ignores its
siblings while a 2019-09 one does not.

Every standard output format is available by name: `flag` (the default),
`basic`, `detailed`, and `verbose` from the
[IETF working group draft-03](https://www.ietf.org/archive/id/draft-ietf-jsonschema-json-schema-03.html)
output sections, and `list` and `hierarchical` from the
[machines-oriented proposal](https://github.com/json-schema-org/json-schema-spec/blob/main/specs/output/jsonschema-validation-output-machines.md).
Annotations are a separate control (`annotations=True`, or an
`AnnotationSelection`), `verbose=True` asks `list`/`hierarchical` for the
verbose level with irrelevant records marked as dropped, and `trace=True`
adds the application tree with error indexes into `result.errors`.

```python
result = engine.evaluate(uri, {"name": 3}, output="hierarchical")
assert result.output_document == {
    "valid": False,
    "evaluationPath": "",
    "schemaLocation": "https://example.com/person#",
    "instanceLocation": "",
    "details": [
        {
            "valid": False,
            "evaluationPath": "/properties/name",
            "schemaLocation": "https://example.com/person#/properties/name",
            "instanceLocation": "/name",
            "errors": {"type": "expected string"},
        }
    ],
}
```

`create_engine(validate_schemas=True)` checks every registered document
against its metaschema, each embedded dialect against its own, and raises
`SchemaValidationError` with the errors.
A loader that reports source positions (see `parse_json_with_ranges`,
exported from `json_schema_engine.core`) lets `evaluate(..., positions=True)`
attach a `source` location to every error and annotation, and
`engine.locate()` answers the same question for any schema location.

## Compile

The compiler tier turns a registered schema into a Python function. It is
not a second implementation: any subschema it cannot emit (a `$dynamicRef`
whose target differs by path, an in-place cycle) calls back into the
interpreter, so a compiled validator is exactly
as correct as `Engine.evaluate` and never less complete. Tier choice is a
performance decision, not a semantic one.

```python
from json_schema_engine.compiler import compile_validator, emit_standalone

compiled = compile_validator(engine, uri)
assert compiled.validate({"name": "Ada"}) is True
assert compiled.validate({}) is False
print(compiled.source)  # the emitted module, for reading
module_source = emit_standalone(engine, uri)  # importable without the compiler
assert "def validate" in module_source
assert "import json_schema_engine.compiler" not in module_source
```

`compile_validator` returns a verdict-only validator (the flag level) that
binds a snapshot of the registries at compile time, so register everything
first. `emit_standalone` writes the same code as a module that imports
only the standard library and this package's pure helpers; it refuses,
with `StandaloneUnsupportedError`, a schema that would need the
interpreter at evaluation time. Compiled code assumes plain data as
`json.loads` produces it (`dict`, `list`, `str`, `int`, `float`, `bool`,
`None`); subclasses of those types belong to the interpreter.

`compile_evaluator` compiles a schema into an evaluator serving every
output format the interpreter does — errors, annotations, dropped
records, and the application trace, not only the verdict. The annotation
selection is fixed at compile time; every other control (`output`,
`error_params`, `verbose`, `trace`, `positions`) is chosen per call, same
as `Engine.evaluate`.

```python
from json_schema_engine.compiler import compile_evaluator

evaluator = compile_evaluator(engine, uri, annotations=True)
compiled_result = evaluator.evaluate({}, output="list", error_params=True)
interpreted_result = engine.evaluate(
    uri, {}, output="list", error_params=True, annotations=True
)
assert compiled_result.errors == interpreted_result.errors
```

## Formats

`format` annotates by default in every dialect (the specs' default, and
what the official `format.json` legs require). Assertion is opt-in, from a
format table implemented from each format's RFC and verified against the
official `optional/format` suite:

```python
from json_schema_engine.core import create_engine
from json_schema_engine.formats import FORMATS_2020_12, format_table_for

# The 2020-12 format-assertion vocabulary: a metaschema declaring it makes
# `format` assert; names the table lacks are refused at registration.
engine = create_engine(formats=FORMATS_2020_12)
# Best effort in every standard dialect: known names assert, unknown names
# annotate only.
engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
uri = engine.register_schema({"format": "date-time"}, "https://example.com/dt")
assert engine.evaluate(uri, "1998-12-31T23:59:60Z").valid
assert not engine.evaluate(uri, "1998-12-31T22:59:60Z").valid
```

`FORMATS_2020_12` (also 2019-09) carries the nineteen defined formats;
`FORMATS_DRAFT_07` and `FORMATS_DRAFT_06` carry each draft's list, and
`format_table_for(dialect_uri)` picks one. A metaschema that declares the
format-assertion vocabulary on an engine without a table raises
`FormatsRequiredError`, and `assert_formats=True` without a table does too.
A custom table is any mapping of names to `FormatDefinition(test, types)`;
`types` scopes a format to instance types other than strings.

`idn-hostname` and the A-label checks inside `hostname` need IDNA2008,
provided by the `idna` extra:

```sh
pip install 'json-schema-engine[idna]'
```

Without it, asserting `idn-hostname` raises `FormatUnavailableError` at
registration, and `hostname` accepts a well-formed `xn--` label without
decoding it. Compiled validators assert formats too; a standalone module
imports the predicates it needs from `json_schema_engine.formats`, so the
extra must be installed wherever such a module runs.

## Documentation

- [User guide](docs/guide/index.md) — validation, output formats,
  annotations, dialects, loaders, source positions, metaschemas, custom
  keywords, security, compiling schemas, and formats, topic by topic.
- [API reference](docs/reference.md) — every public name, by package.
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, gates, and conventions.
- [CHANGELOG.md](CHANGELOG.md) — what changed, release by release.
- [DESIGN.md](DESIGN.md) — the engineering design contract and milestone
  status.

## Security

Schemas and instances are both often untrusted input. The interpreter
generates no code — there is no `compile()` or `exec()` on its path — so
code-injection concerns do not apply to it; a denial-of-service bound is
best effort, not a guarantee, so treat wildly untrusted schemas with the
same care as any other untrusted program input. Three specific vectors have
a bound or an opt-out.

**Regular expressions (ReDoS).** `pattern` and `patternProperties` compile
untrusted regexes and run them against untrusted strings; Python's `re` can
backtrack catastrophically on a pattern like `(a+)+$`. `reject_unsafe_regex`
screens for nested unbounded quantifiers at registration:

```python
from json_schema_engine.core import create_engine, UnsafeRegexError

engine = create_engine(reject_unsafe_regex=True)
try:
    engine.register_schema({"pattern": "(a+)+$"}, "https://ex/redos")
except UnsafeRegexError:
    pass  # rejected before it ever runs
else:
    raise AssertionError("expected UnsafeRegexError")
```

Patterns are ECMA-262 by default, translated by the `ecma-regex` package to
the `re` backend (a `regex` backend is available via the `regex` extra);
neither backend is linear-time, so the screen is a heuristic, not a proof.
`regex_dialect="python"` hands patterns to `re` untouched, for schemas
written for Python only.

**Recursion depth.** `max_depth` (default 512) bounds both registration
nesting and evaluation nesting, raising the typed `MaxDepthExceededError`
before CPython's own stack limit can produce an untyped `RecursionError`; a
stray `RecursionError` that does slip through is still converted to the
same typed error. The engine stays usable afterward — each `evaluate` or
`register_schema` call runs in fresh state, so a rejected document does not
poison later calls.

**Array uniqueness.** `uniqueItems` compares elements in O(n) by bucketing
on a canonical key and confirming collisions with full JSON equality, so
large arrays of distinct values do not incur quadratic cost, while genuine
duplicates — including numbers equal across `int`/`float` and objects that
differ only in member order — are still reported.

## Development

```sh
uv sync --all-packages --all-groups
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run lint-imports
```

The official test suite is a git submodule at `test-suite/`; clone with
`--recurse-submodules` or run `git submodule update --init`.

The [Bowtie](https://bowtie.report) conformance leg builds a container
image and runs the suite through Bowtie's harness protocol. It needs a
reachable container engine (Docker, or `podman machine start`) and fetches
Bowtie through `uvx`:

```sh
uv run python scripts/bowtie_check.py
```

### Benchmarks

```sh
uv run python scripts/bench.py --budget-ms 250 --filter user
```

`scripts/bench.py` times every jse tier (the interpreter, the compiler's
flag validator and evaluator, and the standalone artifact) against two
competitors (fastjsonschema, jsonschema) over seven corpora in
`packages/bench`: three small hand-authored schemas, the official OpenAPI
3.1 schema against a real document, a generated API-payload corpus, and
two 2000-record corpora. Every jse tier is timed against every corpus,
`jse standalone` against `oas-document` included, since its `$dynamicRef`
sites resolve at plan time and leave no interpreted unit. Two subjects
measure the record-producing tier against the verdict-only tiers:
`jse interpreter list` and `jse compiled evaluator (list)`, both timing
`output="list"`. The bench is report-only (it enforces no performance
threshold) and, per the IP policy below, runs the competitors only, never
reading or porting their source. `--filter` takes a regex over
corpus/subject/partition names; omit `--out` to skip writing JSON;
`--compare BEFORE AFTER` prints a before/after comparison of two results
files. The committed run lives at `packages/bench/results/results.json`
(`--budget-ms 250`). The interpreter is the reference semantics, so ratios
are informational, not a compatibility claim.
[`packages/bench/README.md`](packages/bench/README.md) covers corpus
provenance and licensing, methodology, and the recorded exclusions.

## IP policy

The implementation is written from the JSON Schema specifications and the
official test suite only. Other validators are executed as benchmark subjects
and correctness oracles; their source is never used as an implementation
reference. See [DESIGN.md](DESIGN.md) §0.
