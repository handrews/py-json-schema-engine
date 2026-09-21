# The official draft2020-12 `optional/format` leg (DESIGN.md M7): every format
# file, asserted through the dialect's standard table on the interpreter and
# on both compiled surfaces (and standalone where the plan is static), with
# exact pins and zero skips.

import pytest

from json_schema_engine.core import DIALECT_2020_12, FormatsRequiredError, create_engine
from json_schema_engine.formats import FORMATS_2020_12
from json_schema_engine.test_kit import (
    SuiteCase,
    collect_suite_params,
    count_params,
    suite_remotes_loader,
)

from .test_draft2020_12 import REMOTES_DIR, RETRIEVAL_URI, SUITE_DIR, UNSUPPORTED
from .test_formats_common import formats_case

FILES = sorted(
    f"optional/format/{p.stem}"
    for p in (SUITE_DIR / "optional" / "format").glob("*.json")
)
PARAMS = collect_suite_params(SUITE_DIR, FILES, UNSUPPORTED)
EXPECTED_RUN, EXPECTED_SKIPPED = 866, 0


@pytest.mark.parametrize("case", PARAMS)
def test_format_case(case: SuiteCase) -> None:
    formats_case(case, DIALECT_2020_12, FORMATS_2020_12, REMOTES_DIR, RETRIEVAL_URI)


def test_exact_case_counts() -> None:
    assert count_params(PARAMS) == (EXPECTED_RUN, EXPECTED_SKIPPED)


def test_every_skip_names_an_unimplemented_keyword() -> None:
    for param in PARAMS:
        for mark in param.marks:
            reason = str(mark.kwargs.get("reason", ""))
            assert reason.startswith("uses "), reason


# `optional/format-assertion.json`: the vocabulary asserts under both
# metaschemas with a table given and no `assert_formats`.
ASSERTION_PARAMS = collect_suite_params(
    SUITE_DIR, ["optional/format-assertion"], UNSUPPORTED
)
EXPECTED_ASSERTION_RUN, EXPECTED_ASSERTION_SKIPPED = 4, 0


@pytest.mark.parametrize("case", ASSERTION_PARAMS)
def test_format_assertion_case(case: SuiteCase) -> None:
    formats_case(
        case,
        DIALECT_2020_12,
        FORMATS_2020_12,
        REMOTES_DIR,
        RETRIEVAL_URI,
        assert_formats=False,
    )


@pytest.mark.parametrize("case", ASSERTION_PARAMS)
def test_format_assertion_requires_a_table(case: SuiteCase) -> None:
    engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    with pytest.raises(FormatsRequiredError, match="formats="):
        engine.load_schema(case.schema, RETRIEVAL_URI)


def test_format_assertion_counts() -> None:
    assert count_params(ASSERTION_PARAMS) == (
        EXPECTED_ASSERTION_RUN,
        EXPECTED_ASSERTION_SKIPPED,
    )
