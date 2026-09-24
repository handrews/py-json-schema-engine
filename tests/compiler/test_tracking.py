# Runtime coverage tracking (DESIGN.md D9a, §4 rules 3/4/7; M9): a consumer
# whose coverage is runtime-conditional compiles as a tracked unit whose
# in-place closure produces into a channel, instead of islanding. These
# pins cover what the broad gates under-sample: the classification, the
# channel discipline (a failed branch's productions never cover), islands
# inside a region, and the shapes the TS engine's M6.6 finding named.

from collections.abc import Callable

import pytest

from json_schema_engine.compiler import (
    build_plan,
    compile_validator,
    emit_standalone,
    explain_compilation,
)
from json_schema_engine.compiler.plan import DEFAULT_MAX_DYNAMIC_WINNERS
from json_schema_engine.core import DIALECT_2019_09, JsonValue, create_engine

Case = tuple[JsonValue, list[JsonValue]]
URI = "https://tracking.example/schema"


def _parity(
    schema: JsonValue,
    instances: list[JsonValue],
    dialect: str | None = None,
    *,
    max_dynamic_winners: int = DEFAULT_MAX_DYNAMIC_WINNERS,
) -> Callable[[JsonValue], bool]:
    engine = create_engine(default_dialect=dialect) if dialect else create_engine()
    uri = engine.register_schema(schema, URI)
    fast = compile_validator(
        engine, uri, max_dynamic_winners=max_dynamic_winners
    ).validate
    conservative = compile_validator(
        engine, uri, conservative=True, max_dynamic_winners=max_dynamic_winners
    ).validate
    for instance in instances:
        expected = engine.evaluate(uri, instance).valid
        assert fast(instance) is expected, (instance, expected)
        assert conservative(instance) is expected, (instance, expected, "conservative")
    return fast


def test_classification_tracked_root_and_its_region() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {
            "anyOf": [{"properties": {"a": True}}, {"properties": {"b": True}}],
            "unevaluatedProperties": False,
        },
        URI,
    )
    plan = build_plan(engine, uri)
    root = plan.units[plan.root_key]
    assert root.kind == "static" and root.tracked and not root.in_region
    assert all(plan.units[f"{URI}#/anyOf/{i}"].in_region for i in range(2))
    assert plan.targets == ()
    explanation = explain_compilation(plan)
    assert (explanation.tracked_units, explanation.region_units) == (1, 2)
    source = compile_validator(engine, uri).source
    assert "H_COVN(ev[m0:]" in source
    assert "def validate" in emit_standalone(engine, uri)


def test_a_failed_any_of_branch_never_covers() -> None:
    # The M6.6 finding: static coverage models only the parent-success
    # path. `b` is covered only when the branch declaring it passes.
    validate = _parity(
        {
            "anyOf": [
                {"properties": {"a": {"type": "integer"}}},
                {"properties": {"b": {"type": "string"}}, "required": ["b"]},
            ],
            "unevaluatedProperties": False,
        },
        [{"a": 1}, {"b": "x"}, {"a": 1, "b": 2}, {"a": "no", "b": "x"}, {"c": 1}],
    )
    assert validate({"a": 1, "b": 2}) is False


def test_one_of_with_two_passing_branches_still_fails() -> None:
    _parity(
        {
            "oneOf": [{"properties": {"a": True}}, {"properties": {"b": True}}],
            "unevaluatedProperties": False,
        },
        [{"a": 1}, {"a": 1, "b": 2}, {}],
    )


def test_a_passing_not_subschema_fails_and_a_failing_one_never_covers() -> None:
    _parity(
        {
            "not": {"properties": {"a": {"type": "string"}}, "required": ["a"]},
            "unevaluatedProperties": False,
        },
        [{"a": 1}, {"a": "x"}, {"b": 1}, {}],
    )


def test_a_failing_if_condition_never_covers_and_then_else_do() -> None:
    _parity(
        {
            "if": {"properties": {"a": {"const": 1}}, "required": ["a"]},
            "then": {"properties": {"b": True}},
            "else": {"properties": {"c": True}},
            "unevaluatedProperties": False,
        },
        [
            {"a": 1, "b": 2},
            {"a": 1, "c": 3},
            {"a": 2, "c": 3},
            {"a": 2, "b": 2},
            {"c": 1},
        ],
    )


def test_nested_consumers_in_all_of() -> None:
    _parity(
        {
            "allOf": [
                {
                    "anyOf": [{"properties": {"a": True}}, {"properties": {"b": True}}],
                    "unevaluatedProperties": {"type": "integer"},
                }
            ],
            "unevaluatedProperties": False,
        },
        [{"a": 1}, {"a": 1, "c": 2}, {"a": 1, "c": "x"}, {"d": 1}],
    )


@pytest.mark.parametrize("cap", [0, DEFAULT_MAX_DYNAMIC_WINNERS])
def test_an_island_inside_a_region_contributes_coverage(cap: int) -> None:
    # The `$dynamicRef` has two possible declarers. With specialization off
    # it stays an island reached in place from the tracked root, and its
    # productions must still feed the consumer (through the coverage
    # trampoline); specialized, each clone produces into the channel as
    # ordinary compiled code.
    schema: JsonValue = {
        "$defs": {
            "generic": {
                "$id": "generic",
                "$defs": {"d": {"$dynamicAnchor": "shape", "properties": {"x": True}}},
                "$dynamicRef": "#shape",
            },
            "strict": {
                "$id": "strict",
                "$defs": {"s": {"$dynamicAnchor": "shape", "properties": {"a": True}}},
                "$ref": "generic",
            },
            "loose": {
                "$id": "loose",
                "$defs": {"l": {"$dynamicAnchor": "shape", "properties": {"b": True}}},
                "$ref": "generic",
            },
        },
        "if": {"required": ["strict"]},
        "then": {"$ref": "#/$defs/strict"},
        "else": {"$ref": "#/$defs/loose"},
        "unevaluatedProperties": False,
    }
    engine = create_engine()
    uri = engine.register_schema(schema, URI)
    explanation = explain_compilation(build_plan(engine, uri, max_dynamic_winners=cap))
    source = compile_validator(engine, uri, max_dynamic_winners=cap).source
    if cap == 0:
        assert explanation.causes == {"dynamic": 1}
        assert "H_FRAGC(" in source
    else:
        assert explanation.causes == {}
        assert explanation.specialized_units > 0
        assert "H_FRAGC(" not in source and "H_FRAG(" not in source
    assert explanation.tracked_units == 1
    _parity(
        schema,
        [{"strict": 1, "a": 1}, {"strict": 1, "b": 1}, {"b": 1}, {"a": 1}, {"x": 1}],
        max_dynamic_winners=cap,
    )


def test_contains_matches_feed_unevaluated_items() -> None:
    _parity(
        {
            "anyOf": [{"contains": {"type": "string"}}, {"prefixItems": [True]}],
            "unevaluatedItems": {"type": "integer"},
        },
        [["a", 1], [1, 2], ["a", "b"], [1, "b"], [], [1.5, 2]],
    )


def test_min_contains_zero_produces_nothing_when_nothing_matches() -> None:
    _parity(
        {
            "anyOf": [{"contains": {"type": "string"}, "minContains": 0}],
            "unevaluatedItems": False,
        },
        [[], [1], ["a"], ["a", 1]],
    )


def test_prefix_items_and_items_cover_indexes_conditionally() -> None:
    _parity(
        {
            "anyOf": [
                {"prefixItems": [{"type": "integer"}]},
                {"items": {"type": "string"}},
            ],
            "unevaluatedItems": False,
        },
        [[1], [1, 2], ["a", "b"], ["a", 1], []],
    )


def test_2019_09_recursive_ref_and_additional_items_in_a_region() -> None:
    _parity(
        {
            "anyOf": [
                {"items": [{"type": "integer"}], "additionalItems": {"type": "string"}},
                {"items": [True, True]},
            ],
            "unevaluatedItems": False,
        },
        [[1, "a"], [1, 2], [1, 2, 3], []],
        DIALECT_2019_09,
    )


@pytest.mark.parametrize(
    "instance",
    [{"a": 1}, {"a": 1, "b": "x"}, {"b": "x"}, {"c": 3}, {"a": "no"}],
)
def test_the_fixture_agrees_with_the_interpreter(instance: JsonValue) -> None:
    import json
    from pathlib import Path

    schema = json.loads(
        (
            Path(__file__).parent / "fixtures" / "tracked-consumer.schema.json"
        ).read_text()
    )
    _parity(schema, [instance])
