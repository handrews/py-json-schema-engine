# The one place code is materialized (DESIGN.md D10, P5): `compile()` of
# the emitted `ast.Module` and `exec()` into the runtime namespace.
# Confining both calls here keeps the code-generation story auditable —
# `tests/test_fences.py` asserts they appear nowhere else, and an audit
# hook (`sys.addaudithook`) sees exactly one `compile` and one `exec`
# event per artifact, tagged with `FILENAME`. `sys.setrecursionlimit` is
# never touched (P3): the depth budget and the `RecursionError` backstop
# are the bounds.
#
# Dependency direction: imports `ast` and core's `JsonValue`. The public
# API imports this.

import ast
from collections.abc import Callable
from typing import cast

from json_schema_engine.compiler.emit import VALIDATE
from json_schema_engine.core.json_model import JsonValue

FILENAME = "<json_schema_engine.compiler>"

type Validator = Callable[[JsonValue], bool]


def instantiate(module: ast.Module, namespace: dict[str, object]) -> Validator:
    """Execute an emitted module in `namespace` and return its `validate`."""
    return cast(Validator, instantiate_entry(module, namespace, VALIDATE))


def instantiate_entry(
    module: ast.Module, namespace: dict[str, object], entry: str
) -> Callable[..., object]:
    """Execute an emitted module in `namespace` and return its `entry`
    function (`validate` for a flag artifact, `evaluate` for an evaluator)."""
    code = compile(module, FILENAME, "exec")
    exec(code, namespace)
    return cast(Callable[..., object], namespace[entry])
