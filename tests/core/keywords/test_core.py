# The core and meta-data vocabularies (DESIGN.md D2, §3): `$ref` resolution
# by pointer, anchor, and embedded `$id`; `$defs`' walked-but-inert
# subschema positions; and every meta-data keyword's annotation-only shape.

import pytest

from json_schema_engine.core.channel import materialize_path
from json_schema_engine.core.dialect import (
    CompiledRegex,
    DialectRegistry,
)
from json_schema_engine.core.errors import InfiniteLoopError, InvalidSchemaError
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import VOCAB_CORE, VOCAB_META_DATA
from json_schema_engine.core.keywords.core import CORE_VOCABULARY
from json_schema_engine.core.keywords.meta_data import META_DATA_VOCABULARY
from json_schema_engine.core.registry import SchemaRegistry

DIALECT = "urn:test:core-dialect"
SCHEMA_URI = "https://core.example/schema"


class _Regex:
    def search(self, _text: str, /) -> bool:
        raise AssertionError("no keyword in this vocabulary compiles a regex")


def _compile_regex(_pattern: str) -> CompiledRegex:
    return _Regex()


def make_registry() -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_CORE, CORE_VOCABULARY)
    dialects.register_vocabulary(VOCAB_META_DATA, META_DATA_VOCABULARY)
    dialects.register_dialect(DIALECT, [VOCAB_CORE, VOCAB_META_DATA])
    return SchemaRegistry(dialects, DIALECT)


def run(
    schema: JsonValue, instance: JsonValue, *, uri: str = SCHEMA_URI
) -> tuple[bool, EvalState]:
    registry = make_registry()
    base_uri = registry.register(schema, uri)
    return run_evaluation(registry, base_uri, instance, compile_regex=_compile_regex)


def annotations(state: EvalState) -> list[tuple[str, str, JsonValue]]:
    return [
        (
            materialize_path(a.path_node) + "/" + a.keyword_name,
            a.cursor.pointer,
            a.value,
        )
        for a in state.root_annotations
    ]


# --- $ref ------------------------------------------------------------------


def test_ref_by_pointer_applies_in_place_with_reference_path() -> None:
    schema: JsonValue = {"$defs": {"t": {"title": "via ref"}}, "$ref": "#/$defs/t"}
    valid, state = run(schema, 0)
    assert valid
    assert annotations(state) == [("/$ref/title", "", "via ref")]
    assert state.root_annotations[0].schema_ref.location == (f"{SCHEMA_URI}#/$defs/t")


def test_ref_by_anchor_resolves() -> None:
    schema: JsonValue = {
        "$defs": {"t": {"$anchor": "found", "title": "anchored"}},
        "$ref": "#found",
    }
    valid, state = run(schema, 0)
    assert valid
    assert annotations(state) == [("/$ref/title", "", "anchored")]


def test_ref_to_embedded_id_resource() -> None:
    schema: JsonValue = {
        "$id": "https://core.example/root",
        "$defs": {"sub": {"$id": "https://core.example/sub", "title": "embedded"}},
        "$ref": "https://core.example/sub",
    }
    valid, state = run(schema, 0, uri="https://core.example/root")
    assert valid
    assert annotations(state) == [("/$ref/title", "", "embedded")]
    assert state.root_annotations[0].schema_ref.location == (
        "https://core.example/sub#"
    )


def test_ref_cycle_at_same_instance_location_is_loud() -> None:
    with pytest.raises(InfiniteLoopError):
        run({"$ref": "#"}, 0)


def test_non_string_ref_raises_invalid_schema_error() -> None:
    with pytest.raises(InvalidSchemaError):
        run({"$ref": 5}, 0)


# --- $defs and $comment: structural, walked, never applied ------------------


def test_defs_are_walked_for_identifiers_but_never_applied() -> None:
    schema: JsonValue = {
        "$defs": {
            "on": {"$anchor": "found", "title": "found me"},
            # Never referenced or applied: a `false` entry here must not
            # fail the instance, because `$defs` itself is structural.
            "off": False,
        },
        "$ref": "#found",
    }
    valid, state = run(schema, 0)
    assert valid
    assert ("/$ref/title", "", "found me") in annotations(state)


def test_comment_never_annotates() -> None:
    schema: JsonValue = {"$comment": "must never be collected", "title": "t"}
    _, state = run(schema, 0)
    assert not any(a.keyword_name == "$comment" for a in state.root_annotations)
    assert any(a.keyword_name == "title" for a in state.root_annotations)


# --- meta-data vocabulary: every member is annotation-only -----------------


def test_every_meta_data_keyword_annotates_its_own_value() -> None:
    schema: JsonValue = {
        "title": "T",
        "description": "D",
        "default": 1,
        "deprecated": True,
        "readOnly": True,
        "writeOnly": False,
        "examples": [1, 2],
    }
    valid, state = run(schema, {"anything": "goes"})
    assert valid
    got = annotations(state)
    for name, value in schema.items():
        assert (f"/{name}", "", value) in got
    assert len(got) == len(schema)


def test_meta_data_keyword_annotates_at_the_applied_instance_location() -> None:
    schema: JsonValue = {
        "$defs": {"child": {"title": "nested"}},
        "$ref": "#/$defs/child",
    }
    _, state = run(schema, {"x": 1})
    assert state.root_annotations[0].cursor.pointer == ""
