# D12: serves the official suite's test-suite/remotes/ tree for the URIs
# suite files reference via $ref/$id, so $ref resolution against the suite
# has something to resolve against without a real HTTP server.
#
# IP policy (DESIGN.md D15): implementation from the official test suite's
# own remotes/ layout only. Shaped to satisfy the engine's loader contract
# structurally (P4: `Loader = Callable[[str], LoadedDocument | None]`)
# without test-kit depending on json_schema_engine.core — mirrors the TS
# engine's own `suiteRemotesLoader` (our prior work), rewritten in Python.

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from json_schema_engine.test_kit.suite import Json, reject_non_finite_constant


@dataclass(frozen=True)
class LoadedDocument:
    """Duck-typed to core's loader-result contract (P4): a successful load
    carries the parsed value and the URI it was ultimately retrieved from.
    Defined locally, not imported from json_schema_engine.core, since
    test-kit must not depend on core (import-linter contract) — the real
    engine only needs this shape to match structurally, not by identity.
    """

    value: Json
    uri: str


def suite_remotes_loader(
    remotes_dir: Path, base_url: str = "http://localhost:1234/"
) -> Callable[[str], LoadedDocument | None]:
    """Returns a loader (P4: sync, ``None`` on miss, never raises) that
    resolves a suite-referenced URI under ``base_url`` to a file under
    ``remotes_dir``.

    A URI outside ``base_url``, one that escapes ``remotes_dir`` via a
    ``..`` path segment, or one with no corresponding file, is a loader
    miss — ``None`` — not an error, per the loader contract. Any fragment on
    the requested URI is dropped before mapping to a path, since fragments
    identify a location *within* a retrieved document, not a different
    document.
    """

    def load(uri: str) -> LoadedDocument | None:
        uri_without_fragment = uri.split("#", 1)[0]
        if not uri_without_fragment.startswith(base_url):
            return None
        relative = uri_without_fragment[len(base_url) :]
        segments = relative.split("/") if relative else []
        if any(segment == ".." for segment in segments):
            return None

        path = remotes_dir.joinpath(*segments) if segments else remotes_dir
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        value: Json = json.loads(text, parse_constant=reject_non_finite_constant)
        return LoadedDocument(value=value, uri=uri_without_fragment)

    return load
