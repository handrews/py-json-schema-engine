# Annotations

Annotations are keyword values a schema attaches to instance locations —
`title`, `description`, `default`, `deprecated`, `readOnly`, `writeOnly`,
`examples`, `format` (unless it is asserting, see [Formats](formats.md)),
`contentMediaType`/`contentEncoding`/`contentSchema`, and unknown extension
keywords. An annotation's value is always the keyword's own value.
Applicator keywords such as `properties` never appear as annotations: what
they communicate to `unevaluatedProperties` and `unevaluatedItems` is
dependency data, internal to evaluation and unaffected by any annotation
setting (see [Custom keywords and vocabularies](custom-keywords.md)).

Collection is off by default (`annotations=False`), so annotation work can
be elided entirely. Annotations are reported only for valid results: on
failure, a failed subschema's own annotations are dropped, per the
specification's relevance rule.

## Collect everything

`annotations=True` collects every annotation.

```python
from json_schema_engine.core import create_engine

engine = create_engine()
uri = engine.register_schema(
    {
        "title": "Config",
        "properties": {"retries": {"title": "Retry count", "deprecated": True}},
        "x-internal": True,
    },
    "https://example.com/config",
)

result = engine.evaluate(uri, {"retries": 3}, output="basic", annotations=True)
assert result.valid is True

by_keyword = {f"{a['keyword']}@{a['inputLocation']}": a for a in result.annotations}
assert by_keyword["title@"]["annotation"] == "Config"
assert by_keyword["title@/retries"]["annotation"] == "Retry count"
assert by_keyword["deprecated@/retries"]["annotation"] is True
# Unknown keywords are collected as annotations too.
assert by_keyword["x-internal@"]["annotation"] is True

unit = by_keyword["title@"]
assert unit["vocabulary"] == "https://json-schema.org/draft/2020-12/vocab/meta-data"
```

Each `AnnotationUnit` carries `evaluationPath`, `schemaLocation`, and
`inputLocation` (the same three locations as an `ErrorUnit`), plus `keyword`
and `annotation`. `keyword` and `vocabulary` (when the keyword's vocabulary
is known) are always present on an annotation unit — unlike `ErrorUnit`,
where they appear only with `error_params=True`.

## Select what to collect

`annotations` also accepts an `AnnotationSelection`: allow lists
(`keywords`, `vocabularies`, OR'd together), deny lists
(`exclude_keywords`, `exclude_vocabularies`, subtracted after the allow
lists), and a `keep` predicate run last over the rendered unit. The
selection applies the same way regardless of output format.

```python
from json_schema_engine.core import AnnotationSelection

allow_uri = engine.register_schema(
    {"title": "T", "description": "D", "default": 0}, "https://example.com/allow"
)
result = engine.evaluate(
    allow_uri,
    5,
    output="basic",
    annotations=AnnotationSelection(keywords=frozenset({"title", "default"})),
)
assert sorted(a["keyword"] for a in result.annotations) == ["default", "title"]
```

```python
deny_uri = engine.register_schema(
    {"title": "T", "description": "D", "x-internal": True},
    "https://example.com/deny",
)
result = engine.evaluate(
    deny_uri,
    1,
    output="basic",
    annotations=AnnotationSelection(exclude_keywords=frozenset({"description"})),
)
assert [a["keyword"] for a in result.annotations] == ["title", "x-internal"]
```

```python
keep_uri = engine.register_schema(
    {"title": "root", "properties": {"a": {"title": "leaf"}}},
    "https://example.com/keep",
)
result = engine.evaluate(
    keep_uri,
    {"a": 1},
    output="basic",
    annotations=AnnotationSelection(
        keywords=frozenset({"title"}), keep=lambda unit: unit["inputLocation"] == ""
    ),
)
assert len(result.annotations) == 1
assert result.annotations[0]["annotation"] == "root"
```

## Dropped annotations are verbose-only

A failed subschema's annotations are relevant to nothing, so the relevant
level omits them entirely — `Result.annotations` is `None` on an invalid
result even when `annotations=True`. `verbose=True` retains and exposes
them as `Result.dropped_annotations`.

```python
drop_uri = engine.register_schema(
    {
        "title": "root",
        "properties": {
            "item": {"title": "x", "type": "string"},
            "count": {"type": "integer"},
        },
    },
    "https://example.com/dropann",
)
result = engine.evaluate(
    drop_uri,
    {"item": "ok", "count": "bad"},
    output="list",
    verbose=True,
    annotations=True,
)
assert result.valid is False
assert result.annotations is None
assert sorted(a["keyword"] for a in result.dropped_annotations) == ["title", "title"]
```

Without `verbose=True`, the same evaluation would carry no annotation
information at all — `dropped_annotations` is `None` unless both
`annotations` is selected and `verbose=True` is given. See
[Output formats](output-formats.md) for the full relevance/verbosity model.

## Annotations in `list` and `hierarchical`

The `list` and `hierarchical` output documents key annotations by keyword
name at each unit, rather than listing flat units.

```python
hier_uri = engine.register_schema(
    {"title": "root", "properties": {"name": {"title": "the name", "type": "string"}}},
    "https://example.com/hier-ann",
)
result = engine.evaluate(
    hier_uri, {"name": "Ada"}, output="hierarchical", annotations=True
)
root = result.output_document
assert root["annotations"] == {"title": "root"}

name_detail = root["details"][0]
assert name_detail["annotations"] == {"title": "the name"}
```

## Selection never affects validation

Keywords that read other keywords' dependency data
(`unevaluatedProperties`, `unevaluatedItems`) see it regardless of any
annotation selection: dependency data is not annotation output. Selection
controls only what the caller receives.

```python
unevaluated_uri = engine.register_schema(
    {"properties": {"a": True}, "unevaluatedProperties": False},
    "https://example.com/unevaluated",
)
selection = AnnotationSelection(keywords=frozenset())

assert (
    engine.evaluate(
        unevaluated_uri, {"a": 1}, output="basic", annotations=selection
    ).valid
    is True
)
assert (
    engine.evaluate(
        unevaluated_uri, {"a": 1, "b": 2}, output="basic", annotations=selection
    ).valid
    is False
)
```

## The compiled evaluator

`compile_evaluator` (see [Compiling schemas](compiled.md#every-output-format))
collects the same annotations the interpreter does — the selection is
fixed once at compile time rather than chosen per call, but a ruled-in
annotation renders identically on both tiers:

```python
from json_schema_engine.compiler import compile_evaluator

evaluator = compile_evaluator(engine, uri, annotations=True)
compiled = evaluator.evaluate({"retries": 3}, output="basic")
interpreted = engine.evaluate(uri, {"retries": 3}, output="basic", annotations=True)
assert compiled.annotations == interpreted.annotations
```
