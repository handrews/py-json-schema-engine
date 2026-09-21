# M6 Step 2 parity: the official suite's `properties`, `patternProperties`,
# `additionalProperties`, `propertyNames`, `unevaluatedProperties`, and
# `unevaluatedItems` groups (2020-12), plus the 2019-09 `unevaluated*`
# groups (their own id space and consumer set), through the same
# interpreter/compiled differential `test_smoke.py` uses. Also: a static
# consumer plans static and emits a `for` sweep when the planner licenses
# static coverage, and a dynamically-contributed coverage falls back to the
# interpreter (`cause == "unlowerable"`), per D9a/M6.

from pathlib import Path

import pytest

from json_schema_engine.compiler import compile_validator
from json_schema_engine.core import DIALECT_2019_09, create_engine
from json_schema_engine.test_kit import SuiteCase, load_suite_file, suite_remotes_loader

from .test_smoke import assert_parity

ROOT = Path(__file__).resolve().parents[2]
SUITE_2020_12 = ROOT / "test-suite" / "tests" / "draft2020-12"
SUITE_2019_09 = ROOT / "test-suite" / "tests" / "draft2019-09"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
RETRIEVAL_URI = "https://parity-object.example/schema"

FILES_2020_12 = [
    "properties",
    "patternProperties",
    "additionalProperties",
    "propertyNames",
    "unevaluatedProperties",
    "unevaluatedItems",
]
FILES_2019_09 = ["unevaluatedProperties", "unevaluatedItems"]


def _cases(suite_dir: Path, files: list[str]) -> list[SuiteCase]:
    cases: list[SuiteCase] = []
    for name in files:
        cases.extend(load_suite_file(suite_dir / f"{name}.json"))
    return cases


@pytest.mark.parametrize(
    "case",
    _cases(SUITE_2020_12, FILES_2020_12),
    ids=lambda c: f"{c.file}/{c.group}/{c.description}",
)
def test_suite_2020_12_parity(case: SuiteCase) -> None:
    engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid
    assert_parity(engine, uri, case.data)


@pytest.mark.parametrize(
    "case",
    _cases(SUITE_2019_09, FILES_2019_09),
    ids=lambda c: f"{c.file}/{c.group}/{c.description}",
)
def test_suite_2019_09_parity(case: SuiteCase) -> None:
    engine = create_engine(
        default_dialect=DIALECT_2019_09, loaders=[suite_remotes_loader(REMOTES_DIR)]
    )
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid
    assert_parity(engine, uri, case.data)


# --- static vs. dynamic coverage licensing -----------------------------------


def test_static_name_coverage_plans_static_and_emits_a_sweep() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"properties": {"a": True}, "unevaluatedProperties": False},
        "https://parity-object.example/static-coverage",
    )
    compiled = compile_validator(engine, uri)
    root = compiled.plan.units[compiled.plan.root_key]
    assert root.kind == "static"
    assert root.coverage is not None
    assert root.coverage.names == frozenset({"a"})
    assert "for " in compiled.source


def test_dynamic_contributor_falls_back_to_interpreted() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        {"anyOf": [{"properties": {"a": True}}], "unevaluatedProperties": False},
        "https://parity-object.example/dynamic-coverage",
    )
    compiled = compile_validator(engine, uri)
    root = compiled.plan.units[compiled.plan.root_key]
    assert root.kind == "interpreted"
    assert root.cause == "unlowerable"
