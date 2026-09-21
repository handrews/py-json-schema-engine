# Compiled format assertion (DESIGN.md D9 format hoisting; M7): the plan's
# format list, the hoisted `fmtN` bindings, parity with the interpreter in
# both optimization settings, the runtime's single-table guard, and the
# standalone module's predicate imports.

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from json_schema_engine.compiler import (
    FormatTableError,
    StandaloneUnsupportedError,
    build_plan,
    compile_validator,
    emit_standalone,
)
from json_schema_engine.compiler.runtime import make_runtime
from json_schema_engine.core import FormatDefinition, JsonValue, create_engine
from json_schema_engine.formats import FORMATS_2020_12
from json_schema_engine.formats.net import ipv4


def _is_int32(value: object) -> bool:
    return isinstance(value, int | float) and -(2**31) <= value < 2**31


CUSTOM = {
    "ipv4": FormatDefinition(ipv4, import_path="json_schema_engine.formats.net:ipv4"),
    "int32": FormatDefinition(_is_int32, types=("integer",)),
}


def test_plan_lists_only_asserted_known_formats() -> None:
    engine = create_engine(formats=CUSTOM, assert_formats=True)
    uri = engine.register_schema(
        {"properties": {"a": {"format": "ipv4"}, "b": {"format": "no-such"}}},
        "https://cfmt.example/s",
    )
    plan = build_plan(engine, uri)
    assert plan.formats == ("ipv4",)
    assert all(u.kind == "static" for u in plan.units.values())
    plain = create_engine()
    uri = plain.register_schema({"format": "ipv4"}, "https://cfmt.example/p")
    assert build_plan(plain, uri).formats == ()


def test_compiled_agrees_with_the_interpreter() -> None:
    engine = create_engine(formats=CUSTOM, assert_formats=True)
    uri = engine.register_schema(
        {"properties": {"a": {"format": "ipv4"}, "n": {"format": "int32"}}},
        "https://cfmt.example/s",
    )
    compiled = compile_validator(engine, uri)
    assert "fmt0 = R.formats['ipv4']" in compiled.source
    assert "fmt0(t0)" in compiled.source or "fmt0(v" in compiled.source
    probes: list[JsonValue] = [
        {"a": "1.2.3.4"},
        {"a": "nope"},
        {"a": 5},
        {"n": 5},
        {"n": 2**40},
        {"n": 5.5},
        {"n": "5"},
        "not an object",
    ]
    conservative = compile_validator(engine, uri, conservative=True)
    for probe in probes:
        expected = engine.evaluate(uri, probe).valid
        assert compiled.validate(probe) is expected, probe
        assert conservative.validate(probe) is expected, probe


def test_runtime_refuses_a_missing_definition() -> None:
    engine = create_engine(formats=CUSTOM, assert_formats=True)
    with pytest.raises(FormatTableError, match="uuid"):
        make_runtime(
            engine.schemas.snapshot(),
            engine.regex_cache,
            (),
            512,
            formats=("uuid",),
            format_table=engine.formats,
        )
    with pytest.raises(FormatTableError):
        make_runtime(
            engine.schemas.snapshot(), engine.regex_cache, (), 512, formats=("ipv4",)
        )


RUNNER = textwrap.dedent(
    """
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("standalone_formats", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "json_schema_engine.compiler" not in sys.modules
    events = []
    def hook(name, args):
        if name in ("compile", "exec"):
            events.append(name)
    sys.addaudithook(hook)
    assert module.validate({"a": "1.2.3.4"}) is True
    assert module.validate({"a": "nope"}) is False
    assert module.validate({"a": 7}) is True
    assert events == [], events
    print("ok")
    """
)


def test_standalone_imports_the_predicate(tmp_path: Path) -> None:
    engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
    uri = engine.register_schema(
        {"properties": {"a": {"format": "ipv4"}}}, "https://cfmt.example/sa"
    )
    source = emit_standalone(engine, uri)
    assert "from json_schema_engine.formats.net import ipv4 as fmt0" in source
    assert "fmt0(" in source
    ast.parse(source)
    path = tmp_path / "artifact.py"
    path.write_text(source)
    completed = subprocess.run(
        [sys.executable, "-c", RUNNER, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_standalone_refuses_predicates_without_an_import_path() -> None:
    engine = create_engine(formats=CUSTOM, assert_formats=True)
    uri = engine.register_schema({"format": "int32"}, "https://cfmt.example/np")
    with pytest.raises(StandaloneUnsupportedError, match="import path"):
        emit_standalone(engine, uri)
    # A path that does not resolve to the table's predicate is refused too.
    bogus = {
        "ipv4": FormatDefinition(
            _is_int32, import_path="json_schema_engine.formats.net:ipv4"
        )
    }
    engine = create_engine(formats=bogus, assert_formats=True)
    uri = engine.register_schema({"format": "ipv4"}, "https://cfmt.example/bogus")
    with pytest.raises(StandaloneUnsupportedError, match="does not resolve"):
        emit_standalone(engine, uri)


def test_custom_integer_format_compiles_with_the_integer_guard() -> None:
    engine = create_engine(formats=CUSTOM, assert_formats=True)
    uri = engine.register_schema({"format": "int32"}, "https://cfmt.example/int")
    compiled = compile_validator(engine, uri)
    assert "is_integer()" in compiled.source
    validate = compiled.validate
    assert validate(2**40) is False and validate(1.0) is True and validate("x") is True
