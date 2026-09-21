# Standalone-emission smoke (DESIGN.md D10; CI): emit one module and import
# it in a fresh interpreter, proving the compiler package is not needed to
# run it and that the verdicts match the interpreter's.
#
# Local + CI: `uv run python scripts/standalone_smoke.py`.

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from json_schema_engine.compiler import emit_standalone
from json_schema_engine.core import JsonValue, create_engine
from json_schema_engine.formats import FORMATS_2020_12

SCHEMA: JsonValue = {
    "type": "object",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "name": {"type": "string", "pattern": "^[a-z]+$"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "email": {"format": "email"},
    },
    "additionalProperties": False,
}
INSTANCES: list[JsonValue] = [
    {"id": 1, "name": "ada"},
    {"id": 0, "name": "ada"},
    {"id": 1, "name": "Ada"},
    {"id": 1, "name": "ada", "tags": ["a", "b", "c", "d"]},
    {"id": 1, "name": "ada", "extra": True},
    [],
    {"id": 1, "name": "ada", "email": "ada@example.com"},
    {"id": 1, "name": "ada", "email": "nope"},
]

PROBE = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("standalone_smoke_module", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert "json_schema_engine.compiler" not in sys.modules, "the compiler was imported"
expected = json.load(open(sys.argv[2]))
for instance, verdict in expected:
    assert module.validate(instance) is verdict, (instance, verdict)
print("STANDALONE SMOKE PASS", len(expected), "verdicts")
"""


def main() -> int:
    engine = create_engine(formats=FORMATS_2020_12, assert_formats=True)
    uri = engine.register_schema(SCHEMA, "https://smoke.example/schema")
    expected = [(i, engine.evaluate(uri, i).valid) for i in INSTANCES]
    with tempfile.TemporaryDirectory() as directory:
        module_path = Path(directory) / "artifact.py"
        module_path.write_text(emit_standalone(engine, uri))
        manifest = Path(directory) / "expected.json"
        manifest.write_text(json.dumps(expected))
        completed = subprocess.run(
            [sys.executable, "-c", PROBE, str(module_path), str(manifest)],
            capture_output=True,
            text=True,
            check=False,
        )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
