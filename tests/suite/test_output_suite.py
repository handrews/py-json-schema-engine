# The official output-tests conformance leg (DESIGN.md M5 §2, D5/D6). For
# each case: render `data` against the group `schema` in the named format on
# a fresh engine, then validate the rendered document against the case's own
# output schema on a second fresh engine that also knows the release's
# `output-schema.json` (test-suite/output-tests/README.md) — "the rendered
# document self-validates" is the pass condition, not a structural diff, the
# same wiring as the TS engine's `packages/core/test/output-suite.test.ts`
# (our own prior work), rewritten as pytest parameter sets.
#
# v1's output-schema.json declares `"$schema": "https://json-schema.org/v1"`
# (test-suite/output-tests/v1/output-schema.json) — a hypothetical future
# release this engine does not implement as a dialect. Rather than skip the
# leg, both engines register an empty stub document (`{}`, no `$vocabulary`)
# at that URI before registering anything that names it: `_assemble_dialect`
# treats a `$vocabulary`-less metaschema as "the least-surprise reading is
# the default dialect's vocabularies" (json_schema_engine/core/engine.py),
# so the stub makes "https://json-schema.org/v1" resolve to 2020-12's own
# keyword set — the vocabulary v1's fixtures actually exercise (`type`,
# `properties`, `readOnly`, ...). This is the engine's own documented
# fallback, invoked from the test harness; nothing in `core` changes.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from json_schema_engine.compiler import compile_evaluator
from json_schema_engine.core import DIALECT_2019_09, DIALECT_2020_12, create_engine
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.test_kit import OutputCase, collect_output_params, count_params

SUITE_ROOT = Path(__file__).resolve().parents[2] / "test-suite" / "output-tests"
RETRIEVAL_URI = "https://output-suite.example/schema"
FALLBACK_OUTPUT_SCHEMA_URI = "https://output-suite.example/schema/output"

# The hypothetical dialect v1's own fixtures (and its output-schema.json)
# declare via `$schema`; not one of this engine's bundled dialects.
V1_DIALECT_URI = "https://json-schema.org/v1"

CONTENT_FILES = ["escape", "general", "readOnly", "type"]
V1_CONTENT_FILES = ["general", "readOnly", "type"]

DRAFT_2020_12_DIR = SUITE_ROOT / "draft2020-12"
DRAFT_2019_09_DIR = SUITE_ROOT / "draft2019-09"
V1_DIR = SUITE_ROOT / "v1"

PARAMS_2020_12 = collect_output_params(
    DRAFT_2020_12_DIR / "content", CONTENT_FILES, ["basic"]
)
PARAMS_2019_09 = collect_output_params(
    DRAFT_2019_09_DIR / "content", CONTENT_FILES, ["basic"]
)
PARAMS_V1 = collect_output_params(V1_DIR / "content", V1_CONTENT_FILES, ["list"])

# Pinned from the first green run (DESIGN.md D12's exact-count convention):
# every vendored case in these directories carries a supported format today.
EXPECTED_2020_12 = (4, 0)
EXPECTED_2019_09 = (4, 0)
EXPECTED_V1 = (3, 0)


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _render(
    dialect: str, schema: JsonValue, data: JsonValue, format_name: str, *, v1: bool
) -> JsonValue:
    engine = create_engine(default_dialect=dialect)
    if v1:
        engine.register_schema(cast(JsonValue, {}), V1_DIALECT_URI)
    uri = engine.register_schema(schema, RETRIEVAL_URI)
    result = engine.evaluate(uri, data, output=format_name, annotations=True)
    assert result.output_document is not None
    # The compiled evaluator (M9) must render the same document.
    evaluator = compile_evaluator(engine, uri, annotations=True)
    assert evaluator.evaluate(data, output=format_name) == result
    # `OutputDocument` is a union of specific TypedDicts (one per format);
    # here it is only ever handed to another engine as an opaque JSON
    # instance, so it is treated as the general `JsonValue` it structurally
    # is.
    return cast(JsonValue, result.output_document)


def _validate(
    dialect: str,
    output_schema_doc: dict[str, Any],
    case_output_schema: dict[str, Any],
    document: JsonValue,
    *,
    v1: bool,
) -> bool:
    engine = create_engine(default_dialect=dialect)
    if v1:
        engine.register_schema(cast(JsonValue, {}), V1_DIALECT_URI)
    meta_id = output_schema_doc["$id"]
    assert isinstance(meta_id, str)
    engine.register_schema(cast(JsonValue, output_schema_doc), meta_id)
    schema_id = case_output_schema.get("$id", FALLBACK_OUTPUT_SCHEMA_URI)
    assert isinstance(schema_id, str)
    uri = engine.register_schema(cast(JsonValue, case_output_schema), schema_id)
    return engine.evaluate(uri, document).valid


def _run_case(
    dialect: str, draft_dir: Path, case: OutputCase, format_name: str, *, v1: bool
) -> None:
    document = _render(
        dialect,
        cast(JsonValue, case.schema),
        cast(JsonValue, case.data),
        format_name,
        v1=v1,
    )
    output_schema_doc = _load_json(draft_dir / "output-schema.json")
    case_output_schema = cast(dict[str, Any], case.output[format_name])
    assert _validate(dialect, output_schema_doc, case_output_schema, document, v1=v1)


@pytest.mark.parametrize(("case", "format_name"), PARAMS_2020_12)
def test_draft2020_12_case(case: OutputCase, format_name: str) -> None:
    _run_case(DIALECT_2020_12, DRAFT_2020_12_DIR, case, format_name, v1=False)


@pytest.mark.parametrize(("case", "format_name"), PARAMS_2019_09)
def test_draft2019_09_case(case: OutputCase, format_name: str) -> None:
    _run_case(DIALECT_2019_09, DRAFT_2019_09_DIR, case, format_name, v1=False)


@pytest.mark.parametrize(("case", "format_name"), PARAMS_V1)
def test_v1_case(case: OutputCase, format_name: str) -> None:
    _run_case(DIALECT_2020_12, V1_DIR, case, format_name, v1=True)


def test_exact_case_counts() -> None:
    assert count_params(PARAMS_2020_12) == EXPECTED_2020_12
    assert count_params(PARAMS_2019_09) == EXPECTED_2019_09
    assert count_params(PARAMS_V1) == EXPECTED_V1
