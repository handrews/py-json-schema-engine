# Formats

`format` annotates by default in every dialect: the specs' own default,
and what the official `format.json` suite legs (mandatory, not
`optional/format`) require. Assertion is opt-in, through a format table
implemented from each format's RFC and verified against the official
`optional/format` suite.

```python
from json_schema_engine.core import create_engine

engine = create_engine()
uri = engine.register_schema({"format": "email"}, "https://example.com/plain")
result = engine.evaluate(uri, "not an email", output="list", annotations=True)
assert result.valid is True  # annotates only; never asserts by default
assert result.annotations is not None
assert [a["annotation"] for a in result.annotations] == ["email"]
```

## Two assertion postures

Passing a table with `formats=` makes the 2020-12 format-assertion
*vocabulary* available, but that vocabulary asserts only for a dialect
whose metaschema actually declares it — 2020-12's own bundled metaschema
does not, by default:

```python
from json_schema_engine.core import DIALECT_2020_12, VOCAB_FORMAT_ASSERTION
from json_schema_engine.formats import FORMATS_2020_12

vocab_engine = create_engine(formats=FORMATS_2020_12)
vocab_uri = vocab_engine.register_schema(
    {"format": "email"}, "https://example.com/vocab"
)
assert vocab_engine.evaluate(vocab_uri, "nope").valid is True  # not asserted yet

base = vocab_engine.dialects.get_dialect(DIALECT_2020_12)
vocab_engine.dialects.register_dialect(
    "urn:example:format-assertion-dialect",
    [*base.vocabulary_uris, VOCAB_FORMAT_ASSERTION],
)
asserting_uri = vocab_engine.register_schema(
    {"$schema": "urn:example:format-assertion-dialect", "format": "email"},
    "https://example.com/asserting",
)
assert vocab_engine.evaluate(asserting_uri, "nope").valid is False
```

A metaschema that declares the vocabulary promises assertion for every
format, so a name the table lacks is refused at registration:

```python
from json_schema_engine.core import UnknownFormatError

try:
    vocab_engine.register_schema(
        {"$schema": "urn:example:format-assertion-dialect", "format": "not-a-format"},
        "https://example.com/refused",
    )
except UnknownFormatError:
    pass
else:
    raise AssertionError("expected UnknownFormatError")
```

`assert_formats=True` is the other posture: best effort in *every*
standard dialect (2020-12, 2019-09, draft-07, draft-06), with no
metaschema declaration needed. A known name asserts; an unknown name
still only annotates.

```python
strict_engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
strict_uri = strict_engine.register_schema(
    {"format": "email"}, "https://example.com/strict"
)
assert strict_engine.evaluate(strict_uri, "ada@example.com").valid is True
assert strict_engine.evaluate(strict_uri, "nope").valid is False

unknown_uri = strict_engine.register_schema(
    {"format": "not-a-format"}, "https://example.com/unknown"
)
assert strict_engine.evaluate(unknown_uri, "anything").valid is True
```

`assert_formats=True` without a table raises `FormatsRequiredError`
(there is nothing to assert against); the same error fires for a
table-less engine whose metaschema declares the format-assertion
vocabulary.

```python
from json_schema_engine.core import FormatsRequiredError

try:
    create_engine(assert_formats=True)
except FormatsRequiredError:
    pass
else:
    raise AssertionError("expected FormatsRequiredError")
```

## The standard tables

`FORMATS_2020_12` carries the nineteen formats 2020-12 §7.3 defines;
`FORMATS_2019_09` is the identical object (2019-09 §7.3 names the same
list). `FORMATS_DRAFT_07` drops `uuid` and `duration` (seventeen names).
`FORMATS_DRAFT_06` carries only the nine draft-06 §8.3 defines.
`format_table_for(dialect_uri)` picks the standard table for a built-in
dialect URI (fragment ignored).

```python
from json_schema_engine.formats import (
    FORMATS_2019_09,
    FORMATS_DRAFT_06,
    FORMATS_DRAFT_07,
    format_table_for,
)

assert len(FORMATS_2020_12) == 19
assert FORMATS_2019_09 is FORMATS_2020_12
assert len(FORMATS_DRAFT_07) == 17
assert set(FORMATS_2020_12) - set(FORMATS_DRAFT_07) == {"uuid", "duration"}
assert len(FORMATS_DRAFT_06) == 9
assert format_table_for(DIALECT_2020_12) is FORMATS_2020_12
assert sorted(FORMATS_2020_12) == [
    "date",
    "date-time",
    "duration",
    "email",
    "hostname",
    "idn-email",
    "idn-hostname",
    "ipv4",
    "ipv6",
    "iri",
    "iri-reference",
    "json-pointer",
    "regex",
    "relative-json-pointer",
    "time",
    "uri",
    "uri-reference",
    "uri-template",
    "uuid",
]
```

## Custom tables

A table is any `Mapping[str, FormatDefinition]`. `FormatDefinition(test,
types=("string",), unavailable=None, import_path=None)` pairs a predicate
with the instance types it constrains; an instance of any other type
passes vacuously (the format never applies to it). `types` is not limited
to `"string"` — a custom format can scope itself to numbers instead:

```python
from json_schema_engine.core import FormatDefinition


def _is_int32(value: object) -> bool:
    return isinstance(value, int | float) and -(2**31) <= value < 2**31


custom_table = {"int32": FormatDefinition(_is_int32, types=("integer",))}
custom_engine = create_engine(formats=custom_table, assert_formats=True)
custom_uri = custom_engine.register_schema(
    {"format": "int32"}, "https://example.com/int32"
)
assert custom_engine.evaluate(custom_uri, 2**31).valid is False
assert custom_engine.evaluate(custom_uri, 5).valid is True
assert custom_engine.evaluate(custom_uri, 5.5).valid is True  # not an integer
assert custom_engine.evaluate(custom_uri, "5").valid is True  # a string, out of scope
```

`unavailable` marks an entry that exists in the table but cannot run in
this environment (an optional extra is missing). Asserting it fails
loudly at registration, as `FormatUnavailableError`, rather than silently
passing:

```python
from json_schema_engine.core import FormatUnavailableError

gated_table = {
    "needs-x": FormatDefinition(lambda v: True, unavailable="needs the 'x' extra")
}
gated_engine = create_engine(formats=gated_table, assert_formats=True)
try:
    gated_engine.register_schema({"format": "needs-x"}, "https://example.com/gated")
except FormatUnavailableError as error:
    assert "x' extra" in str(error)
else:
    raise AssertionError("expected FormatUnavailableError")
```

`import_path` (`"module:attribute"`) lets a standalone module import the
predicate by name instead of needing the compiler; see
[Compiling schemas](compiled.md#formats).

## The `idna` extra

`idn-hostname`, and the A-label check inside `hostname`, need IDNA2008,
provided by the optional `idna` extra:

```sh
pip install 'json-schema-engine[idna]'
```

Without it, the table marks `idn-hostname` `unavailable` (asserting it
raises `FormatUnavailableError` at registration), and `hostname` degrades:
a well-formed `xn--` label is accepted without decoding it, rather than
checked against IDNA2008.

```python
from json_schema_engine.formats import idna_, net

if idna_.HAVE_IDNA:
    assert net.hostname("xn--nxasmq6b") is True  # canonical, decodes correctly
    assert net.hostname("xn---9uc") is False  # non-canonical Punycode
else:
    assert net.hostname("xn--X") is True  # documented degradation: unchecked
```

Compiled validators assert formats too, and a standalone module imports
predicates by `import_path` from `json_schema_engine.formats` — so the
`idna` extra must be installed wherever such a module runs, not just
wherever it was emitted.

## Error text

An asserting `format` reports `must match format '<name>'`, with
`params={"format": name}` under `error_params=True`:

```python
err_engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
err_uri = err_engine.register_schema({"format": "ipv4"}, "https://example.com/err")
outcome = err_engine.evaluate(err_uri, "nope", output="list", error_params=True)
assert outcome.valid is False
(error_unit,) = outcome.errors
assert error_unit["error"] == "must match format 'ipv4'"
assert error_unit["params"] == {"format": "ipv4"}
```

## Notable rulings the suite pins

A few formats have edge cases the official suite fixes exactly, so the
predicates follow the suite rather than a looser reading of the RFC:

- **Leap seconds.** `time`/`date-time` accept `second == 60` only when the
  UTC-equivalent wall clock (the local time adjusted by the numeric
  offset) is `23:59`.
- **`duration` is RFC 3339 Appendix A**, not general ISO 8601: `P1Y2D`
  is invalid (a year component reaches a day only through an optional
  month: `dur-year = 1*DIGIT "Y" [dur-month]`, `dur-month = 1*DIGIT "M"
  [dur-day]`), while `P1M2D` is valid.
- **`regex` is ECMA-262 syntax**, checked through this repository's own
  `ecma_regex` parser — never Python's `re` grammar.

```python
from json_schema_engine.formats import datetime_, misc

assert datetime_.time("23:59:60Z") is True  # UTC-equivalent wall clock 23:59
assert datetime_.time("22:59:60Z") is False  # wall clock 22:59: not a leap second
assert datetime_.duration("P1Y2D") is False
assert datetime_.duration("P1M2D") is True
assert misc.regex("(?<=a+)b") is True  # ECMA-262 lookbehind syntax
assert misc.regex("(?P<n>x)") is False  # Python-only named-group syntax
```

## See also

- [Compiling schemas](compiled.md) — how a compiled or standalone artifact
  resolves and imports format predicates.
- [Validation](validation.md) — `error_params`, output formats, and the
  rest of the evaluation surface `format` participates in.
