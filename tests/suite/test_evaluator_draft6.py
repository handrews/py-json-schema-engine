# The official draft6 suite through the compiled evaluator (DESIGN.md D12,
# M9): the interpreter leg's parameter sets, verbatim, so the pins are the
# same numbers; every non-flag output of `compile_evaluator` must equal the
# interpreter's in both optimization settings, exception classes included.

import pytest

from json_schema_engine.core import DIALECT_DRAFT_06
from json_schema_engine.test_kit import SuiteCase, count_params

from .test_draft6 import (
    EXPECTED_OPTIONAL_RUN,
    EXPECTED_OPTIONAL_SKIPPED,
    EXPECTED_RUN,
    EXPECTED_SKIPPED,
    OPTIONAL_PARAMS,
    PARAMS,
    REMOTES_DIR,
    RETRIEVAL_URI,
)
from .test_evaluator_common import evaluator_case


@pytest.mark.parametrize("case", PARAMS)
def test_evaluator_case(case: SuiteCase) -> None:
    evaluator_case(case, DIALECT_DRAFT_06, REMOTES_DIR, RETRIEVAL_URI)


@pytest.mark.parametrize("case", OPTIONAL_PARAMS)
def test_evaluator_optional_case(case: SuiteCase) -> None:
    evaluator_case(case, DIALECT_DRAFT_06, REMOTES_DIR, RETRIEVAL_URI)


def test_same_pins_as_the_interpreter_leg() -> None:
    assert count_params(PARAMS) == (EXPECTED_RUN, EXPECTED_SKIPPED)
    assert count_params(OPTIONAL_PARAMS) == (
        EXPECTED_OPTIONAL_RUN,
        EXPECTED_OPTIONAL_SKIPPED,
    )
