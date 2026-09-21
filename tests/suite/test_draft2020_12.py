# The official draft2020-12 suite leg (DESIGN.md D12, §6 done-signals).
# Groups whose schemas use a keyword the dialect does not bind yet are
# skipped by the schema-position scan and counted; the exact-count pins make
# a submodule bump or a keyword landing a deliberate two-number edit.

from pathlib import Path

import pytest

from json_schema_engine.core import DIALECT_2020_12, create_engine
from json_schema_engine.test_kit import (
    SuiteCase,
    collect_suite_params,
    count_params,
    suite_remotes_loader,
)

from .keyword_census import ALL_2020_12

SUITE_ROOT = Path(__file__).resolve().parents[2] / "test-suite"
SUITE_DIR = SUITE_ROOT / "tests" / "draft2020-12"
REMOTES_DIR = SUITE_ROOT / "remotes"
RETRIEVAL_URI = "https://suite.example/schema"

# Every draft2020-12 file except: `refRemote` (its own leg, below);
# `dynamicRef` and `vocabulary` (M3 — and `vocabulary.json` drives
# `$vocabulary` through `$schema`, which the keyword scan cannot see, so it
# is excluded by name rather than by scan); `defs` (validates against the
# 2020-12 metaschema, which M3 bundles).
FILES = [
    "additionalProperties",
    "allOf",
    "anchor",
    "anyOf",
    "boolean_schema",
    "const",
    "contains",
    "content",
    "default",
    "dependentRequired",
    "dependentSchemas",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "if-then-else",
    "infinite-loop-detection",
    "items",
    "maxContains",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minContains",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "not",
    "oneOf",
    "pattern",
    "patternProperties",
    "prefixItems",
    "properties",
    "propertyNames",
    "ref",
    "required",
    "type",
    "unevaluatedItems",
    "unevaluatedProperties",
    "uniqueItems",
]

IMPLEMENTED = frozenset(create_engine().dialects.get_dialect(DIALECT_2020_12).keywords)
UNSUPPORTED = ALL_2020_12 - IMPLEMENTED

# Groups the keyword scan cannot see through: they reference the 2020-12
# metaschema, whose evaluation needs keywords and bundling that land in M3.
NEEDS_METASCHEMA = "needs the bundled 2020-12 metaschema (M3)"
SKIP_GROUPS = {("ref", "remote ref, containing refs itself"): NEEDS_METASCHEMA}

PARAMS = collect_suite_params(SUITE_DIR, FILES, UNSUPPORTED, SKIP_GROUPS)
REMOTE_PARAMS = collect_suite_params(SUITE_DIR, ["refRemote"], UNSUPPORTED)

# Pinned from the first green run, after checking every skip reason names
# an unimplemented keyword (test_every_skip_names_an_unimplemented_keyword).
EXPECTED_RUN, EXPECTED_SKIPPED = 418, 123
EXPECTED_REMOTE_RUN, EXPECTED_REMOTE_SKIPPED = 25, 6


def test_census_covers_the_dialect() -> None:
    # A keyword the dialect binds but the census omits would never be
    # marked unsupported when it is later removed; keep the census total.
    assert IMPLEMENTED <= ALL_2020_12, sorted(IMPLEMENTED - ALL_2020_12)


@pytest.mark.parametrize("case", PARAMS)
def test_suite_case(case: SuiteCase) -> None:
    engine = create_engine()
    uri = engine.register_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid


@pytest.mark.parametrize("case", REMOTE_PARAMS)
def test_ref_remote_case(case: SuiteCase) -> None:
    engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid


def test_exact_case_counts() -> None:
    assert count_params(PARAMS) == (EXPECTED_RUN, EXPECTED_SKIPPED)
    assert count_params(REMOTE_PARAMS) == (EXPECTED_REMOTE_RUN, EXPECTED_REMOTE_SKIPPED)


def test_every_skip_names_an_unimplemented_keyword() -> None:
    for param in [*PARAMS, *REMOTE_PARAMS]:
        for mark in param.marks:
            reason = str(mark.kwargs.get("reason", ""))
            if reason == NEEDS_METASCHEMA:
                continue
            assert reason.startswith("uses "), reason
            for name in reason.removeprefix("uses ").split(", "):
                assert name in UNSUPPORTED, name
