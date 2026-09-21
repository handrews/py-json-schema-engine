# Tests for the M4 legacy keywords shared by 2019-09 and draft-07/06
# (DESIGN.md D11, §3, §4 rules 4/6): `items` (2019-09's folded
# prefixItems+items), `additionalItems`, and `dependencies` (draft-07/06's
# folded dependentRequired+dependentSchemas). Assembled into minimal
# dialects of just this module's keywords, mirroring
# `tests/core/keywords/test_applicator_array.py`.

from json_schema_engine.core.channel import materialize_path
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    identifiers_2020,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import (
    DIALECT_2019_09,
    VOCAB_APPLICATOR_2019,
    keyword_id,
)
from json_schema_engine.core.keywords.applicator_array import CONTAINS_ID
from json_schema_engine.core.keywords.legacy import (
    ADDITIONAL_ITEMS,
    ADDITIONAL_ITEMS_ID,
    DEPENDENCIES,
    DEPENDENCIES_VOCABULARY,
    ITEMS_LEGACY,
    ITEMS_LEGACY_ID,
    LEGACY_ARRAY_VOCABULARY,
)
from json_schema_engine.core.keywords.unevaluated import unevaluated_items
from json_schema_engine.core.registry import SchemaRegistry

KEYWORDS: dict[str, KeywordBehavior] = {
    **LEGACY_ARRAY_VOCABULARY,
    **DEPENDENCIES_VOCABULARY,
}


def make_registry(*, allow_unknown: bool = False) -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_APPLICATOR_2019, KEYWORDS)
    dialects.register_dialect(
        DIALECT_2019_09,
        [VOCAB_APPLICATOR_2019],
        allow_unknown_keywords=allow_unknown,
        identifiers=identifiers_2020,
    )
    return SchemaRegistry(dialects, DIALECT_2019_09)


def _no_regex(_pattern: str) -> object:
    raise AssertionError("no keyword under test compiles a regex")


def run(schema: JsonValue, instance: JsonValue) -> tuple[bool, EvalState]:
    registry = make_registry()
    uri = registry.register(schema, "https://legacy.example/schema")
    return run_evaluation(
        registry,
        uri,
        instance,
        compile_regex=_no_regex,  # type: ignore[arg-type]
    )


# --- items: tuple form (folds prefixItems) --------------------------------


def test_items_tuple_applies_positionally_at_the_right_path() -> None:
    schema: JsonValue = {"items": [{}, False]}
    valid, state = run(schema, [1, 2, 3])
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/items/1"
    assert err.cursor.pointer == "/1"


def test_items_tuple_ignores_elements_past_its_own_length() -> None:
    schema: JsonValue = {"items": [{}, False]}
    assert run(schema, [1])[0] is True


def test_items_tuple_shorter_than_instance_produces_largest_applied_index() -> None:
    schema: JsonValue = {"items": [{}, {}]}
    _, state = run(schema, [1, 2, 3])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == ITEMS_LEGACY.id
    ]
    assert produced == [1]


def test_items_tuple_covering_the_whole_array_produces_true() -> None:
    schema: JsonValue = {"items": [{}, {}, {}]}
    _, state = run(schema, [1, 2])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == ITEMS_LEGACY.id
    ]
    assert produced == [True]


def test_items_tuple_longer_than_instance_passes_and_produces_true() -> None:
    schema: JsonValue = {"items": [{}, {}, {}]}
    valid, state = run(schema, [1])
    assert valid
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == ITEMS_LEGACY.id
    ]
    assert produced == [True]


def test_items_tuple_produces_nothing_when_empty_or_rejecting() -> None:
    schema_empty: JsonValue = {"items": []}
    _, state = run(schema_empty, [1, 2])
    assert not any(d.behavior_id == ITEMS_LEGACY.id for d in state.root_dependencies)

    schema_fail: JsonValue = {"items": [False]}
    _, state = run(schema_fail, [1])
    assert not any(d.behavior_id == ITEMS_LEGACY.id for d in state.root_dependencies)


def test_items_non_array_instance_or_non_schema_value_passes() -> None:
    schema: JsonValue = {"items": [False]}
    assert run(schema, "not an array")[0] is True
    # A member that is neither a list nor a schema value: analyze() gives it
    # no facts, and evaluate() falls through to a no-op rather than crashing.
    assert run({"items": 5}, [1])[0] is True


# --- items: schema form (folds 2020-12's `items`) -------------------------


def test_items_schema_form_applies_to_every_element() -> None:
    schema: JsonValue = {"items": False}
    assert run(schema, [1])[0] is False
    assert run(schema, [])[0] is True


def test_items_schema_form_applies_at_the_right_path() -> None:
    schema: JsonValue = {"items": False}
    valid, state = run(schema, [1])
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/items"
    assert err.cursor.pointer == "/0"


def test_items_schema_form_produces_true_only_when_it_applied() -> None:
    schema: JsonValue = {"items": {}}
    _, state = run(schema, [1, 2])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == ITEMS_LEGACY.id
    ]
    assert produced == [True]

    _, state = run(schema, [])
    assert not any(d.behavior_id == ITEMS_LEGACY.id for d in state.root_dependencies)


# --- additionalItems -------------------------------------------------------


def test_additional_items_with_tuple_items_applies_from_index_len() -> None:
    schema: JsonValue = {"items": [{}, {}], "additionalItems": False}
    assert run(schema, [1, 2, 3])[0] is False
    assert run(schema, [1, 2])[0] is True


def test_additional_items_applies_at_the_right_path() -> None:
    schema: JsonValue = {"items": [{}], "additionalItems": False}
    valid, state = run(schema, [1, 2])
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/additionalItems"
    assert err.cursor.pointer == "/1"


def test_additional_items_produces_true_only_when_it_applied() -> None:
    schema: JsonValue = {"items": [{}], "additionalItems": {}}
    _, state = run(schema, [1, 2, 3])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == ADDITIONAL_ITEMS.id
    ]
    assert produced == [True]

    _, state = run(schema, [1])
    assert not any(
        d.behavior_id == ADDITIONAL_ITEMS.id for d in state.root_dependencies
    )


def test_additional_items_inert_with_schema_form_items() -> None:
    schema: JsonValue = {"items": {}, "additionalItems": False}
    valid, state = run(schema, [1, 2, 3])
    assert valid
    assert not any(
        d.behavior_id == ADDITIONAL_ITEMS.id for d in state.root_dependencies
    )


def test_additional_items_inert_with_no_items_sibling() -> None:
    schema: JsonValue = {"additionalItems": False}
    valid, state = run(schema, [1, 2, 3])
    assert valid
    assert not any(
        d.behavior_id == ADDITIONAL_ITEMS.id for d in state.root_dependencies
    )


# --- dependencies: array form (folds dependentRequired) -------------------


def test_dependencies_array_form_present_triggers_and_absent_does_not() -> None:
    schema: JsonValue = {"dependencies": {"a": ["b", "c"]}}
    assert run(schema, {"a": 1, "b": 1, "c": 1})[0] is True
    assert run(schema, {"a": 1})[0] is False
    assert run(schema, {"x": 1})[0] is True


def test_dependencies_array_form_multiple_missing_reports_in_order() -> None:
    schema: JsonValue = {"dependencies": {"a": ["b", "c"]}}
    _, state = run(schema, {"a": 1})
    assert [e.message for e in state.errors] == [
        "'a' requires 'b' to be present",
        "'a' requires 'c' to be present",
    ]
    assert [e.params for e in state.errors] == [
        {"property": "a", "missingProperty": "b"},
        {"property": "a", "missingProperty": "c"},
    ]


def test_dependencies_non_object_instance_passes() -> None:
    schema: JsonValue = {"dependencies": {"a": ["b"]}}
    assert run(schema, [1, 2])[0] is True
    assert run(schema, "a string")[0] is True


# --- dependencies: schema form (folds dependentSchemas) --------------------


def test_dependencies_schema_form_applies_in_place_at_the_same_cursor() -> None:
    # A nested `dependencies` inside the applied subschema still sees the
    # *same* instance object (in-place application, not a child cursor) —
    # proof that records from the applied subschema merge at the outer
    # cursor rather than a descended one.
    schema: JsonValue = {"dependencies": {"a": {"dependencies": {"x": ["y"]}}}}
    valid, state = run(schema, {"a": 1, "x": 1})
    assert not valid
    err = state.errors[0]
    assert err.cursor.pointer == ""
    assert err.message == "'x' requires 'y' to be present"


def test_dependencies_boolean_subschema_form() -> None:
    schema_false: JsonValue = {"dependencies": {"a": False}}
    assert run(schema_false, {"a": 1})[0] is False
    assert run(schema_false, {"b": 1})[0] is True

    schema_true: JsonValue = {"dependencies": {"a": True}}
    assert run(schema_true, {"a": 1})[0] is True


def test_dependencies_escaped_names() -> None:
    schema: JsonValue = {"dependencies": {"foo\nbar": ['foo"bar']}}
    assert run(schema, {"foo\nbar": 1, 'foo"bar': 1})[0] is True
    valid, state = run(schema, {"foo\nbar": 1})
    assert not valid
    assert state.errors[0].params == {
        "property": "foo\nbar",
        "missingProperty": 'foo"bar',
    }


def test_dependencies_mixed_map_of_array_and_schema_members() -> None:
    schema: JsonValue = {
        "dependencies": {"a": ["b"], "c": {"dependencies": {}}},
    }
    assert run(schema, {"a": 1, "b": 1, "c": 1})[0] is True
    assert run(schema, {"a": 1, "c": 1})[0] is False  # "a" requires missing "b"
    assert run(schema, {"c": 1})[0] is True  # "a" absent; "c"'s subschema is empty


# --- vocabulary shape --------------------------------------------------------


def test_legacy_vocabularies_contain_exactly_these_keywords() -> None:
    assert set(LEGACY_ARRAY_VOCABULARY) == {"items", "additionalItems"}
    assert LEGACY_ARRAY_VOCABULARY["items"].id == ITEMS_LEGACY_ID
    assert LEGACY_ARRAY_VOCABULARY["additionalItems"].id == ADDITIONAL_ITEMS_ID
    assert set(DEPENDENCIES_VOCABULARY) == {"dependencies"}
    assert DEPENDENCIES_VOCABULARY["dependencies"].id == DEPENDENCIES.id


# --- fold: 2019-09 unevaluatedItems over items/additionalItems -------------
#
# `core/keywords/unevaluated.py` now exposes a
# `unevaluated_items(behavior_id, consumes, prefix_producer_id, contains_id)`
# factory built for this fold; build the 2019-09 consumer with it directly
# rather than hand-rolling one.

UNEVALUATED_ITEMS_LEGACY_ID = keyword_id(VOCAB_APPLICATOR_2019, "unevaluatedItems")

UNEVALUATED_ITEMS_LEGACY = unevaluated_items(
    UNEVALUATED_ITEMS_LEGACY_ID,
    (ITEMS_LEGACY_ID, ADDITIONAL_ITEMS_ID, CONTAINS_ID, UNEVALUATED_ITEMS_LEGACY_ID),
    ITEMS_LEGACY_ID,
)

FOLD_KEYWORDS: dict[str, KeywordBehavior] = {
    **LEGACY_ARRAY_VOCABULARY,
    "unevaluatedItems": UNEVALUATED_ITEMS_LEGACY,
}


def make_fold_registry() -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_APPLICATOR_2019, FOLD_KEYWORDS)
    dialects.register_dialect(
        DIALECT_2019_09,
        [VOCAB_APPLICATOR_2019],
        allow_unknown_keywords=False,
        identifiers=identifiers_2020,
    )
    return SchemaRegistry(dialects, DIALECT_2019_09)


def run_fold(schema: JsonValue, instance: JsonValue) -> tuple[bool, EvalState]:
    registry = make_fold_registry()
    uri = registry.register(schema, "https://legacy-unevaluated.example/schema")
    return run_evaluation(
        registry,
        uri,
        instance,
        compile_regex=_no_regex,  # type: ignore[arg-type]
    )


def test_unevaluated_items_fold_accepts_a_fully_covered_array() -> None:
    schema: JsonValue = {
        "items": [{}],
        "additionalItems": {},
        "unevaluatedItems": False,
    }
    assert run_fold(schema, [1, 2, 3])[0] is True


def test_unevaluated_items_fold_rejects_an_uncovered_element() -> None:
    schema: JsonValue = {"items": [{}], "unevaluatedItems": False}
    assert run_fold(schema, [1, 2, 3])[0] is False
