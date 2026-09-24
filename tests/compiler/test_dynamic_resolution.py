# Plan-time resolution of `$dynamicRef`/`$recursiveRef` (DESIGN.md D8; M9,
# after the TS engine's ADR 0004, plus per-context specialization). Three
# legs: the seed corpus's pinned classifications with verdict parity on
# every surface; every official suite group holding a dynamic reference,
# where the target the planner chose must be the target the interpreter
# applied (observed through the trace), under the default cap and with
# specialization off; and the two measured schemas (OpenAPI 3.1, the
# 2020-12 metaschema as root) planning with no interpreted unit.

import json
from pathlib import Path

import pytest

from json_schema_engine.compiler import (
    build_plan,
    compile_validator,
    emit_standalone,
    explain_compilation,
)
from json_schema_engine.compiler.plan import DEFAULT_MAX_DYNAMIC_WINNERS
from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    Engine,
    JsonSchemaEngineError,
    JsonValue,
    TraceUnit,
    create_engine,
)
from json_schema_engine.test_kit import SuiteCase, load_suite_file, suite_remotes_loader

from .dynamic_seeds import DYNAMIC_SEEDS, DynamicSeed

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "test-suite" / "tests"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
OAS_SCHEMA = (
    ROOT / "packages/bench/src/json_schema_engine/bench/corpora/oas-3.1-schema.json"
)
METASCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"

# Suite groups whose site's target differs by path: islands with
# specialization off, specialized per declarer under the default cap.
PATH_DEPENDENT_GROUPS = {
    "draft2020-12": {"multiple dynamic paths to the $dynamicRef keyword"},
    "draft2019-09": {
        "multiple dynamic paths to the $recursiveRef keyword",
        "dynamic $recursiveRef destination (not predictable at schema compile time)",
    },
}
DYNAMIC_KEYWORDS = {"draft2020-12": "$dynamicRef", "draft2019-09": "$recursiveRef"}
MIN_GROUPS = {"draft2020-12": 15, "draft2019-09": 10}
MIN_RESOLVED = {"draft2020-12": 15, "draft2019-09": 8}
DIALECTS = {"draft2020-12": DIALECT_2020_12, "draft2019-09": DIALECT_2019_09}
CAPS = [DEFAULT_MAX_DYNAMIC_WINNERS, 0]


# --- leg 1: the seed corpus --------------------------------------------------


@pytest.mark.parametrize("seed", DYNAMIC_SEEDS, ids=lambda s: s.key)
def test_seed_classification_and_parity(seed: DynamicSeed) -> None:
    engine = create_engine(default_dialect=seed.dialect)
    uri = engine.register_schema(seed.schema, f"https://seeds.example/{seed.key}")
    cap = seed.max_dynamic_winners
    explanation = explain_compilation(build_plan(engine, uri, max_dynamic_winners=cap))
    if seed.classification == "island":
        assert explanation.causes.get("dynamic", 0) >= 1, explanation.causes
        assert explanation.split_anchors == ()
    else:
        assert explanation.interpreted_units == 0, explanation.interpreted_keys
        assert explanation.resolved_dynamic_sites
        assert "def validate" in emit_standalone(engine, uri, max_dynamic_winners=cap)
        if seed.classification == "static":
            assert explanation.split_anchors == ()
            assert explanation.specialized_units == 0
        else:
            assert explanation.split_anchors, seed.key
            assert explanation.specialized_units > 0
    fast = compile_validator(engine, uri, max_dynamic_winners=cap).validate
    conservative = compile_validator(
        engine, uri, conservative=True, max_dynamic_winners=cap
    ).validate
    for instance, valid in seed.tests:
        assert engine.evaluate(uri, instance).valid is valid, (seed.key, instance)
        assert fast(instance) is valid, (seed.key, instance)
        assert conservative(instance) is valid, (seed.key, instance, "conservative")


# --- leg 2: the official suite ------------------------------------------------


def _dynamic_groups(directory: str) -> list[tuple[str, list[SuiteCase]]]:
    keyword = DYNAMIC_KEYWORDS[directory]
    files = [
        f"{keyword[1:]}.json",
        "unevaluatedItems.json",
        "unevaluatedProperties.json",
    ]
    groups: dict[str, list[SuiteCase]] = {}
    for name in files:
        for case in load_suite_file(SUITE / directory / name):
            if keyword in json.dumps(case.schema):
                groups.setdefault(f"{name}/{case.group}", []).append(case)
    return sorted(groups.items())


def _observed_resolutions(
    engine: Engine, uri: str, keyword: str, instances: list[JsonValue]
) -> dict[str, set[str]]:
    """For every application of `keyword` the interpreter performed, the
    site's schema location → the set of targets it applied."""
    seen: dict[str, set[str]] = {}

    def walk(node: TraceUnit) -> None:
        for child in node["children"]:
            if child["segments"] and child["segments"][0] == keyword:
                seen.setdefault(node["schemaLocation"], set()).add(
                    child["schemaLocation"]
                )
            walk(child)

    for instance in instances:
        try:
            result = engine.evaluate(uri, instance, output="list", trace=True)
        except JsonSchemaEngineError:
            continue  # depth and loop cases belong to the verdict legs
        assert result.trace is not None
        walk(result.trace)
    return seen


@pytest.mark.parametrize("cap", CAPS)
@pytest.mark.parametrize("directory", sorted(DIALECTS))
def test_suite_groups_resolve_to_the_interpreters_target(
    directory: str, cap: int
) -> None:
    keyword = DYNAMIC_KEYWORDS[directory]
    groups = _dynamic_groups(directory)
    assert len(groups) >= MIN_GROUPS[directory], len(groups)
    islands: set[str] = set()
    specialized: set[str] = set()
    resolved_total = 0
    for key, cases in groups:
        engine = create_engine(
            default_dialect=DIALECTS[directory],
            loaders=[suite_remotes_loader(REMOTES_DIR)],
        )
        uri = engine.load_schema(cases[0].schema, "https://suite.example/schema")
        explanation = explain_compilation(
            build_plan(engine, uri, max_dynamic_winners=cap)
        )
        if explanation.causes.get("dynamic"):
            islands.add(cases[0].group)
        if explanation.split_anchors:
            specialized.add(cases[0].group)
        resolved_total += len(explanation.resolved_dynamic_sites)
        observed = _observed_resolutions(
            engine, uri, keyword, [case.data for case in cases]
        )
        # Clones of one location share its trace node: the planner's
        # targets, taken together, must be exactly what the interpreter
        # applied there.
        planned: dict[str, set[str]] = {}
        for site in explanation.resolved_dynamic_sites:
            planned.setdefault(site.location, set()).add(site.target_location)
        for location, targets in planned.items():
            applied = observed.get(location)
            if applied is None:
                continue  # the instances never reached this site
            assert applied <= targets, (key, location, applied, targets)
            if len(targets) == 1:
                assert applied == targets, (key, location)
        validate = compile_validator(engine, uri, max_dynamic_winners=cap).validate
        for case in cases:
            assert validate(case.data) is case.valid, (key, case.description)
    if cap == 0:
        assert islands == PATH_DEPENDENT_GROUPS[directory]
        assert specialized == set()
    else:
        assert islands == set()
        assert specialized == PATH_DEPENDENT_GROUPS[directory]
    assert resolved_total >= MIN_RESOLVED[directory], resolved_total


# --- leg 3: the measured schemas --------------------------------------------


def test_openapi_schema_compiles_with_no_interpreted_unit() -> None:
    schema = json.loads(OAS_SCHEMA.read_text())
    engine = create_engine()
    uri = engine.register_schema(schema, schema["$id"])
    explanation = explain_compilation(build_plan(engine, uri))
    assert explanation.interpreted_units == 0, explanation.interpreted_keys
    assert explanation.split_anchors == ()
    assert len(explanation.resolved_dynamic_sites) == 4
    assert {site.winner for site in explanation.resolved_dynamic_sites} == {
        schema["$id"]
    }
    # The root's `anyOf` beside `unevaluatedProperties` is tracked at runtime.
    assert explanation.tracked_units >= 1 and explanation.region_units >= 1
    assert "def validate" in emit_standalone(engine, uri)


def test_metaschema_as_root_resolves_every_site() -> None:
    engine = create_engine()
    explanation = explain_compilation(build_plan(engine, METASCHEMA_2020_12))
    assert explanation.interpreted_units == 0, explanation.interpreted_keys
    assert explanation.split_anchors == ()
    assert len(explanation.resolved_dynamic_sites) > 10
    assert {site.winner for site in explanation.resolved_dynamic_sites} == {
        METASCHEMA_2020_12
    }
    wrapper = create_engine()
    uri = wrapper.register_schema(
        {"$ref": METASCHEMA_2020_12}, "https://seeds.example/wrapper"
    )
    wrapped = explain_compilation(build_plan(wrapper, uri))
    assert wrapped.interpreted_units == 0
    assert len(wrapped.resolved_dynamic_sites) == len(
        explanation.resolved_dynamic_sites
    )
    assert "def validate" in emit_standalone(wrapper, uri)
