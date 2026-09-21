# The plan census (DESIGN.md M6): exact per-dialect counts of static and
# interpreted units over every suite group. Interpreted fallback is always
# correct, so a static→interpreted regression passes every other gate;
# only exact pins notice. A deliberate lowering change re-pins here.

from collections.abc import Callable
from pathlib import Path

import pytest

from json_schema_engine.compiler import build_plan, explain_compilation
from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
    Engine,
    create_engine,
)
from json_schema_engine.formats import FORMATS_2020_12
from json_schema_engine.test_kit import load_suite_file, suite_remotes_loader

ROOT = Path(__file__).resolve().parents[2] / "test-suite"
REMOTES_DIR = ROOT / "remotes"

# (groups, total units, interpreted units, causes) per dialect directory,
# pinned from the first green run of the full lowering fan-out. In M6 the
# only fallback causes are dynamic references and `unevaluated*` consumers
# whose coverage is runtime-conditional (no runtime tracking until M9).
PINS: dict[str, tuple[str, tuple[int, int, int, dict[str, int]]]] = {
    "draft2020-12": (
        DIALECT_2020_12,
        (384, 1206, 79, {"dynamic": 59, "unlowerable": 20}),
    ),
    "draft2019-09": (
        DIALECT_2019_09,
        (373, 1184, 65, {"dynamic": 49, "unlowerable": 16}),
    ),
    # No dynamic references and no unevaluated* keywords: fully static.
    "draft7": (DIALECT_DRAFT_07, (258, 762, 0, {})),
    "draft6": (DIALECT_DRAFT_06, (233, 680, 0, {})),
}


def _default_engine(dialect: str) -> Engine:
    return create_engine(
        default_dialect=dialect, loaders=[suite_remotes_loader(REMOTES_DIR)]
    )


def census(
    directory: str,
    dialect: str,
    *,
    engine_factory: Callable[[str], Engine] = _default_engine,
) -> tuple[int, int, int, dict[str, int]]:
    groups = total = interpreted = 0
    causes: dict[str, int] = {}
    for path in sorted((ROOT / "tests" / directory).glob("*.json")):
        seen: set[str] = set()
        for case in load_suite_file(path):
            if case.group in seen:
                continue
            seen.add(case.group)
            engine = engine_factory(dialect)
            uri = engine.load_schema(case.schema, "https://census.example/schema")
            explanation = explain_compilation(build_plan(engine, uri))
            groups += 1
            total += explanation.total_units
            interpreted += explanation.interpreted_units
            for cause, count in explanation.causes.items():
                causes[cause] = causes.get(cause, 0) + count
    return groups, total, interpreted, dict(sorted(causes.items()))


@pytest.mark.parametrize("directory", list(PINS))
def test_census_is_pinned(directory: str) -> None:
    dialect, expected = PINS[directory]
    assert census(directory, dialect) == expected


def test_assert_formats_changes_no_classification() -> None:
    """Asserting formats (best effort, every standard dialect) never demotes
    a unit to interpreted: the draft2020-12 census built with an engine that
    has the standard 2020-12 table and `assert_formats=True` classifies
    every unit exactly as the plain census does."""

    def with_asserted_formats(dialect: str) -> Engine:
        return create_engine(
            default_dialect=dialect,
            loaders=[suite_remotes_loader(REMOTES_DIR)],
            formats=FORMATS_2020_12,
            assert_formats=True,
        )

    dialect, expected = PINS["draft2020-12"]
    assert (
        census("draft2020-12", dialect, engine_factory=with_asserted_formats)
        == expected
    )
