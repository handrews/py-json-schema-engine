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

## Levels

- **Minimal** (`flag`): `valid` only. The default, and the cheapest.
- **Relevant** (`basic`, `detailed`, `list`, `hierarchical`): every relevant
  error and, when selected, every relevant annotation. Relevance is IETF
  draft-03 §12.2: a keyword that accepts makes the errors beneath it
  irrelevant (the losing branch of a passing `anyOf`), a schema that
  rejects makes the annotations beneath it irrelevant, and nothing
  irrelevant becomes relevant again. Irrelevant records are omitted, and
  units left with nothing to report are pruned.
- **Verbose** (`verbose`; `list` and `hierarchical` with `verbose=True`):
  irrelevant results are included as well. How each document tells them
  apart is [below](#telling-relevant-results-from-irrelevant-ones).

### `list`, `hierarchical`, and the machines-oriented proposal

The [machines-oriented proposal](https://github.com/json-schema-org/json-schema-spec/blob/4f56a9900674b27804f0ec32e3b7fdfa4efad695/specs/output/jsonschema-validation-output-machines.md)
that defines `list` and `hierarchical` is a proposal, not part of the
ratified specification, and it has no concept of relevance. Its
`hierarchical` structure includes every output unit, and its `list`
structure SHOULD exclude units that carry no errors or annotations.
Removing anything else is optional "Output Unit Pruning", and the proposal
requires every such filtering behavior to be configurable and disabled by
default.

The relevant and verbose levels of `list` and `hierarchical` are this
engine's mapping of draft-03 relevance onto the proposal's structures, and
the default departs from the proposal deliberately:

- At the relevant level, the default, both formats omit irrelevant
  records, and `hierarchical` prunes every unit that has no relevant error
  or annotation of its own and none below it, including valid units with
  nothing to report. Those are the proposal's two example reasons for
  pruning, applied by default.
- `verbose=True` turns both off. Every unit appears, as the proposal's
  `hierarchical` describes, and irrelevant records are kept under
  `droppedErrors` and `droppedAnnotations`. The proposal defines
  `droppedAnnotations` for a failed unit's own annotations; the engine also
  uses it on a passing unit beneath a failed one, and adds `droppedErrors`
  for irrelevant errors, which the proposal, having no relevance, would
  report under `errors`.

### Telling relevant results from irrelevant ones

A node's own `valid` does not say whether it is relevant. Under the losing
branch of a passing `oneOf`, a subschema that accepted is `valid: true` and
still irrelevant, because the branch around it rejected.

- In the `verbose` document, a node's `error` or `annotation` is relevant
  exactly when every node from the root down to it has the root's `valid`.
  The first node that differs makes itself and everything beneath it
  irrelevant. This is how draft-03 §13.4.4's recommended `valid` on every
  node identifies relevance: read along the whole path, not node by node.
- In `list` and `hierarchical` at the verbose level, every record is
  marked: `errors` and `annotations` hold relevant records,
  `droppedErrors` and `droppedAnnotations` irrelevant ones. The units
  themselves are not marked, and here `valid` along the path is not enough
  either: the keyword whose acceptance made a branch irrelevant has no unit
  of its own, so the losing branch of a passing `anyOf` under a failing
  root is `valid: false` beneath `valid: false` and still irrelevant.

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
the relevant level only units that report a relevant error or annotation,
and their ancestors, appear; the proposal itself includes every unit, which
is what `verbose=True` gives (see
[the machines-oriented proposal](#list-hierarchical-and-the-machines-oriented-proposal)).

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
name. At the relevant level only units carrying a relevant error or
annotation are listed, as the proposal says they SHOULD be; at the verbose
level every unit is.

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
accepting or not, with irrelevant results included. `valid` on every node,
read along the path from the root, tells relevant results apart from
irrelevant ones (see
[Telling relevant results from irrelevant ones](#telling-relevant-results-from-irrelevant-ones)).

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

A single node's `valid` is not the marker. Here the root passes through
`oneOf/0`, so the `oneOf/1` branch rejected and everything beneath it is
irrelevant — including the `$ref` into `fields`, which accepted:

```python
one_of_uri = engine.register_schema(
    {
        "$id": "https://example.com/one-of",
        "oneOf": [{"required": ["a"]}, {"required": ["b"], "$ref": "#/$defs/fields"}],
        "$defs": {"fields": {"title": "fields"}},
    },
    "https://example.com/one-of",
)
result = engine.evaluate(one_of_uri, {"a": 1}, output="verbose", annotations=True)
one_of = result.output_document["annotations"][0]
losing = one_of["annotations"][1]
assert (losing["keywordLocation"], losing["valid"]) == ("/oneOf/1", False)
ref = losing["errors"][0]
assert (ref["keywordLocation"], ref["valid"]) == ("/oneOf/1/$ref", True)
# `valid: true` under a `valid: false` node: the title is irrelevant.
assert result.annotations == []
assert [a["annotation"] for a in result.dropped_annotations] == ["fields"]
```

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

The markers classify records, not units. Read `errors`/`annotations`
against `droppedErrors`/`droppedAnnotations`, not `valid`: when the root
fails for another reason, the losing branch is `valid: false` beneath a
`valid: false` root and its error is still irrelevant, because the `anyOf`
that accepted has no unit of its own.

```python
failing_uri = engine.register_schema(
    {"required": ["x"], "anyOf": [{"required": ["a"]}, {"required": ["b"]}]},
    "https://example.com/failing",
)
result = engine.evaluate(failing_uri, {"a": 1}, output="list", verbose=True)
units = {d["evaluationPath"]: d for d in result.output_document["details"]}
assert units[""]["valid"] is False
assert units["/anyOf/1"]["valid"] is False
assert "errors" not in units["/anyOf/1"]
assert units["/anyOf/1"]["droppedErrors"] == {
    "required": "missing required property 'b'"
}
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
