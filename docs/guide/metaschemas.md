# Metaschemas

A metaschema is a schema for schemas: it defines which keywords a dialect
recognizes (its `$vocabulary`) and, when checked against, whether a given
document uses them correctly. The engine ships the metaschemas for its
four built-in drafts and can assemble further dialects from any metaschema
that declares its vocabularies.

## Validating registered schemas against their metaschema

`create_engine(validate_schemas=True)` checks every document at
registration time — not only ones you write, but any document a loader
brings in — against its own dialect's metaschema, and raises
`SchemaValidationError` if it fails.

```python
from json_schema_engine.core import SchemaValidationError, create_engine

engine = create_engine(validate_schemas=True)
try:
    engine.register_schema({"type": "not-a-type"}, "https://ex.example/bad")
    raised = False
except SchemaValidationError as error:
    raised = True
    message = str(error)
    location = error.schema_location
    errors = error.errors
assert raised is True
assert message == (
    "schema 'https://ex.example/bad' fails its metaschema "
    "'https://json-schema.org/draft/2020-12/schema'"
)
# A schema location is always `base#pointer` (P10). The failure is about
# the document as a whole, so the pointer is empty rather than absent.
assert location == "https://ex.example/bad#"
# `errors` is the `list`-format output of the failed metaschema evaluation:
# one entry per violated metaschema keyword, each with its own location.
assert len(errors) >= 1
assert all("schemaLocation" in unit for unit in errors)
```

A document that satisfies its metaschema registers exactly as it would
without the option — `validate_schemas` only adds a check, never changes
what a valid document means:

```python
ok_uri = engine.register_schema({"type": "integer"}, "https://ex.example/ok")
assert engine.evaluate(ok_uri, 1).valid is True
```

When a document's metaschema is not available (unregistered, and no loader
supplies it), the check is skipped rather than treated as failure — there
is nothing to validate against.

## `$vocabulary`: assembling a dialect from a custom metaschema

A metaschema's own `$vocabulary` object names the vocabularies a dialect
built from it requires (`true`) or merely permits (`false`). Registering a
schema whose `$schema` points at such a metaschema assembles that dialect
on demand, from whatever vocabularies are already registered on the
engine — the same built-in vocabularies the four standard dialects are
built from (see [Custom keywords](custom-keywords.md) for registering your
own).

```python
from json_schema_engine.core import create_engine

CORE = "https://json-schema.org/draft/2020-12/vocab/core"
VALIDATION = "https://json-schema.org/draft/2020-12/vocab/validation"
META_2020 = "https://json-schema.org/draft/2020-12/schema"

# core + validation only: no applicators (`properties`, `items`, ...).
VALIDATION_ONLY_META = {
    "$schema": META_2020,
    "$id": "https://ex.example/meta/validation-only",
    "$vocabulary": {CORE: True, VALIDATION: True},
}

vocab_engine = create_engine()
vocab_engine.register_schema(VALIDATION_ONLY_META, VALIDATION_ONLY_META["$id"])
uri = vocab_engine.register_schema(
    {"$schema": VALIDATION_ONLY_META["$id"], "minimum": 10},
    "https://ex.example/uses-validation-only",
)
assert vocab_engine.evaluate(uri, 12).valid is True
assert vocab_engine.evaluate(uri, 1).valid is False
```

A schema is registered as its own metaschema exactly like any other
document — `register_schema` (or `load_schema`, if a loader should supply
it instead), before any document names it in `$schema`.

### An unknown *required* vocabulary is loud

If a metaschema's `$vocabulary` marks a vocabulary URI the engine has
never heard of as `true`, assembling the dialect raises
`UnknownVocabularyError` — the spec's MUST for a required vocabulary
nobody implements.

```python
from json_schema_engine.core import UnknownVocabularyError

REQUIRES_UNKNOWN_META = {
    "$schema": META_2020,
    "$id": "https://ex.example/meta/requires-unknown",
    "$vocabulary": {CORE: True, "https://ex.example/vocab/nonexistent": True},
}
vocab_engine.register_schema(REQUIRES_UNKNOWN_META, REQUIRES_UNKNOWN_META["$id"])
try:
    vocab_engine.register_schema(
        {"$schema": REQUIRES_UNKNOWN_META["$id"]}, "https://ex.example/doc-unknown"
    )
    raised2 = False
except UnknownVocabularyError:
    raised2 = True
assert raised2 is True
```

### A `false` vocabulary is tolerated

The same unknown URI marked `false` (optional) is skipped instead: the
dialect assembles without it, and any keyword from that vocabulary falls
back to unknown-keyword annotation handling rather than failing schema
assembly, per the spec's own MUST for an optional vocabulary.

```python
OPTIONAL_UNKNOWN_META = {
    "$schema": META_2020,
    "$id": "https://ex.example/meta/optional-unknown",
    "$vocabulary": {
        CORE: True,
        VALIDATION: True,
        "https://ex.example/vocab/nonexistent": False,
    },
}
vocab_engine.register_schema(OPTIONAL_UNKNOWN_META, OPTIONAL_UNKNOWN_META["$id"])
uri2 = vocab_engine.register_schema(
    {"$schema": OPTIONAL_UNKNOWN_META["$id"], "type": "number"},
    "https://ex.example/doc-optional",
)
assert vocab_engine.evaluate(uri2, 1).valid is True
assert vocab_engine.evaluate(uri2, "s").valid is False
```

## The bundled metaschemas resolve without loaders

Eighteen metaschema documents ship with the engine: nine 2020-12 resources
(the top-level `schema` plus its eight `meta/*` vocabularies, including
format-assertion), seven 2019-09 resources, and the single draft-07 and
draft-06 schemas. They register themselves lazily, the first time
something resolves a `$ref` to one, no matter what loaders (if any) the
engine has.

```python
BUNDLED_2020_12 = [
    "https://json-schema.org/draft/2020-12/schema",
    "https://json-schema.org/draft/2020-12/meta/core",
    "https://json-schema.org/draft/2020-12/meta/applicator",
    "https://json-schema.org/draft/2020-12/meta/validation",
    "https://json-schema.org/draft/2020-12/meta/unevaluated",
    "https://json-schema.org/draft/2020-12/meta/meta-data",
    "https://json-schema.org/draft/2020-12/meta/format-annotation",
    "https://json-schema.org/draft/2020-12/meta/format-assertion",
    "https://json-schema.org/draft/2020-12/meta/content",
]
BUNDLED_2019_09 = [
    "https://json-schema.org/draft/2019-09/schema",
    "https://json-schema.org/draft/2019-09/meta/core",
    "https://json-schema.org/draft/2019-09/meta/applicator",
    "https://json-schema.org/draft/2019-09/meta/validation",
    "https://json-schema.org/draft/2019-09/meta/meta-data",
    "https://json-schema.org/draft/2019-09/meta/format",
    "https://json-schema.org/draft/2019-09/meta/content",
]
BUNDLED_LEGACY = [
    "http://json-schema.org/draft-07/schema",
    "http://json-schema.org/draft-06/schema",
]
BUNDLED = BUNDLED_2020_12 + BUNDLED_2019_09 + BUNDLED_LEGACY
assert len(BUNDLED) == 18

no_loader_engine = create_engine()
assert all(no_loader_engine.schemas.has(uri) for uri in BUNDLED)
meta_uri = no_loader_engine.load_schema(
    {"$ref": "https://json-schema.org/draft/2020-12/schema"},
    "https://ex.example/uses-bundled-meta",
)
assert no_loader_engine.evaluate(meta_uri, {"type": "integer"}).valid is True
assert no_loader_engine.evaluate(meta_uri, {"type": 1}).valid is False
```

See [Loaders](loaders.md) for how a `$ref` to a *non*-bundled resource
gets resolved instead.

## `FormatsRequiredError`: the format-assertion vocabulary needs a table

The 2020-12 format-assertion vocabulary is special: a metaschema can name
it (required or merely permitted — the ruling below applies either way),
but asserting `format` needs an actual table of format predicates, which
is an engine-level option (`formats=`), not something a metaschema can
supply on its own. Registering a document under a metaschema that names
the format-assertion vocabulary, on an engine with no `formats=` table,
raises `FormatsRequiredError` — pointing at the metaschema itself, since
that is where the unmet requirement was declared.

```python
from json_schema_engine.core import VOCAB_FORMAT_ASSERTION, FormatsRequiredError

FORMAT_ASSERTING_META = {
    "$schema": META_2020,
    "$id": "https://ex.example/meta/format-asserting",
    "$vocabulary": {CORE: True, VOCAB_FORMAT_ASSERTION: True},
}

no_formats_engine = create_engine()  # no formats= table
no_formats_engine.register_schema(FORMAT_ASSERTING_META, FORMAT_ASSERTING_META["$id"])
try:
    no_formats_engine.register_schema(
        {"$schema": FORMAT_ASSERTING_META["$id"]}, "https://ex.example/doc-fa"
    )
    raised3 = False
except FormatsRequiredError as error:
    raised3 = True
    # A schema location is always `base#pointer` (P10); a document-level
    # error points at that document's root, so the pointer is empty.
    assert error.schema_location == FORMAT_ASSERTING_META["$id"] + "#"
assert raised3 is True
```

Passing a table makes it work, and `format` asserts under that metaschema
specifically (see [Formats](formats.md) for the bundled tables and
`assert_formats`, which turns on the same behavior across every standard
dialect instead of only a custom one):

```python
from json_schema_engine.formats import FORMATS_2020_12

formats_engine = create_engine(formats=FORMATS_2020_12)
formats_engine.register_schema(FORMAT_ASSERTING_META, FORMAT_ASSERTING_META["$id"])
uri3 = formats_engine.register_schema(
    {"$schema": FORMAT_ASSERTING_META["$id"], "format": "date"},
    "https://ex.example/doc-fa-ok",
)
assert formats_engine.evaluate(uri3, "2020-01-01").valid is True
assert formats_engine.evaluate(uri3, "not-a-date").valid is False
```
