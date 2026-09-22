# Changelog

All notable changes to `ecma-regex`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/) with the 0.x caveat that minor versions may
change public API.

## [0.1.0] - 2026-09-21

The first documented release: the README and docstrings are audited
against the code, every README example is executed by the test suite, and
the package ships a `py.typed` marker. The translator itself is the one
published as 0.0.1.

### Added

- `py.typed` (PEP 561), so strict type checkers see the package's
  annotations.
- `CHANGELOG.md`.

## [0.0.1] - 2026-09-20

First release: parse ECMA-262 (`u`-mode) patterns, translate them for
`re` or `regex`, `search` with JavaScript semantics, `star_height` for
ReDoS screening.
