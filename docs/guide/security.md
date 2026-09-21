# Security

Schemas and instances are both often untrusted input. This page expands on
the README's Security section: what the two tiers do and do not generate,
the plain-data contract compiled validators assume, and the three
resource-exhaustion vectors with a bound or an opt-out.

## The interpreter generates no code

`Engine.evaluate` and `Engine.register_schema` never call `compile()` or
`exec()`. `json_schema_engine.core` does not import `ast` at all — an
import-linter contract (`core never uses ast`) fails the build if it ever
does — so a hostile schema value cannot become Python source on the
interpreter's path. Schema-as-code injection, the class of attack where a
crafted property name or pattern ends up executed as code, does not apply
to the interpreter tier: there is no code generation step for it to reach.

```python
from json_schema_engine.core import create_engine

engine = create_engine()
hostile_property = '"; __import__("os").system("echo pwned"); "'
uri = engine.register_schema(
    {"properties": {hostile_property: {"type": "string"}}},
    "https://ex.example/hostile-property",
)
assert engine.evaluate(uri, {hostile_property: "just a string"}).valid is True
assert engine.evaluate(uri, {hostile_property: 1}).valid is False
```

The hostile text above is ordinary instance data to the interpreter: a
dict key compared for membership, never a code fragment.

## The compiler tier does generate code — from a narrow, audited path

`json_schema_engine.compiler` turns a registered schema into a Python
function by building an `ast.Module` and compiling it (see
[Compiling schemas](compiled.md)). That module's source comes from exactly
two channels, both gated in `compiler/emit.py`:

- **A minted identifier vocabulary.** Every `ast.Name`, `ast.arg`, and
  `ast.FunctionDef` name in an emitted module is either a fixed helper
  name the emitter always uses, a builtin, or a name minted by the
  emitter's own counter (`fresh()`, producing names like `u0`, `t3`) —
  never a string taken from schema or instance data. A hostile property
  name, pattern, or keyword name is never turned into an identifier, even
  when it is spelled exactly like one of those names already.
- **`const()` data entry.** Schema-derived values (a `properties` key, an
  `enum` member, a `pattern` source) enter the generated module only as
  `ast.Constant` nodes (or lists/dicts of them) through one gated
  function, `emit.const()` — never concatenated into source text.

`tests/compiler/test_injection.py` is the corpus proving this for a wide
range of hostile shapes (quote and backtick breakout attempts, comment
markers, `__class__`/`__import__` payloads, null bytes, line/paragraph
separators, even strings spelled like the emitter's own helper names).
This is a summary of that guarantee, not an independent proof — read that
module for the exact corpus.

`compile()` and `exec()` themselves are confined to one function,
`compiler/runtime_compile.py::instantiate`, so the surface is auditable
with `sys.addaudithook`:

```python
import sys

from json_schema_engine.compiler import compile_validator

audited_events: list[str] = []


def _hook(name: str, _args: object) -> None:
    if name in ("compile", "exec"):
        audited_events.append(name)


sys.addaudithook(_hook)
compiled = compile_validator(engine, uri)
assert audited_events == ["compile", "exec"]
assert compiled.validate("safe string") is True
```

Exactly one `compile` and one `exec` event, for the one module this
artifact needed — never more, no matter how large or hostile the schema.

## The plain-data contract for compiled validators (P9)

A compiled validator tests instance types with `type(x) is dict` / `list`
/ `str` / `int` / `float` / `bool`, and `x is None` — never `isinstance`.
It assumes the instance is exactly what `json.loads` produces. A subclass
of one of those types (an `OrderedDict`, an `IntEnum`, a `str` subclass)
is not a JSON value to the compiled tier and is treated as *none* of the
JSON types, even though `isinstance` would say otherwise:

```python
from collections import OrderedDict

od = OrderedDict(name="Ada")
person_engine = create_engine()
person_uri = person_engine.register_schema(
    {"type": "object", "required": ["name"]}, "https://ex.example/person"
)
person_compiled = compile_validator(person_engine, person_uri)

assert isinstance(od, dict) is True
assert (type(od) is dict) is False
# The interpreter uses `isinstance`-based object checks: a `dict` subclass
# satisfies `type: object`.
assert person_engine.evaluate(person_uri, od).valid is True
# The compiled validator's `type(x) is dict` does not: `type(od) is dict`
# is False, so `od` is "not an object" to compiled code, and `type: object`
# is an assertion, not a vacuous skip — it fails outright.
assert person_compiled.validate(od) is False
```

This is a real behavior difference, not a corner case to ignore: a caller
that needs subclass instances validated at compiled speed adds a
normalizing copy (`dict(od)`) before calling in, rather than expecting
compiled code to special-case it with `isinstance`. Hand-built or
subclassed objects belong to the interpreter; the compiled tier is for
plain `json.loads`-shaped data, and the differential fuzzer that referees
the compiler against the interpreter only ever generates plain data.

## Regular expressions (ReDoS)

`pattern` and `patternProperties` compile untrusted regexes and run them
against untrusted strings. Python's `re` (and the `regex` extra) can
backtrack catastrophically on a pattern like `(a+)+$`. `detect_unsafe_regex`
is a conservative, standalone screen for nested unbounded quantifiers —
necessary, not sufficient, so it over-reports rather than under-reports:

```python
from json_schema_engine.core import detect_unsafe_regex

unsafe = detect_unsafe_regex("(a+)+$")
assert unsafe.safe is False
assert unsafe.reason == "nested unbounded quantifiers (star height 2)"

safe = detect_unsafe_regex("^[a-z]{2,10}$")
assert safe.safe is True
assert safe.reason is None
```

`reject_unsafe_regex=True` runs this screen at registration and raises
`UnsafeRegexError` before an unsafe pattern is ever tested against data:

```python
from json_schema_engine.core import UnsafeRegexError, create_engine

strict_engine = create_engine(reject_unsafe_regex=True)
try:
    strict_engine.register_schema({"pattern": "(a+)+$"}, "https://ex.example/redos")
    raised = False
except UnsafeRegexError:
    raised = True
assert raised is True

safe_uri = strict_engine.register_schema(
    {"pattern": "^[a-z]{2,10}$"}, "https://ex.example/safe-pattern"
)
assert strict_engine.evaluate(safe_uri, "hello").valid is True
assert strict_engine.evaluate(safe_uri, "TOO LONG!!").valid is False
```

Neither backend is linear-time, so this screen is a heuristic, not a
proof — treat a wildly untrusted schema's patterns with the same care as
any other untrusted program input. The bundled metaschemas' own patterns
are never screened (they are trusted, not caller-supplied), so
`reject_unsafe_regex=True` never rejects a `$ref` to one of them.

## Recursion depth

`max_depth` (default 512) bounds both registration nesting and evaluation
nesting, raising the typed `MaxDepthExceededError` — comfortably before
CPython's own stack limit could instead raise an untyped `RecursionError`.
Both registration and evaluation are covered, and the engine stays usable
afterward: a rejected document or a rejected instance never poisons a
later, unrelated call on the same engine.

```python
from json_schema_engine.core import MaxDepthExceededError, create_engine


def deep_instance(depth: int):
    node = {}
    for _ in range(depth):
        node = {"child": node}
    return node


shallow_engine = create_engine(max_depth=5)
recursive_uri = shallow_engine.register_schema(
    {"properties": {"child": {"$ref": "#"}}}, "https://ex.example/deep"
)
try:
    shallow_engine.evaluate(recursive_uri, deep_instance(10))
    raised2 = False
except MaxDepthExceededError:
    raised2 = True
assert raised2 is True
# The engine is untouched by the failed evaluation.
assert shallow_engine.evaluate(recursive_uri, {"child": {}}).valid is True
```

A schema nested too deeply is rejected the same way, at registration:

```python
def deep_not_schema(depth: int):
    schema = {"type": "string"}
    for _ in range(depth):
        schema = {"not": schema}
    return schema


try:
    shallow_engine.register_schema(
        deep_not_schema(50), "https://ex.example/deep-schema"
    )
    raised3 = False
except MaxDepthExceededError:
    raised3 = True
assert raised3 is True
# A fresh, unrelated document still registers on the same engine.
fine_uri = shallow_engine.register_schema({"type": "string"}, "https://ex.example/fine")
assert shallow_engine.evaluate(fine_uri, "ok").valid is True
```

## `uniqueItems` is near-linear, not quadratic

`uniqueItems` buckets elements by a canonical key and confirms collisions
with full JSON equality, so a large array of distinct values costs O(n)
rather than the O(n²) a naive pairwise comparison would, while genuine
duplicates — including numbers equal across `int`/`float`, and objects
that differ only in member order — are still reported precisely:

```python
import time

unique_engine = create_engine()
unique_uri = unique_engine.register_schema(
    {"uniqueItems": True}, "https://ex.example/unique"
)
start = time.perf_counter()
big_result = unique_engine.evaluate(unique_uri, list(range(50_000)))
elapsed = time.perf_counter() - start
assert big_result.valid is True
assert elapsed < 5.0  # comfortably sub-quadratic; typically well under 1s

dup_result = unique_engine.evaluate(
    unique_uri, [1, 2, 3, 2], output="list", error_params=True
)
assert dup_result.valid is False
(dup_error,) = dup_result.errors
assert dup_error["error"] == "items at 1 and 3 are not unique"
assert dup_error["params"] == {"duplicates": [1, 3]}
```

## `InfiniteLoopError`

A schema re-entered at the *same instance location*, with no progress
through either the schema or the instance, is a genuine infinite loop —
not merely deep recursion — and is detected and reported as such rather
than exhausting the depth budget or the stack:

```python
from json_schema_engine.core import InfiniteLoopError

loop_engine = create_engine()
loop_uri = loop_engine.register_schema({"$ref": "#"}, "https://ex.example/loop")
try:
    loop_engine.evaluate(loop_uri, 0)
    raised4 = False
except InfiniteLoopError:
    raised4 = True
assert raised4 is True
```

Re-evaluating the *same schema location* against the *same instance
location* twice in one run is not by itself a sign of a loop (two
sibling applicators legitimately converge on one spot); only re-entering
without any progress trips the guard.

## Large inputs

The engine does not bound instance size on its own — there is no built-in
cap on array length, object member count, or string length. A
denial-of-service bound from the defenses above is best effort, not a
guarantee: treat a wildly untrusted schema or instance with the same care
you would give any other untrusted program input (a request body size
limit in front of the engine, for instance).

## No prototype hazard in Python

Python `dict`s have no prototype chain, so there is nothing for a hostile
property name to pollute. `__proto__`, `constructor`, and similar
reserved-looking names evaluate as ordinary properties, with no
special-casing anywhere in the engine:

```python
reserved_engine = create_engine()
reserved_uri = reserved_engine.register_schema(
    {
        "type": "object",
        "properties": {"__proto__": {"type": "number", "title": "proto"}},
        "required": ["__class__"],
    },
    "https://ex.example/reserved",
)
reserved_result = reserved_engine.evaluate(
    reserved_uri,
    {"__proto__": 5, "__class__": 1},
    output="list",
    annotations=True,
)
assert reserved_result.valid is True
assert any(a["inputLocation"] == "/__proto__" for a in reserved_result.annotations)
```
