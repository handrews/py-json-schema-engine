# D12: official-suite runner. Loads test-suite/tests/<draft>/*.json groups
# into flat pytest parameter sets, with a schema-position-only scan for
# keywords the evaluator under test declares unsupported, so a group that
# exercises them is skipped (not silently mis-scored) rather than dropped
# from the suite entirely.
#
# IP policy (DESIGN.md D15): this module is implementation from the JSON
# Schema specifications and the official test suite only. It mirrors the
# shape of the TS engine's own `packages/test-kit/src/index.ts`
# (`unsupportedIn`, `runSuiteFiles`) — our own prior work, not a third-party
# validator — rewritten in Python idioms rather than ported line-for-line.

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

if TYPE_CHECKING:
    # pytest has no public type for a parametrize entry; this is the actual
    # runtime type returned by `pytest.param(...)` and consumed by
    # `pytest.mark.parametrize`. Private-module import, type-checking only.
    from _pytest.mark.structures import (
        ParameterSet,  # pyright: ignore[reportPrivateImportUsage]
    )

# Local alias: test-kit must not import json_schema_engine.core (import-linter
# forbids it; the evaluator under test is injected by the caller), so it
# cannot use core's own Json/JsonValue type. This is structurally identical.
type Json = bool | int | float | str | list[Json] | dict[str, Json] | None


def reject_non_finite_constant(constant: str) -> NoReturn:
    """``json.loads(parse_constant=...)`` hook, shared with :mod:`remotes`.

    ``NaN``, ``Infinity``, and ``-Infinity`` are not valid JSON (RFC 8259);
    Python's ``json`` module accepts them by default as an extension
    (DESIGN.md P2, §5). Every JSON parse boundary in test-kit uses this hook
    so it rejects them instead of silently handing a non-finite float to a
    group's schema or test data.
    """
    msg = f"{constant} is not valid JSON (DESIGN.md P2)"
    raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SuiteCase:
    """One official-suite test case, flattened out of its enclosing group."""

    file: str
    group: str
    description: str
    schema: Json
    data: Json
    valid: bool
    skip_reason: str | None = None


def load_suite_file(path: Path) -> list[SuiteCase]:
    """Parses one ``test-suite/tests/<draft>/<file>.json`` file into cases.

    Each entry in the top-level array is a *group*: a schema plus a list of
    test cases sharing it. This flattens groups into individual
    :class:`SuiteCase` values, one per (group, test) pair; ``skip_reason`` is
    always ``None`` here — it is filled in by :func:`collect_suite_params`,
    which is the layer that knows which keywords are unsupported.
    """
    text = path.read_text(encoding="utf-8")
    groups: list[dict[str, Any]] = json.loads(
        text, parse_constant=reject_non_finite_constant
    )
    file_stem = path.stem
    cases: list[SuiteCase] = []
    for group in groups:
        schema: Json = group["schema"]
        group_description: str = group["description"]
        for test in group["tests"]:
            cases.append(
                SuiteCase(
                    file=file_stem,
                    group=group_description,
                    description=test["description"],
                    schema=schema,
                    data=test["data"],
                    valid=test["valid"],
                )
            )
    return cases


# --- Schema-position-only unsupported-keyword scan -------------------------
#
# This traversal map is suite-shape knowledge, not engine knowledge: it says
# where a 2020-12 schema keyword's value is itself a schema (or holds
# schemas), so the scan can skip a group whose schema *uses* an unsupported
# keyword without also matching that keyword's name if it merely appears as
# plain data (e.g. inside `enum`, `const`, `default`, `examples`, or a data
# value the test schema itself never looks at). It is hardcoded here rather
# than sourced from the engine under test because test-kit has no dependency
# on json_schema_engine.core (import-linter forbids it) and must work for any
# evaluator shape.

# Keywords whose value is a single schema.
_SINGLE_SCHEMA_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "contains",
        "propertyNames",
        "if",
        "then",
        "else",
        "not",
        "items",
        "unevaluatedItems",
        "unevaluatedProperties",
        "contentSchema",
        "additionalItems",
    }
)
# Keywords whose value is an array of schemas.
_ARRAY_OF_SCHEMAS_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
# Keywords whose value is an object mapping names to schemas.
_MAP_OF_SCHEMAS_KEYWORDS = frozenset(
    {"properties", "patternProperties", "dependentSchemas", "$defs", "definitions"}
)


def _is_schema(value: Json) -> bool:
    # A schema is a JSON object or a boolean; bool must be checked as its own
    # branch (not folded into "truthy object") per DESIGN.md P2's bool/int
    # discipline, though here it's just a type check, not an equality one.
    return isinstance(value, dict | bool)


def _scan(schema: Json, unsupported: AbstractSet[str], found: set[str]) -> None:
    if not isinstance(schema, dict):
        return  # boolean schemas (and malformed non-object schemas) have no keywords
    for key, value in schema.items():
        if key in unsupported:
            found.add(key)
        if key == "items" and isinstance(value, list):
            # draft-07 tuple form of "items"; harmless to also recognize for
            # 2020-12, where "items" is otherwise a single-schema keyword.
            for sub in value:
                _scan(sub, unsupported, found)
        elif key in _SINGLE_SCHEMA_KEYWORDS:
            if _is_schema(value):
                _scan(value, unsupported, found)
        elif key in _ARRAY_OF_SCHEMAS_KEYWORDS:
            if isinstance(value, list):
                for sub in value:
                    _scan(sub, unsupported, found)
        elif key in _MAP_OF_SCHEMAS_KEYWORDS:
            if isinstance(value, dict):
                for sub in value.values():
                    _scan(sub, unsupported, found)
        elif key == "dependencies" and isinstance(value, dict):
            # draft-07 "dependencies": each value is either a schema or an
            # array of property-name strings; only the schema case descends.
            for sub in value.values():
                if _is_schema(sub):
                    _scan(sub, unsupported, found)
        # Anything else (enum, const, default, examples, title, $comment,
        # unrecognized keywords, ...) is never descended into: a keyword name
        # appearing there is data, not a schema position.


def unsupported_in(schema: Json, unsupported: AbstractSet[str]) -> set[str]:
    """Returns the subset of ``unsupported`` that appears as a keyword name
    in a schema position somewhere in ``schema`` (including ``schema``
    itself). Never matches a keyword name that only appears as plain data
    (e.g. inside ``enum``)."""
    found: set[str] = set()
    _scan(schema, unsupported, found)
    return found


def collect_suite_params(
    suite_dir: Path,
    files: Sequence[str],
    unsupported: AbstractSet[str],
    skip_groups: Mapping[tuple[str, str], str] | None = None,
) -> list[ParameterSet]:
    """Builds one ``pytest.param(case, id=...)`` per suite case across
    ``files`` (stems, relative to ``suite_dir``).

    A case whose group's schema hits any keyword in ``unsupported`` (per
    :func:`unsupported_in`) is marked ``pytest.mark.skip`` with the hit
    keyword names as the reason, and its ``SuiteCase.skip_reason`` is filled
    in to match. IDs are ``f"{file}/{group}/{description}"``; the suite has a
    handful of groups with identical descriptions, so a duplicate id within a
    file gets a ``#2``, ``#3``, ... suffix to stay unique.

    ``skip_groups`` maps ``(file, group)`` to a reason for groups that must
    be skipped for a cause the keyword scan cannot see (a reference to a
    metaschema that is not bundled yet); such skips are counted like any
    other, so they stay visible in the pins.
    """
    explicit = skip_groups or {}
    params: list[ParameterSet] = []
    for file in files:
        cases = load_suite_file(suite_dir / f"{file}.json")
        seen_ids: dict[str, int] = {}
        for case in cases:
            hits = unsupported_in(case.schema, unsupported)
            base_id = f"{case.file}/{case.group}/{case.description}"
            seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
            occurrence = seen_ids[base_id]
            case_id = base_id if occurrence == 1 else f"{base_id}#{occurrence}"

            marks: list[pytest.MarkDecorator] = []
            reason = explicit.get((case.file, case.group))
            if reason is None and hits:
                reason = f"uses {', '.join(sorted(hits))}"
            if reason is not None:
                case = replace(case, skip_reason=reason)
                marks.append(pytest.mark.skip(reason=reason))

            params.append(pytest.param(case, id=case_id, marks=marks))
    return params


def count_params(params: Sequence[ParameterSet]) -> tuple[int, int]:
    """Returns ``(run, skipped)`` for a list of parameter sets built by
    :func:`collect_suite_params`, by inspecting each entry's marks — the
    exact-count pin helper (DESIGN.md D12)."""
    skipped = sum(1 for p in params if any(m.name == "skip" for m in p.marks))
    return len(params) - skipped, skipped
