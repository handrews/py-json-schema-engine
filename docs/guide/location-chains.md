# Location chains

A schema location names a position exactly and still may not tell you where
it is. In a bundled document — one file holding several `$id`-bearing
resources — an error reported at `https://x.example/sub/#/properties/a` is
precise and useless: nothing in it says which part of the file you registered
that resource is, and if the `$id` was relative, the URI does not appear in
your file at all.

A **location chain** walks outward from the position through each enclosing
resource, ending at the document root. `Engine.location_chain` builds one from
any schema location, and the engine attaches one to every error it raises.

## Read a chain

```python
from json_schema_engine.core import create_engine, format_location_chain

engine = create_engine()
engine.register_schema(
    {
        "$id": "https://x.example/bundle",
        "$defs": {
            "address": {
                "$id": "addresses/",
                "$defs": {
                    "postal": {
                        "$id": "postal.json",
                        "properties": {"zip": {"type": "string"}},
                    }
                },
            }
        },
    },
    "file:///srv/schemas/bundle.json",
)

chain = engine.location_chain("https://x.example/addresses/postal.json#/properties/zip")
assert len(chain) == 3
```

Hop 0 is the position itself. Each later hop names a resource and the pointer
to the resource *below it*, within that resource — not within the document:

```python
assert chain[0].resource_uri == "https://x.example/addresses/postal.json"
assert chain[0].pointer == "/properties/zip"

assert chain[1].resource_uri == "https://x.example/addresses/"
assert chain[1].pointer == "/$defs/postal"

assert chain[2].resource_uri == "https://x.example/bundle"
assert chain[2].pointer == "/$defs/address"
```

Two fields exist for the parts a reader cannot otherwise recover.
`declared_id` is the `$id` exactly as written, which is the only way to find a
relative one by searching the file. `retrieval_uri` is on the outermost hop
only, and names the document as you actually fetched it:

```python
assert chain[1].declared_id == "addresses/"
assert chain[2].retrieval_uri == "file:///srv/schemas/bundle.json"
```

Every hop is itself a schema location, so it round-trips:

```python
assert chain[1].location == "https://x.example/addresses/#/$defs/postal"
assert engine.location_chain(chain[1].location)[0].pointer == "/$defs/postal"
```

## Errors carry their own chain

You rarely need to build one by hand. Any error leaving `register_schema`,
`load_schema`, `load`, or `evaluate` already has its chain attached, and
printing the error shows it:

```python
from json_schema_engine.core import UnresolvableReferenceError

engine.register_schema(
    {
        "$id": "https://x.example/catalog",
        "$defs": {"item": {"$id": "items/", "$ref": "#/$defs/missing"}},
    },
    "file:///srv/schemas/catalog.json",
)

try:
    engine.evaluate("https://x.example/items/", 1)
    raise AssertionError("expected UnresolvableReferenceError")
except UnresolvableReferenceError as error:
    # `error` is unbound once the clause ends, so keep what is needed.
    report = str(error)
    attached = error.location_chain
    attempted = (error.reference, error.resolved_against)

assert attached is not None
assert len(attached) == 2
print(report)
```

```text
pointer '/$defs/missing' not found in 'https://x.example/items/': no '$defs' at the root (object)
  https://x.example/items/#/$ref
    in https://x.example/catalog at /$defs/item (written as "items/")
    retrieved as file:///srv/schemas/catalog.json
```

The same error also says what the reference attempted, which the chain does
not cover — where you are, and what you asked for, are different questions:

```python
assert attempted == ("#/$defs/missing", "https://x.example/items/")
```

## The single-resource case costs nothing

Most schemas are one resource, and there a chain has nothing to add. It is one
hop, and it formats to exactly the location you already had — so an ordinary
error message is unchanged, character for character:

```python
plain = create_engine()
uri = plain.register_schema({"properties": {"a": {"type": "string"}}}, "urn:plain")

single = plain.location_chain("urn:plain#/properties/a/type")
assert len(single) == 1
assert format_location_chain(single) == "urn:plain#/properties/a/type"
```

`str(error)` follows the same rule: it appends a chain only when there is more
than one hop, so errors from single-resource schemas read as they always did.

## Chains and source positions

A chain answers *which resource, inside which*. [Source
positions](source-positions.md) answer *where in the file*. They compose:
every hop's `.location` is a valid `Engine.locate` argument, so you can get a
document-rooted pointer — and a line and column, when the loader reported
them — for any hop:

```python
assert engine.locate(chain[0].location) == {
    "documentUri": "https://x.example/bundle",
    "pointer": "/$defs/address/$defs/postal/properties/zip",
}
```

That is why a hop does not carry a source range of its own: an exception may
outlive the parse tree the ranges came from, and asking is one call.

## When a chain is empty

`location_chain` returns `()` for a resource the engine never saw — including
a lexical base that pointer navigation produced but registration never indexed,
which a draft-07 `$ref` sibling can do:

```python
assert plain.location_chain("https://never.example/seen#/x") == ()
```

Empty means "no answer", and is deliberately not the same as a one-hop chain,
which asserts that the position sits in a root resource.
