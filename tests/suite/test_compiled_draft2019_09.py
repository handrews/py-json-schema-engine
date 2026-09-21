# The official draft2019-09 suite through the compiled tier (DESIGN.md D12,
# M6): the interpreter leg's parameter sets, verbatim, so the pins are the
# same numbers, evaluated by `compile_validator` in both optimization
# settings. Exception classes must match the interpreter's too.

import pytest

from json_schema_engine.core import DIALECT_2019_09
from json_schema_engine.test_kit import SuiteCase, count_params

from .test_compiled_common import compiled_case
from .test_draft2019_09 import (
    EXPECTED_OPTIONAL_RUN,
    EXPECTED_OPTIONAL_SKIPPED,
    EXPECTED_RUN,
    EXPECTED_SKIPPED,
    OPTIONAL_PARAMS,
    PARAMS,
    REMOTES_DIR,
    RETRIEVAL_URI,
)


@pytest.mark.parametrize("case", PARAMS)
def test_compiled_case(case: SuiteCase) -> None:
    compiled_case(case, DIALECT_2019_09, REMOTES_DIR, RETRIEVAL_URI)


@pytest.mark.parametrize("case", OPTIONAL_PARAMS)
def test_compiled_optional_case(case: SuiteCase) -> None:
    compiled_case(case, DIALECT_2019_09, REMOTES_DIR, RETRIEVAL_URI)


def test_same_pins_as_the_interpreter_leg() -> None:
    assert count_params(PARAMS) == (EXPECTED_RUN, EXPECTED_SKIPPED)
    assert count_params(OPTIONAL_PARAMS) == (
        EXPECTED_OPTIONAL_RUN,
        EXPECTED_OPTIONAL_SKIPPED,
    )
