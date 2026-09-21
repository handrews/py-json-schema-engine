# json-schema-engine-bench

Internal benchmark harness for [json-schema-engine](../../README.md). Not
published; not for external use. It times the compiler tier's flag and
standalone artifacts against the interpreter and two competitors
(`fastjsonschema`, `jsonschema`) over seven named corpora, using an
oracle-first methodology so a wrong verdict is never mistaken for speed.
Report-only: nothing here gates CI.

## Provenance and licensing

| File / corpus                    | Source                                                                                  | License        |
| --------------------------------- | ---------------------------------------------------------------------------------------- | -------------- |
| `oas-3.1-schema.json`              | Official OpenAPI 3.1 JSON Schema, `spec.openapis.org/oas/3.1/schema/2025-09-15`          | Apache-2.0     |
| `openapi-document.json`            | Hand-authored OpenAPI 3.1 description, copied from the owner's TS reference engine       | MIT (upstream) |
| `api-payload-schema.json`          | Hand-authored API-payload schema, copied from the owner's TS reference engine            | MIT (upstream) |
| `user.schema.json`, `event.schema.json`, `profile.schema.json` | Hand-authored for this repo                                          | MIT (repo)     |
| _(generated)_ `oas-document` instances | `corpora.py`'s `_load_oas_document`: the vendored document, plus a deep copy with `"openapi": 4` | MIT (repo) |
| _(generated)_ `api-payload`        | `corpora/api_payload.py`: seeded `random.Random`, 32 payload instances                   | MIT (repo)     |
| _(generated)_ `records-uniform`, `records-sparse` | `corpora/records.py`: 150 typed properties x 2000 records, two shape variants     | MIT (repo)     |

The two files copied from the owner's TS reference engine
([handrews/json-schema-engine](https://github.com/handrews/json-schema-engine))
are copied verbatim per DESIGN.md §0 / D15: `oas-3.1-schema.json` is the
OpenAPI Initiative's Apache-2.0 schema, vendored as-is; `openapi-document.json`
and `api-payload-schema.json` are this owner's own hand-authored MIT
fixtures. Everything else is either hand-authored for this repo or
generated deterministically at bench time (seeded PRNG, no wall clock, no
third-party data).

## IP policy

Per DESIGN.md §0 / D15: `fastjsonschema` and `jsonschema` are executed
here as bench subjects and correctness oracles only. Their source is
never read, ported, or quoted; their imports are isolated behind
`# type: ignore` in `subjects.py` so the rest of the package stays
strictly typed.

## Methodology

- **Oracle first.** Every corpus's `expected` verdicts come from the
  interpreter (`Engine.evaluate(...).valid`) — the reference semantics.
  Before any subject is timed, its `validate` callable must agree with
  the oracle on every instance in the corpus; a subject that disagrees on
  even one instance is recorded as an `exclusion` with a reason instead
  of timed. Timing a validator that returns the wrong verdict (and may
  short-circuit on it) would not be a throughput comparison — it would be
  timing how fast something gets the wrong answer.
- **Budget, not a fixed sample count.** `_autorange` doubles/quintuples a
  batch size until one batch takes at least 5 ms, then runs batches until
  `--budget-ms` (default 250 ms) is spent per corpus/subject/partition
  task. Cheap tasks get more samples; expensive ones do not blow the
  budget.
- **Partitions.** Each surviving pair is timed over `hot` (every
  instance, round-robin), `valid`, and `invalid`, plus a `compile`
  partition timing `prepare` itself (the cold artifact build) for every
  subject except the plain interpreter.
- **Exclusions are recorded, not hidden.** `results.json`'s `exclusions`
  list names every corpus/subject pair that never got timed and why —
  a schema `jse standalone` cannot emit, or a subject whose verdicts
  disagree with the oracle.
- **`--filter REGEX`** restricts which corpus/subject pairs run at all
  (oracle checking included, not just timing), so iterating on one corpus
  does not pay for the rest — compiling every subject's cold artifact for
  every corpus is real work.

## What each corpus measures

- **user**, **event**, **profile** — small, hand-authored object schemas
  exercising ordinary keyword combinations (formats aside, since format
  assertions are never checked by any subject here).
- **oas-document** — the official OAS 3.1 meta-schema (2020-12,
  `$dynamicRef`, ~135 internal `$ref`s) validating a real OpenAPI
  description. The large-schema, reference-heavy, dynamic-scoping case.
- **api-payload** — a moderate object schema over 32 generated request
  payloads, half valid and half carrying one planted defect each. The
  hot-path throughput case over realistic nesting (array of line items,
  a nested `attributes` object).
- **records-uniform** — one schema applied to 2000 records that all
  share one shape (same fields, same order). Isolates per-application
  cost from property-access variance.
- **records-sparse** — the same schema over records whose shapes differ
  (0-3 optional fields each, in varying order). The polymorphic
  property-access case.

## Running

```sh
uv run python scripts/bench.py --budget-ms 250 --filter user
```

`--filter` takes a regex over corpus/subject/partition names (matched
against `"<corpus> | <subject>"` for oracle-checking, and against
`"<corpus> | <partition> | <subject>"` for timing). Omit `--out` to skip
writing JSON; the committed run lives at
`packages/bench/results/results.json`, refreshed with:

```sh
uv run python scripts/bench.py --budget-ms 250 --out packages/bench/results/results.json
```

The printed table's header line reports the machine (`machdep.cpu.brand_string`
on macOS, the first `model name` line of `/proc/cpuinfo` on Linux,
`platform.processor()` otherwise), the commit (`git rev-parse --short HEAD`,
or `None` outside a repo or a shallow clone missing the ref), and the
installed subject versions — all also written into the JSON's `machine`,
`commit`, and `subjects` fields, so a later `--compare` run can tell what
changed between two files besides the numbers.

### Comparing two runs

```sh
uv run python scripts/bench.py --compare before.json after.json
```

Loads two previously written results files, joins their rows by task
name, and prints a `task | before ops/s | after ops/s | after/before`
table (a 2-decimal ratio, or `n/a` when a task is missing, excluded, or
present on only one side), followed by "only in before" / "only in
after" lists for tasks that did not survive on both sides. `--compare` is
mutually exclusive with `--budget-ms`/`--filter`/`--out` — there is
nothing to run. Sample output:

```text
task                                before ops/s  after ops/s  after/before
user | hot | jse compiled flag      2,501,446     2,506,593    1.00
user | hot | jse interpreter flag   27,590        27,000       0.98

only in before:
  user | hot | jsonschema
```

## Known exclusions

- **`fastjsonschema` on `event`**: disagrees with the oracle on
  `unevaluatedProperties` — a documented divergence, not a bench bug.
- **`fastjsonschema` on `oas-document`**: disagrees with the oracle,
  accepting a document this bench's oracle (and `jsonschema`) reject.

Every exclusion above is recorded in `results.json`'s `exclusions` list
with its reason, not silently dropped from the table.
