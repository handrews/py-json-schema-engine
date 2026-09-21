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

## What compiled, and what fell back

`explain_compilation(plan)` returns a `CompilationExplanation`: unit
counts and, for every interpreted unit, a `FallbackCause` — `"dynamic"`
(a `$dynamicRef`-class keyword whose target depends on dynamic scope),
`"unlowerable"` (a keyword without `lower()`, an unresolvable reference,
or a coverage consumer whose evaluated set is only known at runtime),
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

A site whose target differs by path stays an island: here `#item` resolves
to a number under one branch and a string under the other.

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
island_compiled = compile_validator(island_engine, island_uri)
explanation = explain_compilation(island_compiled.plan)
assert explanation.causes == {"dynamic": 1}
assert explanation.interpreted_keys == ("https://example.com/generic#/items",)

# The trampoline still returns the interpreter's answer for that subschema.
assert island_compiled.validate({"kind": "numbers", "list": [1]}) is True
assert island_compiled.validate({"kind": "numbers", "list": ["x"]}) is False
assert island_compiled.validate({"kind": "strings", "list": ["x"]}) is True
```

Islands are a performance characteristic, not a correctness one. Use
`explain_compilation` when a schema compiles more slowly than expected and
you want to know why.

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

Standalone emission is flag-only and covers fully static schemas only: it
raises `StandaloneUnsupportedError` when the plan has any interpreted
unit, rather than emitting something that would quietly disagree with the
interpreter.

```python
from json_schema_engine.compiler import StandaloneUnsupportedError

try:
    emit_standalone(island_engine, island_uri)
except StandaloneUnsupportedError as error:
    assert "dynamic" in str(error)
else:
    raise AssertionError("expected StandaloneUnsupportedError")
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

M9 will add errors, annotations, and the output formats to compiled
artifacts; today they are verdict-only.

## See also

- [Formats](formats.md) — the format tables, assertion postures, and the
  `idna` extra.
- [Security and resource limits](security.md) — `max_depth` and the
  bounds that apply to both tiers.
