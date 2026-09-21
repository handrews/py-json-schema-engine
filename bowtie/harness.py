"""Bowtie IO-protocol harness (version 1) for json-schema-engine.

Bowtie (https://github.com/bowtie-json-schema/bowtie) drives conformance
harnesses over a line-delimited JSON protocol on stdin/stdout: one command
per line in, one response per line out, never interleaved. This harness
speaks protocol version 1 only, using the public engine API
(`json_schema_engine.core`) exactly as any other embedder would.

Case registries (`case["registry"]`) are served to the engine as a loader
for the duration of a single `run` command, so remote `$ref`s resolve
exactly the way a real application's loader would, rather than being
inlined ahead of time.

Only `output: "flag"` is served; `"annotations"` cases are reported as
skipped. The engine renders annotations (M5), but wiring Bowtie's
annotation protocol is a separate piece of work.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
import traceback
from collections.abc import Callable, Iterable
from typing import IO, Any

from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
    JsonSchemaEngineError,
    LoadedDocument,
    create_engine,
)

PROTOCOL_VERSION = 1

# Neutral retrieval URI for case schemas that carry no `$id` of their own;
# an http-scheme URI so relative references resolve through normal URI
# resolution rather than needing special-cased handling.
RETRIEVAL_URI = "urn:bowtie:schema"

SUPPORTED_DIALECTS = [
    DIALECT_2020_12,
    DIALECT_2019_09,
    DIALECT_DRAFT_07,
    DIALECT_DRAFT_06,
]

IMPLEMENTATION = {
    "language": "python",
    "name": "json-schema-engine",
    "homepage": "https://github.com/handrews/py-json-schema-engine",
    "issues": "https://github.com/handrews/py-json-schema-engine/issues",
    "source": "https://github.com/handrews/py-json-schema-engine",
    "dialects": SUPPORTED_DIALECTS,
}


def _error_context(exc: BaseException) -> dict[str, str]:
    return {
        "message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }


def _registry_loader(
    registry: dict[str, Any],
) -> Callable[[str], LoadedDocument | None]:
    """Build a loader over a case's registry (D7: served as a real loader).

    Bowtie registry keys are not guaranteed to carry the same trailing-`#`
    form the engine normalizes URIs to, so a miss is retried once with a
    trailing `#` stripped before giving up.
    """

    def loader(uri: str) -> LoadedDocument | None:
        if uri in registry:
            return LoadedDocument(registry[uri], uri)
        stripped = uri.rstrip("#")
        if stripped in registry:
            return LoadedDocument(registry[stripped], uri)
        return None

    return loader


class Harness:
    """Holds the small bit of state the protocol carries between commands."""

    def __init__(self) -> None:
        self.current_dialect: str = SUPPORTED_DIALECTS[0]

    def handle_start(self, request: dict[str, Any]) -> dict[str, Any] | None:
        version = request.get("version")
        if version != PROTOCOL_VERSION:
            return {
                "version": PROTOCOL_VERSION,
                "errored": True,
                "context": {
                    "message": f"unsupported protocol version: {version!r}",
                },
            }
        return {
            "version": PROTOCOL_VERSION,
            "implementation": {
                **IMPLEMENTATION,
                "version": importlib.metadata.version("json-schema-engine"),
                "language_version": platform.python_version(),
                "os": platform.system(),
                "os_version": platform.release(),
            },
        }

    def handle_dialect(self, request: dict[str, Any]) -> dict[str, Any]:
        dialect = str(request["dialect"]).rstrip("#")
        self.current_dialect = dialect
        return {"ok": dialect in SUPPORTED_DIALECTS}

    def handle_run(self, request: dict[str, Any]) -> dict[str, Any]:
        seq = request["seq"]
        case = request["case"]
        output = request.get("output", "flag")

        if output == "annotations":
            return {
                "seq": seq,
                "skipped": True,
                "message": "this harness serves flag output only",
            }

        try:
            registry: dict[str, Any] = case.get("registry") or {}
            engine = create_engine(
                default_dialect=self.current_dialect,
                loaders=[_registry_loader(registry)],
            )
            uri = engine.load_schema(case["schema"], RETRIEVAL_URI)
        except JsonSchemaEngineError as exc:
            return {"seq": seq, "errored": True, "context": _error_context(exc)}
        except Exception as exc:
            return {"seq": seq, "errored": True, "context": _error_context(exc)}

        results: list[dict[str, Any]] = []
        for test in case["tests"]:
            try:
                result = engine.evaluate(uri, test["instance"])
                results.append({"valid": result.valid})
            except Exception as exc:
                results.append({"errored": True, "context": _error_context(exc)})
        return {"seq": seq, "results": results}


def _write(stdout: IO[str], response: dict[str, Any]) -> None:
    stdout.write(json.dumps(response) + "\n")
    stdout.flush()


def main(stdin: IO[str], stdout: IO[str]) -> int:
    harness = Harness()
    for line in _iter_lines(stdin):
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"bowtie harness: invalid JSON: {exc}", file=sys.stderr)
            continue

        cmd = request.get("cmd")
        if cmd == "start":
            response = harness.handle_start(request)
            if response is None:
                continue
            _write(stdout, response)
            if response.get("errored"):
                return 1
        elif cmd == "dialect":
            _write(stdout, harness.handle_dialect(request))
        elif cmd == "run":
            _write(stdout, harness.handle_run(request))
        elif cmd == "stop":
            return 0
        else:
            print(f"bowtie harness: unknown cmd: {cmd!r}", file=sys.stderr)
    return 0


def _iter_lines(stdin: IO[str]) -> Iterable[str]:
    for raw_line in stdin:
        line = raw_line.strip()
        if line:
            yield line


if __name__ == "__main__":
    raise SystemExit(main(sys.stdin, sys.stdout))
