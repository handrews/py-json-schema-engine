# Validation

Register a schema under a retrieval URI, then evaluate instances against it.
Evaluation is synchronous and has no I/O of its own.

## Register and evaluate

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

assert engine.evaluate(uri, {"name": "Ada"}).valid is True
assert engine.evaluate(uri, {}).valid is False
assert engine.evaluate(uri, {"name": 3}).valid is False
```

`register_schema` returns the document's canonical URI: the retrieval URI
resolved against any `$id` the document declares. Use the returned value
(not necessarily the retrieval URI itself) to evaluate.

The default output is `flag`: `Result.valid` only, no error detail, and the
least evaluation work.

```python
flag_result = engine.evaluate(uri, {})
assert flag_result.output_document is None
assert flag_result.errors is None
```

See [Output formats](output-formats.md) for every other format.

## Read error details

Request `output="list"` for one unit per error. Each `ErrorUnit` carries
three locations plus the message: `evaluationPath` (the dynamic path
through the schema, including `$ref` traversals), `schemaLocation` (the
canonical URI of the failing keyword), `inputLocation` (a JSON Pointer into
the instance), and `error` (the message). `error_params=True` adds
`keyword`, `vocabulary`, and a structured `params` object.

The two kinds of location are spelled differently, and the difference only
shows when a name holds an awkward character. `schemaLocation` is a **URI**,
so its pointer is fragment-encoded: a property named `a b` appears as
`#/properties/a%20b`, and one named `100%` as `#/properties/100%25`. That is
what lets the string be pasted into a `$ref` or handed back to
`Engine.locate` unchanged. `evaluationPath` and `inputLocation` are
**plain-text** JSON Pointers and are never encoded, because neither is a
URI: the same property reads `/properties/a b` and `/a b`. An interface
showing schema locations to people can decode them for display; the engine
emits the form that round-trips.

```python
named_uri = engine.register_schema(
    {
        "$defs": {"name": {"type": "string", "minLength": 1}},
        "properties": {"name": {"$ref": "#/$defs/name"}},
    },
    "https://example.com/named",
)

result = engine.evaluate(named_uri, {"name": ""}, output="list", error_params=True)
assert result.valid is False

unit = result.errors[0]
assert unit["evaluationPath"] == "/properties/name/$ref/minLength"
assert unit["schemaLocation"] == "https://example.com/named#/$defs/name/minLength"
assert unit["inputLocation"] == "/name"
assert unit["keyword"] == "minLength"
assert unit["params"] == {"limit": 1}
assert unit["error"] == "must be at least 1 characters"
```

`evaluationPath` names every keyword on the way to the failure, including
the `$ref` segment itself; `schemaLocation` is the canonical location the
reference resolved to, in the document that actually declares `minLength`.

## Boolean schemas

`True` and `False` are schemas on their own: `True` accepts everything,
`False` rejects everything. They may appear anywhere a schema is expected,
including as the root document.

```python
never_uri = engine.register_schema(False, "https://example.com/never")
always_uri = engine.register_schema(True, "https://example.com/always")

assert engine.evaluate(never_uri, "anything").valid is False
assert engine.evaluate(always_uri, "anything").valid is True
```

## Evaluate a subschema directly

A schema's canonical URI can carry a fragment: registering
`https://example.com/named` above also indexes
`https://example.com/named#/$defs/name` as its own evaluable schema
location, so a caller can validate directly against an embedded definition
without wrapping it in `$ref`.

```python
name_schema_uri = named_uri + "#/$defs/name"

assert engine.evaluate(name_schema_uri, "ok").valid is True
assert engine.evaluate(name_schema_uri, "").valid is False
```

## Schema and reference errors

`register_schema` raises `InvalidSchemaError` when a position the dialect
requires to be a schema holds a value that is neither an object nor a
boolean — a non-schema value in a schema position always fails loud rather
than being silently ignored as an empty schema.

`register_schema` does not follow `$ref` targets (see
[Loaders and remote references](loaders.md) for `load_schema`, which does),
so a dangling reference is not an error at registration. `evaluate` raises
`UnresolvableReferenceError` once such a reference is actually followed, or
when the URI passed to `evaluate` itself names a schema the registry does
not know.

```python
from json_schema_engine.core import InvalidSchemaError, UnresolvableReferenceError

try:
    engine.register_schema(
        {"properties": {"bad": "not-a-schema"}}, "https://example.com/bad"
    )
except InvalidSchemaError as error:
    assert "non-schema value" in str(error)
else:
    raise AssertionError("expected InvalidSchemaError")

missing_ref_uri = engine.register_schema(
    {"$ref": "https://example.com/missing-target"}, "https://example.com/refmissing"
)
try:
    engine.evaluate(missing_ref_uri, 1)
except UnresolvableReferenceError as error:
    assert "missing-target" in str(error)
else:
    raise AssertionError("expected UnresolvableReferenceError")
```
