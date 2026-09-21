# Tests for the M1 applicator/unevaluated keywords (DESIGN.md §3 exemplars,
# §4 rules 3, 4, 6, 7): `properties`, `anyOf`, `allOf`, `unevaluatedProperties`
# assembled into a real dialect (no `type`/`required` — those land in M2, so
# failures are forced with boolean subschemas and `properties`-only shapes).
# Mirrors the hand-written-vocabulary pattern in `tests/core/test_evaluator.py`.

from json_schema_engine.core.channel import materialize_path
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    identifiers_2020,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import DIALECT_2020_12, VOCAB_APPLICATOR
from json_schema_engine.core.keywords.applicator import (
    ALL_OF,
    ANY_OF,
    APPLICATOR_VOCABULARY,
)
from json_schema_engine.core.keywords.applicator_object import (
    OBJECT_APPLICATOR_VOCABULARY,
    PROPERTIES,
)
from json_schema_engine.core.keywords.unevaluated import (
    UNEVALUATED_PROPERTIES,
    UNEVALUATED_VOCABULARY,
)
from json_schema_engine.core.registry import SchemaRegistry

KEYWORDS: dict[str, KeywordBehavior] = {
    **APPLICATOR_VOCABULARY,
    **OBJECT_APPLICATOR_VOCABULARY,
    **UNEVALUATED_VOCABULARY,
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


def _no_regex(_pattern: str) -> object:
    raise AssertionError("no keyword under test compiles a regex")


def run(schema: JsonValue, instance: JsonValue) -> tuple[bool, EvalState]:
    registry = make_registry()
    uri = registry.register(schema, "https://applicator.example/schema")
    return run_evaluation(
        registry,
        uri,
        instance,
        compile_regex=_no_regex,  # type: ignore[arg-type]
    )


# --- properties (EXEMPLAR: child applicator) ------------------------------


def test_properties_applies_matching_children_at_the_right_path() -> None:
    # No annotating keyword in this vocabulary, so path/location are proven
    # through a failing child subschema and its error's paths instead.
    schema: JsonValue = {"properties": {"x": False}}
    valid, state = run(schema, {"x": 1, "y": 2})
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/properties/x"
    assert err.cursor.pointer == "/x"


def test_properties_skips_absent_names() -> None:
    schema: JsonValue = {"properties": {"x": False}}
    assert run(schema, {"y": 2})[0] is True


def test_properties_non_object_instance_passes() -> None:
    schema: JsonValue = {"properties": {"x": False}}
    assert run(schema, "not an object")[0] is True
    assert run(schema, [1, 2])[0] is True


def test_properties_produces_matched_names_only_on_success() -> None:
    schema: JsonValue = {
        "allOf": [{"properties": {"x": {}, "y": {}}}],
        "unevaluatedProperties": False,
    }
    _, state = run(schema, {"x": 1, "y": 2})
    matched = [
        d.data for d in state.root_dependencies if d.behavior_id == PROPERTIES.id
    ]
    assert matched == [["x", "y"]]

    # A rejecting `properties` produces nothing (§4 rule 6).
    schema_fail: JsonValue = {"properties": {"x": False, "y": {}}}
    _, state = run(schema_fail, {"x": 1, "y": 2})
    assert not any(d.behavior_id == PROPERTIES.id for d in state.root_dependencies)


# --- anyOf (EXEMPLAR: in-place applicator) --------------------------------


def test_any_of_runs_every_branch_and_drops_the_failed_branchs_error() -> None:
    schema: JsonValue = {"anyOf": [{"properties": {"x": False}}, {}]}
    valid, state = run(schema, {"x": 1})
    assert valid
    assert state.errors == []


def test_any_of_all_failing_reports_branch_errors_plus_its_own() -> None:
    schema: JsonValue = {
        "anyOf": [{"properties": {"x": False}}, {"properties": {"x": False}}]
    }
    valid, state = run(schema, {"x": 1})
    assert not valid
    messages = [e.message for e in state.errors]
    assert messages == [
        "schema is false",
        "schema is false",
        "does not match any anyOf branch",
    ]
    assert state.errors[-1].keyword_name == "anyOf"


# --- allOf -----------------------------------------------------------------


def test_all_of_requires_every_branch() -> None:
    schema: JsonValue = {
        "allOf": [{"properties": {"x": {}}}, {"properties": {"x": False}}]
    }
    valid, state = run(schema, {"x": 1})
    assert not valid
    # allOf contributes no message of its own (mirrors the TS convention).
    assert [e.message for e in state.errors] == ["schema is false"]
    assert not any(e.keyword_name == "allOf" for e in state.errors)


def test_all_of_passes_when_every_branch_passes() -> None:
    schema: JsonValue = {"allOf": [{"properties": {"x": {}}}, {}]}
    assert run(schema, {"x": 1})[0] is True


# --- unevaluatedProperties (EXEMPLAR: consumer) ---------------------------


def test_unevaluated_properties_false_rejects_extra_and_accepts_none() -> None:
    schema: JsonValue = {"properties": {"x": {}}, "unevaluatedProperties": False}
    assert run(schema, {"x": 1, "y": 2})[0] is False
    assert run(schema, {"x": 1})[0] is True


def test_unevaluated_properties_ignores_names_from_a_failed_anyof_branch() -> None:
    # TS channels test: annotations/dependency data from a failed branch must
    # not mark properties evaluated.
    schema: JsonValue = {
        "anyOf": [
            {"properties": {"x": {}}},
            {"properties": {"y": {}}, "allOf": [False]},
        ],
        "unevaluatedProperties": False,
    }
    assert run(schema, {"x": 1, "y": 2})[0] is False
    assert run(schema, {"x": 1})[0] is True


def test_unevaluated_properties_merges_coverage_across_all_of() -> None:
    schema: JsonValue = {
        "allOf": [{"properties": {"x": {}}}, {"properties": {"y": {}}}],
        "unevaluatedProperties": False,
    }
    assert run(schema, {"x": 1, "y": 2})[0] is True
    assert run(schema, {"x": 1, "y": 2, "z": 3})[0] is False


def test_unevaluated_properties_cousin_invisibility() -> None:
    schema: JsonValue = {
        "properties": {"a": {"properties": {"b": {}}}},
        "unevaluatedProperties": False,
    }
    # "b" is evaluated only inside "a"'s own subschema; at the root, "b" was
    # never a member, and "c" is unevaluated at the root.
    assert run(schema, {"a": {"b": 1}, "c": 2})[0] is False
    assert run(schema, {"a": {"b": 1}})[0] is True


def test_unevaluated_properties_subschema_applies_at_the_right_path() -> None:
    schema: JsonValue = {"unevaluatedProperties": {"properties": {"x": False}}}
    valid, state = run(schema, {"extra": {"x": 1}})
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/unevaluatedProperties/properties/x"
    assert err.cursor.pointer == "/extra/x"


def test_unevaluated_properties_dependency_data_shape() -> None:
    schema: JsonValue = {"properties": {"x": {}}, "unevaluatedProperties": {}}
    _, state = run(schema, {"x": 1, "y": 2, "z": 3})
    unevaluated = [
        d.data
        for d in state.root_dependencies
        if d.behavior_id == UNEVALUATED_PROPERTIES.id
    ]
    assert unevaluated == [["y", "z"]]


def test_unevaluated_properties_non_object_instance_passes() -> None:
    schema: JsonValue = {"unevaluatedProperties": False}
    assert run(schema, [1, 2, 3])[0] is True
    assert run(schema, "string")[0] is True


def test_dialect_assembles_from_applicator_and_unevaluated_vocabularies_only() -> None:
    assert set(APPLICATOR_VOCABULARY) == {"anyOf", "allOf"}
    assert set(OBJECT_APPLICATOR_VOCABULARY) == {"properties"}
    assert set(UNEVALUATED_VOCABULARY) == {"unevaluatedProperties"}
    assert APPLICATOR_VOCABULARY["anyOf"].id == ANY_OF.id
    assert APPLICATOR_VOCABULARY["allOf"].id == ALL_OF.id
