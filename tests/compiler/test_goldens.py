# Codegen goldens (DESIGN.md D9, D10): the emitted source of each fixture,
# pinned byte for byte. A deliberate codegen change re-pins them in the
# same commit with `UPDATE_GOLDENS=1 uv run pytest tests/compiler/test_goldens.py`.
# The unparsed source must also round-trip through `ast.parse`, and every
# identifier in the module must be one the emitter minted.

import ast
import json
import os
from pathlib import Path

import pytest

from json_schema_engine.compiler import compile_evaluator, compile_validator
from json_schema_engine.compiler.emit import BUILTINS_USED
from json_schema_engine.compiler.plan import DEFAULT_MAX_DYNAMIC_WINNERS
from json_schema_engine.core import create_engine

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = Path(__file__).parent / "goldens"
# `island` keeps an unstable dynamic site (M9, specialization off);
# `dynamic-static` pins a resolved one; `tracked-consumer` a consumer
# tracked at runtime with its `anyOf` region; `dynamic-consumer` a region
# holding a resolved site; `extensible-tree` a recursive base specialized
# per extension.
NAMES = [
    "user",
    "event",
    "profile",
    "static-consumer",
    "island",
    "dynamic-static",
    "tracked-consumer",
    "dynamic-consumer",
    "extensible-tree",
]
OPTIONS: dict[str, int] = {"island": 0}


MODES = ["flag", "evaluator"]


def compile_fixture(name: str, mode: str = "flag") -> str:
    engine = create_engine()
    schema = json.loads((FIXTURES / f"{name}.schema.json").read_text())
    uri = engine.register_schema(schema, f"https://spike.example/{name}")
    cap = OPTIONS.get(name, DEFAULT_MAX_DYNAMIC_WINNERS)
    if mode == "flag":
        compiled = compile_validator(engine, uri, max_dynamic_winners=cap)
        source, module = compiled.source, compiled.module
    else:
        evaluator = compile_evaluator(
            engine, uri, annotations=True, max_dynamic_winners=cap
        )
        source, module = evaluator.source, evaluator.module
    # The source is the module: parsing it back gives the same tree.
    assert ast.dump(ast.parse(source)) == ast.dump(module)
    return source


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", NAMES)
def test_golden(name: str, mode: str) -> None:
    source = compile_fixture(name, mode)
    golden = GOLDENS / f"{name}.{mode}.py"
    if os.environ.get("UPDATE_GOLDENS") == "1":
        golden.write_text(source + "\n")
    assert source + "\n" == golden.read_text()


def test_every_identifier_is_minted() -> None:
    engine = create_engine()
    schema = json.loads((FIXTURES / "user.schema.json").read_text())
    uri = engine.register_schema(schema, "https://spike.example/user")
    module = compile_validator(engine, uri).module
    minted = {
        "validate",
        "v",
        "d",
        "s",
        "R",
        "T",
        "H_EQ",
        "H_MOF",
        "H_DUP",
        "H_FRAG",
        "H_FRAGC",
        "H_COVN",
        "H_COVI",
        "ev",
        "H_DEEP",
        "H_MAXD",
        "MaxDepthExceededError",
    } | BUILTINS_USED
    for node in ast.walk(module):
        if isinstance(node, ast.Name):
            assert node.id in minted or (
                node.id[0] in "ubtgcrkmwx" and node.id[1:].isdigit()
            ), node.id
        elif isinstance(node, ast.arg):
            assert node.arg in ("v", "d", "s", "ev")
        elif isinstance(node, ast.FunctionDef):
            assert node.name == "validate" or (
                node.name[0] == "u" and node.name[1:].isdigit()
            )
