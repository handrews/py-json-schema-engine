# The planner (DESIGN.md D1, D8, D9): fallback causes, consumer licensing,
# in-place cycle islanding, `reaches_interpreted`, `use_count`, and the
# explanation projection.

import pytest

from json_schema_engine.compiler import build_plan, explain_compilation
from json_schema_engine.core import DIALECT_DRAFT_07, JsonValue, create_engine


def plan_for(schema: JsonValue, dialect: str | None = None):
    engine = (
        create_engine() if dialect is None else create_engine(default_dialect=dialect)
    )
    uri = engine.register_schema(schema, "https://plan.example/s")
    return build_plan(engine, uri), uri


def test_static_root_with_child_edges() -> None:
    plan, uri = plan_for({"properties": {"a": {"type": "string"}}, "required": ["a"]})
    root = plan.units[plan.root_key]
    assert plan.root_key == uri + "#"
    assert root.kind == "static"
    assert [(e.keyword, e.app.mode, e.target_key) for e in root.edges] == [
        ("properties", "child_by_key", uri + "#/properties/a")
    ]
    child = plan.units[uri + "#/properties/a"]
    assert child.use_count == 1 and not child.reaches_interpreted
    assert plan.targets == ()
    assert explain_compilation(plan).causes == {}


def test_dynamic_ref_islands_the_unit_and_marks_reachers() -> None:
    plan, uri = plan_for(
        {
            "properties": {"p": {"$dynamicRef": "#node"}},
            "$defs": {"node": {"$dynamicAnchor": "node", "type": "string"}},
        }
    )
    island = plan.units[uri + "#/properties/p"]
    assert island.kind == "interpreted" and island.cause == "dynamic"
    assert plan.units[plan.root_key].reaches_interpreted
    assert [t.key for t in plan.targets] == [island.key]


def test_unlowerable_keyword_islands() -> None:
    engine = create_engine()
    # A custom keyword without `lower` in an extension vocabulary.
    from json_schema_engine.core.dialect import KeywordBehavior

    engine.dialects.register_vocabulary(
        "urn:x:vocab",
        {"x-custom": KeywordBehavior("urn:x:custom", lambda v, c, ctx: True)},
    )
    engine.dialects.register_dialect(
        "urn:x:dialect",
        [
            *engine.dialects.get_dialect(
                "https://json-schema.org/draft/2020-12/schema"
            ).vocabulary_uris,
            "urn:x:vocab",
        ],
    )
    uri = engine.register_schema(
        {"properties": {"a": {"x-custom": 1}}},
        "https://plan.example/s",
        "urn:x:dialect",
    )
    plan = build_plan(engine, uri)
    assert plan.units[uri + "#/properties/a"].cause == "unlowerable"
    assert plan.units[plan.root_key].kind == "static"


def test_unresolvable_ref_islands_lazily() -> None:
    plan, uri = plan_for(
        {"properties": {"a": {"$ref": "https://plan.example/missing"}}}
    )
    assert plan.units[uri + "#/properties/a"].cause == "unlowerable"
    assert plan.units[plan.root_key].kind == "static"


def test_in_place_cycle_islands_the_target() -> None:
    plan, _ = plan_for({"$ref": "#"})
    root = plan.units[plan.root_key]
    assert root.kind == "interpreted" and root.cause == "cycle"
    plan, _ = plan_for(
        {"allOf": [{"$ref": "#/$defs/a"}], "$defs": {"a": {"$ref": "#"}}}
    )
    assert plan.units[plan.root_key].cause == "cycle"
    # Child-cursor recursion is not a cycle.
    plan, _ = plan_for({"properties": {"next": {"$ref": "#"}}})
    assert plan.units[plan.root_key].kind == "static"
    assert plan.units[plan.root_key].use_count == 1


def test_ref_into_data_is_a_non_schema_unit() -> None:
    plan, uri = plan_for(
        {"x-data": {"n": 5}, "properties": {"a": {"$ref": "#/x-data/n"}}}
    )
    assert plan.units[uri + "#/x-data/n"].cause == "non_schema"


@pytest.mark.xfail(strict=True, reason="unevaluated* lowering lands in Step 2")
def test_consumer_licensing_needs_static_coverage() -> None:
    licensed, _ = plan_for({"properties": {"a": True}, "unevaluatedProperties": False})
    root = licensed.units[licensed.root_key]
    assert root.kind == "static"
    assert root.coverage is not None and root.coverage.names == frozenset({"a"})
    # Through an unconditional in-place application too.
    via_all_of, _ = plan_for(
        {"allOf": [{"properties": {"b": True}}], "unevaluatedProperties": False}
    )
    coverage = via_all_of.units[via_all_of.root_key].coverage
    assert coverage is not None and coverage.names == frozenset({"b"})
    # A conditional contributor makes coverage dynamic: interpreted in M6.
    unlicensed, _ = plan_for(
        {"anyOf": [{"properties": {"b": True}}], "unevaluatedProperties": False}
    )
    assert unlicensed.units[unlicensed.root_key].cause == "unlowerable"


def test_draft7_ref_ignores_siblings_in_the_plan() -> None:
    plan, _ = plan_for(
        {
            "$ref": "#/definitions/a",
            "properties": {"x": True},
            "definitions": {"a": {}},
        },
        DIALECT_DRAFT_07,
    )
    root = plan.units[plan.root_key]
    assert [e.keyword for e in root.edges] == ["$ref"]


def test_explanation_counts() -> None:
    plan, _ = plan_for(
        {
            "properties": {"p": {"$dynamicRef": "#node"}, "q": {"$ref": "#/q"}},
            "$defs": {"node": {"$dynamicAnchor": "node"}},
        }
    )
    explanation = explain_compilation(plan)
    assert explanation.total_units == 3
    assert explanation.static_units == 1
    assert explanation.causes == {"dynamic": 1, "unlowerable": 1}
    assert explanation.reaches_interpreted == 1
