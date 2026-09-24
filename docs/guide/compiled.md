# Compiling schemas

`json_schema_engine.core` interprets a schema on every evaluation.
`json_schema_engine.compiler` turns a registered schema into a Python
function once, so later evaluations skip the interpretive walk. The
compiler is not a second implementation: any subschema it cannot emit
trampolines back into the interpreter, so a compiled validator is exactly
as correct as `Engine.evaluate` and never less complete. Tier choice is a
performance decision, not a semantic one.

## Compile a validator

`compile_validator(engine, uri, *, max_depth=None, conservative=False)`
produces a verdict-only `CompiledValidator`: `validate(instance) -> bool`,
the `plan` it was built from, the emitted `module` (a Python `ast.Module`),
and its unparsed `source`.

```python
from json_schema_engine.compiler import compile_validator
from json_schema_engine.core import create_engine

engine = create_engine()
uri = engine.register_schema(
    {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id"],
    },
    "https://example.com/item",
)

compiled = compile_validator(engine, uri)
assert compiled.validate({"id": 1, "tags": ["a"]}) is True
assert compiled.validate({"tags": ["a"]}) is False
assert compiled.plan.root_key == uri + "#"
assert isinstance(compiled.source, str) and "def validate" in compiled.source
```

`validate` agrees with the interpreter on every instance, including
subschemas the compiler trampolines into `Engine.evaluate`:

```python
assert compiled.validate({"id": 1}) == engine.evaluate(uri, {"id": 1}).valid
```

## The registry-snapshot rule

`compile_validator` binds a read-only snapshot of the engine's schema and
dialect registries taken at compile time (`SchemaRegistry.snapshot`, in
`core/registry.py`). Compile after registration is complete. Registering
on the snapshot itself raises `ReadOnlyRegistryError`, and registering on
the *live* engine afterward does not reach an artifact already compiled:

```python
from json_schema_engine.core import ReadOnlyRegistryError

frozen = engine.schemas.snapshot()
try:
    frozen.register({"type": "string"}, "https://example.com/late")
except ReadOnlyRegistryError:
    pass
else:
    raise AssertionError("expected ReadOnlyRegistryError")

# A later registration on the live engine is invisible to the artifact.
engine.register_schema({"type": "object"}, "https://example.com/irrelevant")
assert compiled.validate({"id": 1}) is True
```

If you need an artifact to see a new schema, compile a new one.

## Every output format

`compile_evaluator(engine, schema_uri, *, annotations=False, max_depth=None,
conservative=False) -> CompiledEvaluator` compiles a schema into an
evaluator serving every output format, not only the verdict-only `flag`
level `compile_validator` produces. Every consumer is tracked at runtime
and every branch runs regardless of how many siblings already matched
(§4 rule 7), so the errors, annotations, dropped records, output document,
and trace it produces equal `Engine.evaluate`'s.

A handful of controls are fixed once, at compile time; everything else is
chosen fresh on each call to `evaluate`:

| Control                    | Fixed at compile time                    |
| --------------------------- | ------------------------------------------ |
| Annotation selection        | `compile_evaluator(..., annotations=...)`  |
| Application-nesting budget  | `compile_evaluator(..., max_depth=...)`    |
| Emitter optimizations       | `compile_evaluator(..., conservative=...)` |

| Control        | Chosen per evaluation                          |
| ---------------- | ------------------------------------------------- |
| `output`        | `evaluator.evaluate(instance, output=...)`       |
| `error_params`  | `evaluator.evaluate(instance, error_params=...)` |
| `verbose`       | `evaluator.evaluate(instance, verbose=...)`      |
| `trace`         | `evaluator.evaluate(instance, trace=...)`        |
| `positions`     | `evaluator.evaluate(instance, positions=...)`    |

Ruled-out annotations are never recorded and their values never reach the
emitted source — the selection is not merely filtered after the fact.

```python
from json_schema_engine.compiler import compile_evaluator

evaluator = compile_evaluator(engine, uri, annotations=True)
instance = {"id": 1, "tags": ["a"]}
for output in ("list", "hierarchical", "basic", "detailed", "verbose"):
    compiled_result = evaluator.evaluate(instance, output=output)
    interpreted_result = engine.evaluate(uri, instance, output=output, annotations=True)
    assert compiled_result.output_document == interpreted_result.output_document

assert isinstance(evaluator.source, str) and "def evaluate" in evaluator.source
```

`OutputOptionsError` rejects the same combinations the engine does — `flag`
carries no records, so any other control raises with it, on both tiers
alike:

```python
from json_schema_engine.core import OutputOptionsError

try:
    evaluator.evaluate(instance, output="flag")
except OutputOptionsError as compiled_error:
    compiled_message = str(compiled_error)
else:
    raise AssertionError("expected OutputOptionsError")

try:
    engine.evaluate(uri, instance, output="flag", annotations=True)
except OutputOptionsError as interpreted_error:
    assert str(interpreted_error) == compiled_message
else:
    raise AssertionError("expected OutputOptionsError")
```

`positions=True` attaches the same `source` locations the interpreter
would, through the compiling engine's own `locate`:

```python
missing = {"tags": ["a"]}  # missing the required "id"
compiled_missing = evaluator.evaluate(
    missing, output="list", error_params=True, positions=True
)
interpreted_missing = engine.evaluate(
    uri, missing, output="list", error_params=True, positions=True, annotations=True
)
assert compiled_missing.errors == interpreted_missing.errors
```

## What compiled, and what fell back

`explain_compilation(plan)` returns a `CompilationExplanation`: unit
counts and, for every interpreted unit, a `FallbackCause` — `"dynamic"`
(a `$dynamicRef`-class keyword the planner could not discharge: more
possible targets than `max_dynamic_winners` allows, or no resolution fact),
`"unlowerable"` (a keyword without `lower()` or an unresolvable reference),
`"cycle"` (an in-place `$ref` cycle at the same cursor), or `"non_schema"`
(a reference into a position that is not a schema at all).

A `$dynamicRef` whose target is the same on every path that can reach it
is resolved at compile time and compiled as an ordinary static edge; the
explanation lists such sites in `resolved_dynamic_sites`:

```python
from json_schema_engine.compiler import explain_compilation

resolved_engine = create_engine()
resolved_uri = resolved_engine.register_schema(
    {
        "properties": {"p": {"$dynamicRef": "#node"}},
        "$defs": {"node": {"$dynamicAnchor": "node", "type": "string"}},
    },
    "https://example.com/resolved",
)
explanation = explain_compilation(compile_validator(resolved_engine, resolved_uri).plan)
assert explanation.interpreted_units == 0
(site,) = explanation.resolved_dynamic_sites
assert site.target == "https://example.com/resolved#/$defs/node"
assert site.winner == "https://example.com/resolved"
```

A site whose target differs by path is *specialized*. The winner of a
`$dynamicRef` is the first resource on the path that declares the anchor,
so the planner splits the anchor and compiles the units below each
declaring resource once per declarer; every copy's site then has one
target and compiles as a static edge, and the copies report the schema
location they share. Here `#item` resolves to a number under one branch
and a string under the other, so `generic#/items` is compiled twice:

```python
island_engine = create_engine()
island_uri = island_engine.register_schema(
    {
        "$defs": {
            "generic": {
                "$id": "generic",
                "$defs": {"d": {"$dynamicAnchor": "item", "type": "null"}},
                "items": {"$dynamicRef": "#item"},
            },
            "numbers": {
                "$id": "numbers",
                "$defs": {"i": {"$dynamicAnchor": "item", "type": "number"}},
                "$ref": "generic",
            },
            "strings": {
                "$id": "strings",
                "$defs": {"i": {"$dynamicAnchor": "item", "type": "string"}},
                "$ref": "generic",
            },
        },
        "if": {"properties": {"kind": {"const": "numbers"}}},
        "then": {"properties": {"list": {"$ref": "#/$defs/numbers"}}},
        "else": {"properties": {"list": {"$ref": "#/$defs/strings"}}},
    },
    "https://example.com/island",
)
specialized = compile_validator(island_engine, island_uri)
explanation = explain_compilation(specialized.plan)
assert explanation.causes == {}
(anchor,) = explanation.split_anchors
assert (anchor.kind, anchor.anchor) == ("dynamic", "item")
assert anchor.winners == ("https://example.com/numbers", "https://example.com/strings")
assert explanation.specialized_units == 8
assert {
    (site.location, site.target_location) for site in explanation.resolved_dynamic_sites
} == {
    ("https://example.com/generic#/items", "https://example.com/numbers#/$defs/i"),
    ("https://example.com/generic#/items", "https://example.com/strings#/$defs/i"),
}
assert specialized.validate({"kind": "numbers", "list": [1]}) is True
assert specialized.validate({"kind": "numbers", "list": ["x"]}) is False
assert specialized.validate({"kind": "strings", "list": ["x"]}) is True
```

Specialization is bounded: `max_dynamic_winners` (default 16) caps the
declaring resources one anchor may be specialized for, since every
declarer adds a copy of the units below it. Beyond the cap, or with the
option at `0`, such a site stays an island, and the trampoline returns
the interpreter's answer for that subschema:

```python
island_compiled = compile_validator(island_engine, island_uri, max_dynamic_winners=0)
explanation = explain_compilation(island_compiled.plan)
assert explanation.causes == {"dynamic": 1}
assert explanation.interpreted_keys == ("https://example.com/generic#/items",)
assert explanation.split_anchors == ()
assert island_compiled.validate({"kind": "numbers", "list": [1]}) is True
assert island_compiled.validate({"kind": "numbers", "list": ["x"]}) is False
assert island_compiled.validate({"kind": "strings", "list": ["x"]}) is True
```

Islands are a performance characteristic, not a correctness one. Use
`explain_compilation` when a schema compiles more slowly than expected and
you want to know why.

### Runtime coverage tracking

An `unevaluated*` consumer whose evaluated coverage depends on which
`anyOf`/`oneOf` branch matches, or on an `if`'s runtime condition, cannot
be licensed against a static coverage — but that no longer means falling
back to the interpreter (M9). The consumer becomes a *tracked* unit and
its in-place closure a *region*: both take a runtime coverage channel as
a parameter instead of inlining, and the consumer folds it once at the
end. `CompilationExplanation.tracked_units`/`region_units` count them:

```python
tracking_engine = create_engine()
tracking_uri = tracking_engine.register_schema(
    {
        "anyOf": [
            {"properties": {"a": {"type": "integer"}}},
            {"properties": {"b": {"type": "string"}}},
        ],
        "unevaluatedProperties": False,
    },
    "https://example.com/tracked",
)
tracking_compiled = compile_validator(tracking_engine, tracking_uri)
tracking_explanation = explain_compilation(tracking_compiled.plan)
assert tracking_explanation.interpreted_units == 0
assert tracking_explanation.tracked_units == 1
assert tracking_explanation.region_units == 2

assert tracking_compiled.validate({"a": 1}) is True
assert tracking_compiled.validate({"a": 1, "c": 1}) is False
```

Before M9 this schema islanded with `FallbackCause` `"unlowerable"` (a
consumer without static coverage); now `unevaluatedProperties` compiles
directly, and `explain_compilation` reports zero interpreted units. The
official OpenAPI 3.1 schema — whose root combines `anyOf` with
`unevaluatedProperties` the same way — plans with zero interpreted units
for exactly this reason (368 total units, 8 tracked, 68 in their
regions); it is too large to reproduce here (see
`packages/bench/results/results.json` for its compiled-versus-interpreter
timing). The bundled 2020-12 metaschema plans with zero interpreted units
too, and needs no tracking at all: every `unevaluated*` consumer in it has
a static licence.

## Standalone modules

`emit_standalone(engine, uri, *, max_depth=None)` returns the source of a
module that imports only the standard library, `json_schema_engine.core`'s
pure helpers, and — when the schema asserts formats — predicates from
`json_schema_engine.formats`. The compiler package is not needed to import
or run it.

```python
from json_schema_engine.compiler import emit_standalone

static_engine = create_engine()
static_uri = static_engine.register_schema(
    {"type": "object", "required": ["id"]}, "https://example.com/static"
)
source = emit_standalone(static_engine, static_uri)
assert "def validate" in source
assert "import json_schema_engine.compiler" not in source
```

Standalone emission is flag-only (a verdict, never errors, annotations, or
the output formats) and covers fully static schemas: it raises
`StandaloneUnsupportedError` when the plan has any *interpreted* unit,
rather than emitting something that would quietly disagree with the
interpreter. A *tracked* schema — one whose `unevaluated*` consumer needs
the runtime coverage channel (M9) rather than a static licence — has no
interpreted units at all, so it emits as standalone same as any other
fully static plan; the channel is ordinary emitted code, not a trampoline:

```python
tracked_source = emit_standalone(tracking_engine, tracking_uri)
assert "def validate" in tracked_source
assert "import json_schema_engine.compiler" not in tracked_source
```

```python
from json_schema_engine.compiler import StandaloneUnsupportedError

try:
    emit_standalone(island_engine, island_uri, max_dynamic_winners=0)
except StandaloneUnsupportedError as error:
    assert "dynamic" in str(error)
else:
    raise AssertionError("expected StandaloneUnsupportedError")

# Specialized under the default cap, the same schema has no island to refuse.
assert "def validate" in emit_standalone(island_engine, island_uri)
```

Write the emitted source to a file and import it with `importlib.util`,
exactly as a build step would:

```python
import importlib.util
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    module_path = Path(directory) / "artifact.py"
    module_path.write_text(source)
    spec = importlib.util.spec_from_file_location("artifact", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.validate({"id": 1}) is True
    assert module.validate({}) is False
```

## The plain-data instance contract

Compiled code (both the runtime and standalone tiers) tests types with
`type(x) is dict`/`list`/`str`/`bool`/`int`/`float` and `x is None`: the
instance is assumed to be plain data, shaped the way `json.loads` produces
it. A subclass of a JSON type — an `OrderedDict`, an `IntEnum`, a `str`
subclass — is not a JSON value to the compiled tier, even though
`isinstance` would say otherwise.

```python
plain_engine = create_engine()
plain_uri = plain_engine.register_schema(
    {"type": "integer"}, "https://example.com/plain"
)
plain_compiled = compile_validator(plain_engine, plain_uri)
assert plain_compiled.validate(5) is True
assert plain_compiled.validate(True) is False  # bool is never a number
```

The interpreter uses `isinstance` and makes no such assumption; it is the
surface for hand-built or subclassed objects.

## `conservative=True`

`conservative=True` turns the emitter's optimizations off: no inlining of
single-use static children, no `frozenset` specialization for all-string
or all-number sets. It exists so the differential fuzzer can referee both
configurations against each other and against the interpreter; the two
configurations always agree.

```python
conservative = compile_validator(engine, uri, conservative=True)
assert conservative.validate({"id": 1, "tags": ["a"]}) is True
assert conservative.validate({"tags": ["a"]}) is False
```

## `max_depth`

`max_depth` bounds application nesting in compiled code exactly as it does
in the interpreter, defaulting to the engine's own budget. Compiled code
raises the same typed `MaxDepthExceededError`, never an untyped
`RecursionError`.

```python
from json_schema_engine.core import MaxDepthExceededError

deep_engine = create_engine()
deep_uri = deep_engine.register_schema(
    {"properties": {"a": {"$ref": "#"}}}, "https://example.com/deep"
)
shallow = compile_validator(deep_engine, deep_uri, max_depth=3)
nested = {"a": {"a": {"a": {"a": {}}}}}
try:
    shallow.validate(nested)
except MaxDepthExceededError:
    pass
else:
    raise AssertionError("expected MaxDepthExceededError")
```

## Formats

A plan hoists every format name any static unit asserts; the compiled
runtime resolves each name against the compiling engine's own format
table, and a standalone module imports the predicate by the table entry's
`import_path` instead.

```python
from json_schema_engine.formats import FORMATS_2020_12

fmt_engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
fmt_uri = fmt_engine.register_schema({"format": "ipv4"}, "https://example.com/fmt")

fmt_compiled = compile_validator(fmt_engine, fmt_uri)
assert fmt_compiled.validate("1.2.3.4") is True
assert fmt_compiled.validate("nope") is False

fmt_source = emit_standalone(fmt_engine, fmt_uri)
assert "from json_schema_engine.formats" in fmt_source
```

A format the plan needs but the compiling engine's table cannot serve
(no entry, or an entry marked `unavailable`) raises `FormatTableError` —
the single-table contract in `core/keywords/format.py`: the table a
schema's `format` keyword was lowered against must be the same table the
compiled runtime resolves names against. See [Formats](formats.md) for
the table contract itself, including the `idna` extra a standalone module
needs installed wherever it runs if it asserts `idn-hostname`.

`compile_evaluator` resolves formats the same way; a schema its plan
cannot serve raises the same `FormatTableError` there too.

## See also

- [Formats](formats.md) — the format tables, assertion postures, and the
  `idna` extra.
- [Security and resource limits](security.md) — `max_depth` and the
  bounds that apply to both tiers.
