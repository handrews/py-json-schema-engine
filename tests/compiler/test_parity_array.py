# M6 Step 2 differential: the official suite's array-keyword coverage,
# across every dialect this step lowers, run through the interpreter and
# the compiled validator (both optimization settings via `assert_parity`).
# Mirrors `test_smoke.py`'s suite-subset pattern, but spans dialects rather
# than sticking to 2020-12.

from pathlib import Path

import pytest

from json_schema_engine.core import create_engine
from json_schema_engine.core.keywords._ids import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
)
from json_schema_engine.test_kit import SuiteCase, load_suite_file, suite_remotes_loader

from .test_smoke import assert_parity

ROOT = Path(__file__).resolve().parents[2]
SUITE_ROOT = ROOT / "test-suite" / "tests"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
RETRIEVAL_URI = "https://parity-array.example/schema"


def _cases(dialect_dir: str, files: list[str]) -> list[SuiteCase]:
    cases: list[SuiteCase] = []
    for name in files:
        cases.extend(load_suite_file(SUITE_ROOT / dialect_dir / f"{name}.json"))
    return cases


CASES_2020_12 = _cases(
    "draft2020-12",
    ["prefixItems", "items", "contains", "minContains", "maxContains"],
)
CASES_2019_09 = _cases("draft2019-09", ["items", "additionalItems", "contains"])
CASES_DRAFT_07 = _cases(
    "draft7", ["items", "additionalItems", "dependencies", "contains"]
)
CASES_DRAFT_06 = _cases(
    "draft6", ["items", "additionalItems", "dependencies", "contains"]
)


def _run(default_dialect: str, case: SuiteCase) -> None:
    engine = create_engine(
        default_dialect=default_dialect, loaders=[suite_remotes_loader(REMOTES_DIR)]
    )
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid
    assert_parity(engine, uri, case.data)


@pytest.mark.parametrize(
    "case", CASES_2020_12, ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_2020_12_array_suite_parity(case: SuiteCase) -> None:
    _run(DIALECT_2020_12, case)


@pytest.mark.parametrize(
    "case", CASES_2019_09, ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_2019_09_array_suite_parity(case: SuiteCase) -> None:
    _run(DIALECT_2019_09, case)


@pytest.mark.parametrize(
    "case", CASES_DRAFT_07, ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_draft_07_array_suite_parity(case: SuiteCase) -> None:
    _run(DIALECT_DRAFT_07, case)


@pytest.mark.parametrize(
    "case", CASES_DRAFT_06, ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_draft_06_array_suite_parity(case: SuiteCase) -> None:
    _run(DIALECT_DRAFT_06, case)
