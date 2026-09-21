# The M6 Step 2 differential for this module's keywords: every official
# 2020-12 suite case for `allOf`, `anyOf`, `oneOf`, `not`, `if-then-else`,
# `dependentSchemas`, `ref`, and `refRemote`, evaluated by both the
# interpreter and the compiled validator (both optimization settings),
# verdicts equal. `ref`/`refRemote` are included because these keywords'
# `in_place` applications are exercised through references as much as
# directly.

from pathlib import Path

import pytest

from json_schema_engine.core import create_engine
from json_schema_engine.test_kit import SuiteCase, load_suite_file, suite_remotes_loader

from .test_smoke import assert_parity

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "test-suite" / "tests" / "draft2020-12"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
RETRIEVAL_URI = "https://parity-applicator.example/schema"

SUITE_FILES = [
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if-then-else",
    "dependentSchemas",
    "ref",
    "refRemote",
]


def _cases() -> list[SuiteCase]:
    cases: list[SuiteCase] = []
    for name in SUITE_FILES:
        cases.extend(load_suite_file(SUITE_DIR / f"{name}.json"))
    return cases


@pytest.mark.parametrize(
    "case", _cases(), ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_applicator_suite_parity(case: SuiteCase) -> None:
    engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid
    assert_parity(engine, uri, case.data)
