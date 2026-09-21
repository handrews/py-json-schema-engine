# Tests for M2 object child applicators (DESIGN.md §3, §4 rules 3, 4, 6):
# `patternProperties`, `additionalProperties`, `propertyNames`. `properties`
# is the exemplar already covered by `test_applicator.py`; this module
# assembles its own small dialect (this keyword file's vocabulary only, plus
# one test-local `pattern`-shaped keyword to exercise `propertyNames`'
# name-as-instance semantics without depending on `validation.py`, which
# another M2 agent owns concurrently) and exercises the regex compiler for
# real (`RegexCache`), since three of these keywords compile patterns.

from json_schema_engine.core.channel import materialize_path
from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    DialectRegistry,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
    identifiers_2020,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import DIALECT_2020_12, VOCAB_APPLICATOR
from json_schema_engine.core.keywords.applicator_object import (
    ADDITIONAL_PROPERTIES,
    OBJECT_APPLICATOR_VOCABULARY,
    PATTERN_PROPERTIES,
)
from json_schema_engine.core.regex import RegexCache
from json_schema_engine.core.registry import SchemaRegistry

# A minimal test-local stand-in for the real `pattern` keyword (owned by
# `validation.py`, edited concurrently by another agent): unanchored regex
# match against a string instance. Used only to prove `propertyNames` feeds
# the member name to its subschema as the instance, at the right cursor.


def _test_pattern_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(regexes=(value,) if isinstance(value, str) else ())


def _test_pattern_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    if not isinstance(cursor.value, str) or not isinstance(value, str):
        return True
    if ctx.compile_regex(value).search(cursor.value):
        return True
    ctx.error("does not match pattern")
    return False


_TEST_PATTERN = KeywordBehavior(
    id="test:pattern", evaluate=_test_pattern_evaluate, analyze=_test_pattern_analyze
)

KEYWORDS: dict[str, KeywordBehavior] = {
    **OBJECT_APPLICATOR_VOCABULARY,
    "pattern": _TEST_PATTERN,
}


def make_registry(*, allow_unknown: bool = False) -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_APPLICATOR, KEYWORDS)
    dialects.register_dialect(
        DIALECT_2020_12,
        [VOCAB_APPLICATOR],
        allow_unknown_keywords=allow_unknown,
        identifiers=identifiers_2020,
    )
    return SchemaRegistry(dialects, DIALECT_2020_12)


def run(schema: JsonValue, instance: JsonValue) -> tuple[bool, EvalState]:
    registry = make_registry()
    uri = registry.register(schema, "https://applicator-object.example/schema")
    return run_evaluation(
        registry,
        uri,
        instance,
        compile_regex=RegexCache().compile,
    )


# --- patternProperties -----------------------------------------------------


def test_pattern_properties_applies_to_matching_names_at_the_right_path() -> None:
    schema: JsonValue = {"patternProperties": {"^x": False}}
    valid, state = run(schema, {"xa": 1, "y": 2})
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/patternProperties/^x"
    assert err.cursor.pointer == "/xa"


def test_pattern_properties_matches_by_unanchored_search() -> None:
    # "at$" has no leading anchor, so `search` still finds it anywhere the
    # suffix occurs, proving the match is `search`, not `fullmatch`.
    schema: JsonValue = {"patternProperties": {"at$": False}}
    assert run(schema, {"cat": 1})[0] is False
    assert run(schema, {"dog": 1})[0] is True


def test_pattern_properties_multiple_patterns_matching_one_name_applied_once_each() -> (
    None
):
    # Both patterns match "ab": the subschema for each pattern is applied to
    # it once (two `apply` calls, both accepting here), but the produced name
    # list records "ab" only once.
    schema: JsonValue = {"patternProperties": {"^a": {}, "b$": {}}}
    valid, state = run(schema, {"ab": 1})
    assert valid
    matched = [
        d.data
        for d in state.root_dependencies
        if d.behavior_id == PATTERN_PROPERTIES.id
    ]
    assert matched == [["ab"]]


def test_pattern_properties_non_object_instance_passes() -> None:
    schema: JsonValue = {"patternProperties": {"^x": False}}
    assert run(schema, "not an object")[0] is True
    assert run(schema, [1, 2])[0] is True


def test_pattern_properties_produces_matched_names_only_on_success() -> None:
    schema: JsonValue = {"patternProperties": {"^x": {}}}
    _, state = run(schema, {"xa": 1, "y": 2})
    matched = [
        d.data
        for d in state.root_dependencies
        if d.behavior_id == PATTERN_PROPERTIES.id
    ]
    assert matched == [["xa"]]

    schema_fail: JsonValue = {"patternProperties": {"^x": False}}
    _, state = run(schema_fail, {"xa": 1})
    assert not any(
        d.behavior_id == PATTERN_PROPERTIES.id for d in state.root_dependencies
    )


def test_pattern_properties_produces_names_it_matched() -> None:
    schema: JsonValue = {"patternProperties": {"^x": {}, "^y": {}}}
    _, state = run(schema, {"xa": 1, "yb": 2, "z": 3})
    matched = [
        d.data
        for d in state.root_dependencies
        if d.behavior_id == PATTERN_PROPERTIES.id
    ]
    assert matched == [["xa", "yb"]]


def test_pattern_properties_ecma_property_escape_matches_non_ascii_letters() -> None:
    # \p{L} is an ECMA property escape (DESIGN.md §5): it matches any letter,
    # including non-ASCII ones such as "é". Stdlib `re` alone rejects `\p`,
    # so a pass here proves the ECMA front-end is wired through
    # `ctx.compile_regex`.
    schema: JsonValue = {"patternProperties": {"\\p{L}": False}}
    assert run(schema, {"é": 1})[0] is False
    assert run(schema, {"1": 1})[0] is True


# --- additionalProperties ---------------------------------------------------


def test_additional_properties_skips_properties_names() -> None:
    schema: JsonValue = {
        "properties": {"x": {}},
        "additionalProperties": False,
    }
    assert run(schema, {"x": 1})[0] is True


def test_additional_properties_skips_pattern_properties_matches() -> None:
    schema: JsonValue = {
        "patternProperties": {"^x": {}},
        "additionalProperties": False,
    }
    assert run(schema, {"xa": 1})[0] is True


def test_additional_properties_false_rejects_extras_with_error_at_the_right_path() -> (
    None
):
    schema: JsonValue = {
        "properties": {"x": {}},
        "additionalProperties": False,
    }
    valid, state = run(schema, {"x": 1, "extra": 2})
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/additionalProperties"
    assert err.cursor.pointer == "/extra"


def test_additional_properties_non_object_instance_passes() -> None:
    schema: JsonValue = {"additionalProperties": False}
    assert run(schema, "not an object")[0] is True
    assert run(schema, [1, 2])[0] is True


def test_additional_properties_produces_applied_list() -> None:
    schema: JsonValue = {"properties": {"x": {}}, "additionalProperties": {}}
    _, state = run(schema, {"x": 1, "y": 2, "z": 3})
    produced = [
        d.data
        for d in state.root_dependencies
        if d.behavior_id == ADDITIONAL_PROPERTIES.id
    ]
    assert produced == [["y", "z"]]


def test_additional_properties_produces_empty_list_when_nothing_applied() -> None:
    schema: JsonValue = {"properties": {"x": {}}, "additionalProperties": {}}
    _, state = run(schema, {"x": 1})
    produced = [
        d.data
        for d in state.root_dependencies
        if d.behavior_id == ADDITIONAL_PROPERTIES.id
    ]
    assert produced == [[]]


def test_additional_properties_rejecting_produces_nothing() -> None:
    schema: JsonValue = {"additionalProperties": False}
    _, state = run(schema, {"extra": 1})
    assert not any(
        d.behavior_id == ADDITIONAL_PROPERTIES.id for d in state.root_dependencies
    )


# --- propertyNames -----------------------------------------------------------


def test_property_names_applies_subschema_to_each_name_as_the_instance() -> None:
    schema: JsonValue = {"propertyNames": {"pattern": "^a"}}
    assert run(schema, {"apple": 1, "avocado": 2})[0] is True
    assert run(schema, {"apple": 1, "banana": 2})[0] is False


def test_property_names_false_rejects_every_name_with_error_at_the_right_path() -> None:
    schema: JsonValue = {"propertyNames": False}
    valid, state = run(schema, {"x": 1})
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/propertyNames"
    assert err.cursor.pointer == "/x"


def test_property_names_non_object_instance_passes() -> None:
    schema: JsonValue = {"propertyNames": False}
    assert run(schema, "not an object")[0] is True
    assert run(schema, [1, 2])[0] is True


def test_property_names_empty_object_passes() -> None:
    schema: JsonValue = {"propertyNames": False}
    assert run(schema, {})[0] is True


# --- dialect assembly --------------------------------------------------------


def test_dialect_assembles_object_applicator_vocabulary() -> None:
    assert set(OBJECT_APPLICATOR_VOCABULARY) == {
        "properties",
        "patternProperties",
        "additionalProperties",
        "propertyNames",
    }
