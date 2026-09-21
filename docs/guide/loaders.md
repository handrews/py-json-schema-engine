# Loaders and remote references

A schema often `$ref`s a document that is not registered yet. A loader is
the engine's only way to fetch one: a plain function from URI to resource,
tried in order until one answers.

## The `Loader` contract

```text
Loader = Callable[[str], LoadedResource | None]
```

`Loader` (exported from `json_schema_engine.core`) is exactly this type
alias. A loader takes the URI the engine needs and returns a
`LoadedResource`, or `None` if it does not recognize that URI. Returning
`None` is not an error — the engine tries the next loader, and only reports
`UnresolvableReferenceError` if the reference is actually followed during
evaluation and no loader ever answered for it.

`LoadedResource` is a `Protocol`, not a base class: anything with a `value`
property and a `uri` property satisfies it structurally, so a loader can
return an instance of its own document type with no dependency on this
engine. `uri` is normally the URI requested; a loader that followed a
redirect reports where the document actually lives instead.

For loaders that do not already have their own resource type, the engine
exports a concrete dataclass:

```python
from json_schema_engine.core import LoadedDocument

doc = LoadedDocument(value={"type": "integer"}, uri="https://example.com/int")
assert doc.value == {"type": "integer"}
assert doc.uri == "https://example.com/int"
assert doc.get_range is None
```

`get_range` is the optional [source-position](source-positions.md)
capability (D17); a `LoadedDocument` without one is still a fully valid
`LoadedResource`, since the engine reads `get_range` with `getattr` rather
than requiring it.

## Wiring loaders into an engine

Pass loaders to `create_engine`; they are tried in the order given.

```python
from json_schema_engine.core import LoadedDocument, create_engine

DOCUMENTS = {
    "https://example.com/schemas/person": {
        "$id": "https://example.com/schemas/person",
        "type": "object",
        "properties": {"pet": {"$ref": "https://example.com/schemas/pet"}},
    },
    "https://example.com/schemas/pet": {
        "$id": "https://example.com/schemas/pet",
        "type": "object",
        "properties": {"name": {"type": "string"}},
    },
}


def dict_loader(uri: str) -> LoadedDocument | None:
    document = DOCUMENTS.get(uri)
    return None if document is None else LoadedDocument(document, uri)


engine = create_engine(loaders=[dict_loader])
```

This is the whole shape of an in-memory, dict-backed loader: look the URI
up, return `None` on a miss, wrap a hit in `LoadedDocument`.

## `Engine.load`: fetch through the loaders

```python
uri = engine.load("https://example.com/schemas/person")
assert engine.evaluate(uri, {"pet": {"name": "Fido"}}).valid is True
assert engine.evaluate(uri, {"pet": {"name": 1}}).valid is False
```

`load(uri)` drives the loaders for `uri`, then drains every reference the
loaded document (and anything it references, transitively) reveals,
calling the loaders again for each one until nothing is left unresolved.
It returns the URI it was asked for.

When the retrieval location and the document's own root `$id` differ, both
names resolve to the same registered document:

```python
MIRRORED = {"$id": "https://example.com/schemas/canonical-int", "type": "integer"}


def mirror_loader(uri: str) -> LoadedDocument | None:
    return (
        LoadedDocument(MIRRORED, uri) if uri == "https://example.com/mirror" else None
    )


mirror_engine = create_engine(loaders=[mirror_loader])
mirror_uri = mirror_engine.load("https://example.com/mirror")
assert mirror_uri == "https://example.com/mirror"
assert mirror_engine.evaluate(mirror_uri, 1).valid is True
# The document's own `$id` resolves too, as an alias of the same document.
assert (
    mirror_engine.evaluate("https://example.com/schemas/canonical-int", 1).valid is True
)
assert mirror_engine.evaluate(mirror_uri, "not an integer").valid is False
```

A URI no loader recognizes is simply left unregistered; `load` does not
raise for it.

```python
def none_loader(uri: str) -> LoadedDocument | None:
    return None


quiet_engine = create_engine(loaders=[none_loader])
quiet_engine.load("https://example.com/unknown")
assert quiet_engine.schemas.has("https://example.com/unknown") is False
```

## `Engine.load_schema`: register a document you already have, then drain

`load_schema` is for a document the caller already holds (parsed from a
file, received over the network) rather than one only a loader can reach.
It registers the document locally, exactly as `register_schema` does, and
then drains its references through the loaders — so any `$ref` the
document makes to an *external* document still resolves.

```python
pet_ref_schema = {
    "type": "object",
    "properties": {"pet": {"$ref": "https://example.com/schemas/pet"}},
}
uri2 = engine.load_schema(pet_ref_schema, "https://example.com/schemas/owner")
assert engine.evaluate(uri2, {"pet": {"name": "Rex"}}).valid is True
assert engine.evaluate(uri2, {"pet": {"name": 3}}).valid is False
```

## `register_schema` does not fetch

`register_schema` only registers the document it is given; it never calls
a loader. An unresolvable `$ref` is not an error at registration — it only
surfaces if evaluation actually follows it.

```python
from json_schema_engine.core import UnresolvableReferenceError

quiet2 = create_engine(loaders=[dict_loader])
uri3 = quiet2.register_schema(
    {"$ref": "https://example.com/schemas/pet"}, "https://example.com/schemas/owner2"
)
# Registration succeeded even though "pet" was never fetched.
try:
    quiet2.evaluate(uri3, {"name": 1})
    raised = False
except UnresolvableReferenceError:
    raised = True
assert raised is True
```

The same is true of `load_schema` when no loader recognizes the reference:
draining leaves it pending rather than raising, and only evaluation, if it
ever follows that `$ref`, reports `UnresolvableReferenceError`.

```python
none_engine = create_engine(loaders=[none_loader])
uri4 = none_engine.load_schema(
    {"$ref": "https://nowhere.example/x"}, "https://example.com/schemas/owner3"
)
try:
    none_engine.evaluate(uri4, 1)
    raised2 = False
except UnresolvableReferenceError:
    raised2 = True
assert raised2 is True
```

So an unresolvable remote `$ref` is checked exactly once: at evaluation, in
whichever call actually follows the reference — never at
`register_schema`, and not even at `load`/`load_schema` if draining could
not resolve it.

## Embedded `$id` resources

A single document a loader returns may embed further resources under
`$id`, commonly inside `$defs`. The registration walk finds every one of
them without a separate fetch: an embedded resource is reachable by its own
`$id` the moment the containing document is registered.

```python
bundle = {
    "$id": "https://example.com/schemas/bundle",
    "$defs": {
        "address": {
            "$id": "https://example.com/schemas/address",
            "type": "object",
            "properties": {"city": {"type": "string"}},
        }
    },
    "$ref": "https://example.com/schemas/address",
}


def bundle_loader(uri: str) -> LoadedDocument | None:
    return LoadedDocument(bundle, uri) if uri == bundle["$id"] else None


bundle_engine = create_engine(loaders=[bundle_loader])
bundle_uri = bundle_engine.load("https://example.com/schemas/bundle")
# The embedded resource is registered too, with no loader call of its own.
assert bundle_engine.schemas.has("https://example.com/schemas/address") is True
assert bundle_engine.evaluate(bundle_uri, {"city": "NYC"}).valid is True
assert bundle_engine.evaluate(bundle_uri, {"city": 1}).valid is False
```

## Bundled metaschemas never go through loaders

The standard metaschemas (2020-12, 2019-09, draft-07, draft-06, and the
2020-12 format-assertion vocabulary) ship with the engine and register
themselves lazily on first use, regardless of what loaders are configured.
A loader that recognizes nothing at all still lets `$ref` to a bundled
metaschema resolve.

```python
no_loader_engine = create_engine(loaders=[none_loader])
meta_uri = no_loader_engine.load_schema(
    {"$ref": "https://json-schema.org/draft/2020-12/schema"},
    "https://example.com/schemas/uses-meta",
)
assert no_loader_engine.evaluate(meta_uri, {"type": "integer"}).valid is True
assert no_loader_engine.evaluate(meta_uri, {"type": 1}).valid is False
```

See [Metaschemas](metaschemas.md) for `validate_schemas` and
`$vocabulary`-assembled dialects, and [Source positions](source-positions.md)
for a loader that also reports line/column ranges.
