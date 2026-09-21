# M5 §2: official output-tests runner. Loads test-suite/output-tests's
# per-release `content/*.json` files (README.md: "for each test case, the
# `valid` property has been removed, and an `output` property has been
# added") into flat pytest parameter sets, one per (case, format) pair,
# picking the first format a caller supports out of each case's `output`
# keys; a case with none of the caller's supported formats becomes a loud,
# counted skip rather than being silently dropped.
#
# IP policy (DESIGN.md D15): this module is implementation from the official
# output-tests fixtures and their README only. It mirrors the shape of
# `suite.py` (this package's own prior work, not a third-party validator)
# and, for the overall wiring (a runner that renders a document and then
# validates it against the case's own output schema), the TS engine's
# `packages/core/test/output-suite.test.ts` — rewritten in Python idioms,
# as pytest parameter sets rather than an async runner, rather than ported
# line-for-line.

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from json_schema_engine.test_kit.suite import Json, reject_non_finite_constant

if TYPE_CHECKING:
    # pytest has no public type for a parametrize entry; this is the actual
    # runtime type returned by `pytest.param(...)` and consumed by
    # `pytest.mark.parametrize`. Private-module import, type-checking only.
    from _pytest.mark.structures import (
        ParameterSet,  # pyright: ignore[reportPrivateImportUsage]
    )


@dataclass(frozen=True, slots=True)
class OutputCase:
    """One official output-tests case, flattened out of its enclosing group.

    `output` carries every format the fixture author populated for this
    case (README.md: "a property for each of the output formats where the
    value is a schema that will successfully validate for compliant
    output"), keyed by format name; a caller picks the one format it can
    exercise via :func:`collect_output_params`.
    """

    file: str
    group: str
    description: str
    schema: Json
    data: Json
    output: dict[str, Json]


def load_output_tests(directory: Path, files: Sequence[str]) -> list[OutputCase]:
    """Parses ``directory/<file>.json`` output-tests files into cases.

    Each entry in a file's top-level array is a *group*: a schema plus a
    list of test cases sharing it, the same shape `load_suite_file` reads,
    minus `valid` and plus `output` (README.md, "Test Files").
    """
    cases: list[OutputCase] = []
    for file in files:
        text = (directory / f"{file}.json").read_text(encoding="utf-8")
        groups: list[dict[str, Any]] = json.loads(
            text, parse_constant=reject_non_finite_constant
        )
        for group in groups:
            schema: Json = group["schema"]
            group_description: str = group["description"]
            for test in group["tests"]:
                output: dict[str, Json] = test["output"]
                cases.append(
                    OutputCase(
                        file=file,
                        group=group_description,
                        description=test["description"],
                        schema=schema,
                        data=test["data"],
                        output=output,
                    )
                )
    return cases


def collect_output_params(
    directory: Path, files: Sequence[str], supported: Sequence[str]
) -> list[ParameterSet]:
    """Builds one ``pytest.param(case, format, id=...)`` per output-tests
    case across ``files`` (stems, relative to ``directory``).

    For each case, the first format in ``supported`` that is also a key of
    the case's ``output`` is chosen; a case matching none of them is marked
    ``pytest.mark.skip`` with reason ``"output formats <names> not
    supported"`` (``<names>`` the case's own, sorted, comma-joined format
    names) and parametrized with an arbitrary one of its own formats, since
    the mark keeps the test body from ever running. IDs are
    ``f"{file}/{group}/{description}/{format}"``; a duplicate
    file/group/description within a file (a handful occur in the suite)
    gets a ``#2``, ``#3``, ... suffix on the shared prefix, mirroring
    `collect_suite_params`.
    """
    params: list[ParameterSet] = []
    for file in files:
        cases = load_output_tests(directory, [file])
        seen_ids: dict[str, int] = {}
        for case in cases:
            base_id = f"{case.file}/{case.group}/{case.description}"
            seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
            occurrence = seen_ids[base_id]
            case_id = base_id if occurrence == 1 else f"{base_id}#{occurrence}"

            marks: list[pytest.MarkDecorator] = []
            format_name = next((f for f in supported if f in case.output), None)
            if format_name is None:
                names = ", ".join(sorted(case.output))
                reason = f"output formats {names} not supported"
                marks.append(pytest.mark.skip(reason=reason))
                format_name = next(iter(case.output))

            params.append(
                pytest.param(
                    case, format_name, id=f"{case_id}/{format_name}", marks=marks
                )
            )
    return params
