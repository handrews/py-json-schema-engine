# The official draft7 `optional/format` leg (DESIGN.md M7): every format
# file, asserted through the dialect's standard table on the interpreter and
# on both compiled surfaces (and standalone where the plan is static), with
# exact pins and zero skips.

import pytest

from json_schema_engine.core import DIALECT_DRAFT_07
from json_schema_engine.formats import FORMATS_DRAFT_07
from json_schema_engine.test_kit import SuiteCase, collect_suite_params, count_params

from .test_draft7 import REMOTES_DIR, RETRIEVAL_URI, SUITE_DIR, UNSUPPORTED
from .test_formats_common import formats_case

FILES = sorted(
    f"optional/format/{p.stem}"
    for p in (SUITE_DIR / "optional" / "format").glob("*.json")
)
PARAMS = collect_suite_params(SUITE_DIR, FILES, UNSUPPORTED)
EXPECTED_RUN, EXPECTED_SKIPPED = 785, 0


@pytest.mark.parametrize("case", PARAMS)
def test_format_case(case: SuiteCase) -> None:
    formats_case(case, DIALECT_DRAFT_07, FORMATS_DRAFT_07, REMOTES_DIR, RETRIEVAL_URI)


def test_exact_case_counts() -> None:
    assert count_params(PARAMS) == (EXPECTED_RUN, EXPECTED_SKIPPED)


def test_every_skip_names_an_unimplemented_keyword() -> None:
    for param in PARAMS:
        for mark in param.marks:
            reason = str(mark.kwargs.get("reason", ""))
            assert reason.startswith("uses "), reason
