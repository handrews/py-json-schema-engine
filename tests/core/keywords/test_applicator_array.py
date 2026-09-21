# Tests for the M2 array applicator keywords (DESIGN.md §3, §4 rules 4, 6):
# `prefixItems`, `items`, `contains`. Assembled into a minimal dialect of
# just the array applicator vocabulary — `type`/`const`/`enum` are
# validation-vocabulary concerns (another agent's module), so `contains`'s
# partial-match tests discriminate instance elements structurally: a nested
# `{"items": False}` subschema matches an array element iff that element is
# itself an empty array (`items` never applies to an empty array, so it
# vacuously accepts; it rejects the first element of any non-empty one).
# Mirrors the hand-written-vocabulary pattern in `tests/core/test_evaluator.py`
# and `tests/core/keywords/test_applicator.py`.

from json_schema_engine.core.channel import materialize_path
from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    identifiers_2020,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import DIALECT_2020_12, VOCAB_APPLICATOR
from json_schema_engine.core.keywords.applicator_array import (
    ARRAY_APPLICATOR_VOCABULARY,
    CONTAINS,
    ITEMS,
    PREFIX_ITEMS,
)
from json_schema_engine.core.registry import SchemaRegistry

KEYWORDS: dict[str, KeywordBehavior] = {**ARRAY_APPLICATOR_VOCABULARY}


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
    # `minContains`/`maxContains` are inert siblings this vocabulary reads
    # off `ctx.schema` directly (validation.py owns their own assertions, if
    # any); allow them as unknown keywords here rather than registering them.
    registry = make_registry(allow_unknown=True)
    uri = registry.register(schema, "https://applicator-array.example/schema")
    return run_evaluation(
        registry,
        uri,
        instance,
        compile_regex=_no_regex,  # type: ignore[arg-type]
    )


# --- prefixItems -----------------------------------------------------------


def test_prefix_items_applies_positionally_at_the_right_path() -> None:
    schema: JsonValue = {"prefixItems": [{}, False]}
    valid, state = run(schema, [1, 2, 3])
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/prefixItems/1"
    assert err.cursor.pointer == "/1"


def test_prefix_items_ignores_elements_past_its_own_length() -> None:
    # Fewer subschemas than instance elements: the extra elements are
    # untouched by prefixItems (items/unevaluatedItems would pick them up).
    schema: JsonValue = {"prefixItems": [{}, False]}
    assert run(schema, [1])[0] is True


def test_prefix_items_shorter_than_instance_produces_largest_applied_index() -> None:
    schema: JsonValue = {"prefixItems": [{}, {}]}
    _, state = run(schema, [1, 2, 3])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == PREFIX_ITEMS.id
    ]
    assert produced == [1]


def test_prefix_items_covering_the_whole_array_produces_true() -> None:
    schema: JsonValue = {"prefixItems": [{}, {}, {}]}
    _, state = run(schema, [1, 2])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == PREFIX_ITEMS.id
    ]
    assert produced == [True]


def test_prefix_items_non_array_instance_or_value_passes() -> None:
    schema: JsonValue = {"prefixItems": [False]}
    assert run(schema, "not an array")[0] is True
    assert run(schema, {"a": 1})[0] is True


def test_prefix_items_produces_nothing_when_empty_or_rejecting() -> None:
    schema_empty: JsonValue = {"prefixItems": []}
    _, state = run(schema_empty, [1, 2])
    assert not any(d.behavior_id == PREFIX_ITEMS.id for d in state.root_dependencies)

    schema_fail: JsonValue = {"prefixItems": [False]}
    _, state = run(schema_fail, [1])
    assert not any(d.behavior_id == PREFIX_ITEMS.id for d in state.root_dependencies)


# --- items -------------------------------------------------------------------


def test_items_applies_past_the_sibling_prefix_at_the_right_path() -> None:
    schema: JsonValue = {"prefixItems": [{}], "items": False}
    valid, state = run(schema, [1, 2, 3])
    assert not valid
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/items"
    assert err.cursor.pointer == "/1"


def test_items_applies_to_every_element_without_prefix_items() -> None:
    schema: JsonValue = {"items": False}
    assert run(schema, [1])[0] is False
    assert run(schema, [])[0] is True


def test_items_produces_true_only_when_it_applied() -> None:
    schema: JsonValue = {"prefixItems": [{}], "items": {}}
    _, state = run(schema, [1, 2])
    produced = [d.data for d in state.root_dependencies if d.behavior_id == ITEMS.id]
    assert produced == [True]

    # Nothing past the prefix: items never applies, so it produces nothing.
    _, state = run(schema, [1])
    assert not any(d.behavior_id == ITEMS.id for d in state.root_dependencies)


def test_items_non_array_instance_passes() -> None:
    schema: JsonValue = {"items": False}
    assert run(schema, "not an array")[0] is True


# --- contains ----------------------------------------------------------------


def test_contains_default_requires_at_least_one_match() -> None:
    schema: JsonValue = {"contains": {"items": False}}
    assert run(schema, [[1], [2]])[0] is False
    assert run(schema, [[1], []])[0] is True


def test_contains_min_contains_zero_allows_no_matches() -> None:
    schema: JsonValue = {"contains": {"items": False}, "minContains": 0}
    assert run(schema, [[1], [2]])[0] is True


def test_contains_max_contains_rejects_too_many_matches() -> None:
    schema: JsonValue = {"contains": {"items": False}, "maxContains": 1}
    assert run(schema, [[], [1]])[0] is True
    assert run(schema, [[], []])[0] is False


def test_contains_min_and_max_bound_the_match_count() -> None:
    schema: JsonValue = {
        "contains": {"items": False},
        "minContains": 2,
        "maxContains": 3,
    }
    assert run(schema, [[], [1]])[0] is False  # 1 match: below minContains
    assert run(schema, [[], [], [1]])[0] is True  # 2 matches
    assert run(schema, [[], [], [], [1]])[0] is True  # 3 matches
    assert run(schema, [[], [], [], []])[0] is False  # 4 matches: above maxContains


def test_contains_at_the_right_path() -> None:
    schema: JsonValue = {"contains": {"items": False}}
    valid, state = run(schema, [[1]])
    assert not valid
    # contains itself rejects, so the failing probe's error stays relevant
    # (§4 rule 6) alongside contains' own "no match" error.
    err = state.errors[0]
    assert materialize_path(err.path_node) == "/contains/items"
    assert err.cursor.pointer == "/0/0"
    assert state.errors[-1].message == (
        "0 item(s) match the contains subschema, expected at least 1"
    )


def test_contains_produces_matched_indexes_or_true_when_every_element_matches() -> None:
    schema: JsonValue = {"contains": {"items": False}}
    _, state = run(schema, [[1], [], [2], []])
    produced = [d.data for d in state.root_dependencies if d.behavior_id == CONTAINS.id]
    assert produced == [[1, 3]]

    _, state = run(schema, [[], []])
    produced = [d.data for d in state.root_dependencies if d.behavior_id == CONTAINS.id]
    assert produced == [True]


def test_contains_min_contains_zero_with_no_matches_produces_nothing() -> None:
    schema: JsonValue = {"contains": {"items": False}, "minContains": 0}
    _, state = run(schema, [[1], [2]])
    assert not any(d.behavior_id == CONTAINS.id for d in state.root_dependencies)


def test_contains_error_message_and_params_with_only_max_contains() -> None:
    schema: JsonValue = {"contains": {"items": False}, "maxContains": 1}
    _, state = run(schema, [[], []])
    err = state.errors[0]
    assert err.message == "2 item(s) match the contains subschema, expected 1-1"
    assert err.params == {"count": 2, "minContains": 1, "maxContains": 1}


def test_contains_error_message_and_params_default_unbounded_max() -> None:
    schema: JsonValue = {"contains": {"items": False}, "minContains": 2}
    _, state = run(schema, [[1]])
    err = state.errors[-1]
    assert err.message == "0 item(s) match the contains subschema, expected at least 2"
    assert err.params == {"count": 0, "minContains": 2}


def test_contains_non_array_instance_passes() -> None:
    schema: JsonValue = {"contains": {}}
    assert run(schema, "not an array")[0] is True


# --- vocabulary shape --------------------------------------------------------


def test_array_applicator_vocabulary_contains_exactly_these_keywords() -> None:
    assert set(ARRAY_APPLICATOR_VOCABULARY) == {"prefixItems", "items", "contains"}
    assert ARRAY_APPLICATOR_VOCABULARY["prefixItems"].id == PREFIX_ITEMS.id
    assert ARRAY_APPLICATOR_VOCABULARY["items"].id == ITEMS.id
    assert ARRAY_APPLICATOR_VOCABULARY["contains"].id == CONTAINS.id
