# The M6 smoke differential: the spike fixtures and a suite subset, every
# case evaluated by the interpreter and by the compiled validator (both
# optimization settings), verdicts and exception classes equal.

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from json_schema_engine.compiler import compile_validator, explain_compilation
from json_schema_engine.core import (
    Engine,
    JsonSchemaEngineError,
    JsonValue,
    create_engine,
)
from json_schema_engine.test_kit import SuiteCase, load_suite_file, suite_remotes_loader

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
SUITE_DIR = ROOT / "test-suite" / "tests" / "draft2020-12"
REMOTES_DIR = ROOT / "test-suite" / "remotes"
RETRIEVAL_URI = "https://smoke.example/schema"

type Outcome = tuple[str, object]


def outcome(run: Callable[[], bool]) -> Outcome:
    try:
        return ("valid", run())
    except JsonSchemaEngineError as error:
        return ("raise", type(error).__name__)


def assert_parity(engine: Engine, uri: str, instance: JsonValue) -> None:
    expected = outcome(lambda: engine.evaluate(uri, instance).valid)
    for conservative in (False, True):
        validate = compile_validator(engine, uri, conservative=conservative).validate
        assert outcome(lambda validate=validate: validate(instance)) == expected, (
            instance,
            conservative,
        )


def load_fixture(name: str) -> JsonValue:
    return json.loads((FIXTURES / f"{name}.schema.json").read_text())


USER_OK: JsonValue = {
    "id": 1,
    "name": "Ada",
    "email": "ada@example.com",
    "tags": ["x"],
    "role": "admin",
    "address": {"street": "s", "city": "c", "zip": "12345"},
}


@pytest.mark.parametrize(
    "instance",
    [
        USER_OK,
        {**USER_OK, "id": 0},
        {**USER_OK, "id": 1.0},
        {**USER_OK, "id": True},
        {**USER_OK, "name": ""},
        {**USER_OK, "email": "nope"},
        {**USER_OK, "role": "root"},
        {**USER_OK, "tags": list(range(11))},
        {**USER_OK, "tags": ["a", 1]},
        {**USER_OK, "address": {"street": "s"}},
        {**USER_OK, "address": {**USER_OK["address"], "zip": "1"}},  # type: ignore[index]
        {**USER_OK, "extra": 1},
        {"id": 1},
        [],
        None,
        "user",
    ],
)
def test_user_fixture_parity(instance: JsonValue) -> None:
    engine = create_engine()
    uri = engine.register_schema(load_fixture("user"), "https://spike.example/user")
    assert_parity(engine, uri, instance)


@pytest.mark.parametrize("name", ["event", "profile", "static-consumer", "island"])
def test_other_fixtures_compile_and_agree_on_probes(name: str) -> None:
    engine = create_engine()
    uri = engine.register_schema(load_fixture(name), f"https://spike.example/{name}")
    probes: list[JsonValue] = [
        {},
        {"a": "x", "p": "y"},
        {"a": 1, "p": 2},
        {"kind": "created", "id": "i", "actor": "a", "createdAt": "t"},
        {"kind": "created", "id": "i", "actor": "a", "createdAt": "t", "x": 1},
        [],
        "s",
    ]
    for probe in probes:
        assert_parity(engine, uri, probe)


def test_island_plan_reports_the_dynamic_unit() -> None:
    engine = create_engine()
    uri = engine.register_schema(load_fixture("island"), "https://spike.example/island")
    compiled = compile_validator(engine, uri)
    explanation = explain_compilation(compiled.plan)
    # The fixture's site has two possible declarers (M9): it stays an island.
    assert explanation.causes == {"dynamic": 1}
    assert explanation.interpreted_keys == ("https://spike.example/genericList#/items",)
    assert explanation.resolved_dynamic_sites == ()
    assert "H_FRAG(T[0]" in compiled.source
    assert "s = (*s, 'https://spike.example/genericList')" in compiled.source


# --- suite subset -----------------------------------------------------------

SUBSET_FILES = [
    "dynamicRef",
    "infinite-loop-detection",
    "ref",
    "refRemote",
    "anyOf",
    "type",
    "required",
    "pattern",
    "properties",
]


def _subset_cases() -> list[SuiteCase]:
    cases: list[SuiteCase] = []
    for name in SUBSET_FILES:
        cases.extend(load_suite_file(SUITE_DIR / f"{name}.json"))
    return cases


@pytest.mark.parametrize(
    "case", _subset_cases(), ids=lambda c: f"{c.file}/{c.group}/{c.description}"
)
def test_suite_subset_parity(case: SuiteCase) -> None:
    engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    uri = engine.load_schema(case.schema, RETRIEVAL_URI)
    assert engine.evaluate(uri, case.data).valid is case.valid
    assert_parity(engine, uri, case.data)
