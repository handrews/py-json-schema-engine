"""Bowtie conformance gate for json-schema-engine (M3 Step 3).

Builds the harness image locally, smokes it, then runs the official
JSON-Schema-Test-Suite through Bowtie's own runner and pins an exact
per-dialect test count with zero failures/errors/skips. Local + CI only:
the image stays `localhost/json-schema-engine-bowtie` and nothing leaves
the machine.

Run with: `uv run python scripts/bowtie_check.py`

Requirements: a reachable container engine (Docker or Podman) and network
access for `uvx` to fetch the pinned `bowtie-json-schema` release.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "localhost/json-schema-engine-bowtie"
BOWTIE_PIN = "bowtie-json-schema==2026.6.1"
# The `bowtie-json-schema` distribution's console script is named `bowtie`,
# not `bowtie-json-schema`, so uvx needs `--from` to run it without
# installing it into the active environment.
BOWTIE_CMD = ["uvx", "--from", BOWTIE_PIN, "bowtie"]

# Expected: every test in the dialect's suite directory runs and matches.
PINS = {
    "draft2020-12": 1301,
    "draft2019-09": 1261,
    "draft7": 929,
    "draft6": 841,
}

EXTRA_PATH_DIRS = ["/opt/podman/bin"]


def _extended_path() -> str:
    return os.pathsep.join([os.environ.get("PATH", ""), *EXTRA_PATH_DIRS])


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, **kwargs)  # type: ignore[arg-type]


def _tool_reachable(path: str, env: dict[str, str]) -> bool:
    try:
        subprocess.run(
            [path, "info"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def pick_container_tool() -> str:
    env = {**os.environ, "PATH": _extended_path()}
    docker = shutil.which("docker", path=env["PATH"])
    if docker and _tool_reachable(docker, env):
        return docker
    podman = shutil.which("podman", path=env["PATH"])
    if podman and _tool_reachable(podman, env):
        return podman
    print(
        "no reachable container engine; start the podman machine "
        "(`podman machine start`) or Docker",
        file=sys.stderr,
    )
    sys.exit(1)


def build_wheels() -> None:
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    _run(["uv", "build", "--package", "json-schema-engine"], cwd=ROOT)
    _run(["uv", "build", "--package", "ecma-regex"], cwd=ROOT)


def build_image(container_tool: str) -> None:
    _run(
        [
            container_tool,
            "build",
            "-q",
            "-t",
            IMAGE,
            "-f",
            str(ROOT / "bowtie" / "Containerfile"),
            ".",
        ],
        cwd=ROOT,
    )


def run_smoke() -> None:
    result = _run(
        [*BOWTIE_CMD, "smoke", "-i", f"image:{IMAGE}", "--format", "json"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
    )
    smoke: dict[str, Any] = json.loads(result.stdout)
    if not smoke.get("success"):
        print("bowtie smoke FAILED", file=sys.stderr)
        sys.exit(1)


def run_suite(dialect: str, report_path: Path) -> str:
    result = _run(
        [
            *BOWTIE_CMD,
            "suite",
            "-i",
            f"image:{IMAGE}",
            str(ROOT / "test-suite" / "tests" / dialect),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
    )
    report_path.write_text(result.stdout)
    return result.stdout


def summarize(report_path: Path) -> dict[str, int]:
    result = _run(
        [
            *BOWTIE_CMD,
            "summary",
            "--show",
            "failures",
            "--format",
            "json",
            str(report_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
    )
    summary: list[Any] = json.loads(result.stdout)
    counts: dict[str, Any] = summary[0][1] if summary else {}
    return {
        "failed": counts.get("failed", -1),
        "errored": counts.get("errored", -1),
        "skipped": counts.get("skipped", -1),
    }


def count_and_check(report: str) -> tuple[int, int]:
    """Return (tests, mismatches) by comparing each result to its expectation."""
    tests = 0
    mismatches = 0
    for line in report.splitlines():
        if not line:
            continue
        entry: dict[str, Any] = json.loads(line)
        results: list[dict[str, Any]] | None = entry.get("results")
        expected: list[Any] | None = entry.get("expected")
        if results is None or expected is None:
            continue
        tests += len(results)
        for result, want in zip(results, expected, strict=False):
            if result.get("valid") != want:
                mismatches += 1
    return tests, mismatches


def main() -> int:
    build_wheels()
    container_tool = pick_container_tool()
    build_image(container_tool)

    print("bowtie smoke...")
    run_smoke()

    failed_overall = False
    with tempfile.TemporaryDirectory(prefix="jse-bowtie-") as scratch:
        for dialect, pin in PINS.items():
            report_path = Path(scratch) / f"{dialect}.jsonl"
            report = run_suite(dialect, report_path)
            counts = summarize(report_path)
            tests, mismatches = count_and_check(report)

            ok = (
                counts["failed"] == 0
                and counts["errored"] == 0
                and counts["skipped"] == 0
                and mismatches == 0
                and tests == pin
            )
            print(
                f"{dialect}: tests={tests} (pin {pin}) "
                f"failed={counts['failed']} errored={counts['errored']} "
                f"skipped={counts['skipped']} mismatches={mismatches} "
                + ("OK" if ok else "FAIL")
            )
            if not ok:
                failed_overall = True

    if failed_overall:
        print("BOWTIE CHECK FAIL", file=sys.stderr)
        return 1
    print("BOWTIE CHECK PASS (all dialects exact, zero failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
