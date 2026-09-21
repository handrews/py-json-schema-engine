# Adversarial resource-exhaustion and safety tests (DESIGN.md D20, P3): the
# three interpreter-level DoS vectors — ReDoS, O(n^2) uniqueItems, unbounded
# recursion — plus the Python-specific finding that prototype pollution is
# N/A (dicts have no prototype chain) while reserved names are still
# unit-tested as ordinary properties. Mirrors
# `packages/core/test/security.test.ts` in the TS reference engine
# (read-only per DESIGN.md §0/D15).
#
# Each resource-bound test asserts a wall-clock budget with
# `time.perf_counter()`, generous for CI: the TS suite's per-test vitest
# timeouts are doubled or more here (its 1s -> our 2s; its 5s -> our 10s).

import time

import pytest

from json_schema_engine.core import (
    JsonValue,
    KeywordBehavior,
    KeywordContext,
    create_engine,
    detect_unsafe_regex,
)
from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.errors import (
    MaxDepthExceededError,
    UndeclaredConsumptionError,
    UndeclaredProductionError,
    UnsafeRegexError,
)

# --- uniqueItems is near-linear (D20) --------------------------------------


def test_uniqueitems_validates_100k_distinct_items_within_budget() -> None:
    engine = create_engine()
    uri = engine.register_schema({"uniqueItems": True}, "https://sec.example/unique")
    items: JsonValue = list(range(100_000))
    start = time.perf_counter()
    result = engine.evaluate(uri, items)
    elapsed = time.perf_counter() - start
    assert result.valid is True
    # TS budget: 1000ms; doubled for CI headroom. Measured locally ~35ms.
    assert elapsed < 2.0


def test_uniqueitems_reports_a_real_duplicate_with_ascending_indices() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"uniqueItems": True}, "https://sec.example/unique-dup"
    )
    result = engine.evaluate(uri, [1, 2, 3, 2], output="list", error_params=True)
    assert result.valid is False
    assert result.errors is not None
    (error,) = result.errors
    assert error["error"] == "items at 1 and 3 are not unique"
    # `validation.py`'s uniqueItems reports the colliding pair as `duplicates`,
    # not a keyword value or the offending items themselves.
    assert error.get("params") == {"duplicates": [1, 3]}


# --- hash-miss guard (P2): canonical_key confirmed by json_equal -----------


def test_lookalike_values_are_pairwise_distinct() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"uniqueItems": True}, "https://sec.example/unique-mixed"
    )
    # 1, "1", true, null, "true" are pairwise unequal under JSON equality.
    assert engine.evaluate(uri, [1, "1", True, None, "true"]).valid is True


def test_json_numbers_are_equal_across_int_and_float() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"uniqueItems": True}, "https://sec.example/unique-numeric"
    )
    assert engine.evaluate(uri, [1, 1.0]).valid is False


def test_bool_is_never_a_number() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"uniqueItems": True}, "https://sec.example/unique-bool"
    )
    assert engine.evaluate(uri, [True, 1]).valid is True


def test_reordered_object_members_are_duplicates() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"uniqueItems": True}, "https://sec.example/unique-object"
    )
    instance: JsonValue = [{"a": 1, "b": 2}, {"b": 2, "a": 1}]
    assert engine.evaluate(uri, instance).valid is False


def test_nested_arrays_compare_by_value_too() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"uniqueItems": True}, "https://sec.example/unique-nested"
    )
    assert engine.evaluate(uri, [[1, 2], [1, 2]]).valid is False


# --- recursion depth is bounded (D20/P3) -----------------------------------


def _deep_object(depth: int) -> JsonValue:
    """`{"child": {"child": ... {}}}`, nested `depth` times."""
    node: JsonValue = {}
    for _ in range(depth):
        node = {"child": node}
    return node


def _deep_not_schema(depth: int) -> JsonValue:
    """`{"not": {"not": ... {"type": "string"}}}`, nested `depth` times."""
    schema: JsonValue = {"type": "string"}
    for _ in range(depth):
        schema = {"not": schema}
    return schema


RECURSIVE_SCHEMA: JsonValue = {"properties": {"child": {"$ref": "#"}}}


def test_deep_instance_raises_typed_error_and_leaves_engine_usable() -> None:
    engine = create_engine()
    uri = engine.register_schema(RECURSIVE_SCHEMA, "https://sec.example/deep-instance")
    with pytest.raises(MaxDepthExceededError):
        engine.evaluate(uri, _deep_object(5000))
    # The engine is untouched by a failed evaluation: a shallow instance on
    # the same engine still evaluates.
    assert engine.evaluate(uri, {"child": {}}).valid is True


def test_deep_schema_raises_typed_error_at_registration() -> None:
    engine = create_engine()
    with pytest.raises(MaxDepthExceededError):
        engine.register_schema(
            _deep_not_schema(5000), "https://sec.example/deep-schema"
        )
    # The registry is untouched by a failed registration: a fresh, unrelated
    # document still registers on the same engine.
    uri = engine.register_schema({"type": "string"}, "https://sec.example/fine")
    assert engine.evaluate(uri, "ok").valid is True


def test_custom_max_depth_boundary() -> None:
    """The exact `max_depth=8` boundary, established empirically.

    Each nesting level of `RECURSIVE_SCHEMA` costs two `apply_schema` frames
    (one for the `properties`-applied child schema, one for the `$ref`
    resolution's re-application of the root), plus one for the initial root
    application: depth used = 1 + 2*n. With `max_depth=8`, n=3 uses depth 7
    (passes) and n=4 uses depth 9 (fails) — the boundary sits between 3 and
    4 levels of instance nesting, not at a nesting count of 8 itself.
    """
    engine = create_engine(max_depth=8)
    uri = engine.register_schema(RECURSIVE_SCHEMA, "https://sec.example/shallow")
    assert engine.evaluate(uri, _deep_object(3)).valid is True
    with pytest.raises(MaxDepthExceededError):
        engine.evaluate(uri, _deep_object(4))


def test_backstop_converts_stray_recursion_error_on_evaluation() -> None:
    """`max_depth=1_000_000` never trips the typed depth check itself, so a
    ~20k-deep instance must exhaust CPython's own (much lower, default
    1000-frame) call stack — proving the `RecursionError` backstop (P3),
    not the counter, is what fires. Bounded well under CPython's stack
    limit's own cost, so this must not take more than a couple of seconds.
    """
    engine = create_engine(max_depth=1_000_000)
    uri = engine.register_schema(RECURSIVE_SCHEMA, "https://sec.example/backstop")
    start = time.perf_counter()
    with pytest.raises(MaxDepthExceededError):
        engine.evaluate(uri, _deep_object(20_000))
    assert time.perf_counter() - start < 3.0


def test_backstop_converts_stray_recursion_error_on_registration() -> None:
    engine = create_engine(max_depth=1_000_000)
    start = time.perf_counter()
    with pytest.raises(MaxDepthExceededError):
        engine.register_schema(
            _deep_not_schema(20_000), "https://sec.example/backstop-schema"
        )
    assert time.perf_counter() - start < 3.0


# --- regex safety (D20/P1) --------------------------------------------------


def test_reject_unsafe_regex_rejects_exponential_pattern_at_registration() -> None:
    engine = create_engine(reject_unsafe_regex=True)
    with pytest.raises(UnsafeRegexError):
        engine.register_schema({"pattern": "(a+)+$"}, "https://sec.example/redos")


def test_reject_unsafe_regex_rejects_exponential_pattern_properties_key() -> None:
    engine = create_engine(reject_unsafe_regex=True)
    with pytest.raises(UnsafeRegexError):
        engine.register_schema(
            {"patternProperties": {"(a+)+$": True}},
            "https://sec.example/redos-props",
        )


def test_reject_unsafe_regex_still_accepts_safe_patterns() -> None:
    engine = create_engine(reject_unsafe_regex=True)
    uri = engine.register_schema(
        {"pattern": "^[a-z]{2,10}$"}, "https://sec.example/safe"
    )
    assert engine.evaluate(uri, "hello").valid is True
    assert engine.evaluate(uri, "TOO LONG!!").valid is False


def test_reject_unsafe_regex_never_screens_bundled_metaschemas() -> None:
    # Bundled metaschemas contain patterns; construction must not raise even
    # though the screen is active, and a schema that references one by $ref
    # registers and evaluates normally.
    engine = create_engine(reject_unsafe_regex=True)
    uri = engine.register_schema(
        {"$ref": "https://json-schema.org/draft/2020-12/schema"},
        "https://sec.example/meta-ref",
    )
    assert engine.evaluate(uri, {"type": "string"}).valid is True
    assert engine.evaluate(uri, 5).valid is False


UNSAFE_PATTERNS = ["(a+)+$", "(a*)*", "(.*)+", "(?:ab+)+"]
SAFE_PATTERNS = ["^[a-z]+$", "a{1,5}b", "(abc)+", r"\d{3}-\d{4}", "(a|b)*c"]


@pytest.mark.parametrize("pattern", UNSAFE_PATTERNS)
def test_detect_unsafe_regex_flags_nested_unbounded_quantifiers(
    pattern: str,
) -> None:
    report = detect_unsafe_regex(pattern)
    assert report.safe is False


@pytest.mark.parametrize("pattern", SAFE_PATTERNS)
def test_detect_unsafe_regex_accepts_benign_patterns(pattern: str) -> None:
    report = detect_unsafe_regex(pattern)
    assert report.safe is True


# --- no prototype hazard in Python; reserved names are ordinary keys ------
#
# D20's prototype-pollution defense is N/A for Python (dicts have no
# prototype chain), but the suite's trap keys are still exercised end to end
# — through `properties`, `required`, `additionalProperties`,
# `patternProperties`, and `dependentRequired` — so the absence of the
# hazard is proven, not assumed, and the reserved names appear as ordinary
# keys in `list`/`hierarchical` output with no special-casing.

RESERVED_SCHEMA: JsonValue = {
    "type": "object",
    "properties": {
        "__proto__": {"type": "number", "title": "proto title"},
        "constructor": {"type": "string", "title": "ctor title"},
    },
    "required": ["__class__"],
    "additionalProperties": True,
    "patternProperties": {"^__init__$": {"type": "null"}},
    "dependentRequired": {"__dict__": ["__proto__"]},
}


def test_reserved_names_evaluate_as_ordinary_properties() -> None:
    engine = create_engine()
    uri = engine.register_schema(RESERVED_SCHEMA, "https://sec.example/reserved")
    instance: JsonValue = {
        "__proto__": 5,
        "constructor": "c",
        "__class__": 1,
        "__init__": None,
        "__dict__": True,
    }
    result = engine.evaluate(
        uri, instance, output="list", annotations=True, error_params=True
    )
    assert result.valid is True
    assert result.annotations is not None
    by_location = {a["inputLocation"]: a["keyword"] for a in result.annotations}
    assert by_location["/__proto__"] == "title"
    assert by_location["/constructor"] == "title"


def test_reserved_names_report_errors_as_ordinary_keys() -> None:
    engine = create_engine()
    uri = engine.register_schema(RESERVED_SCHEMA, "https://sec.example/reserved-err")
    # Missing the required `__class__`, and `__dict__` present without its
    # dependent `__proto__`: both errors key on the reserved name exactly as
    # any other keyword value would.
    instance: JsonValue = {"__dict__": True}
    result = engine.evaluate(uri, instance, output="hierarchical")
    assert result.valid is False
    document = result.output_document
    assert isinstance(document, dict)
    errors = document.get("errors")
    assert isinstance(errors, dict)
    assert "required" in errors and "dependentRequired" in errors

    # A dict key holding the reserved name maps straight through, no
    # special-casing: `hasOwnProperty`-style keys just aren't declared here,
    # but `__proto__`/`__dict__` as *keys* of the errors/annotations maps
    # would show up exactly as any other keyword name would.
    valid_instance: JsonValue = {
        "__proto__": 5,
        "__class__": 1,
        "__dict__": True,
    }
    ok_result = engine.evaluate(uri, valid_instance, output="list", annotations=True)
    assert ok_result.valid is True
    assert ok_result.annotations is not None
    assert any(a["inputLocation"] == "/__proto__" for a in ok_result.annotations)


# --- wide instances are bounded by memory, not argument count -------------


def test_collects_165k_annotation_units_from_one_evaluation() -> None:
    properties: dict[str, JsonValue] = {}
    record: dict[str, JsonValue] = {}
    for p in range(150):
        properties[f"p{p}"] = {"type": "string", "title": f"Property {p}"}
        record[f"p{p}"] = "x"
    engine = create_engine()
    uri = engine.register_schema(
        {"type": "array", "items": {"type": "object", "properties": properties}},
        "https://sec.example/wide-annotations",
    )
    instance: JsonValue = [dict(record) for _ in range(1100)]
    start = time.perf_counter()
    result = engine.evaluate(uri, instance, output="basic", annotations=True)
    elapsed = time.perf_counter() - start
    assert result.valid is True
    assert result.annotations is not None
    assert len(result.annotations) == 150 * 1100
    # TS budget: 5000ms; doubled for CI headroom. Measured locally ~2s.
    assert elapsed < 10.0


def test_retains_160k_dropped_errors_at_the_verbose_level() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"anyOf": [{"items": {"type": "string"}}, True]},
        "https://sec.example/wide-dropped",
    )
    instance: JsonValue = list(range(160_000))
    start = time.perf_counter()
    result = engine.evaluate(uri, instance, output="list", verbose=True)
    elapsed = time.perf_counter() - start
    assert result.valid is True
    assert result.errors is None
    assert result.dropped_errors is not None
    assert len(result.dropped_errors) == 160_000
    # TS budget: 5000ms; doubled for CI headroom. Measured locally ~2s.
    assert elapsed < 10.0


# --- undeclared production/consumption raise under every output format ----
#
# A hand-registered custom vocabulary, as tests/core/test_evaluator.py does:
# one keyword calls `ctx.produce` without declaring `produces`, one calls
# `ctx.visible` without declaring `consumes`. Through the public `Engine`
# facade the record-time gate is always installed (even for `annotations=
# False`, D5's elision predicate is `_record_nothing`, never `None`), so
# both errors are loud regardless of output format — verified here for
# `flag` (the minimal format) and `hierarchical` (a located-tree format).

_VOCAB = "urn:sec-test:vocab"
_DIALECT = "urn:sec-test:dialect"
_UNDECLARED_CONSUMES_ID = "urn:sec-test:declared-elsewhere"


def _undeclared_produce(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.produce("x")
    return True


def _undeclared_read(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.visible((_UNDECLARED_CONSUMES_ID,))
    return True


_SECURITY_KEYWORDS = {
    "undeclaredProduce": KeywordBehavior(
        id="urn:sec-test:undeclaredProduce", evaluate=_undeclared_produce
    ),
    "undeclaredRead": KeywordBehavior(
        id="urn:sec-test:undeclaredRead", evaluate=_undeclared_read
    ),
}


@pytest.mark.parametrize("output", ["flag", "hierarchical"])
def test_undeclared_production_is_loud_under_every_format(output: str) -> None:
    engine = create_engine()
    engine.dialects.register_vocabulary(_VOCAB, _SECURITY_KEYWORDS)
    engine.dialects.register_dialect(_DIALECT, [_VOCAB])
    uri = engine.register_schema(
        {"undeclaredProduce": 1},
        f"https://sec.example/undeclared-produce-{output}",
        dialect_uri=_DIALECT,
    )
    with pytest.raises(UndeclaredProductionError):
        engine.evaluate(uri, 0, output=output)


@pytest.mark.parametrize("output", ["flag", "hierarchical"])
def test_undeclared_consumption_is_loud_under_every_format(output: str) -> None:
    engine = create_engine()
    engine.dialects.register_vocabulary(_VOCAB, _SECURITY_KEYWORDS)
    engine.dialects.register_dialect(_DIALECT, [_VOCAB])
    uri = engine.register_schema(
        {"undeclaredRead": 1},
        f"https://sec.example/undeclared-read-{output}",
        dialect_uri=_DIALECT,
    )
    with pytest.raises(UndeclaredConsumptionError):
        engine.evaluate(uri, 0, output=output)
