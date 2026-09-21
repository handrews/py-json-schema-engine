# M6 Step 2 parity: every official-suite case for the validation vocabulary
# keywords this module lowers, run through `assert_parity` (interpreter vs
# compiled, both optimization settings). Mirrors `test_smoke.py`'s
# suite-subset pattern; every case here must pass outright (no skips).

from pathlib import Path

import pytest

from json_schema_engine.core import Engine, create_engine
from json_schema_engine.test_kit import SuiteCase, load_suite_file, suite_remotes_loader

from .test_smoke import RETRIEVAL_URI, assert_parity

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "test-suite" / "tests" / "draft2020-12"
REMOTES_DIR = ROOT / "test-suite" / "remotes"

SUBSET_FILES = [
    "type",
    "enum",
    "const",
    "multipleOf",
    "maximum",
    "exclusiveMaximum",
    "minimum",
    "exclusiveMinimum",
    "maxLength",
    "minLength",
    "maxItems",
    "minItems",
    "maxProperties",
    "minProperties",
    "uniqueItems",
    "required",
    "pattern",
    "dependentRequired",
    "minContains",
    "maxContains",
]


def _subset_cases() -> list[SuiteCase]:
    cases: list[SuiteCase] = []
    for name in SUBSET_FILES:
        cases.extend(load_suite_file(SUITE_DIR / f"{name}.json"))
    return cases


@pytest.mark.parametrize(
    "case", _subset_cases(), ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_suite_subset_parity(case: SuiteCase) -> None:
    engine: Engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid
    assert_parity(engine, uri, case.data)
