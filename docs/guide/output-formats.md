# Output formats

The `output` option selects a format by name. Every name renders the same
evaluation; they differ in structure, field vocabulary, and how much of the
evaluation they surface.

| Name           | Source                                  | Level                                   | Structure                                     |
| -------------- | ---------------------------------------- | ---------------------------------------- | ---------------------------------------------- |
| `flag`         | IETF draft-03 §13.4.1 / machines-oriented proposal (identical) | minimal | `{valid}` |
| `basic`        | IETF draft-03 §13.4.2                    | relevant                                 | root unit with a flat `errors` or `annotations` array |
| `detailed`     | IETF draft-03 §13.4.3                    | relevant                                 | condensed keyword-level tree                   |
| `verbose`      | IETF draft-03 §13.4.4                    | verbose                                  | full keyword-level tree                        |
| `list`         | machines-oriented output proposal        | relevant; verbose with `verbose=True`    | root `{valid, details}` holding flat units      |
| `hierarchical` | machines-oriented output proposal        | relevant; verbose with `verbose=True`    | units nested under `details` along the evaluation path |

"IETF draft-03" is `draft-ietf-jsonschema-json-schema-03`, not the 2010 JSON
Schema draft named draft-03.

## The flat surface and the output document

Every format but `flag` populates `Result.errors` on failure and
`Result.annotations` on success (when annotations are selected), using the
engine's native field names: `evaluationPath`, `schemaLocation`,
`inputLocation`, and `error` or `keyword`/`vocabulary`/`annotation`.
`Result.output_document` is the same evaluation rendered into the requested
format's own structure and field names.

| Concept         | Flat surface     | IETF draft-03 documents   | Machines-oriented documents |
| --------------- | ---------------- | -------------------------- | ---------------------------- |
| evaluation path | `evaluationPath` | `keywordLocation`           | `evaluationPath`              |
| schema location | `schemaLocation` | `absoluteKeywordLocation`   | `schemaLocation`               |
| input location  | `inputLocation`  | `instanceLocation`          | `instanceLocation`            |
| keyword identity| `keyword`, `vocabulary` | last segment of `keywordLocation` | keys of `errors`/`annotations` maps |

IETF draft-03 calls the value being validated the "instance" in its output
section; the engine's own concept is the input location, so the flat
surface keeps `inputLocation` while every rendered document keeps the field
name its source specifies.

The schema-location row is spelled as a URI in every column: its JSON
Pointer is percent-encoded into a URI fragment, so a property named `a b`
appears as `#/properties/a%20b`. The evaluation-path and input-location
rows are plain-text JSON Pointers in every column and are never encoded.
See [Read error details](validation.md#read-error-details).

## Flag

```python
from json_schema_engine.core import create_engine

engine = create_engine()
uri = engine.register_schema(
    {
        "$id": "https://example.com/config",
        "title": "root",
        "properties": {
            "item": {"$ref": "#/$defs/named"},
            "count": {"type": "integer"},
        },
        "$defs": {"named": {"title": "a named thing", "type": "string"}},
    },
    "https://example.com/config",
)

flag_result = engine.evaluate(uri, {"item": "widget", "count": "nope"})
assert flag_result.valid is False
assert flag_result.errors is None
assert flag_result.output_document is None
```

## Basic

A root unit with a flat `errors` array on failure or `annotations` array on
success. `basic` builds no located evaluation tree, so it is the cheapest
way to read errors or collect annotations.

```python
result = engine.evaluate(uri, {"item": "widget", "count": "nope"}, output="basic")
assert result.valid is False
assert result.output_document == {
    "valid": False,
    "keywordLocation": "",
    "absoluteKeywordLocation": "https://example.com/config#",
    "instanceLocation": "",
    "errors": [
        {
            "keywordLocation": "/properties/count/type",
            "absoluteKeywordLocation": "https://example.com/config#/properties/count/type",
            "instanceLocation": "/count",
            "error": "expected integer",
        }
    ],
}
assert result.errors == [
    {
        "evaluationPath": "/properties/count/type",
        "schemaLocation": "https://example.com/config#/properties/count/type",
        "inputLocation": "/count",
        "error": "expected integer",
    }
]
```

## Hierarchical

A tree of units nested under `details`, following the evaluation path. At
the relevant level only reporting units and their ancestors appear.

```python
result = engine.evaluate(
    uri, {"item": "widget", "count": 3}, output="hierarchical", annotations=True
)
assert result.valid is True
assert result.output_document == {
    "valid": True,
    "evaluationPath": "",
    "schemaLocation": "https://example.com/config#",
    "instanceLocation": "",
    "annotations": {"title": "root"},
    "details": [
        {
            "valid": True,
            "evaluationPath": "/properties/item",
            "schemaLocation": "https://example.com/config#/properties/item",
            "instanceLocation": "/item",
            "details": [
                {
                    "valid": True,
                    "evaluationPath": "/properties/item/$ref",
                    "schemaLocation": "https://example.com/config#/$defs/named",
                    "instanceLocation": "/item",
                    "annotations": {"title": "a named thing"},
                }
            ],
        }
    ],
}
```

The `$ref` traversal adds its own node (`/properties/item/$ref`), located at
the referenced schema (`.../$defs/named`) rather than at `/properties/item`
— the same distinction the flat surface's `evaluationPath` /
`schemaLocation` pair makes.

## List

The `hierarchical` units flattened in pre-order under a root that carries
only `valid` and `details`. Errors and annotations are keyed by keyword
name.

```python
result = engine.evaluate(uri, {"item": "widget", "count": "nope"}, output="list")
detail = result.output_document["details"][0]
assert detail["evaluationPath"] == "/properties/count"
assert detail["errors"] == {"type": "expected integer"}
```

## Detailed

The condensed keyword-level tree of §13.4.3: every keyword evaluation and
schema application is a node; a node with no local result is removed, and a
node with a single child is replaced by that child.

```python
result = engine.evaluate(uri, {"item": "widget", "count": "nope"}, output="detailed")
assert [n["keywordLocation"] for n in result.output_document["errors"]] == [
    "/properties/count/type"
]
```

## Verbose

The full keyword-level tree of §13.4.4: one node per keyword evaluation,
accepting or not, with irrelevant results included. `valid` on every node
tells relevant results apart from irrelevant ones.

```python
poly_uri = engine.register_schema(
    {
        "$id": "https://example.com/poly",
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "additionalProperties": False,
    },
    "https://example.com/poly",
)
result = engine.evaluate(poly_uri, {"n": "x", "extra": 1}, output="verbose")
nodes = [(n["keywordLocation"], n["valid"]) for n in result.output_document["errors"]]
assert nodes == [
    ("/properties", False),
    ("/additionalProperties", False),
    ("/type", True),
]
```

`/type` (the root's own `type: "object"`) is accepting and appears anyway —
this is what "verbose" means: irrelevant results included and marked, not
omitted.

## Structured error params

`error_params=True` adds `keyword`, `vocabulary`, and `params` to each flat
error unit, so tooling can consume the failure mechanically instead of
parsing the message string.

```python
params_uri = engine.register_schema(
    {"required": ["a", "b"], "enum": [{"a": 1, "b": 2}]},
    "https://example.com/params",
)
result = engine.evaluate(params_uri, {"a": 1}, output="list", error_params=True)
by_keyword = {u["keyword"]: u["params"] for u in result.errors}
assert by_keyword["required"] == {"missingProperty": "b"}
assert by_keyword["enum"] == {"allowedValues": [{"a": 1, "b": 2}]}
```

## Trace

`trace=True` adds `Result.trace`, a `TraceUnit` tree mirroring the
evaluation exactly (including subtrees that passed), whose `errorIndexes`
index `Result.errors` of the same run.

```python
result = engine.evaluate(
    uri, {"item": "widget", "count": "nope"}, output="list", trace=True
)
assert result.trace["schemaLocation"] == "https://example.com/config#"
assert result.trace["valid"] is False

count_child = result.trace["children"][1]
assert count_child["segments"] == ["properties", "count"]
assert count_child["errorIndexes"] == [0]
```

## The verbose level and dropped records

`verbose=True` asks `list`/`hierarchical` for the verbose level: every unit
is kept, and irrelevant records — an error under a passing `anyOf` branch
that lost, an annotation under a failed ancestor — are marked
`droppedErrors`/`droppedAnnotations` instead of omitted. `Result.dropped_errors`
and `Result.dropped_annotations` carry the same records as flat units.

```python
anyof_uri = engine.register_schema(
    {"title": "root", "anyOf": [{"required": ["a"]}, {"required": ["b"]}]},
    "https://example.com/anyof",
)
result = engine.evaluate(
    anyof_uri, {"a": 1}, output="list", verbose=True, annotations=True
)
assert result.dropped_errors == [
    {
        "evaluationPath": "/anyOf/1/required",
        "schemaLocation": "https://example.com/anyof#/anyOf/1/required",
        "inputLocation": "",
        "error": "missing required property 'b'",
    }
]
losing_branch = next(
    d for d in result.output_document["details"] if d["evaluationPath"] == "/anyOf/1"
)
assert losing_branch["droppedErrors"] == {"required": "missing required property 'b'"}
```

## Unsupported combinations

`resolve_output_demand` admits or rejects every combination of `output` and
its controls before evaluation, so a caller never pays for a run whose
result it cannot be given. `flag` carries no records, so any control raises
`OutputOptionsError` with it; `verbose=True` is rejected for `basic` and
`detailed`, which are relevant-level formats by definition.

```python
from json_schema_engine.core import OutputOptionsError

try:
    engine.evaluate(uri, 1, output="basic", verbose=True)
except OutputOptionsError as error:
    assert 'does not apply to output "basic"' in str(error)
else:
    raise AssertionError("expected OutputOptionsError")
```

## Source positions

`positions=True` decorates every flat error and annotation unit with a
`source` location (document URI, pointer, and range) when the owning
document was loaded through a loader that reports positions — see
[Source positions](source-positions.md).

## The compiled evaluator

`compile_evaluator` (see [Compiling schemas](compiled.md#every-output-format))
produces every output format documented on this page too, byte for byte
the same as `Engine.evaluate`'s:

```python
from json_schema_engine.compiler import compile_evaluator

evaluator = compile_evaluator(engine, uri, annotations=True)
compiled_result = evaluator.evaluate({"item": "widget", "count": "nope"}, output="list")
interpreted_result = engine.evaluate(
    uri, {"item": "widget", "count": "nope"}, output="list", annotations=True
)
assert compiled_result.output_document == interpreted_result.output_document
```
