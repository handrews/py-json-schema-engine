# The compiled tier's trampoline seam (DESIGN.md D1, D8, P3; M6):
# `evaluate_fragment` evaluates one schema position with pre-seeded dynamic
# scope, depth, and path prefix, and returns records with cursor identity
# intact.

import pytest

from json_schema_engine.core import JsonValue, MaxDepthExceededError, create_engine
from json_schema_engine.core.channel import PathNode, materialize_path
from json_schema_engine.core.cursor import root_cursor
from json_schema_engine.core.evaluator import evaluate_fragment


def _engine(schema: JsonValue, uri: str = "https://fragment.example/s"):
    engine = create_engine()
    return engine, engine.register_schema(schema, uri)


def test_fragment_returns_the_verdict_and_relevant_errors() -> None:
    engine, uri = _engine({"$defs": {"t": {"type": "string", "minLength": 2}}})
    target = engine.schemas.resolve_ref("#/$defs/t", uri)
    result = evaluate_fragment(
        engine.schemas, target, root_cursor(1), compile_regex=engine.regex_cache.compile
    )
    assert result.valid is False
    assert [e.keyword_name for e in result.errors] == ["type"]
    assert evaluate_fragment(
        engine.schemas,
        target,
        root_cursor("ok"),
        compile_regex=engine.regex_cache.compile,
    ).valid


def test_fragment_records_keep_cursor_identity_and_path_prefix() -> None:
    engine, uri = _engine({"title": "root", "properties": {"a": {"type": "integer"}}})
    cursor = root_cursor({"a": 1})
    prefix = PathNode(None, "allOf/0")  # a synthetic, pre-escaped prefix segment
    result = evaluate_fragment(
        engine.schemas,
        engine.schemas.root_ref(uri),
        cursor,
        compile_regex=engine.regex_cache.compile,
        path_node=prefix,
    )
    assert result.valid
    (annotation,) = result.annotations
    assert annotation.cursor is cursor
    assert materialize_path(annotation.path_node) == "/allOf/0"
    (dependency,) = result.dependencies
    assert dependency.cursor is cursor
    assert dependency.data == ["a"]


def test_fragment_seeds_the_dynamic_scope() -> None:
    # The inner resource's `$dynamicRef` rebinds to the outer scope only
    # when the caller reports having entered it.
    engine, uri = _engine(
        {
            "$id": "https://fragment.example/outer",
            "$dynamicAnchor": "node",
            "type": "string",
            "$defs": {
                "inner": {
                    "$id": "inner",
                    "$dynamicAnchor": "node",
                    "items": {"$dynamicRef": "#node"},
                }
            },
        }
    )
    target = engine.schemas.resolve_ref("#/$defs/inner", uri)
    compile_regex = engine.regex_cache.compile
    # Without the outer scope, `#node` resolves to the inner anchor (no
    # type constraint) and 1 is fine.
    assert evaluate_fragment(
        engine.schemas, target, root_cursor([1]), compile_regex=compile_regex
    ).valid
    # With it, the outer anchor wins and 1 is not a string.
    assert not evaluate_fragment(
        engine.schemas,
        target,
        root_cursor([1]),
        compile_regex=compile_regex,
        dynamic_scope=[uri],
    ).valid


def test_fragment_shares_the_depth_budget() -> None:
    engine, uri = _engine({"properties": {"child": {"$ref": "#"}}})
    deep: JsonValue = {}
    for _ in range(20):
        deep = {"child": deep}
    root = engine.schemas.root_ref(uri)
    compile_regex = engine.regex_cache.compile
    assert evaluate_fragment(
        engine.schemas,
        root,
        root_cursor(deep),
        compile_regex=compile_regex,
        max_depth=64,
    ).valid
    with pytest.raises(MaxDepthExceededError):
        evaluate_fragment(
            engine.schemas,
            root,
            root_cursor(deep),
            compile_regex=compile_regex,
            max_depth=64,
            depth=40,
        )


def test_fragment_backstop_is_typed() -> None:
    engine, uri = _engine({"properties": {"child": {"$ref": "#"}}})
    deep: JsonValue = {}
    for _ in range(3000):
        deep = {"child": deep}
    with pytest.raises(MaxDepthExceededError):
        evaluate_fragment(
            engine.schemas,
            engine.schemas.root_ref(uri),
            root_cursor(deep),
            compile_regex=engine.regex_cache.compile,
            max_depth=1_000_000,
        )
