# Per-context specialization of path-dependent dynamic sites (DESIGN.md D8):
# an anchor whose site resolves differently by path is split, and the units
# below its declarers are cloned per first declarer, so every clone's site
# is a static edge. Pins the plan shape on the extensible recursive type
# (a base `tree` re-declared by each extension), clone identity, verdict
# and whole-`Result` parity with the interpreter, standalone emission, the
# 2019-09 analogue, the stale-decision regression, coverage licensing
# through a split in-place site, the cap, and the evaluator plan.

from collections.abc import Callable
from typing import cast

import pytest

from json_schema_engine.compiler import (
    SplitAnchor,
    build_plan,
    compile_evaluator,
    compile_validator,
    emit_standalone,
    explain_compilation,
)
from json_schema_engine.compiler.plan import (
    CompilationPlan,
    PlannedUnit,
    build_plan_over,
)
from json_schema_engine.core import DIALECT_2019_09, Engine, JsonValue, create_engine

from .dynamic_seeds import (
    EXTENSIBLE_TREE,
    EXTENSIBLE_TREE_RECURSIVE,
    EXTENSIBLE_TREE_TESTS,
    GENERIC_LIST,
    STALE_DECISION,
    STALE_DECISION_TESTS,
)

BASE = "https://specialize.example"
URI = f"{BASE}/schema"
TAXONOMY = f"{BASE}/taxonomyTree"
PHYLOGENY = f"{BASE}/phylogenyTree"

type Validator = Callable[[JsonValue], bool]


def _engine(schema: JsonValue, dialect: str | None = None) -> tuple[Engine, str]:
    engine = create_engine(default_dialect=dialect) if dialect else create_engine()
    return engine, engine.register_schema(schema, URI)


def _by_location(plan: CompilationPlan) -> dict[str, list[PlannedUnit]]:
    by_location: dict[str, list[PlannedUnit]] = {}
    for unit in plan.units.values():
        by_location.setdefault(unit.ref.location, []).append(unit)
    return by_location


def _assert_tree_plan(plan: CompilationPlan, kind: str, anchor: str) -> None:
    assert plan.targets == ()
    assert plan.split_anchors == (SplitAnchor(kind, anchor, (PHYLOGENY, TAXONOMY)),)  # type: ignore[arg-type]
    explanation = explain_compilation(plan)
    assert explanation.causes == {} and explanation.reaches_interpreted == 0
    by_location = _by_location(plan)
    # Every unit of the base `tree` exists once per extension, and the
    # clones share one `SchemaRef` (records render the same location).
    tree_locations = [loc for loc in by_location if loc.startswith(f"{BASE}/tree#")]
    assert tree_locations
    for location in tree_locations:
        clones = by_location[location]
        assert {clone.context for clone in clones} == {
            ((kind, anchor, PHYLOGENY),),  # type: ignore[comparison-overlap]
            ((kind, anchor, TAXONOMY),),
        }, location
        assert len({id(clone.ref) for clone in clones}) == 1
    # Only the root resource's units carry no context.
    unspecialized = [unit for unit in plan.units.values() if not unit.context]
    assert {unit.ref.location.split("#", 1)[0] for unit in unspecialized} == {URI}
    assert explanation.specialized_units == explanation.total_units - len(unspecialized)
    # Each clone's site resolves to the extension its context names.
    site = f"{BASE}/tree#/properties/children/items"
    for clone in by_location[site]:
        (edge,) = clone.edges
        winner = clone.context[0][2]
        assert edge.dynamic is not None and edge.dynamic.winner == winner
        assert plan.units[edge.target_key].ref.location == f"{winner}#"
    assert {
        (s.location, s.target_location) for s in explanation.resolved_dynamic_sites
    } == {
        (site, f"{PHYLOGENY}#"),
        (site, f"{TAXONOMY}#"),
    }


def test_extensible_tree_plans_one_clone_per_extension() -> None:
    engine, uri = _engine(EXTENSIBLE_TREE)
    _assert_tree_plan(build_plan(engine, uri), "dynamic", "tree")


def test_recursive_extensible_tree_plans_one_clone_per_extension() -> None:
    engine, uri = _engine(EXTENSIBLE_TREE_RECURSIVE, DIALECT_2019_09)
    _assert_tree_plan(build_plan(engine, uri), "recursive", "$recursiveAnchor")


DEEP_TAXONOMY: JsonValue = {
    "taxonomy": {
        "rank": "Class",
        "name": "Echinoidea",
        "children": [
            {
                "rank": "Order",
                "children": [
                    {"rank": "Family", "children": [{"rank": "genus", "name": "g"}]},
                    {"rank": "Family", "children": [{"name": "missing rank"}]},
                ],
            }
        ],
    }
}
DEEP_PHYLOGENY: JsonValue = {
    "phylogeny": {
        "support": 1,
        "children": [
            {"support": 0.7, "children": [{"name": "leaf"}, {"rank": "stray"}]},
            {"children": [{"support": "high"}]},
        ],
    }
}
INSTANCES: tuple[JsonValue, ...] = (
    *(instance for instance, _ in EXTENSIBLE_TREE_TESTS),
    DEEP_TAXONOMY,
    DEEP_PHYLOGENY,
    {"taxonomy": 1},
    {},
)


@pytest.mark.parametrize(
    ("schema", "dialect"),
    [(EXTENSIBLE_TREE, None), (EXTENSIBLE_TREE_RECURSIVE, DIALECT_2019_09)],
    ids=["2020-12", "2019-09"],
)
def test_every_surface_agrees_with_the_interpreter(
    schema: JsonValue, dialect: str | None
) -> None:
    engine, uri = _engine(schema, dialect)
    fast = compile_validator(engine, uri).validate
    conservative = compile_validator(engine, uri, conservative=True).validate
    evaluator = compile_evaluator(engine, uri, annotations=True).evaluate
    namespace: dict[str, object] = {}
    exec(compile(emit_standalone(engine, uri), "<standalone>", "exec"), namespace)
    standalone = cast(Validator, namespace["validate"])
    for instance in INSTANCES:
        expected = engine.evaluate(uri, instance).valid
        assert fast(instance) is expected, instance
        assert conservative(instance) is expected, (instance, "conservative")
        assert standalone(instance) is expected, (instance, "standalone")
        # Clones report their shared location: the records, errors, and
        # trace equal the interpreter's, output format by output format.
        for output in ("list", "hierarchical"):
            want = engine.evaluate(
                uri,
                instance,
                output=output,
                annotations=True,
                error_params=True,
                trace=True,
            )
            got = evaluator(instance, output=output, error_params=True, trace=True)
            assert got == want, (instance, output)
    for instance, valid in EXTENSIBLE_TREE_TESTS:
        assert fast(instance) is valid, instance


def test_stale_decision_is_re_derived() -> None:
    # `r1#/$defs/u` is resolved with winner `r1` in the first round; the
    # second round plans `r2#/$defs/y`, which reaches it with `r2` already in
    # scope. The decision must be revisited, not kept.
    engine, uri = _engine(STALE_DECISION)
    plan = build_plan(engine, uri)
    assert plan.split_anchors == (
        SplitAnchor("dynamic", "x", (f"{BASE}/r1", f"{BASE}/r2")),
    )
    assert plan.targets == ()
    validate = compile_validator(engine, uri).validate
    for instance, valid in STALE_DECISION_TESTS:
        assert engine.evaluate(uri, instance).valid is valid, instance
        assert validate(instance) is valid, instance
    # With specialization off the site islands instead of keeping the stale
    # single-winner decision.
    islanded = build_plan(engine, uri, max_dynamic_winners=0)
    assert explain_compilation(islanded).causes == {"dynamic": 1}
    validate = compile_validator(engine, uri, max_dynamic_winners=0).validate
    for instance, valid in STALE_DECISION_TESTS:
        assert validate(instance) is valid, instance


SHAPES: JsonValue = {
    "$defs": {
        "generic": {
            "$id": "generic",
            "$defs": {"d": {"$dynamicAnchor": "shape", "properties": {"x": True}}},
            "allOf": [{"$dynamicRef": "#shape"}],
            "unevaluatedProperties": False,
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
    "properties": {"s": {"$ref": "strict"}, "l": {"$ref": "loose"}},
}


def test_coverage_is_licensed_per_clone_through_a_split_in_place_site() -> None:
    # `generic`'s consumer sees its `allOf` contributor through a split
    # `$dynamicRef`: each clone's static coverage names the extension's
    # property, and neither clone needs runtime tracking.
    engine, uri = _engine(SHAPES)
    plan = build_plan(engine, uri)
    explanation = explain_compilation(plan)
    assert explanation.causes == {} and explanation.tracked_units == 0
    clones = {
        unit.context[0][2]: unit
        for unit in plan.units.values()
        if unit.ref.location == f"{BASE}/generic#"
    }
    assert set(clones) == {f"{BASE}/strict", f"{BASE}/loose"}
    for winner, unit in clones.items():
        assert unit.coverage is not None and not unit.tracked
        assert unit.coverage.names == frozenset(
            {"a" if winner.endswith("strict") else "b"}
        )
    fast = compile_validator(engine, uri).validate
    conservative = compile_validator(engine, uri, conservative=True).validate
    cases: list[tuple[JsonValue, bool]] = [
        ({"s": {"a": 1}}, True),
        ({"s": {"b": 1}}, False),
        ({"s": {"x": 1}}, False),
        ({"l": {"b": 1}}, True),
        ({"l": {"a": 1}}, False),
        ({"s": {"a": 1}, "l": {"b": 2}}, True),
    ]
    for instance, valid in cases:
        assert engine.evaluate(uri, instance).valid is valid, instance
        assert fast(instance) is valid, instance
        assert conservative(instance) is valid, (instance, "conservative")


def test_the_cap_ladder() -> None:
    engine, uri = _engine(GENERIC_LIST)
    for cap in (0, 1):
        explanation = explain_compilation(
            build_plan(engine, uri, max_dynamic_winners=cap)
        )
        assert explanation.causes == {"dynamic": 1}, cap
        assert explanation.split_anchors == ()
    explanation = explain_compilation(build_plan(engine, uri, max_dynamic_winners=2))
    assert explanation.causes == {}
    assert [(a.kind, a.anchor) for a in explanation.split_anchors] == [
        ("dynamic", "item")
    ]
    with pytest.raises(ValueError, match="max_dynamic_winners"):
        build_plan(engine, uri, max_dynamic_winners=-1)
    with pytest.raises(ValueError, match="max_dynamic_winners"):
        compile_validator(engine, uri, max_dynamic_winners=-1)


def test_the_evaluator_plan_tracks_each_extension_clone() -> None:
    engine, uri = _engine(EXTENSIBLE_TREE)
    plan = build_plan_over(engine.schemas, uri, track_all=True)
    explanation = explain_compilation(plan)
    assert explanation.interpreted_units == 0
    assert plan.split_anchors == (
        SplitAnchor("dynamic", "tree", (PHYLOGENY, TAXONOMY)),
    )
    extensions = [
        unit
        for unit in plan.units.values()
        if unit.ref.location in (f"{TAXONOMY}#", f"{PHYLOGENY}#")
    ]
    assert len(extensions) == 2 and all(unit.tracked for unit in extensions)
