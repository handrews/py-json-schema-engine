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
_BASE_2019_09 = "https://json-schema.org/draft/2019-09/"

# Directory -> {canonical URI: file}. The draft-07/06 documents declare
# their `$id` with a trailing `#`; the registry keys resources fragment-free.
_FILES: Mapping[str, Mapping[str, str]] = {
    "2020-12": {
        _BASE_2020_12 + "schema": "schema.json",
        _BASE_2020_12 + "meta/core": "core.json",
        _BASE_2020_12 + "meta/applicator": "applicator.json",
        _BASE_2020_12 + "meta/validation": "validation.json",
        _BASE_2020_12 + "meta/unevaluated": "unevaluated.json",
        _BASE_2020_12 + "meta/meta-data": "meta-data.json",
        _BASE_2020_12 + "meta/format-annotation": "format-annotation.json",
        _BASE_2020_12 + "meta/format-assertion": "format-assertion.json",
        _BASE_2020_12 + "meta/content": "content.json",
    },
    "2019-09": {
        _BASE_2019_09 + "schema": "schema.json",
        _BASE_2019_09 + "meta/core": "core.json",
        _BASE_2019_09 + "meta/applicator": "applicator.json",
        _BASE_2019_09 + "meta/validation": "validation.json",
        _BASE_2019_09 + "meta/meta-data": "meta-data.json",
        _BASE_2019_09 + "meta/format": "format.json",
        _BASE_2019_09 + "meta/content": "content.json",
    },
    "draft-07": {"http://json-schema.org/draft-07/schema": "schema.json"},
    "draft-06": {"http://json-schema.org/draft-06/schema": "schema.json"},
}


@cache
def bundled_metaschemas() -> Mapping[str, JsonValue]:
    """Every bundled metaschema resource, keyed by its canonical URI.

    Parsed once per process; the registry reads the mapping lazily, so an
    engine that never touches a metaschema never pays for parsing it either.
    """
    root = resources.files(__name__)
    documents: dict[str, JsonValue] = {}
    for directory, files in _FILES.items():
        for uri, filename in files.items():
            documents[uri] = json.loads(
                (root / directory / filename).read_text("utf-8")
            )
    return documents
