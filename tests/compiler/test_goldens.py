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

from json_schema_engine.compiler import compile_validator
from json_schema_engine.compiler.emit import BUILTINS_USED
from json_schema_engine.core import create_engine

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = Path(__file__).parent / "goldens"
NAMES = ["user", "island"]


def compile_fixture(name: str) -> str:
    engine = create_engine()
    schema = json.loads((FIXTURES / f"{name}.schema.json").read_text())
    uri = engine.register_schema(schema, f"https://spike.example/{name}")
    compiled = compile_validator(engine, uri)
    # The source is the module: parsing it back gives the same tree.
    assert ast.dump(ast.parse(compiled.source)) == ast.dump(compiled.module)
    return compiled.source


@pytest.mark.parametrize("name", NAMES)
def test_golden(name: str) -> None:
    source = compile_fixture(name)
    golden = GOLDENS / f"{name}.flag.py"
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
        "H_DEEP",
        "H_MAXD",
        "MaxDepthExceededError",
    } | BUILTINS_USED
    for node in ast.walk(module):
        if isinstance(node, ast.Name):
            assert node.id in minted or (
                node.id[0] in "ubtgcrk" and node.id[1:].isdigit()
            ), node.id
        elif isinstance(node, ast.arg):
            assert node.arg in ("v", "d", "s")
        elif isinstance(node, ast.FunctionDef):
            assert node.name == "validate" or (
                node.name[0] == "u" and node.name[1:].isdigit()
            )
