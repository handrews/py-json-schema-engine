# Changelog

All notable changes to `json-schema-engine` (the Python engine). The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/) with the 0.x caveat that
minor versions may change public API.

## [0.0.2] - unreleased

The first functional release. Everything below is new relative to the
0.0.1 name reservation.

### Added

- `json_schema_engine.core`: the interpreter tier. Draft 2020-12 (default),
  2019-09, draft-07, and draft-06 with each draft's own semantics
  (`$dynamicRef`, `$recursiveRef`, `$ref` sibling handling); `$vocabulary`
  processing with the bundled metaschemas; loaders for remote references
  with source-position reporting (`parse_json_with_ranges`,
  `positions=True`, `Engine.locate`); metaschema validation on request
  (`validate_schemas=True`); the `flag`, `basic`, `detailed`, `verbose`,
  `list`, and `hierarchical` output formats with annotation selection,
  error params, verbose levels, and the application trace; ECMA-262
  regular expressions through `ecma-regex`, with a Python `re`
  passthrough dialect and the optional `regex` backend; the
  `reject_unsafe_regex` screen, `max_depth`, and O(n) `uniqueItems`.
- `json_schema_engine.compiler`: `compile_validator` (a verdict-only
  Python function bound to a registry snapshot, trampolining into the
  interpreter for whatever it cannot lower), `emit_standalone` (a module
  importable without the compiler), and `explain_compilation`.
- `json_schema_engine.formats`: every format the four drafts define,
  implemented from the RFCs and verified against the official
  `optional/format` suites; the `idna` extra for IDNA2008
  (`idn-hostname`, A-label checks in `hostname`); assertion opt-in through
  `create_engine(formats=..., assert_formats=...)` and the 2020-12
  format-assertion vocabulary.
- Every distribution portion ships a `py.typed` marker.

### Changed

- The distribution depends on `ecma-regex>=0.1,<0.2`.
- The sdist no longer carries the test tree, which needs the repository's
  test-kit and the suite submodule.

## [0.0.1] - 2026-09-20

Name reservation on PyPI; no functionality.
