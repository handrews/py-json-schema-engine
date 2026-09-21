# Custom keywords and vocabularies

Every built-in draft is built from the same mechanism this page exposes:
a vocabulary is a named map of `KeywordBehavior`s, and a dialect is an
ordered set of vocabularies. Nothing about `properties` or `allOf` is
privileged over a keyword you register yourself.

## `KeywordBehavior`

```python
from json_schema_engine.core import KeywordBehavior, Phase

behavior_fields = {f for f in KeywordBehavior.__dataclass_fields__}
assert behavior_fields == {
    "id",
    "evaluate",
    "analyze",
    "phase",
    "structural",
    "lower",
}
assert list(Phase) == [Phase.ASSERT, Phase.UNEVALUATED]
```

- `id` — the keyword's stable identity (a URI, by convention), independent
  of whatever name a dialect binds it under.
- `evaluate` — the interpreter semantics: `(value, cursor, ctx) -> bool`.
  A keyword that reports an error through `ctx.error()` must return
  `False` (an accepting keyword that also errors raises
  `KeywordContractError` — see below).
- `analyze` — `(value, ctx: AnalyzeContext) -> StaticFacts`, optional.
  Absent means "no facts": no subschemas, no productions, nothing to
  screen. This is also what drives the registration walk: only the
  positions a keyword's `StaticFacts.subschemas` names are treated as
  schemas, so a plain data value is never mistaken for one.
- `phase` — `Phase.ASSERT` (the default) or `Phase.UNEVALUATED`. Every
  `ASSERT` keyword in a schema object runs before any `UNEVALUATED`
  keyword there, so an `unevaluated*`-style consumer sees every sibling's
  dependency data already merged.
- `structural` — `True` for an identifier or reserved-location keyword
  (`$id`, `$comment`): it evaluates to nothing and appears in no output
  unit.
- `lower` — the keyword's compiled-tier lowering, optional. Absent means a
  schema object containing this keyword compiles as an interpreted unit
  (a trampoline back into the interpreter) rather than static code — never
  a failure. See [Compiling without `lower`](#compiling-without-lower)
  below.

`StaticFacts` carries `subschemas`, `references`, `produces`, `consumes`,
`regexes`, `formats`, `evaluates_names`, `evaluates_indexes`, and
`applications`; a keyword that applies no subschemas, produces no
dependency data, and declares no patterns simply omits them, which is what
the two exemplars below do.

## `KeywordContext`

`ctx`, the third argument to `evaluate`, is the only path to subschema
application, the dependency channel, and error reporting:

- `ctx.error(message, params=None)` — report an assertion failure with
  optional structured params (D13); the keyword must return `False`
  afterward.
- `ctx.annotate()` — record this keyword's own value as an annotation.
- `ctx.apply(segments, cursor)` — apply the subschema at `segments`
  (relative to the current schema object) to `cursor`; returns whether it
  passed.
- `ctx.resolve_ref(ref)` / `ctx.apply_resolved(target)` — resolve and
  apply a `$ref`-style reference.
- `ctx.compile_regex(pattern)` — compile through the engine's configured
  regex dialect, backend, and cache (see [Security](security.md)).
- `ctx.produce(data)` / `ctx.visible(behavior_ids, scope)` — the
  dependency channel `unevaluated*`-style keywords use to see what their
  siblings covered.

`produce`/`visible` are contract-checked against `analyze()`'s declared
`produces`/`consumes`: calling `ctx.produce()` without listing your own id
in `produces` raises `UndeclaredProductionError`, and reading a behavior id
absent from `consumes` raises `UndeclaredConsumptionError`. Both exist so
that an eliding evaluator (nothing asked for annotations) cannot silently
drop dependency data a keyword thought it was producing.

```python
from json_schema_engine.core import (
    UndeclaredConsumptionError,
    UndeclaredProductionError,
    create_engine,
)

contract_engine = create_engine()


def _bad_produce_evaluate(value, cursor, ctx) -> bool:
    ctx.produce("some dependency data")  # never declared in `produces`
    return True


def _bad_consume_evaluate(value, cursor, ctx) -> bool:
    ctx.visible(("urn:ex.example:never-declared",))  # never declared in `consumes`
    return True


contract_vocab = {
    "badProduce": KeywordBehavior(
        id="urn:ex.example:badProduce", evaluate=_bad_produce_evaluate
    ),
    "badConsume": KeywordBehavior(
        id="urn:ex.example:badConsume", evaluate=_bad_consume_evaluate
    ),
}
contract_engine.dialects.register_vocabulary(
    "urn:ex.example:vocab:contract", contract_vocab
)
contract_engine.dialects.register_dialect(
    "urn:ex.example:dialect:contract", ["urn:ex.example:vocab:contract"]
)

produce_uri = contract_engine.register_schema(
    {"badProduce": 1},
    "urn:ex.example:doc:bad-produce",
    dialect_uri="urn:ex.example:dialect:contract",
)
try:
    contract_engine.evaluate(produce_uri, 0)
    raised_produce = False
except UndeclaredProductionError:
    raised_produce = True
assert raised_produce is True

consume_uri = contract_engine.register_schema(
    {"badConsume": 1},
    "urn:ex.example:doc:bad-consume",
    dialect_uri="urn:ex.example:dialect:contract",
)
try:
    contract_engine.evaluate(consume_uri, 0)
    raised_consume = False
except UndeclaredConsumptionError:
    raised_consume = True
assert raised_consume is True
```

## An assertion keyword: `minWords`

This is the same shape as the `pattern` keyword in
`core/keywords/validation.py`: guard the instance type, then compare.

```python
from json_schema_engine.core import (
    DIALECT_2020_12,
    KeywordContractError,
    create_engine,
)

WORDS_VOCAB = "https://ex.example/vocab/words"
MIN_WORDS_ID = "https://ex.example/vocab/words#minWords"


def _min_words_evaluate(value, cursor, ctx) -> bool:
    instance = cursor.value
    if not isinstance(instance, str):
        return True  # vacuously true for a non-string instance
    if isinstance(value, bool) or not isinstance(value, int | float):
        return True  # not a numeric limit: nothing to enforce
    count = len(instance.split())
    if count < value:
        ctx.error(f"has {count} word(s), fewer than {value}", {"minWords": value})
        return False
    return True


min_words = KeywordBehavior(id=MIN_WORDS_ID, evaluate=_min_words_evaluate)

engine = create_engine()
engine.dialects.register_vocabulary(WORDS_VOCAB, {"minWords": min_words})
```

`engine.dialects` is the `DialectRegistry` every dialect (built-in or
custom) lives in. `register_vocabulary` binds a name-to-`KeywordBehavior`
map under a vocabulary URI; `register_dialect` assembles an ordered
dialect from vocabulary URIs already registered, later vocabularies
rebinding names earlier ones already bound:

```python
words_vocabs = [
    *engine.dialects.get_dialect(DIALECT_2020_12).vocabulary_uris,
    WORDS_VOCAB,
]
WORDS_DIALECT = "https://ex.example/dialect/words"
engine.dialects.register_dialect(WORDS_DIALECT, words_vocabs)
```

A document registers under this dialect either by passing `dialect_uri=`
directly to `register_schema`, or — the mechanism every built-in dialect
actually uses — by declaring a `$schema` that resolves to a metaschema
whose `$vocabulary` names `WORDS_VOCAB` (see
[Metaschemas](metaschemas.md#vocabulary-assembling-a-dialect-from-a-custom-metaschema)).

```python
uri = engine.register_schema(
    {"minWords": 3}, "https://ex.example/words-doc", dialect_uri=WORDS_DIALECT
)
assert engine.evaluate(uri, "a b c d").valid is True

short_result = engine.evaluate(uri, "a b", output="list", error_params=True)
assert short_result.valid is False
(error,) = short_result.errors
assert error["error"] == "has 2 word(s), fewer than 3"
assert error["params"] == {"minWords": 3}
assert error["keyword"] == "minWords"
assert error["vocabulary"] == WORDS_VOCAB
```

A keyword that calls `ctx.error()` but returns `True` anyway violates its
own contract — the interpreter treats that as a bug in the keyword, not a
result to report, and raises `KeywordContractError` rather than silently
dropping the error (which relevance would do to any accepting evaluation's
errors):

```python
def _broken_evaluate(value, cursor, ctx) -> bool:
    ctx.error("reported but accepted anyway")
    return True


engine.dialects.register_vocabulary(
    "https://ex.example/vocab/broken",
    {
        "broken": KeywordBehavior(
            id="https://ex.example/vocab/broken#broken", evaluate=_broken_evaluate
        )
    },
)
engine.dialects.register_dialect(
    "https://ex.example/dialect/broken", ["https://ex.example/vocab/broken"]
)
broken_uri = engine.register_schema(
    {"broken": True},
    "https://ex.example/broken-doc",
    dialect_uri="https://ex.example/dialect/broken",
)
try:
    engine.evaluate(broken_uri, 0)
    raised = False
except KeywordContractError:
    raised = True
assert raised is True
```

## An annotation-only keyword: `wordCount`

Meta-data keywords (`title`, `description`, ...) are all this shape: no
`analyze()` needed (no subschemas, no dependency data), `evaluate` always
accepts, and its only effect is `ctx.annotate()`.

```python
def _word_count_evaluate(value, cursor, ctx) -> bool:
    if value is True and isinstance(cursor.value, str):
        ctx.annotate()
    return True


word_count = KeywordBehavior(
    id="https://ex.example/vocab/words#wordCount", evaluate=_word_count_evaluate
)
engine.dialects.register_vocabulary(
    WORDS_VOCAB, {"minWords": min_words, "wordCount": word_count}
)
engine.dialects.register_dialect(WORDS_DIALECT, words_vocabs)

annotated_uri = engine.register_schema(
    {"wordCount": True}, "https://ex.example/wc-doc", dialect_uri=WORDS_DIALECT
)
annotated = engine.evaluate(
    annotated_uri, "one two three", output="list", annotations=True
)
assert annotated.valid is True
assert annotated.annotations[0]["annotation"] is True
assert annotated.annotations[0]["keyword"] == "wordCount"
```

## Compiling without `lower`

`minWords` and `wordCount` above have no `lower`. `compile_validator`
still works: a schema object using either keyword becomes an *interpreted*
unit in the compiled plan — a trampoline back into `Engine.evaluate` for
just that node — rather than a compile failure. `explain_compilation`
reports exactly why, through `FallbackCause`:

```python
from json_schema_engine.compiler import compile_validator, explain_compilation

compiled = compile_validator(engine, uri)
assert compiled.validate("a b c d") is True
assert compiled.validate("a b") is False

explanation = explain_compilation(compiled.plan)
assert explanation.causes == {"unlowerable": 1}
assert explanation.interpreted_units == 1
assert explanation.total_units == 1
```

`"unlowerable"` is one of four `FallbackCause` values (the others are
`"dynamic"` for `$dynamicRef`-class keywords, `"cycle"` for a possible
in-place cycle, and `"non_schema"` for a reference into non-schema data):
a keyword with no `lower`, an edge the planner cannot resolve statically,
or a consumer without static coverage all fall back the same way. Giving
`minWords` a `lower` (mirroring `validation.py`'s `_pattern_lower`, built
from `json_schema_engine.core`'s lowering IR) would let the compiler emit
it directly instead — a performance decision, never required for
correctness, since the fallback is always available and always correct.

M9 will document giving a custom keyword a `lower` form through the IR
in `json_schema_engine.core.lowering`; until then a custom keyword is
interpreted, as above, and its compiled artifacts stay exactly as
correct as the interpreter.
