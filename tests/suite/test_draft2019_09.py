# The official draft2019-09 suite leg (DESIGN.md D12, §6 done-signals).
# Groups whose schemas use a keyword the dialect does not bind yet are
# skipped by the schema-position scan and counted; the exact-count pins make
# a submodule bump or a keyword landing a deliberate two-number edit.

from pathlib import Path

import pytest

from json_schema_engine.core import DIALECT_2019_09, create_engine
from json_schema_engine.test_kit import (
    SuiteCase,
    collect_suite_params,
    count_params,
    suite_remotes_loader,
)

from .keyword_census import ALL_2019_09

SUITE_ROOT = Path(__file__).resolve().parents[2] / "test-suite"
SUITE_DIR = SUITE_ROOT / "tests" / "draft2019-09"
REMOTES_DIR = SUITE_ROOT / "remotes"
RETRIEVAL_URI = "https://suite.example/schema"

# Every top-level draft2019-09 file. Each case builds an engine with the
# suite's remotes loader and loads the schema, as the TS engine does; the
# loader is inert for the many cases that reference nothing remote.
FILES = sorted(p.stem for p in SUITE_DIR.glob("*.json"))

# Optional files the engine passes today; the rest wait for later
# milestones (`content`/`bignum`/`float-overflow`/`ecmascript-regex`/
# `non-bmp-regex`/`format/*` per the 2020-12 leg's own reasons;
# `dependencies-compatibility` tests the legacy `dependencies` keyword,
# which 2019-09 does not define at all — it was replaced by
# `dependentSchemas`/`dependentRequired` — so there is nothing to implement
# here, only a keyword this dialect never binds).
OPTIONAL_FILES = [
    "optional/anchor",
    "optional/id",
    "optional/no-schema",
    "optional/unknownKeyword",
    "optional/refOfUnknownKeyword",
    "optional/cross-draft",
]

IMPLEMENTED = frozenset(create_engine().dialects.get_dialect(DIALECT_2019_09).keywords)
UNSUPPORTED = ALL_2019_09 - IMPLEMENTED

PARAMS = collect_suite_params(SUITE_DIR, FILES, UNSUPPORTED)
OPTIONAL_PARAMS = collect_suite_params(SUITE_DIR, OPTIONAL_FILES, UNSUPPORTED)

# Pinned from the first green run, after checking every skip reason names
# an unimplemented keyword (test_every_skip_names_an_unimplemented_keyword).
EXPECTED_RUN, EXPECTED_SKIPPED = 1261, 0
EXPECTED_OPTIONAL_RUN, EXPECTED_OPTIONAL_SKIPPED = 26, 0


def test_census_covers_the_dialect() -> None:
    # A keyword the dialect binds but the census omits would never be
    # marked unsupported when it is later removed; keep the census total.
    assert IMPLEMENTED <= ALL_2019_09, sorted(IMPLEMENTED - ALL_2019_09)


@pytest.mark.parametrize("case", PARAMS)
def test_suite_case(case: SuiteCase) -> None:
    engine = create_engine(
        default_dialect=DIALECT_2019_09,
        loaders=[suite_remotes_loader(REMOTES_DIR)],
    )
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid


@pytest.mark.parametrize("case", OPTIONAL_PARAMS)
def test_optional_case(case: SuiteCase) -> None:
    engine = create_engine(
        default_dialect=DIALECT_2019_09,
        loaders=[suite_remotes_loader(REMOTES_DIR)],
    )
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid


def test_exact_case_counts() -> None:
    assert count_params(PARAMS) == (EXPECTED_RUN, EXPECTED_SKIPPED)
    assert count_params(OPTIONAL_PARAMS) == (
        EXPECTED_OPTIONAL_RUN,
        EXPECTED_OPTIONAL_SKIPPED,
    )


def test_every_skip_names_an_unimplemented_keyword() -> None:
    for param in [*PARAMS, *OPTIONAL_PARAMS]:
        for mark in param.marks:
            reason = str(mark.kwargs.get("reason", ""))
            assert reason.startswith("uses "), reason
            for name in reason.removeprefix("uses ").split(", "):
                assert name in UNSUPPORTED, name
