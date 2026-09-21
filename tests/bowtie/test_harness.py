"""Drives `bowtie/harness.py` as a subprocess over the IO protocol (v1).

Exercises the protocol surface end to end: start, dialect negotiation, a
run with a registry-served remote reference, an annotations-output run
(skipped in M3), a run that fails per-test, a run that fails before any
test runs, and a clean stop. No Bowtie install is needed for this test;
it drives the same line-delimited JSON protocol Bowtie itself speaks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "bowtie" / "harness.py"

DIALECT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


class HarnessProcess:
    """Thin line-oriented request/response wrapper around the subprocess."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(HARNESS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
            text=True,
            bufsize=1,
        )

    def send(self, request: dict[str, Any]) -> dict[str, Any]:
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        assert self.proc.stderr is not None
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, f"harness produced no output (stderr: {self.proc.stderr.read()!r})"
        result: dict[str, Any] = json.loads(line)
        return result

    def send_no_response(self, request: dict[str, Any]) -> None:
        """For `stop`, which flushes and exits without a response line."""
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()

    def close(self, expected_returncode: int = 0) -> None:
        assert self.proc.stdin is not None
        assert self.proc.stderr is not None
        self.proc.stdin.close()
        returncode = self.proc.wait(timeout=10)
        assert returncode == expected_returncode, self.proc.stderr.read()


def test_full_protocol_transcript() -> None:
    harness = HarnessProcess()

    # start
    response = harness.send({"cmd": "start", "version": 1})
    assert response["version"] == 1
    implementation = response["implementation"]
    assert implementation["name"] == "json-schema-engine"
    assert implementation["language"] == "python"
    assert implementation["dialects"] == [DIALECT_2020_12]
    assert implementation["homepage"] == (
        "https://github.com/handrews/py-json-schema-engine"
    )
    assert implementation["issues"] == (
        "https://github.com/handrews/py-json-schema-engine/issues"
    )
    assert implementation["source"] == (
        "https://github.com/handrews/py-json-schema-engine"
    )
    assert isinstance(implementation["version"], str) and implementation["version"]
    assert isinstance(implementation["language_version"], str)
    assert isinstance(implementation["os"], str)
    assert isinstance(implementation["os_version"], str)

    # dialect: supported
    response = harness.send({"cmd": "dialect", "dialect": DIALECT_2020_12})
    assert response == {"ok": True}

    # dialect: supported, with a trailing '#' stripped
    response = harness.send({"cmd": "dialect", "dialect": DIALECT_2020_12 + "#"})
    assert response == {"ok": True}

    # dialect: unsupported
    response = harness.send(
        {"cmd": "dialect", "dialect": "http://json-schema.org/draft-07/schema#"}
    )
    assert response == {"ok": False}

    # re-select the supported dialect for the runs below
    harness.send({"cmd": "dialect", "dialect": DIALECT_2020_12})

    # run: registry-served remote reference
    response = harness.send(
        {
            "cmd": "run",
            "seq": 1,
            "case": {
                "description": "remote ref via registry",
                "schema": {"$ref": "http://example.com/r"},
                "registry": {"http://example.com/r": {"type": "integer"}},
                "tests": [
                    {"description": "an integer", "instance": 1, "valid": True},
                    {"description": "a string", "instance": "x", "valid": False},
                ],
            },
            "output": "flag",
        }
    )
    assert response == {
        "seq": 1,
        "results": [{"valid": True}, {"valid": False}],
    }

    # run: annotations output is skipped until M5
    response = harness.send(
        {
            "cmd": "run",
            "seq": 2,
            "case": {
                "description": "annotations requested",
                "schema": True,
                "tests": [{"description": "anything", "instance": 1}],
            },
            "output": "annotations",
        }
    )
    assert response == {
        "seq": 2,
        "skipped": True,
        "message": "annotation output arrives in M5",
    }

    # run: schema loads, but a $ref inside it cannot be resolved at
    # evaluation time -> per-test errored, not a case-level failure.
    response = harness.send(
        {
            "cmd": "run",
            "seq": 3,
            "case": {
                "description": "unresolvable ref",
                "schema": {"$ref": "http://nope.example/missing"},
                "tests": [{"description": "anything", "instance": 1}],
            },
            "output": "flag",
        }
    )
    assert response["seq"] == 3
    assert "results" in response
    assert len(response["results"]) == 1
    (result,) = response["results"]
    assert result["errored"] is True
    assert "message" in result["context"]
    assert "traceback" in result["context"]

    # run: the schema itself is invalid -> case-level errored, no per-test
    # results at all. A bare string is not a valid schema value.
    response = harness.send(
        {
            "cmd": "run",
            "seq": 4,
            "case": {
                "description": "invalid schema",
                "schema": "not-a-schema",
                "tests": [{"description": "anything", "instance": 1}],
            },
            "output": "flag",
        }
    )
    assert response["seq"] == 4
    assert response["errored"] is True
    assert "message" in response["context"]
    assert "traceback" in response["context"]
    assert "results" not in response

    # stop: flushes and exits, with no response line of its own
    harness.send_no_response({"cmd": "stop"})
    harness.close(expected_returncode=0)


def test_start_rejects_unsupported_version() -> None:
    harness = HarnessProcess()
    response = harness.send({"cmd": "start", "version": 2})
    assert response["errored"] is True
    harness.proc.wait(timeout=10)
    assert harness.proc.returncode != 0
