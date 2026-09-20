"""Tests for json_schema_engine.test_kit.remotes (DESIGN.md D12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from json_schema_engine.test_kit.remotes import suite_remotes_loader

REMOTES_DIR = Path(__file__).resolve().parents[3] / "test-suite" / "remotes"


def test_loader_resolves_a_real_submodule_file() -> None:
    load = suite_remotes_loader(REMOTES_DIR)

    doc = load("http://localhost:1234/draft2020-12/integer.json")

    assert doc is not None
    assert doc.value == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "integer",
    }
    assert doc.uri == "http://localhost:1234/draft2020-12/integer.json"


def test_loader_returns_none_outside_base_url() -> None:
    load = suite_remotes_loader(REMOTES_DIR)

    assert load("http://example.com/draft2020-12/integer.json") is None


def test_loader_returns_none_for_missing_file() -> None:
    load = suite_remotes_loader(REMOTES_DIR)

    assert load("http://localhost:1234/draft2020-12/does-not-exist.json") is None


def test_loader_refuses_path_traversal() -> None:
    load = suite_remotes_loader(REMOTES_DIR)

    assert load("http://localhost:1234/../pyproject.toml") is None
    assert load("http://localhost:1234/draft2020-12/../../pyproject.toml") is None


def test_loader_strips_fragment_before_mapping() -> None:
    load = suite_remotes_loader(REMOTES_DIR)

    doc = load("http://localhost:1234/draft2020-12/integer.json#/type")

    assert doc is not None
    assert doc.uri == "http://localhost:1234/draft2020-12/integer.json"


def test_loader_rejects_non_finite_constants(tmp_path: Path) -> None:
    remotes_dir = tmp_path / "remotes"
    remotes_dir.mkdir()
    (remotes_dir / "bad.json").write_text("NaN", encoding="utf-8")
    load = suite_remotes_loader(remotes_dir)

    with pytest.raises(ValueError, match="not valid JSON"):
        load("http://localhost:1234/bad.json")
