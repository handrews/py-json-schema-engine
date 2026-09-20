# json-schema-engine (Python)

This is a **name reservation** release. Version `0.0.1` provides no
functionality; it exists solely to reserve the `json-schema-engine`
distribution name on PyPI ahead of the real implementation.

The finished project will be a Python implementation of the design behind
[handrews/json-schema-engine](https://github.com/handrews/json-schema-engine):
a spec-complete, annotation-first JSON Schema engine built around two tiers
and a single keyword registry, producing all standard output formats.

It is produced by Henry Andrews using Claude Code.

The import namespace is `json_schema_engine`, with subpackages such as
`json_schema_engine.core`, `json_schema_engine.compiler`, and
`json_schema_engine.formats`. Only `json_schema_engine.core` exists today, as
an empty placeholder.

## Install

```
pip install json-schema-engine
```

Do not install this yet expecting any functionality — 0.0.1 is a placeholder
release only.
