# Offline install smoke (DESIGN.md M8; CI): build both publishable
# packages, install the engine from those artifacts alone into a fresh
# virtual environment with the index disabled, and prove from inside that
# environment that the wheel is complete: the three portions import, the
# workspace-private packages are absent, evaluation, compilation, and a
# standalone module work, the format tables assert, the bundled
# metaschemas shipped, every portion carries `py.typed`, the installed
# versions are the ones the tree declares, and a strict pyright run over
# a consumer file sees the package's types through the wheel.
#
# Local + CI: `uv run python scripts/install_smoke.py`.

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = "json-schema-engine"
REGEX = "ecma-regex"

PROBE = r"""
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path

engine_version, regex_version = sys.argv[1], sys.argv[2]
assert importlib.metadata.version("json-schema-engine") == engine_version
assert importlib.metadata.version("ecma-regex") == regex_version

for private in ("json_schema_engine.test_kit", "json_schema_engine.bench"):
    assert importlib.util.find_spec(private) is None, f"{private} leaked"
assert importlib.util.find_spec("idna") is None, "the venv is not extra-free"

import json_schema_engine.core as core
import json_schema_engine.compiler as compiler
import json_schema_engine.formats as formats
import ecma_regex

for portion in (core, compiler, formats, ecma_regex):
    marker = Path(portion.__file__).parent / "py.typed"
    assert marker.is_file(), f"missing {marker}"

from json_schema_engine.core.metaschemas import bundled_metaschemas
assert len(bundled_metaschemas()) == 18, len(bundled_metaschemas())

engine = core.create_engine()
uri = engine.register_schema(
    {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}},
    "https://smoke.example/s",
)
assert engine.evaluate(uri, {"id": 1}).valid is True
result = engine.evaluate(uri, {"id": "x"}, output="list")
assert result.valid is False and result.errors is not None
assert result.errors[0]["evaluationPath"] == "/properties/id/type"

compiled = compiler.compile_validator(engine, uri)
assert compiled.validate({"id": 1}) is True and compiled.validate({}) is False
source = compiler.emit_standalone(engine, uri)
module_path = Path("standalone_smoke_module.py")
module_path.write_text(source)
spec = importlib.util.spec_from_file_location("standalone_smoke_module", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.validate({"id": 1}) is True and module.validate({"id": "x"}) is False

asserting = core.create_engine(formats=formats.FORMATS_2020_12, assert_formats=True)
dt = asserting.register_schema({"format": "date-time"}, "https://smoke.example/dt")
assert asserting.evaluate(dt, "1998-12-31T23:59:60Z").valid is True
assert asserting.evaluate(dt, "1998-12-31T22:59:60Z").valid is False
try:
    asserting.register_schema({"format": "idn-hostname"}, "https://smoke.example/idn")
except core.FormatUnavailableError as error:
    assert "idna" in str(error)
else:
    raise AssertionError("idn-hostname must be unavailable without the extra")

pattern = ecma_regex.compile(r"^\d+$")
assert pattern.search("42") is True and pattern.search("٤٢") is False
print("INSTALL SMOKE PASS")
"""

CONSUMER = """
from json_schema_engine.compiler import compile_validator
from json_schema_engine.core import JsonValue, Result, create_engine
from json_schema_engine.formats import FORMATS_2020_12

engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
uri: str = engine.register_schema({"type": "string"}, "https://consumer.example/s")
result: Result = engine.evaluate(uri, "x", output="list")
valid: bool = result.valid
errors = result.errors
if errors is not None:
    path: str = errors[0]["evaluationPath"]
validate = compile_validator(engine, uri).validate
verdict: bool = validate("y")
instance: JsonValue = {"a": [1, 2.5, None, True]}
"""

PYRIGHT_CONFIG = {
    "typeCheckingMode": "strict",
    "reportMissingTypeStubs": "error",
    "reportMissingModuleSource": "error",
    "reportMissingImports": "error",
}


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kwargs)  # type: ignore[arg-type]


def _version(package: str | None) -> str:
    cmd = ["uv", "version", "--short"]
    if package is not None:
        cmd += ["--package", package]
    return subprocess.run(
        cmd, check=True, text=True, capture_output=True, cwd=ROOT
    ).stdout.strip()


def build(dist: Path) -> None:
    for package in (ENGINE, REGEX):
        _run(["uv", "build", "--package", package, "--out-dir", str(dist)], cwd=ROOT)


def check_artifacts(dist: Path, engine_version: str, regex_version: str) -> None:
    # `uv build` also drops a `.gitignore` into the output directory.
    names = sorted(
        path.name for path in dist.iterdir() if path.suffix in {".whl", ".gz"}
    )
    engine_tag = f"json_schema_engine-{engine_version}"
    regex_tag = f"ecma_regex-{regex_version}"
    for expected in (
        f"{engine_tag}.tar.gz",
        f"{engine_tag}-py3-none-any.whl",
        f"{regex_tag}.tar.gz",
        f"{regex_tag}-py3-none-any.whl",
    ):
        assert expected in names, (expected, names)
    assert len(names) == 4, names

    with tarfile.open(dist / f"{engine_tag}.tar.gz") as sdist:
        members = sdist.getnames()
    for required in ("README.md", "LICENSE", "CHANGELOG.md", "pyproject.toml"):
        assert f"{engine_tag}/{required}" in members, required
    assert not any("/tests/" in name for name in members), "engine sdist ships tests"
    with tarfile.open(dist / f"{regex_tag}.tar.gz") as sdist:
        members = sdist.getnames()
    for required in ("README.md", "LICENSE", "CHANGELOG.md", "pyproject.toml"):
        assert f"{regex_tag}/{required}" in members, required

    with zipfile.ZipFile(dist / f"{engine_tag}-py3-none-any.whl") as wheel:
        names = wheel.namelist()
        metadata = wheel.read(f"{engine_tag}.dist-info/METADATA").decode()
    for portion in ("core", "compiler", "formats"):
        assert f"json_schema_engine/{portion}/py.typed" in names, portion
    assert "json_schema_engine/core/metaschemas/2020-12/format-assertion.json" in names
    assert not any(name.startswith("json_schema_engine/test_kit") for name in names)
    requires = [
        line for line in metadata.splitlines() if line.startswith("Requires-Dist: ")
    ]
    # Hatchling normalizes specifier order, so compare the clauses.
    (regex_dependency,) = [line for line in requires if "ecma-regex" in line]
    clauses = set(regex_dependency.removeprefix("Requires-Dist: ecma-regex").split(","))
    assert clauses == {">=0.1", "<0.2"}, requires
    assert "Provides-Extra: idna" in metadata and "Provides-Extra: regex" in metadata
    with zipfile.ZipFile(dist / f"{regex_tag}-py3-none-any.whl") as wheel:
        assert "ecma_regex/py.typed" in wheel.namelist()
    print("artifacts ok")


def install(dist: Path, venv: Path) -> Path:
    _run(["uv", "venv", "--python", sys.executable, str(venv)])
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-index",
            "--find-links",
            str(dist),
            ENGINE,
        ]
    )
    return python


def probe(python: Path, work: Path, engine_version: str, regex_version: str) -> None:
    probe_path = work / "probe.py"
    probe_path.write_text(PROBE)
    cmd = [str(python), str(probe_path), engine_version, regex_version]
    print("+ " + " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=work, text=True, capture_output=True)
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"probe failed with exit status {completed.returncode}")
    assert "INSTALL SMOKE PASS" in completed.stdout, completed.stdout


def type_check(python: Path, work: Path) -> None:
    (work / "consumer.py").write_text(CONSUMER)
    (work / "pyrightconfig.json").write_text(json.dumps(PYRIGHT_CONFIG))
    _run(
        [sys.executable, "-m", "pyright", "--pythonpath", str(python), "consumer.py"],
        cwd=work,
    )


def main() -> int:
    engine_version = _version(None)
    regex_version = _version(REGEX)
    with tempfile.TemporaryDirectory(prefix="jse-install-smoke-") as tmp:
        work = Path(tmp)
        dist = work / "dist"
        build(dist)
        check_artifacts(dist, engine_version, regex_version)
        python = install(dist, work / "venv")
        probe(python, work, engine_version, regex_version)
        type_check(python, work)
    print(f"INSTALL SMOKE PASS {ENGINE} {engine_version}, {REGEX} {regex_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
