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

## Lowering a custom keyword

`minWords` has no natural lowering: the IR's closed `HelperName` set has
no "count words" operation — `helper("length_of", ...)` counts an
instance's own length (a string's code points, a collection's size),
never the number of whitespace-separated words inside it. Giving
`minWords` a `lower` built from that helper would compile something that
quietly disagrees with `evaluate` on multi-word strings, which is worse
than staying interpreted. `minWords` stays interpreted, as demonstrated
above, and every artifact using it stays exactly as correct as the
interpreter.

`isEven` below is a keyword the IR **can** express exactly: a type guard
plus `Helper("is_multiple_of", ...)`, the same helper
`core/keywords/validation.py`'s built-in `multipleOf` lowers to.

```python
from json_schema_engine.compiler import (
    compile_evaluator,
    compile_validator,
    explain_compilation,
)
from json_schema_engine.core.lowering import (
    and_,
    annotate,
    const,
    fail,
    helper,
    not_,
    type_is,
    when,
)

IS_EVEN_ID = "https://ex.example/vocab/words#isEven"


def _is_even_evaluate(value, cursor, ctx) -> bool:
    if value is not True:
        return True  # not turned on: nothing to enforce
    instance = cursor.value
    if isinstance(instance, bool) or not isinstance(instance, int | float):
        return True  # vacuously true for a non-number instance
    if instance % 2 != 0:
        ctx.error("must be an even number", {"isEven": True})
        return False
    return True


def _is_even_lower(value, lctx) -> None:
    if value is not True:
        return
    instance = lctx.instance
    lctx.emit(
        when(
            and_(
                type_is(instance, "number"),
                not_(helper("is_multiple_of", instance, const(2))),
            ),
            (fail(("must be an even number",), {"isEven": const(True)}),),
        )
    )


is_even = KeywordBehavior(
    id=IS_EVEN_ID, evaluate=_is_even_evaluate, lower=_is_even_lower
)
```

`_is_even_lower` mirrors `_is_even_evaluate` guard for guard: vacuously
true (no `Fail` emitted) unless the instance is a number and fails
`is_multiple_of`, the same failure message and params on both tiers.

Register `isEven` alongside the existing keywords and give `wordCount` a
`lower` too — an annotation keyword's entire lowered form is a guarded
`annotate()`, mirroring the same `value is True and isinstance(...,
str)` test `_word_count_evaluate` runs:

```python
def _word_count_lower(value, lctx) -> None:
    if value is not True:
        return
    lctx.emit(when(type_is(lctx.instance, "string"), (annotate(),)))


word_count_lowered = KeywordBehavior(
    id="https://ex.example/vocab/words#wordCount",
    evaluate=_word_count_evaluate,
    lower=_word_count_lower,
)
engine.dialects.register_vocabulary(
    WORDS_VOCAB,
    {"minWords": min_words, "wordCount": word_count_lowered, "isEven": is_even},
)
engine.dialects.register_dialect(WORDS_DIALECT, words_vocabs)
```

`isEven` evaluates the same on both tiers:

```python
even_uri = engine.register_schema(
    {"isEven": True}, "https://ex.example/even-doc", dialect_uri=WORDS_DIALECT
)
assert engine.evaluate(even_uri, 4).valid is True

odd_result = engine.evaluate(even_uri, 3, output="list", error_params=True)
assert odd_result.valid is False
(odd_error,) = odd_result.errors
assert odd_error["error"] == "must be an even number"
assert odd_error["params"] == {"isEven": True}
```

`explain_compilation` now reports zero interpreted units for a schema
built entirely from keywords with a `lower`:

```python
even_compiled = compile_validator(engine, even_uri)
assert even_compiled.validate(4) is True
assert even_compiled.validate(3) is False

even_explanation = explain_compilation(even_compiled.plan)
assert even_explanation.interpreted_units == 0
assert even_explanation.causes == {}
```

`compile_evaluator` produces the same error unit the interpreter does —
same message, same params, same keyword:

```python
even_evaluator = compile_evaluator(engine, even_uri, annotations=True)
compiled_odd = even_evaluator.evaluate(3, output="list", error_params=True)
assert compiled_odd.valid is False
assert compiled_odd.errors == odd_result.errors
```

And the annotation keyword's compiled and interpreted annotations agree
too:

```python
wc_uri = engine.register_schema(
    {"wordCount": True}, "https://ex.example/wc-lowered-doc", dialect_uri=WORDS_DIALECT
)
interpreted_wc = engine.evaluate(
    wc_uri, "one two three", output="list", annotations=True
)
wc_evaluator = compile_evaluator(engine, wc_uri, annotations=True)
compiled_wc = wc_evaluator.evaluate("one two three", output="list")
assert compiled_wc.annotations == interpreted_wc.annotations
assert explain_compilation(wc_evaluator.plan).interpreted_units == 0
```

**The contract.** `lower` must describe exactly what `evaluate` does —
the same guards, the same failing condition, the same message and
params — never an approximation or a different keyword in disguise. The
compiler's differential fuzzer (`tests/compiler/test_fuzz.py`) is the
referee: it generates schemas and instances and checks every tier against
the interpreter, so a `lower` that drifts from its `evaluate` fails there,
not in production. A keyword without `lower` is interpreted, never wrong —
`lower` is a performance decision the IR either supports or doesn't, and
"doesn't" is always a legitimate answer, as `minWords` shows above.
