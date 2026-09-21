# json-schema-engine (Python)

A JSON Schema implementation for Python that aims to be both spec-complete
and built for speed: an interpreter that is the reference semantics, a
compiler tier for hot paths (planned), full annotation collection, and every
standard output format. It is the Python counterpart of
[handrews/json-schema-engine](https://github.com/handrews/json-schema-engine)
and shares its architecture: two tiers, one keyword registry, a frame-scoped
record channel, and the IETF draft-03 relevance model.

Produced by Henry Andrews via Claude Code.

**Status: pre-release.** The published `0.0.1` is a name reservation with no
functionality. The `main` branch holds the interpreter core with the full
2020-12 keyword set (M2), green on every official draft2020-12 test-suite
file except those needing `$dynamicRef`, `$vocabulary`, or the bundled
metaschema, which land in M3. [DESIGN.md](DESIGN.md) is the design contract and
carries the milestone status.

The regular-expression translator lives in its own package,
[`ecma-regex`](packages/ecma-regex/README.md): ECMA-262 patterns for Python,
with JavaScript semantics, no dependency on this engine.

## Install

```sh
pip install json-schema-engine
```

Do not expect functionality from `0.0.1`; install from source until the
first functional release.

## Use

```python
from json_schema_engine.core import create_engine

engine = create_engine()
uri = engine.register_schema(
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
    "https://example.com/person",
)
assert engine.evaluate(uri, {"name": "Ada"}).valid
result = engine.evaluate(uri, {}, output="list")
assert result.errors is not None and result.errors[0]["evaluationPath"] == "/required"
```

`create_engine(validate_schemas=True)` checks every registered document
against its metaschema and raises `SchemaValidationError` with the errors.
A loader that reports source positions (see the test-kit's
`parse_json_with_ranges`) lets `evaluate(..., positions=True)` attach a
`source` location to every error and annotation, and `engine.locate()`
answers the same question for any schema location.

## Development

```sh
uv sync --all-packages --all-groups
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run lint-imports
```

The official test suite is a git submodule at `test-suite/`; clone with
`--recurse-submodules` or run `git submodule update --init`.

The [Bowtie](https://bowtie.report) conformance leg builds a container
image and runs the suite through Bowtie's harness protocol. It needs a
reachable container engine (Docker, or `podman machine start`) and fetches
Bowtie through `uvx`:

```sh
uv run python scripts/bowtie_check.py
```

## IP policy

The implementation is written from the JSON Schema specifications and the
official test suite only. Other validators are executed as benchmark subjects
and correctness oracles; their source is never used as an implementation
reference. See [DESIGN.md](DESIGN.md) §0.
