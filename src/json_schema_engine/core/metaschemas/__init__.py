# The standard metaschemas, bundled so that a `$ref` to one resolves without
# loaders and `validate_schemas` can check documents written for the
# built-in dialects (DESIGN.md D11, §5). The JSON files are the spec's own
# artifacts, fetched verbatim from json-schema.org.
#
# Dependency direction: imports `json_model` only. The engine hands the
# mapping to the registry, which registers a resource on first use.

import json
from collections.abc import Mapping
from functools import cache
from importlib import resources

from json_schema_engine.core.json_model import JsonValue

_BASE_2020_12 = "https://json-schema.org/draft/2020-12/"

_FILES_2020_12: Mapping[str, str] = {
    _BASE_2020_12 + "schema": "schema.json",
    _BASE_2020_12 + "meta/core": "core.json",
    _BASE_2020_12 + "meta/applicator": "applicator.json",
    _BASE_2020_12 + "meta/validation": "validation.json",
    _BASE_2020_12 + "meta/unevaluated": "unevaluated.json",
    _BASE_2020_12 + "meta/meta-data": "meta-data.json",
    _BASE_2020_12 + "meta/format-annotation": "format-annotation.json",
    _BASE_2020_12 + "meta/content": "content.json",
}


@cache
def bundled_metaschemas() -> Mapping[str, JsonValue]:
    """Every bundled metaschema resource, keyed by its canonical URI.

    Parsed once per process; the registry reads the mapping lazily, so an
    engine that never touches a metaschema never pays for parsing it either.
    """
    package = resources.files(__name__) / "2020-12"
    documents: dict[str, JsonValue] = {}
    for uri, filename in _FILES_2020_12.items():
        documents[uri] = json.loads((package / filename).read_text("utf-8"))
    return documents
