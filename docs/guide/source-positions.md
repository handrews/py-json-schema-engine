# Source positions

An error or annotation unit names a schema location as a canonical
`base_uri#pointer`. That is enough to find the failing keyword
programmatically, but not enough to show a human the exact line and column
in the schema *text* — for that, the loader needs to have kept the
original source alongside the parsed value. This is the D17 capability:
optional, and free when nobody asks for it.

## Parsing JSON with positions: `parse_json_with_ranges`

`json_schema_engine.core` exports a small, dependency-free JSON parser that
records where every value came from as it parses:

```python
from json_schema_engine.core import parse_json_with_ranges

text = '{"type": "object", "required": ["name"]}'
parsed = parse_json_with_ranges(text, "urn:example:doc")
assert parsed.value == {"type": "object", "required": ["name"]}
assert parsed.uri == "urn:example:doc"
```

The result is a `ParsedDocument`: a frozen dataclass with `value`, `uri`,
and `get_range` — which already makes it a valid `LoadedResource` (see
[Loaders](loaders.md)), so a loader can return it as is.

```python
source_range = parsed.get_range("/required")
assert source_range["value"]["start"]["line"] == 1
assert (
    text[source_range["key"]["start"]["offset"] : source_range["key"]["end"]["offset"]]
    == '"required"'
)
```

`get_range(pointer)` takes a document-rooted JSON Pointer (RFC 6901) and
returns a `SourceRange`: a `value` span (`start`/`end`, each a
`line`/`column`/`offset`) covering the value at that pointer, and — for an
object member — a `key` span covering its key token. `line`/`column` are
1-based, `offset` is a 0-based UTF-16-agnostic character offset into
`text`. A pointer the parse never visited (or that names a container that
does not exist) returns `None`.

`parse_json_with_ranges` parses the JSON grammar itself rather than
delegating to `json.loads`, so it also rejects the non-JSON extensions
`json.loads` tolerates (`NaN`, `Infinity`) and raises `JsonSyntaxError` —
also a `ValueError` — with the offending position on any syntax error:

```python
from json_schema_engine.core import JsonSyntaxError

try:
    parse_json_with_ranges("{oops", "urn:example:bad")
    raised = False
except JsonSyntaxError as error:
    raised = True
    assert error.line == 1
    assert error.column == 2
    assert error.offset == 1
    assert isinstance(error, ValueError)
assert raised is True
```

## Using it as a loader

Because `ParsedDocument` is already a `LoadedResource`, a loader can wrap
`parse_json_with_ranges` directly:

```python
from json_schema_engine.core import ParsedDocument, create_engine

DOC_TEXT = """{
  "$id": "https://pos.example/root",
  "$ref": "https://pos.example/leaf",
  "$defs": {
    "leaf": {
      "$id": "https://pos.example/leaf",
      "required": ["x"]
    }
  }
}"""


def positions_loader(uri: str) -> ParsedDocument | None:
    if uri == "https://pos.example/root":
        return parse_json_with_ranges(DOC_TEXT, uri)
    return None


engine = create_engine(loaders=[positions_loader])
root_uri = engine.load("https://pos.example/root")
```

## `evaluate(..., positions=True)`

With a loader that reports ranges, `positions=True` decorates every unit
in the output with a `source: SourceLocation` — `documentUri`, `pointer`,
and (when the underlying document reported one) `range`:

```python
result = engine.evaluate(root_uri, {}, output="list", positions=True)
assert result.valid is False
unit = next(e for e in result.errors if "'x'" in e["error"])
# `schemaLocation` is resource-rooted, in the *referenced* document...
assert unit["schemaLocation"] == "https://pos.example/leaf#/required"
# ...while `source` is document-rooted, in the document the loader parsed.
source = unit["source"]
assert source["documentUri"] == "https://pos.example/root"
assert source["pointer"] == "/$defs/leaf/required"
assert "range" in source
assert source["range"]["key"] is not None
```

`$defs/leaf` embeds its own `$id`, so its canonical `schemaLocation` names
a different resource (`https://pos.example/leaf`) than the document that
physically contains the text (`https://pos.example/root`); `source`
bridges the two, pointing back at the one document a loader actually
parsed. Annotations are decorated the same way, whenever `annotations=True`
is also requested.

`positions=True` is rejected outright, before evaluation runs, for the
`flag` output format — there is no unit for it to decorate:

```python
from json_schema_engine.core import OutputOptionsError

flag_uri = engine.register_schema({}, "urn:example:flag-only")
try:
    engine.evaluate(flag_uri, 1, positions=True)
    raised2 = False
except OutputOptionsError:
    raised2 = True
assert raised2 is True
```

A document registered without a range-reporting loader still gets `source`
under `positions=True` — just without a `range`, since nobody ever
reported one:

```python
plain_uri = engine.register_schema({"type": "string"}, "urn:example:plain")
plain_result = engine.evaluate(plain_uri, 1, output="basic", positions=True)
assert plain_result.errors[0]["source"] == {
    "documentUri": "urn:example:plain",
    "pointer": "/type",
}
```

## `Engine.locate`

`Engine.locate(schema_location)` answers the same question for any
canonical schema location directly, without running an evaluation —
useful for tooling that already has a `schemaLocation` from elsewhere (a
saved report, a `$ref` target) and wants to jump to source.

```python
located = engine.locate(unit["schemaLocation"])
assert located == source

# No range-reporting loader: pointer only, still not None.
assert engine.locate("urn:example:plain#/type") == {
    "documentUri": "urn:example:plain",
    "pointer": "/type",
}
# An unregistered resource: None, not an error.
assert engine.locate("urn:example:missing#/x") is None
```

## Positions on a failed registration

Registration is all-or-nothing: a document whose registration raises leaves
the registry exactly as it found it. That means `locate` has nothing to
place such an error against afterwards — the document is not registered.
The error carries the answer instead, captured before the rollback:

```python
from json_schema_engine.core import InvalidSchemaError, parse_json_with_ranges

bad_text = '{"properties": {"ok": {"type": "string"}, "broken": 7}}'
parsed = parse_json_with_ranges(bad_text, "urn:example:bad")

failing = create_engine()
try:
    failing.register_schema(parsed.value, "urn:example:bad", get_range=parsed.get_range)
    raise AssertionError("expected InvalidSchemaError")
except InvalidSchemaError as error:
    location = error.schema_location
    captured = error.schema_source

# Nothing was registered, so there is nothing to locate.
assert not failing.schemas.has("urn:example:bad")
assert location is not None
assert failing.locate(location) is None

# The error kept the answer anyway, range included.
assert captured is not None
assert captured["pointer"] == "/properties/broken"
span = captured["range"]["value"]
assert bad_text[span["start"]["offset"] : span["end"]["offset"]] == "7"
```

A `SourceRange` is plain integers, so an error held in a log buffer keeps
nothing alive.

## Zero cost on the hot path

Positions are a pure decoration step, applied only when a unit escapes to
output (D17): nothing during evaluation itself consults a range, computes
a pointer eagerly, or pays for `get_range` unless `positions=True` (or an
explicit `locate` call) asks for it. Evaluating without `positions` costs
nothing extra whether or not the engine's loaders happen to report ranges.
