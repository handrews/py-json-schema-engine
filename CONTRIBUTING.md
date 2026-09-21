# Contributing

This document covers setup, the gates, and repository conventions. Design
rationale and milestone status live in [DESIGN.md](DESIGN.md); user-facing
usage lives in [docs/guide/](docs/guide/index.md) and
[docs/reference.md](docs/reference.md). Do not look for either here.

## Setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), git. Optional
for the Bowtie conformance leg: a reachable container engine (Docker, or
`podman machine start`).

```sh
git clone <repo>
cd py-json-schema-engine
git submodule update --init   # the official JSON-Schema-Test-Suite
uv sync --all-packages --all-groups
```

The official test suite is a git submodule at `test-suite/`; most of the
test tree (`tests/suite/`, the compiler's parity tests, the standalone
smoke) reads schemas and cases from it directly, so it must be checked out
before running the suite.

## Repository layout

| Path                    | Contents                                                             |
| ------------------------ | --------------------------------------------------------------------- |
| `src/json_schema_engine/core`     | The interpreter: registry, dialects, evaluation, output renderers |
| `src/json_schema_engine/compiler` | The compiler tier: planner, `ast` emitter, runtime, standalone emission |
| `src/json_schema_engine/formats`  | The standard format tables and predicates (M7)               |
| `packages/ecma-regex`   | ECMA-262 regex parser/translator/matcher; standalone, no dependency on the engine |
| `packages/test-kit`     | Internal: official-suite runner, output-tests runner, position-tracking parser |
| `packages/bench`        | Internal: the benchmark CLI and corpora                              |
| `test-suite/`           | Git submodule: the official JSON-Schema-Test-Suite (pinned)          |
| `bowtie/`               | Bowtie harness (IO protocol) and `Containerfile`                     |
| `scripts/`              | Standalone-run gates: bench, Bowtie, install smoke, standalone smoke |
| `docs/guide/`           | User guide (hand-written; every ` ```python ` block is executed)    |
| `docs/reference.md`     | API reference: every `__all__` export, by package (hand-written; test-enforced) |

`packages/test-kit` and `packages/bench` are workspace-private
(`Private :: Do Not Upload`); nothing publishes them, and `core` never
imports either (`lint-imports`, below).

## The gates

Run the full set before opening a PR; CI runs the same commands.

| Gate                                              | Command                                                        |
| -------------------------------------------------- | --------------------------------------------------------------- |
| Tests                                              | `uv run pytest -q`                                             |
| Lint                                               | `uv run ruff check .`                                          |
| Format check                                       | `uv run ruff format --check .`                                 |
| Types                                              | `uv run pyright`                                                |
| Import boundaries                                  | `uv run lint-imports`                                           |
| Standalone-emission smoke                          | `uv run python scripts/standalone_smoke.py`                     |
| Offline install smoke                              | `uv run python scripts/install_smoke.py`                        |
| Bowtie conformance                                 | `uv run python scripts/bowtie_check.py`                         |
| Benchmarks (report-only)                           | `uv run python scripts/bench.py --budget-ms 250`                |

`pyright` is a Python wheel around a Node-based language server: if it
reports it cannot find a runtime, put a working `node` on `PATH` (e.g. one
managed by `nvm`) before running it — this is an environment quirk, not a
project dependency on Node.

`lint-imports` enforces the dependency-direction contracts in
`pyproject.toml`'s `[[tool.importlinter.contracts]]`: `core` never imports
`compiler`, `formats`, `test_kit`, or `ast`; `compiler` never imports
`formats` or `test_kit`; `formats` never imports `compiler` or `test_kit`;
`test_kit` never imports the engine at all; `ecma_regex` never imports
`json_schema_engine`.

`scripts/bowtie_check.py` builds a local harness image
(`localhost/json-schema-engine-bowtie`) and runs the official suite
through [Bowtie](https://docs.bowtie.report/)'s own protocol; it needs a
reachable container engine and fetches the pinned `bowtie-json-schema`
release through `uvx`. The image is never pushed anywhere.

`scripts/bench.py` is report-only: it enforces no performance threshold
and, per the IP policy below, only ever runs the competing validators
(fastjsonschema, jsonschema) — never reads or ports their source.
`--filter REGEX` narrows the corpus/subject/partition names; `--out PATH`
writes JSON (the committed run at `packages/bench/results/results.json`
is `--budget-ms 250`); `--compare BEFORE AFTER` diffs two previous runs.

Two things run outside the default `pytest -q`:

- **The deep fuzz profile.** The compiler's differential fuzzer
  (`tests/compiler/test_fuzz.py`) uses a small Hypothesis example budget
  by default so the ordinary suite stays fast; run the deep profile
  locally (and in CI, in its own job) before touching planner or emitter
  code:

  ```sh
  HYPOTHESIS_PROFILE=deep uv run pytest -q tests/compiler/test_fuzz.py
  ```

- **Compiler goldens.** `tests/compiler/test_goldens.py` pins each
  fixture's emitted source byte for byte. A deliberate codegen change
  re-pins them in the same commit:

  ```sh
  UPDATE_GOLDENS=1 uv run pytest tests/compiler/test_goldens.py
  ```

  Review the diff — a golden update is data, not something to accept
  blindly.

## Documentation conventions

- Every fenced ` ```python ` block in `README.md`, `packages/*/README.md`,
  and `docs/**/*.md` is **executed by `tests/test_docs.py`**: every block
  on one page runs, in order, in one shared namespace, so a later block
  may use a name an earlier one defined. A block that raises fails CI.
  Examples assert what they claim (`assert x is True`, not a trailing
  `# True` comment). Use only the public API
  (`json_schema_engine.core`/`.compiler`/`.formats`, `ecma_regex`).
- Display-only content (not meant to run, or not Python) uses one of
  ` ```sh `, ` ```text `, ` ```json `, ` ```jsonc `, ` ```toml `,
  ` ```yaml `. Never a bare fence, never ` ```py ` or ` ```pycon `.
- `ruff format` reformats the Markdown code blocks themselves as part of
  the ordinary format gate.
- `docs/reference.md` must name every symbol each public package exports
  through `__all__`, enforced by `tests/test_reference.py`. Add an entry
  when you add a public export; the reference page has no separate
  generator.
- Voice: crisp, declarative, present tense. Document the system as it is,
  not its history. Examples over prose. Wrap prose at roughly 80 columns.

## Code comment policy

- Comments explain **why** — a constraint or a decision the code itself
  cannot show. Never restate what the next line does; never narrate
  history.
- Never describe downstream behavior (what other code does with a
  result); that knowledge drifts. Describe the local contract only.
- Each cross-cutting concept is described in exactly one place; other
  sites reference it instead of re-explaining it. Some canonical homes:
  channel/frame semantics → `core/evaluator.py` header; source positions
  (D17) → `core/loader.py`; the record→unit and trace→render-tree
  transforms → `core/records.py`; keyword/dialect identity (D2, D18) →
  `core/dialect.py`; the registry-snapshot rule → `core/registry.py`
  (`SchemaRegistry.snapshot`); the `format` single-table contract →
  `core/keywords/format.py`.
- Exported symbols carry docstrings; internals use `#` comments.

## IP policy (D15)

Implement and document from the JSON Schema specifications, this
repository's code, and the official test suite only. Other validators
(python-jsonschema, fastjsonschema, AJV, Hyperjump, and any other) may be
**executed** as correctness oracles or benchmark subjects; their source
is never read for implementation, ported, or translated. The TypeScript
engine at `handrews/json-schema-engine` is the one exception: it is this
project's own prior work, readable for structure and topic coverage, port
intent. This binds every contribution and every task prompt, including
one handed to a subagent — restate it there. See [DESIGN.md](DESIGN.md)
§0 for the full statement.

## Releasing

Versions live in `pyproject.toml` (the engine) and
`packages/ecma-regex/pyproject.toml` (`ecma-regex`), bumped with
`uv version --short [--package ecma-regex] <version>`. The engine pins
`ecma-regex>=0.1,<0.2`; widen that range in the same commit that bumps
the pin, and run `uv lock` afterward. Update both `CHANGELOG.md` and
`packages/ecma-regex/CHANGELOG.md` for whichever package changed, and run
the offline install smoke (`uv run python scripts/install_smoke.py`)
before tagging.

If the engine's `ecma-regex` pin needs a version PyPI does not have yet,
release `ecma-regex` first.

A git tag selects which package `.github/workflows/publish.yml` publishes
through PyPI's trusted publishing (no tokens stored in this repository):
`v<version>` publishes `json-schema-engine`; `ecma-regex-v<version>`
publishes `ecma-regex`. Each publish job refuses to run when the tag's
version does not match that package's `pyproject.toml`, so a release is
always the version the tree says it is. The owner tags and merges;
nothing is pushed by automation.
