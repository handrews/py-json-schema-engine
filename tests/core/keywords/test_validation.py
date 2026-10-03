# Tests for the validation, format-annotation, and content vocabularies
# (S8b): `type`, `required`, `pattern` (DESIGN.md D2, D3, P2), the M1
# annotation-only `format`, and `contentMediaType`/`contentEncoding`/
# `contentSchema` (2020-12 §8.5). A dialect assembled from exactly these
# three vocabularies, evaluated with `run_evaluation`, mirroring
# `tests/core/test_evaluator.py`'s pattern.

import json
import re

import pytest

from json_schema_engine.core.dialect import (
    AnalyzeContext,
    CompiledRegex,
    DialectRegistry,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import (
    VOCAB_CONTENT,
    VOCAB_FORMAT_ANNOTATION,
    VOCAB_VALIDATION,
)
from json_schema_engine.core.keywords.content import CONTENT_VOCABULARY, content_schema
from json_schema_engine.core.keywords.format import (
    FORMAT_ANNOTATION_VOCABULARY,
    format_annotation,
)
from json_schema_engine.core.keywords.validation import VALIDATION_VOCABULARY, pattern
from json_schema_engine.core.registry import SchemaRegistry

DIALECT = "urn:test:s8b-dialect"


def make_registry() -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_VALIDATION, VALIDATION_VOCABULARY)
    dialects.register_vocabulary(VOCAB_FORMAT_ANNOTATION, FORMAT_ANNOTATION_VOCABULARY)
    dialects.register_vocabulary(VOCAB_CONTENT, CONTENT_VOCABULARY)
    dialects.register_dialect(
        DIALECT, [VOCAB_VALIDATION, VOCAB_FORMAT_ANNOTATION, VOCAB_CONTENT]
    )
    return SchemaRegistry(dialects, DIALECT)


class _Regex:
    def __init__(self, expr: str) -> None:
        self._compiled = re.compile(expr)

    def search(self, text: str, /) -> bool:
        return self._compiled.search(text) is not None


def _compile_regex(expr: str) -> CompiledRegex:
    return _Regex(expr)


def run(
    schema: JsonValue, instance: JsonValue, *, registry: SchemaRegistry | None = None
) -> tuple[bool, EvalState]:
    reg = registry or make_registry()
    uri = reg.register(schema, "https://s8b.example/schema")
    return run_evaluation(reg, uri, instance, compile_regex=_compile_regex)


# --- type -------------------------------------------------------------

TYPE_NAMES = ["null", "boolean", "object", "array", "number", "string", "integer"]

TYPE_MATRIX: list[tuple[str, JsonValue, frozenset[str]]] = [
    ("null", None, frozenset({"null"})),
    ("true", True, frozenset({"boolean"})),
    ("false", False, frozenset({"boolean"})),
    ("object", {}, frozenset({"object"})),
    ("array", [], frozenset({"array"})),
    ("string", "s", frozenset({"string"})),
    ("int", 3, frozenset({"number", "integer"})),
    ("float_fractional", 3.5, frozenset({"number"})),
    ("float_integral", 3.0, frozenset({"number", "integer"})),
    ("big_int", 10**30, frozenset({"number", "integer"})),
]


@pytest.mark.parametrize(
    ("instance", "expected"),
    [(row[1], row[2]) for row in TYPE_MATRIX],
    ids=[row[0] for row in TYPE_MATRIX],
)
def test_type_matrix(instance: JsonValue, expected: frozenset[str]) -> None:
    for name in TYPE_NAMES:
        valid, state = run({"type": name}, instance)
        if name in expected:
            assert valid
        else:
            assert not valid
            error = state.errors[0]
            assert error.keyword_name == "type"
            actual = _apparent_type_name(instance)
            shown = (
                actual
                if isinstance(instance, list | dict)
                else f"{json.dumps(instance)} ({actual})"
            )
            assert error.message == f"expected {name}, got {shown}"
            assert error.params == {
                "expected": [name],
                "actual": actual,
                "value": instance,
            }


def _apparent_type_name(instance: JsonValue) -> str:
    # Derived independently of the module under test, from the P2 truth
    # table: bool before int, and a mathematical integer reads as one.
    if instance is None:
        return "null"
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, int) or (
        isinstance(instance, float) and instance.is_integer()
    ):
        return "integer"
    if isinstance(instance, float):
        return "number"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, list):
        return "array"
    return "object"


def test_type_array_of_names_matches_any() -> None:
    assert run({"type": ["string", "null"]}, None)[0]
    assert run({"type": ["string", "null"]}, "s")[0]
    valid, state = run({"type": ["string", "null"]}, 5)
    assert not valid
    error = state.errors[0]
    assert error.message == "expected string, null, got 5 (integer)"
    assert error.params == {
        "expected": ["string", "null"],
        "actual": "integer",
        "value": 5,
    }


def test_type_true_never_matches_number_or_integer() -> None:
    assert not run({"type": "number"}, True)[0]
    assert not run({"type": "integer"}, True)[0]
    assert run({"type": "boolean"}, True)[0]


def test_type_analyze_is_absent() -> None:
    assert VALIDATION_VOCABULARY["type"].analyze is None


# --- required ---------------------------------------------------------


def test_required_missing_reports_one_error() -> None:
    valid, state = run({"required": ["a", "b"]}, {"a": 1})
    assert not valid
    assert len(state.errors) == 1
    error = state.errors[0]
    assert error.message == 'missing required property "b"'
    assert error.params == {"missing": ["b"]}
    assert error.keyword_name == "required"


def test_required_all_present_passes() -> None:
    assert run({"required": ["a", "b"]}, {"a": 1, "b": 2})[0]


def test_required_reports_every_missing_name_in_one_error() -> None:
    valid, state = run({"required": ["a", "b", "c"]}, {"b": 1})
    assert not valid
    assert len(state.errors) == 1
    assert state.errors[0].message == 'missing required properties "a", "c"'
    assert state.errors[0].params == {"missing": ["a", "c"]}


def test_required_non_object_instance_is_vacuous() -> None:
    assert run({"required": ["a"]}, "not an object")[0]
    assert run({"required": ["a"]}, 5)[0]
    assert run({"required": ["a"]}, None)[0]
    assert run({"required": ["a"]}, [1, 2])[0]


def test_required_prototype_trap_names_are_ordinary_keys() -> None:
    # Python dicts have no prototype chain (D20, §5): these names are
    # unremarkable dict keys, proven rather than assumed.
    names: list[JsonValue] = ["__proto__", "constructor", "toString"]
    schema: JsonValue = {"required": names}
    valid, state = run(schema, {})
    assert not valid
    assert len(state.errors) == 1
    assert state.errors[0].params == {"missing": names}
    present: JsonValue = {str(n): n for n in names}
    assert run(schema, present)[0]


# --- pattern (EXEMPLAR) ------------------------------------------------


def test_pattern_match_and_mismatch() -> None:
    assert run({"pattern": "^a"}, "abc")[0]
    valid, state = run({"pattern": "^a"}, "xyz")
    assert not valid
    error = state.errors[0]
    assert error.message == 'must match pattern "^a", got "xyz"'
    assert error.params == {"pattern": "^a", "value": "xyz"}
    assert error.keyword_name == "pattern"


def test_pattern_non_string_instance_is_vacuous() -> None:
    assert run({"pattern": "^a"}, 5)[0]
    assert run({"pattern": "^a"}, None)[0]
    assert run({"pattern": "^a"}, [1, 2])[0]
    assert run({"pattern": "^a"}, {"a": 1})[0]


def test_pattern_search_is_unanchored() -> None:
    # "b" is not a prefix of "abc" — an anchored match would reject it.
    assert run({"pattern": "b"}, "abc")[0]
    assert not run({"pattern": "^b"}, "abc")[0]


def test_pattern_analyze_declares_regexes_fact() -> None:
    assert pattern.analyze is not None
    facts = pattern.analyze("^a", AnalyzeContext({}))
    assert facts.regexes == ("^a",)
    facts_non_string = pattern.analyze(5, AnalyzeContext({}))
    assert facts_non_string.regexes == ()


# --- enum (M2) -----------------------------------------------------------


def test_enum_matches_any_candidate_by_json_equal() -> None:
    schema: JsonValue = {"enum": [1, "two", None, [3], {"a": 4}]}
    assert run(schema, 1)[0]
    assert run(schema, "two")[0]
    assert run(schema, None)[0]
    assert run(schema, [3])[0]
    assert run(schema, {"a": 4})[0]
    # json_equal, not identity: 1.0 matches the enumerated 1.
    assert run(schema, 1.0)[0]


def test_enum_no_match_reports_error() -> None:
    valid, state = run({"enum": [1, 2]}, 3)
    assert not valid
    error = state.errors[0]
    assert error.message == "must be one of [1, 2], got 3"
    assert error.params == {"allowedValues": [1, 2], "value": 3}
    assert error.keyword_name == "enum"


def test_enum_bool_does_not_match_numeric_candidate() -> None:
    # P2: bool is never a number, so `1` in the enum does not match `True`.
    assert not run({"enum": [1]}, True)[0]
    assert run({"enum": [True]}, True)[0]


def test_enum_empty_never_matches() -> None:
    assert not run({"enum": []}, "anything")[0]


# --- const (M2) ------------------------------------------------------------


def test_const_matches_via_json_equal() -> None:
    assert run({"const": {"a": [1, 2.0]}}, {"a": [1.0, 2]})[0]
    assert not run({"const": 1}, True)[0]


def test_const_mismatch_reports_error() -> None:
    valid, state = run({"const": 5}, 6)
    assert not valid
    error = state.errors[0]
    assert error.message == "must equal 5, got 6"
    assert error.params == {"allowedValue": 5, "value": 6}
    assert error.keyword_name == "const"


# --- multipleOf (M2) --------------------------------------------------------


def test_multiple_of_matrix() -> None:
    assert run({"multipleOf": 2}, 4)[0]
    assert not run({"multipleOf": 2}, 5)[0]
    assert run({"multipleOf": 0.0001}, 0.0075)[0]
    assert run({"multipleOf": 1}, 10**30)[0]
    assert not run({"multipleOf": 3}, 10**30 + 1)[0]


def test_multiple_of_type_guard_vacuity() -> None:
    assert run({"multipleOf": 2}, "not a number")[0]
    assert run({"multipleOf": 2}, None)[0]
    assert run({"multipleOf": 2}, [1, 2])[0]


def test_multiple_of_excludes_bool() -> None:
    # P2: bool is never a number, on either side of the test.
    assert run({"multipleOf": 1}, True)[0]
    assert run({"multipleOf": True}, 4)[0]


def test_multiple_of_error_params() -> None:
    valid, state = run({"multipleOf": 2}, 5)
    assert not valid
    error = state.errors[0]
    assert error.message == "must be a multiple of 2, got 5"
    assert error.params == {"multipleOf": 2, "value": 5}
    assert error.keyword_name == "multipleOf"


# --- maximum / exclusiveMaximum / minimum / exclusiveMinimum (M2) ----------

NUMERIC_BOUNDS: list[tuple[str, JsonValue, bool]] = [
    ("maximum", 5, True),
    ("maximum", 6, False),
    ("maximum", 4, True),
    ("exclusiveMaximum", 5, False),
    ("exclusiveMaximum", 6, False),
    ("exclusiveMaximum", 4, True),
    ("minimum", 5, True),
    ("minimum", 4, False),
    ("minimum", 6, True),
    ("exclusiveMinimum", 5, False),
    ("exclusiveMinimum", 4, False),
    ("exclusiveMinimum", 6, True),
]


@pytest.mark.parametrize(("keyword", "instance", "expected"), NUMERIC_BOUNDS)
def test_numeric_bounds_matrix(
    keyword: str, instance: JsonValue, expected: bool
) -> None:
    assert run({keyword: 5}, instance)[0] is expected


@pytest.mark.parametrize(
    "keyword", ["maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum"]
)
def test_numeric_bounds_type_guard_vacuity(keyword: str) -> None:
    assert run({keyword: 5}, "not a number")[0]
    assert run({keyword: 5}, None)[0]
    assert run({keyword: 5}, [1])[0]
    assert run({keyword: 5}, {"a": 1})[0]


@pytest.mark.parametrize(
    "keyword", ["maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum"]
)
def test_numeric_bounds_exclude_bool(keyword: str) -> None:
    # P2: bool is never a number, so True/False never trip a numeric bound.
    assert run({keyword: 5}, True)[0]
    assert run({keyword: True}, 5)[0]


def test_numeric_bounds_1_0_vs_1_compare_exactly() -> None:
    assert run({"maximum": 1}, 1.0)[0]
    assert not run({"exclusiveMaximum": 1}, 1.0)[0]
    assert run({"minimum": 1.0}, 1)[0]
    assert not run({"exclusiveMinimum": 1.0}, 1)[0]


@pytest.mark.parametrize(
    ("keyword", "message"),
    [
        ("maximum", "must be <= 5, got 10"),
        ("exclusiveMaximum", "must be < 5, got 10"),
        ("minimum", "must be >= 5, got 0"),
        ("exclusiveMinimum", "must be > 5, got 0"),
    ],
)
def test_numeric_bounds_error_message_and_params(keyword: str, message: str) -> None:
    instance = 10 if keyword in ("maximum", "exclusiveMaximum") else 0
    valid, state = run({keyword: 5}, instance)
    assert not valid
    error = state.errors[0]
    assert error.message == message
    assert error.params == {"limit": 5, "value": instance}
    assert error.keyword_name == keyword


# --- maxLength / minLength (M2) --------------------------------------------


def test_length_bounds_matrix() -> None:
    assert run({"maxLength": 3}, "abc")[0]
    assert not run({"maxLength": 3}, "abcd")[0]
    assert run({"minLength": 3}, "abc")[0]
    assert not run({"minLength": 3}, "ab")[0]


def test_length_bounds_count_code_points_not_code_units() -> None:
    # U+1F600 is one code point, two UTF-16 code units; an implementation
    # that counted units would reject this against maxLength 1.
    assert run({"maxLength": 1}, "\U0001f600")[0]
    assert run({"minLength": 1}, "\U0001f600")[0]


def test_length_bounds_type_guard_vacuity() -> None:
    assert run({"maxLength": 1}, 5)[0]
    assert run({"minLength": 1}, None)[0]
    assert run({"maxLength": 1}, [1, 2, 3])[0]


def test_length_bounds_error_message_and_params() -> None:
    valid, state = run({"maxLength": 3}, "abcd")
    assert not valid
    error = state.errors[0]
    assert error.message == 'must be at most 3 characters, got "abcd" (4)'
    assert error.params == {"limit": 3, "value": "abcd", "length": 4}
    assert error.keyword_name == "maxLength"

    valid, state = run({"minLength": 3}, "ab")
    assert not valid
    error = state.errors[0]
    assert error.message == 'must be at least 3 characters, got "ab" (2)'
    assert error.params == {"limit": 3, "value": "ab", "length": 2}


def test_a_long_instance_is_shown_truncated_but_carried_whole() -> None:
    long = "x" * 200
    valid, state = run({"maxLength": 3}, long)
    assert not valid
    error = state.errors[0]
    assert error.message.startswith('must be at most 3 characters, got "xxx')
    assert "…" in error.message
    assert error.message.endswith("… (200)")
    assert error.params is not None and error.params["value"] == long


def test_a_length_is_counted_in_code_points() -> None:
    valid, state = run({"minLength": 3}, "\U0001f600")
    assert not valid
    assert state.errors[0].message.endswith(" (1)")


def test_enum_and_const_show_values_as_json() -> None:
    valid, state = run({"enum": [True, None, {"a": "b"}]}, False)
    assert not valid
    assert state.errors[0].message == (
        'must be one of [true, null, {"a": "b"}], got false'
    )
    valid, state = run({"const": {"a": [1, 2]}}, [1])
    assert not valid
    assert state.errors[0].message == 'must equal {"a": [1, 2]}, got [1]'


# --- maxItems / minItems (M2) -----------------------------------------------


def test_item_count_bounds_matrix() -> None:
    assert run({"maxItems": 2}, [1, 2])[0]
    assert not run({"maxItems": 2}, [1, 2, 3])[0]
    assert run({"minItems": 2}, [1, 2])[0]
    assert not run({"minItems": 2}, [1])[0]


def test_item_count_bounds_type_guard_vacuity() -> None:
    assert run({"maxItems": 1}, "ab")[0]
    assert run({"minItems": 1}, {"a": 1})[0]
    assert run({"maxItems": 1}, None)[0]


def test_item_count_bounds_error_message_and_params() -> None:
    valid, state = run({"maxItems": 2}, [1, 2, 3])
    assert not valid
    error = state.errors[0]
    assert error.message == "must have at most 2 items, got 3"
    assert error.params == {"limit": 2, "count": 3}
    assert error.keyword_name == "maxItems"


# --- maxProperties / minProperties (M2) -------------------------------------


def test_property_count_bounds_matrix() -> None:
    assert run({"maxProperties": 2}, {"a": 1, "b": 2})[0]
    assert not run({"maxProperties": 2}, {"a": 1, "b": 2, "c": 3})[0]
    assert run({"minProperties": 2}, {"a": 1, "b": 2})[0]
    assert not run({"minProperties": 2}, {"a": 1})[0]


def test_property_count_bounds_type_guard_vacuity() -> None:
    assert run({"maxProperties": 1}, [1, 2])[0]
    assert run({"minProperties": 1}, "ab")[0]
    assert run({"maxProperties": 1}, None)[0]


def test_property_count_bounds_error_message_and_params() -> None:
    valid, state = run({"maxProperties": 2}, {"a": 1, "b": 2, "c": 3})
    assert not valid
    error = state.errors[0]
    assert error.message == "must have at most 2 properties, got 3"
    assert error.params == {"limit": 2, "count": 3}
    assert error.keyword_name == "maxProperties"


# --- uniqueItems (M2) --------------------------------------------------------


def test_unique_items_rejects_1_and_1_0_as_duplicates() -> None:
    # json_equal treats 1 and 1.0 as equal, so uniqueItems must too.
    valid, state = run({"uniqueItems": True}, [1, 1.0])
    assert not valid
    error = state.errors[0]
    assert error.message == "items at 0 and 1 are not unique"
    assert error.params == {"duplicates": [0, 1]}
    assert error.keyword_name == "uniqueItems"


def test_unique_items_accepts_1_and_true_as_distinct() -> None:
    # P2: bool is never a number, so 1 and True are not duplicates.
    assert run({"uniqueItems": True}, [1, True])[0]


def test_unique_items_false_is_inert() -> None:
    assert run({"uniqueItems": False}, [1, 1, 1])[0]


def test_unique_items_non_array_instance_is_vacuous() -> None:
    assert run({"uniqueItems": True}, "not an array")[0]
    assert run({"uniqueItems": True}, None)[0]


def test_unique_items_reports_first_colliding_pair() -> None:
    valid, state = run({"uniqueItems": True}, [1, 2, 1, 2])
    assert not valid
    assert state.errors[0].params == {"duplicates": [0, 2]}


# --- dependentRequired (M2) --------------------------------------------------


def test_dependent_required_all_present_passes() -> None:
    assert run({"dependentRequired": {"a": ["b", "c"]}}, {"a": 1, "b": 2, "c": 3})[0]


def test_dependent_required_trigger_absent_is_vacuous() -> None:
    assert run({"dependentRequired": {"a": ["b"]}}, {"b": 2})[0]
    assert run({"dependentRequired": {"a": ["b"]}}, {})[0]


def test_dependent_required_non_object_instance_is_vacuous() -> None:
    assert run({"dependentRequired": {"a": ["b"]}}, "not an object")[0]
    assert run({"dependentRequired": {"a": ["b"]}}, [1, 2])[0]


def test_dependent_required_reports_every_missing_dependency_in_one_error() -> None:
    schema: JsonValue = {"dependentRequired": {"a": ["b", "c"], "x": ["y"]}}
    valid, state = run(schema, {"a": 1, "x": 1})
    assert not valid
    assert len(state.errors) == 1
    error = state.errors[0]
    assert error.keyword_name == "dependentRequired"
    assert error.params == {"missing": {"a": ["b", "c"], "x": ["y"]}}
    assert error.message == '"a" requires "b", "c"; "x" requires "y"'


# --- minContains / maxContains (inert siblings, M2) --------------------------


def test_min_max_contains_are_registered_but_never_assert_alone() -> None:
    # No `contains` keyword in this schema, so minContains/maxContains have
    # nothing to attach to; they must not fail or annotate on their own.
    valid, state = run({"minContains": 5, "maxContains": 1}, [1, 2])
    assert valid
    assert state.errors == []
    assert state.root_annotations == []


def test_min_max_contains_have_no_analyze() -> None:
    assert VALIDATION_VOCABULARY["minContains"].analyze is None
    assert VALIDATION_VOCABULARY["maxContains"].analyze is None


@pytest.mark.parametrize("instance", [[1, 2], "not an array", None, 0, {}])
def test_min_max_contains_never_fail_regardless_of_instance(
    instance: JsonValue,
) -> None:
    assert run({"minContains": 5, "maxContains": 0}, instance)[0]


# --- format (annotation-only, M1) --------------------------------------


def test_format_annotates_its_own_value() -> None:
    valid, state = run({"format": "date"}, "2020-01-01")
    assert valid
    annotations = [a for a in state.root_annotations if a.keyword_name == "format"]
    assert len(annotations) == 1
    assert annotations[0].value == "date"


def test_format_never_asserts_in_m1() -> None:
    # A value that would violate a real "date" format still passes: M1's
    # `format` is annotation-only, asserting `format` arrives at M7.
    assert run({"format": "date"}, "not-a-date")[0]


def test_annotation_only_format_declares_no_formats_fact() -> None:
    # A `formats` fact means "tested against the engine's table" (M7); the
    # annotation-only behavior tests nothing.
    assert format_annotation.analyze is None
    assert format_annotation.facts("date", {}).formats == ()


# --- content* (annotation-only) -----------------------------------------


def test_content_media_type_and_encoding_annotate() -> None:
    schema: JsonValue = {
        "contentMediaType": "application/json",
        "contentEncoding": "base64",
    }
    valid, state = run(schema, "eyJhIjogMX0=")
    assert valid
    values = {a.keyword_name: a.value for a in state.root_annotations}
    assert values["contentMediaType"] == "application/json"
    assert values["contentEncoding"] == "base64"


def test_content_schema_annotates_and_a_false_subschema_does_not_fail() -> None:
    valid, state = run({"contentSchema": False}, "anything")
    assert valid
    annotation = next(
        a for a in state.root_annotations if a.keyword_name == "contentSchema"
    )
    assert annotation.value is False


def test_content_schema_value_is_walked_for_identifiers_but_never_applied() -> None:
    schema: JsonValue = {"contentSchema": {"$anchor": "inner", "type": "string"}}
    reg = make_registry()
    uri = reg.register(schema, "https://s8b.example/content-schema")
    target = reg.resolve_ref("#inner", uri)
    assert target.node == {"$anchor": "inner", "type": "string"}

    # contentSchema is never applied to the instance: an instance that would
    # violate the inner `type: string` still passes, because the inner
    # schema is only reachable via `resolve_ref`, never `ctx.apply()`.
    valid, state = run(schema, 42)
    assert valid
    assert state.errors == []


def test_content_schema_analyze_declares_empty_relative_subschema() -> None:
    assert content_schema.analyze is not None
    facts = content_schema.analyze({"type": "string"}, AnalyzeContext({}))
    assert facts.subschemas == ((),)
