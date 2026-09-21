# Standalone emission (DESIGN.md D10; M6): every static-plan group of the
# 2020-12 suite emitted as a module, imported in a fresh interpreter with
# the compiler package absent, no code generated while validating, and
# verdict parity with the interpreter; plus the refusals.

import json
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from json_schema_engine.compiler import (
    StandaloneUnsupportedError,
    build_plan,
    emit_standalone,
)
from json_schema_engine.core import JsonValue, create_engine
from json_schema_engine.test_kit import load_suite_file, suite_remotes_loader

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "test-suite" / "tests" / "draft2020-12"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
FIXTURES = Path(__file__).parent / "fixtures"

RUNNER = textwrap.dedent(
    """
    import importlib.util, json, sys
    manifest = json.load(open(sys.argv[1]))
    modules = {}
    for name, path in manifest["modules"].items():
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    # `ecma_regex` arrives with core's package import (core's regex adapter
    # depends on it); the emitted module itself references neither it nor
    # the compiler, and the compiler is never imported.
    assert "json_schema_engine.compiler" not in sys.modules
    events = []
    def hook(name, args):
        if name in ("compile", "exec"):
            events.append(name)
    sys.addaudithook(hook)
    failures = 0
    for name, instance, expected in manifest["cases"]:
        try:
            got = modules[name].validate(instance)
        except Exception as error:  # noqa: BLE001
            got = type(error).__name__
        if got != expected:
            failures += 1
            print("MISMATCH", name, json.dumps(instance)[:200], got, expected)
    assert events == [], events
    print("cases", len(manifest["cases"]), "failures", failures)
    sys.exit(1 if failures else 0)
    """
)


def _static_groups() -> list[tuple[str, JsonValue, list[JsonValue]]]:
    groups: list[tuple[str, JsonValue, list[JsonValue]]] = []
    for path in sorted(SUITE_DIR.glob("*.json")):
        by_group: dict[str, tuple[JsonValue, list[JsonValue]]] = {}
        for case in load_suite_file(path):
            entry = by_group.setdefault(case.group, (case.schema, []))
            entry[1].append(case.data)
        for group, (schema, instances) in by_group.items():
            groups.append((f"{path.stem}/{group}", schema, instances))
    return groups


def test_static_suite_groups_import_without_the_compiler(tmp_path: Path) -> None:
    modules: dict[str, str] = {}
    cases: list[tuple[str, JsonValue, object]] = []
    emitted = skipped = 0
    for index, (_label, schema, instances) in enumerate(_static_groups()):
        engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
        try:
            uri = engine.load_schema(schema, "https://standalone.example/schema")
        except Exception:
            continue
        if build_plan(engine, uri).targets:
            skipped += 1
            continue
        name = f"g{index}"
        path = tmp_path / f"{name}.py"
        path.write_text(emit_standalone(engine, uri))
        modules[name] = str(path)
        emitted += 1
        for instance in instances:
            try:
                expected: object = engine.evaluate(uri, instance).valid
            except Exception as error:
                expected = type(error).__name__
            cases.append((name, instance, expected))
    assert emitted > 200, (emitted, skipped)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"modules": modules, "cases": cases}))
    completed = subprocess.run(
        [sys.executable, "-c", RUNNER, str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"cases {len(cases)} failures 0" in completed.stdout


def test_fixture_module_agrees_in_process(tmp_path: Path) -> None:
    engine = create_engine()
    schema = json.loads((FIXTURES / "user.schema.json").read_text())
    uri = engine.register_schema(schema, "https://spike.example/user")
    source = emit_standalone(engine, uri)
    assert "import json_schema_engine.compiler" not in source
    assert "ecma_regex" not in source
    namespace: dict[str, object] = {}
    exec(compile(source, "<standalone>", "exec"), namespace)
    validate = cast(Callable[[JsonValue], bool], namespace["validate"])
    ok: JsonValue = {
        "id": 1,
        "name": "Ada",
        "email": "ada@example.com",
        "tags": ["x"],
        "address": {"street": "s", "city": "c"},
    }
    probes: list[JsonValue] = [
        ok,
        {**ok, "email": "x"},
        {**ok, "extra": 1},
        {"id": "1"},
        3,
    ]
    for probe in probes:
        assert validate(probe) == engine.evaluate(uri, probe).valid, probe


def test_refuses_islands_and_foreign_backends() -> None:
    engine = create_engine()
    uri = engine.register_schema(
        json.loads((FIXTURES / "island.schema.json").read_text()),
        "https://spike.example/island",
    )
    with pytest.raises(StandaloneUnsupportedError, match="dynamic"):
        emit_standalone(engine, uri)
    engine = create_engine(regex_backend="regex")
    uri = engine.register_schema({"type": "string"}, "https://spike.example/plain")
    with pytest.raises(StandaloneUnsupportedError, match="backend"):
        emit_standalone(engine, uri)
