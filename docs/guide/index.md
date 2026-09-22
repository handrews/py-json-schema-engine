# User guide

`json-schema-engine` is a spec-complete, annotation-first JSON Schema
implementation for Python: register a schema, evaluate an instance, and read
back the result in whichever standard output format the caller needs, from a
plain pass/fail flag to a fully annotated, located evaluation tree.

## Topics

- [Validation](validation.md) — register schemas, evaluate instances, read
  error output, evaluate a subschema directly.
- [Output formats](output-formats.md) — `flag`, `basic`, `detailed`,
  `verbose` (IETF draft-03) and `list`, `hierarchical` (machines-oriented
  proposal); levels and controls.
- [Annotations](annotations.md) — collect annotations, control selection
  with allow and deny lists.
- [Dialects](dialects.md) — 2020-12, 2019-09, draft-07, draft-06; `$schema`
  and default-dialect selection.
- [Loaders and remote references](loaders.md) — resolve `$ref` across
  documents; write a custom loader.
- [Source positions](source-positions.md) — map errors and annotations back
  to line/column in schema source text.
- [Location chains](location-chains.md) — find an error inside a compound
  document: which embedded resource it is in, and where that sits in the file.
- [Metaschemas](metaschemas.md) — `$vocabulary`-defined dialects and
  schema-against-metaschema validation.
- [Custom keywords and vocabularies](custom-keywords.md) — extend the engine
  with the same mechanism the built-in drafts use.
- [Security](security.md) — evaluating untrusted schemas and instances:
  ReDoS, recursion depth, and other resource limits.
- [Compiling schemas](compiled.md) — turn a registered schema into a Python
  function; the registry-snapshot rule; standalone modules.
- [Formats](formats.md) — the `format` keyword, the bundled format tables,
  and asserting formats instead of only annotating them.

See also the [API reference](../reference.md) for every public name, by
package.

## Install

```sh
pip install json-schema-engine
```

The `idna` extra adds IDNA2008 support for `idn-hostname` and `hostname`;
the `regex` extra swaps in the `regex` package as the pattern backend:

```sh
pip install 'json-schema-engine[idna]'
pip install 'json-schema-engine[regex]'
```

The engine requires Python 3.12 or later.
