# Bench corpora (M6 Step 5): named instance sets with oracle-derived
# expected verdicts. Every corpus's `expected` list comes from the
# interpreter (`create_engine().evaluate(...).valid`) — the reference
# semantics that the harness's oracle-first step checks every subject
# against before timing it.
#
# `records.py` and `api_payload.py` live alongside the vendored schema
# fixtures in `corpora/` (they generate corpus instances, and `records.py`
# also generates its schema) but are loaded here by file path rather than
# as submodules: `corpora.py` and the sibling `corpora/` directory share a
# name, and a regular module always shadows a same-named namespace-package
# directory for dotted imports, so neither generator can be reached as
# `json_schema_engine.bench.corpora.<name>`. Any future generator follows
# the same `_load_module_from` path.

from __future__ import annotations

import copy
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from json_schema_engine.core import JsonValue, create_engine
from json_schema_engine.core.keywords._ids import DIALECT_2020_12

_CORPORA_DIR = Path(__file__).parent / "corpora"


@dataclass(frozen=True, slots=True)
class Corpus:
    """A named instance set for the bench harness.

    `expected[i]` is the interpreter's verdict for `instances[i]` — the
    oracle every subject must agree with before it is timed.
    """

    name: str
    dialect: str
    schema: JsonValue
    instances: list[JsonValue]
    expected: list[bool] | None


def _load_module_from(filename: str, module_name: str) -> ModuleType:
    path = _CORPORA_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load generator from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_records = _load_module_from("records.py", "json_schema_engine.bench._records_gen")
_api_payload = _load_module_from(
    "api_payload.py", "json_schema_engine.bench._api_payload_gen"
)


def _read_schema(filename: str) -> JsonValue:
    return json.loads((_CORPORA_DIR / filename).read_text())


def _oracle_expected(schema: JsonValue, instances: list[JsonValue]) -> list[bool]:
    engine = create_engine()
    uri = engine.register_schema(schema, "https://bench.example/oracle")
    return [engine.evaluate(uri, instance).valid for instance in instances]


def _corpus(name: str, filename: str, instances: list[JsonValue]) -> Corpus:
    schema = _read_schema(filename)
    return Corpus(
        name=name,
        dialect=DIALECT_2020_12,
        schema=schema,
        instances=instances,
        expected=_oracle_expected(schema, instances),
    )


# --- user ------------------------------------------------------------------

_USER_VALID: list[JsonValue] = [
    {"id": 1, "name": "Ada", "email": "ada@example.com", "tags": []},
    {
        "id": 2,
        "name": "Grace",
        "email": "grace@example.com",
        "tags": ["a"],
        "role": "admin",
    },
    {
        "id": 3,
        "name": "Alan",
        "email": "alan@example.com",
        "tags": ["x", "y"],
        "role": "user",
        "address": {"street": "1 Infinite Loop", "city": "Cupertino"},
    },
    {
        "id": 4,
        "name": "Barbara",
        "email": "barbara@example.com",
        "tags": [],
        "address": {"street": "10 Downing St", "city": "London", "zip": "12345"},
    },
    {"id": 5, "name": "M" * 100, "email": "m@example.com", "tags": []},
    {
        "id": 6,
        "name": "Ten Tags",
        "email": "t@example.com",
        "tags": [f"t{i}" for i in range(10)],
    },
    {"id": 7, "name": "Guest", "email": "g@example.com", "tags": [], "role": "guest"},
    {
        "id": 8,
        "name": "Full",
        "email": "full@example.com",
        "tags": ["a", "b"],
        "role": "admin",
        "address": {"street": "1 Main St", "city": "Springfield", "zip": "00501"},
    },
]

_USER_INVALID: list[JsonValue] = [
    {"id": 1, "name": "Missing Email", "tags": []},
    {"id": 0, "name": "Zero Id", "email": "z@example.com", "tags": []},
    {"id": 1, "name": "", "email": "e@example.com", "tags": []},
    {"id": 1, "name": "M" * 101, "email": "m@example.com", "tags": []},
    {"id": 1, "name": "Bad Email", "email": "not-an-email", "tags": []},
    {"id": 1, "name": "Bad Role", "email": "r@example.com", "tags": [], "role": "root"},
    {
        "id": 1,
        "name": "Too Many Tags",
        "email": "m@example.com",
        "tags": [f"t{i}" for i in range(11)],
    },
    {"id": 1, "name": "Extra", "email": "e@example.com", "tags": [], "extra": True},
    {
        "id": 1,
        "name": "Bad Address",
        "email": "a@example.com",
        "tags": [],
        "address": {"street": "1 Main St"},
    },
    {
        "id": 1,
        "name": "Bad Zip",
        "email": "z@example.com",
        "tags": [],
        "address": {"street": "1 Main St", "city": "Metropolis", "zip": "abcde"},
    },
]


def _load_user() -> Corpus:
    return _corpus("user", "user.schema.json", _USER_VALID + _USER_INVALID)


# --- event -------------------------------------------------------------------

_EVENT_VALID: list[JsonValue] = [
    {
        "id": "e1",
        "actor": "user1",
        "createdAt": "2026-01-01T00:00:00Z",
        "kind": "created",
    },
    {
        "id": "e2",
        "actor": "user2",
        "createdAt": "2026-01-02T00:00:00Z",
        "updatedAt": "2026-01-03T00:00:00Z",
        "kind": "updated",
    },
    {
        "id": "e3",
        "actor": "user3",
        "createdAt": "2026-01-04T00:00:00Z",
        "kind": "deleted",
    },
    {"id": "", "actor": "", "createdAt": "epoch", "kind": "created"},
]

_EVENT_INVALID: list[JsonValue] = [
    {"id": "e5", "actor": "user5", "createdAt": "2026-01-01T00:00:00Z"},
    {"actor": "user6", "createdAt": "2026-01-01T00:00:00Z", "kind": "created"},
    {"id": "e7", "createdAt": "2026-01-01T00:00:00Z", "kind": "created"},
    {"id": "e8", "actor": "user8", "kind": "created"},
    {
        "id": "e9",
        "actor": "user9",
        "createdAt": "2026-01-01T00:00:00Z",
        "kind": "archived",
    },
    {
        "id": "e10",
        "actor": "user10",
        "createdAt": "2026-01-01T00:00:00Z",
        "kind": "created",
        "extra": True,
    },
    {
        "id": 11,
        "actor": "user11",
        "createdAt": "2026-01-01T00:00:00Z",
        "kind": "created",
    },
    {
        "id": "e12",
        "actor": "user12",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": 12,
        "kind": "created",
    },
    {"id": "e13", "actor": "user13", "createdAt": "2026-01-01T00:00:00Z", "kind": 13},
]


def _load_event() -> Corpus:
    return _corpus("event", "event.schema.json", _EVENT_VALID + _EVENT_INVALID)


# --- profile -----------------------------------------------------------------

_PROFILE_VALID: list[JsonValue] = [
    {"id": "u1"},
    {"id": "u2", "displayName": "Ada"},
    {"id": "u3", "bio": "Mathematician"},
    {"id": "u4", "createdAt": "2026-01-01T00:00:00Z"},
    {
        "id": "u5",
        "displayName": "Grace",
        "bio": "Rear Admiral",
        "createdAt": "2026-01-01T00:00:00Z",
    },
    {"id": "u6", "unknownField": "allowed"},
    {"id": "u7", "displayName": ""},
    {"id": "12345"},
]

_PROFILE_INVALID: list[JsonValue] = [
    {"displayName": "No Id"},
    {"id": 1},
    {"id": "u9", "displayName": 9},
    {"id": "u10", "bio": ["not", "a", "string"]},
    {"id": "u11", "createdAt": True},
    {"id": None},
    ["not", "an", "object"],
    {"id": ["u13"]},
]


def _load_profile() -> Corpus:
    return _corpus("profile", "profile.schema.json", _PROFILE_VALID + _PROFILE_INVALID)


# --- oas-document --------------------------------------------------------
#
# The official OpenAPI 3.1 meta-schema (Apache-2.0, vendored verbatim: no
# external `$ref`s, but four `$dynamicRef: "#meta"` sites) validating a
# hand-authored OpenAPI 3.1 description (MIT, this repo). The schema
# carries its own absolute `$id`
# (https://spec.openapis.org/oas/3.1/schema/2025-09-15); `register_schema`
# resolves that `$id` as the canonical URI regardless of the retrieval URI
# passed in, so `_oracle_expected`'s fixed oracle URI is not a conflict —
# each corpus load builds its own fresh engine.


def _load_oas_document() -> Corpus:
    document = _read_schema("openapi-document.json")
    invalid_document = copy.deepcopy(document)
    assert isinstance(invalid_document, dict)
    invalid_document["openapi"] = 4  # wrong type AND wrong pattern
    return _corpus("oas-document", "oas-3.1-schema.json", [document, invalid_document])


# --- api-payload -----------------------------------------------------------
#
# A moderate hand-authored object schema (MIT, this repo) over generated
# request-payload instances; see `corpora/api_payload.py` for the
# generator.


def _load_api_payload() -> Corpus:
    schema = _read_schema("api-payload-schema.json")
    instances, _by_construction = _api_payload.build_api_payloads()
    return Corpus(
        name="api-payload",
        dialect=DIALECT_2020_12,
        schema=schema,
        instances=instances,
        expected=_oracle_expected(schema, instances),
    )


# --- generated records ---------------------------------------------------


def _load_records(variant: str) -> Corpus:
    schema = _records.build_records_schema()
    # `records.py` tracks which instances it deliberately corrupted, but the
    # oracle is still the interpreter — not the generator's own bookkeeping.
    instances, _by_construction = _records.build_records(variant)
    return Corpus(
        name=f"records-{variant}",
        dialect=DIALECT_2020_12,
        schema=schema,
        instances=instances,
        expected=_oracle_expected(schema, instances),
    )


_LOADERS = {
    "user": _load_user,
    "event": _load_event,
    "profile": _load_profile,
    "oas-document": _load_oas_document,
    "api-payload": _load_api_payload,
    "records-uniform": lambda: _load_records("uniform"),
    "records-sparse": lambda: _load_records("sparse"),
}

CORPUS_NAMES = tuple(_LOADERS)


def load_corpus(name: str) -> Corpus:
    """Build the named corpus (`user`, `event`, `profile`, `oas-document`,
    `api-payload`, `records-uniform`, `records-sparse`)."""
    try:
        loader = _LOADERS[name]
    except KeyError:
        raise KeyError(
            f"unknown corpus {name!r}; known: {', '.join(CORPUS_NAMES)}"
        ) from None
    return loader()


def load_all_corpora() -> list[Corpus]:
    """Every named corpus, in a stable order."""
    return [load_corpus(name) for name in CORPUS_NAMES]
