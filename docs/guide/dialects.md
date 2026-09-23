# Dialects

A dialect is a set of keyword behaviors bound to a `$schema` URI. Four
dialects ship built in: 2020-12, 2019-09, draft-07, and draft-06, exported
as `DIALECT_2020_12`, `DIALECT_2019_09`, `DIALECT_DRAFT_07`, and
`DIALECT_DRAFT_06` from `json_schema_engine.core`. One engine can hold
documents of several dialects at once, and so can a single document: each
schema resource — including one embedded by `$id` — is governed by the
`$schema` at its own root, and `$ref` works across dialect boundaries.

## Select a dialect

A schema resource's own `$schema` keyword picks its dialect. An embedded
resource without one inherits the dialect of the resource containing it;
a document without one gets the engine's `default_dialect` — 2020-12
unless configured otherwise. `$schema` is only meaningful at a resource
root; one written anywhere else is ignored rather than refused, since
refusing it is strict-mode hygiene and the core stays spec-clean (D14).

```python
from json_schema_engine.core import create_engine, DIALECT_DRAFT_07

engine = create_engine(default_dialect=DIALECT_DRAFT_07)
uri = engine.register_schema(
    {"items": [{"type": "boolean"}]}, "https://example.com/no-schema-keyword"
)

# No `$schema` on the document: draft-07 rules apply, including array-form
# `items`.
assert engine.evaluate(uri, [True]).valid is True
assert engine.evaluate(uri, [3]).valid is False
```

## The same keyword, different meaning

In draft-07, `items` accepts either a single schema (applied to every
element) or an array of subschemas (positional, tuple-style). In 2020-12,
tuple validation moved to `prefixItems`, and `items` accepts only a single
schema — an **array** value for `items` is not a valid 2020-12 schema, so
registration rejects the document with `InvalidSchemaError`. A non-schema
value in a schema position always fails loud rather than being silently
ignored.

```python
from json_schema_engine.core import DIALECT_2020_12, InvalidSchemaError

shape = {"items": [{"type": "string"}, {"type": "integer"}]}

legacy = create_engine(default_dialect=DIALECT_DRAFT_07)
legacy_uri = legacy.register_schema(shape, "https://example.com/legacy-tuple")
assert legacy.evaluate(legacy_uri, ["a", 1]).valid is True
assert legacy.evaluate(legacy_uri, [1, "a"]).valid is False

# The same document under 2020-12: the array is a non-schema in a schema
# position (tuples belong to `prefixItems`), so registration raises.
modern = create_engine(default_dialect=DIALECT_2020_12)
try:
    modern.register_schema(shape, "https://example.com/modern-items")
except InvalidSchemaError as error:
    assert "non-schema value (array)" in str(error)
else:
    raise AssertionError("expected InvalidSchemaError")
```

## A dialect boundary inside one document

The rule is per *resource*, not per document, so the same array-form
`items` can be legal in one part of a document and a non-schema in
another. An embedded `$id` resource that declares its own `$schema` is
walked, indexed, and evaluated under it:

```python
mixed = create_engine()
mixed.register_schema(
    {
        "$id": "https://example.com/mixed",
        "$defs": {
            "tuple": {
                "$id": "https://example.com/mixed-legacy",
                "$schema": DIALECT_DRAFT_07,
                # Legal here: this resource is draft-07.
                "items": [{"type": "string"}, {"type": "integer"}],
                # And `$id: "#name"` is an anchor here, not a base URI.
                "definitions": {"tag": {"$id": "#tag", "type": "string"}},
            }
        },
    },
    "https://example.com/mixed",
)
assert mixed.schemas.dialect_uri_for("https://example.com/mixed") == DIALECT_2020_12
assert (
    mixed.schemas.dialect_uri_for("https://example.com/mixed-legacy")
    == "http://json-schema.org/draft-07/schema"
)
# The anchor exists because the inner resource's own dialect minted it.
assert (
    mixed.schemas.resolve_ref("#tag", "https://example.com/mixed-legacy").pointer
    == "/definitions/tag"
)
```

The identifier syntax travels with the dialect too. `$id: "#name"` mints an
anchor under draft-07 and draft-06; under 2019-09 and 2020-12 an `$id` sets
a base URI, and a base URI cannot carry a non-empty fragment — so the same
spelling is an `InvalidIdentifierError` there, pointing you at `$anchor`:

```python
from json_schema_engine.core import InvalidIdentifierError

try:
    create_engine().register_schema(
        {"$id": "https://example.com/frag", "$defs": {"a": {"$id": "#name"}}},
        "https://example.com/frag",
    )
except InvalidIdentifierError as error:
    assert "$anchor" in str(error)
else:
    raise AssertionError("expected InvalidIdentifierError")
```

An empty trailing fragment (`"$id": "https://example.com/s#"`) is legal in
2020-12 and 2019-09, though they say it SHOULD NOT be used; IETF draft-03
forbids it. `create_engine(reject_id_fragments=True)` refuses it now, so
schemas you write today are ready for that change:

```python
strict = create_engine(reject_id_fragments=True)
try:
    strict.register_schema(
        {"$id": "https://example.com/trailing#"}, "https://example.com/trailing"
    )
except InvalidIdentifierError:
    pass
else:
    raise AssertionError("expected InvalidIdentifierError")
```

## `$ref` and its siblings

draft-07 and draft-06 keep `definitions` (not `$defs`) and treat `$ref` as
if it made every sibling keyword absent, both at registration and at
evaluation. 2019-09 and later apply siblings normally.

```python
draft07 = create_engine(default_dialect=DIALECT_DRAFT_07)
defs_uri = draft07.register_schema(
    {
        "$ref": "#/definitions/positive",
        "type": "string",
        "definitions": {"positive": {"type": "integer", "minimum": 0}},
    },
    "https://example.com/legacy-defs",
)
# draft-07: `$ref` makes every sibling act as if absent, so `type: "string"`
# never applies.
assert draft07.evaluate(defs_uri, 5).valid is True
assert draft07.evaluate(defs_uri, "s").valid is False
```

```python
from json_schema_engine.core import DIALECT_2019_09

modern_defs = create_engine(default_dialect=DIALECT_2019_09)
modern_uri = modern_defs.register_schema(
    {
        "$ref": "#/$defs/positive",
        "type": "string",
        "$defs": {"positive": {"type": "integer", "minimum": 0}},
    },
    "https://example.com/modern-defs",
)
# 2019-09 and later: siblings of `$ref` still apply, so both keywords
# reject.
assert modern_defs.evaluate(modern_uri, 5).valid is False
assert modern_defs.evaluate(modern_uri, "s").valid is False
```

## Recursive and dynamic scope

2019-09's `$recursiveRef`/`$recursiveAnchor` and 2020-12's
`$dynamicRef`/`$dynamicAnchor` both let a reference rebind to whatever
resource is outermost in the current dynamic scope — the mechanism behind
an extensible recursive schema — but 2019-09's pair rebinds only when the
anchor's target is the lexical document root (`$recursiveAnchor: true`),
while 2020-12's pair matches by name (`$dynamicAnchor: "name"` /
`$dynamicRef: "#name"`) anywhere in scope.

```python
recursive = create_engine(default_dialect=DIALECT_2019_09)
tree_uri = recursive.register_schema(
    {
        "$id": "https://example.com/strict-tree",
        "$recursiveAnchor": True,
        "$ref": "tree",
        "unevaluatedProperties": False,
        "$defs": {
            "tree": {
                "$id": "tree",
                "$recursiveAnchor": True,
                "type": "object",
                "properties": {
                    "data": True,
                    "children": {"type": "array", "items": {"$recursiveRef": "#"}},
                },
            }
        },
    },
    "https://example.com/strict-tree",
)
# The extension's root carries `$recursiveAnchor`, so `$recursiveRef: "#"`
# inside the base rebinds to the extension, which forbids extra properties.
assert recursive.evaluate(tree_uri, {"children": [{"data": 1}]}).valid is True
assert recursive.evaluate(tree_uri, {"children": [{"unknown": 1}]}).valid is False
```

```python
dynamic = create_engine()
dyn_uri = dynamic.register_schema(
    {
        "$id": "https://example.com/strings",
        "$ref": "list",
        "$defs": {
            "item": {"$dynamicAnchor": "items", "type": "string"},
            "list": {
                "$id": "list",
                "type": "array",
                "items": {"$dynamicRef": "#items"},
                "$defs": {"items": {"$dynamicAnchor": "items"}},
            },
        },
    },
    "https://example.com/strings",
)
# The outer resource's `$dynamicAnchor: "items"` overrides the inner
# default when both are in scope.
assert dynamic.evaluate(dyn_uri, ["a", "b"]).valid is True
assert dynamic.evaluate(dyn_uri, ["a", 1]).valid is False
```

## Unknown dialects

`register_schema` and `load_schema` raise `UnknownDialectError` for a
`$schema` value that names a dialect the engine has neither built in nor
assembled from a loaded metaschema — at a document root or at an embedded
resource root alike. See [Metaschemas](metaschemas.md) for assembling
dialects from `$vocabulary`.

```python
from json_schema_engine.core import UnknownDialectError

try:
    engine.register_schema(
        {"$schema": "https://example.com/no-such-dialect"},
        "https://example.com/bad-dialect",
    )
except UnknownDialectError as error:
    assert "no-such-dialect" in str(error)
else:
    raise AssertionError("expected UnknownDialectError")
```

An embedded resource is no different, except that the error also says
*where* the dialect was asked for. Registration is all-or-nothing, so
nothing from the attempt is left behind:

```python
embedded_bad = create_engine()
try:
    embedded_bad.register_schema(
        {
            "$id": "https://example.com/outer",
            "$defs": {"i": {"$id": "inner", "$schema": "https://example.com/nope"}},
        },
        "https://example.com/outer",
    )
except UnknownDialectError as error:
    assert error.schema_location == "https://example.com/outer#/$defs/i"
else:
    raise AssertionError("expected UnknownDialectError")

assert not embedded_bad.schemas.has("https://example.com/outer")
assert not embedded_bad.schemas.has("https://example.com/inner")
```

## Several dialects, one engine

```python
mixed = create_engine()
u1 = mixed.register_schema(
    {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "integer"},
    "https://example.com/one",
)
u2 = mixed.register_schema(
    {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "items": [{"type": "string"}],
    },
    "https://example.com/two",
)

assert mixed.evaluate(u1, 1).valid is True
assert mixed.evaluate(u2, ["a"]).valid is True
```
