# Tests for the validation, format-annotation, and content vocabularies
# (S8b): `type`, `required`, `pattern` (DESIGN.md D2, D3, P2), the M1
# annotation-only `format`, and `contentMediaType`/`contentEncoding`/
# `contentSchema` (2020-12 §8.5). A dialect assembled from exactly these
# three vocabularies, evaluated with `run_evaluation`, mirroring
# `tests/core/test_evaluator.py`'s pattern.

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
            assert error.message == f"expected {name}"
            assert error.params == {
                "expected": [name],
                "actual": _actual_type_name(instance),
            }


def _actual_type_name(instance: JsonValue) -> str:
    # Derived independently of the module under test, from the P2 truth
    # table: bool before int, integral-ness is irrelevant to the base type.
    if instance is None:
        return "null"
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, int | float):
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
    assert error.message == "expected string, null"
    assert error.params == {"expected": ["string", "null"], "actual": "number"}


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
    assert error.message == "missing required property 'b'"
    assert error.params == {"missingProperty": "b"}
    assert error.keyword_name == "required"


def test_required_all_present_passes() -> None:
    assert run({"required": ["a", "b"]}, {"a": 1, "b": 2})[0]


def test_required_reports_one_error_per_missing_name_in_order() -> None:
    valid, state = run({"required": ["a", "b", "c"]}, {})
    assert not valid
    assert [e.params["missingProperty"] for e in state.errors if e.params] == [
        "a",
        "b",
        "c",
    ]


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
    assert [e.params["missingProperty"] for e in state.errors if e.params] == names
    present: JsonValue = {str(n): n for n in names}
    assert run(schema, present)[0]


# --- pattern (EXEMPLAR) ------------------------------------------------


def test_pattern_match_and_mismatch() -> None:
    assert run({"pattern": "^a"}, "abc")[0]
    valid, state = run({"pattern": "^a"}, "xyz")
    assert not valid
    error = state.errors[0]
    assert error.message == "does not match pattern"
    assert error.params == {"pattern": "^a"}
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


def test_format_declares_formats_fact() -> None:
    assert format_annotation.analyze is not None
    facts = format_annotation.analyze("date", AnalyzeContext({}))
    assert facts.formats == ("date",)
    facts_non_string = format_annotation.analyze(5, AnalyzeContext({}))
    assert facts_non_string.formats == ()


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
