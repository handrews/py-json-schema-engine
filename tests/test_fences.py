# The P5 fences (DESIGN.md D10, P5): the interpreter core and ecma_regex
# never generate code, and only the compiler's one instantiation module
# does. import-linter covers module imports; this test covers the builtins
# `compile`/`exec`/`eval`, which are not imports, by walking the sources
# and by an audit-hook proof in a fresh interpreter.

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "json_schema_engine" / "core"
ECMA = ROOT / "packages" / "ecma-regex" / "src" / "ecma_regex"
COMPILER = ROOT / "src" / "json_schema_engine" / "compiler"
CODEGEN = {"compile", "exec", "eval"}


def _codegen_calls(path: Path, *, ast_allowed: bool = False) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in CODEGEN:
                found.append(func.id)
            elif (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "builtins"
                and func.attr in CODEGEN
            ):
                found.append(func.attr)
        elif ast_allowed:
            continue
        elif isinstance(node, ast.Import):
            if any(alias.name == "ast" for alias in node.names):
                found.append("import ast")
        elif isinstance(node, ast.ImportFrom):
            # Absolute only: `ecma_regex` has a package-relative `ast`
            # module of its own (the regex AST), which is not the stdlib.
            if node.level == 0 and node.module == "ast":
                found.append("import ast")
    return found


def test_core_and_ecma_regex_never_generate_code() -> None:
    for package in (CORE, ECMA):
        for path in sorted(package.rglob("*.py")):
            assert _codegen_calls(path) == [], path


def test_only_runtime_compile_materializes_code() -> None:
    # The compiler may build `ast` trees anywhere; it may turn one into code
    # in exactly one place.
    for path in sorted(COMPILER.rglob("*.py")):
        calls = _codegen_calls(path, ast_allowed=True)
        if path.name == "runtime_compile.py":
            assert sorted(calls) == ["compile", "exec"], path
        else:
            assert calls == [], path


# The hook goes in after the imports: the import system itself raises
# `exec` events while executing module code, which is not the engine
# generating anything.
AUDIT_PROBE = """
import sys
from json_schema_engine.core import create_engine
engine = create_engine()
uri = engine.register_schema(
    {"type": "object", "properties": {"a": {"pattern": "^x"}}, "required": ["a"]},
    "https://fences.example/s",
)
events = []
def hook(name, args):
    if name in ("compile", "exec"):
        events.append(name)
sys.addaudithook(hook)
assert engine.evaluate(uri, {"a": "xy"}).valid
assert not engine.evaluate(uri, {"a": "y"}, output="hierarchical").valid
engine.register_schema({"pattern": "b+"}, "https://fences.example/t")
print(len(events))
"""


def test_interpretation_raises_no_codegen_audit_events() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", AUDIT_PROBE], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "0", completed.stderr


COMPILE_PROBE = """
import sys
from json_schema_engine.core import create_engine
from json_schema_engine.compiler import compile_validator
engine = create_engine()
uri = engine.register_schema({"type": "string"}, "https://fences.example/s")
ours = []
imports = []
def hook(name, args):
    # The import system also compiles and executes module bodies (on some
    # versions `ast.unparse` lazily imports a stdlib helper): those carry a
    # `.py` filename and bytes source, and are not code generation.
    if name == "compile":
        source, filename = args[0], args[1]
        if type(source).__name__ == "Module":
            ours.append(("compile", "ast"))
        elif isinstance(source, bytes) and str(filename).endswith(".py"):
            imports.append(("compile", filename))
        else:
            ours.append(("compile", "TEXT:" + type(source).__name__))
    elif name == "exec":
        filename = getattr(args[0], "co_filename", "")
        if filename == "<json_schema_engine.compiler>":
            ours.append(("exec", filename))
        elif filename.endswith(".py"):
            imports.append(("exec", filename))
        else:
            ours.append(("exec", "OTHER:" + filename))
sys.addaudithook(hook)
validate = compile_validator(engine, uri).validate
assert validate("x") and not validate(1)
print(ours, validate.__code__.co_filename)
"""


def test_compiling_raises_exactly_one_compile_and_one_exec_event() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", COMPILE_PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == (
        "[('compile', 'ast'), ('exec', '<json_schema_engine.compiler>')] "
        "<json_schema_engine.compiler>"
    ), completed.stderr
