# Error message building (DESIGN.md P18): the formatting helpers, and the
# guarantee that `realize` (the interpreter's side) produces exactly what
# the compiled evaluator builds from the same description.

import json
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from json_schema_engine.compiler import compile_evaluator
from json_schema_engine.core import (
    DIALECT_2020_12,
    JsonValue,
    KeywordBehavior,
    create_engine,
)
from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import KeywordContext
from json_schema_engine.core.lowering import (
    INSTANCE,
    Binding,
    Const,
    Expr,
    HelperName,
    LoweringContext,
    LowerMessage,
    LowerParams,
    cond,
    fail,
    helper,
    type_is,
)
from json_schema_engine.core.messages import (
    HELPERS,
    PREVIEW_LIMIT,
    apparent_type,
    describe_once,
    duplicate_groups,
    index_groups,
    index_ranges,
    name_list,
    preview,
    ranges,
    realize,
    typed_preview,
)

# --- helpers -------------------------------------------------------------------


def test_preview_is_compact_json() -> None:
    assert preview({"a": True, "b": [1, 2.5, None]}) == (
        '{"a": true, "b": [1, 2.5, null]}'
    )
    assert preview("é\n") == '"é\\n"'


def test_preview_cuts_at_the_limit() -> None:
    text = preview("x" * 1000)
    assert len(text) == PREVIEW_LIMIT
    assert text.endswith("…")
    assert text.startswith('"xxx')
    exact = "y" * (PREVIEW_LIMIT - 2)  # with its quotes, exactly the limit
    assert preview(exact) == f'"{exact}"'


def _reference_preview(value: JsonValue) -> str:
    # What `preview` promises, spelled independently of its fast paths.
    text = json.dumps(value, ensure_ascii=False)
    return text[: PREVIEW_LIMIT - 1] + "…" if len(text) > PREVIEW_LIMIT else text


@pytest.mark.parametrize(
    "value",
    [
        0,
        -7,
        10**80,
        -(10**80),
        0.5,
        -0.0,
        1e16,
        1e-7,
        True,
        False,
        None,
        "",
        'say "hi"\n',
        "é" * 70,
        *[
            prefix + "x" * (n - len(prefix))
            for n in range(PREVIEW_LIMIT - 3, PREVIEW_LIMIT + 3)
            for prefix in ("", '"', "\\\n")
        ],
    ],
    ids=repr,
)
def test_preview_fast_paths_match_the_general_path(value: JsonValue) -> None:
    assert preview(value) == _reference_preview(value)
    assert len(preview(value)) <= PREVIEW_LIMIT


def test_typed_preview() -> None:
    assert typed_preview(3) == "3 (integer)"
    assert typed_preview(3.0) == "3.0 (integer)"
    assert typed_preview(2.5) == "2.5 (number)"
    assert typed_preview("a") == '"a" (string)'
    assert typed_preview(True) == "true (boolean)"
    assert typed_preview(None) == "null (null)"
    assert typed_preview([1]) == "array"
    assert typed_preview({"a": 1}) == "object"


def test_preview_is_bounded_on_huge_containers() -> None:
    # Walked only as far as it is shown: a million items cost no more.
    huge: JsonValue = list(range(1_000_000))
    assert len(preview(huge)) == PREVIEW_LIMIT


def test_apparent_type() -> None:
    assert apparent_type(3) == "integer"
    assert apparent_type(3.0) == "integer"
    assert apparent_type(3.5) == "number"
    assert apparent_type(True) == "boolean"
    assert apparent_type(None) == "null"
    assert apparent_type([]) == "array"


def test_index_ranges_and_ranges() -> None:
    assert index_ranges([5, 1, 2, 3, 7, 8, 9]) == "1-3, 5, 7-9"
    assert index_ranges([4]) == "4"
    assert index_ranges([0, 1, 3, 4, 5]) == "0, 1, 3-5"
    assert index_ranges([]) == "none"
    assert ranges([1, 2, 3, 5]) == [[1, 3], [5, 5]]


def test_name_list_caps_the_names() -> None:
    assert name_list(["a", "b"]) == '"a", "b"'
    names = [f"p{i}" for i in range(13)]
    assert name_list(names).endswith('"p9" and 3 more')


def test_duplicate_groups_finds_every_group() -> None:
    assert duplicate_groups([1, "a", 1.0, {"x": [1]}, "a", 2, {"x": [1]}, 1]) == [
        [0, 2, 7],
        [1, 4],
        [3, 6],
    ]
    assert duplicate_groups([True, 1, False, 0]) == []


def test_index_groups_reads_as_sentences() -> None:
    assert index_groups([[0, 2, 5], [1, 3]]) == (
        "[0, 2, 5] are equal; [1, 3] are equal"
    )


# --- realize matches the compiled evaluator ---------------------------------

MESSAGE: LowerMessage = (
    "got ",
    helper("preview", INSTANCE),
    " (",
    helper("apparent_type", INSTANCE),
    ")",
    cond(type_is(INSTANCE, "array"), helper("length_of", INSTANCE), Const("-")),
)
PARAMS: LowerParams = {
    "value": INSTANCE,
    "kind": helper("apparent_type", INSTANCE),
    "limit": Const(2.5),
}
EXPLAIN_VOCAB = "urn:test:vocab:explain"
EXPLAIN_DIALECT = "urn:test:dialect:explain"


def _explain_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.error(*realize(MESSAGE, PARAMS, cursor.value))
    return False


def _explain_lower(value: JsonValue, lctx: LoweringContext) -> None:
    lctx.emit(fail(MESSAGE, PARAMS))


EXPLAIN = KeywordBehavior(
    id=EXPLAIN_VOCAB + "#explain", evaluate=_explain_evaluate, lower=_explain_lower
)

JSON_VALUES = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=80),
    lambda inner: (
        st.lists(inner, max_size=6)
        | st.dictionaries(st.text(max_size=8), inner, max_size=6)
    ),
    max_leaves=40,
)


@given(JSON_VALUES)
def test_realize_matches_the_compiled_evaluator(instance: JsonValue) -> None:
    engine = create_engine()
    base = engine.dialects.get_dialect(DIALECT_2020_12)
    engine.dialects.register_vocabulary(EXPLAIN_VOCAB, {"explain": EXPLAIN})
    engine.dialects.register_dialect(
        EXPLAIN_DIALECT, [*base.vocabulary_uris, EXPLAIN_VOCAB]
    )
    uri = engine.register_schema(
        {"explain": True}, "urn:test:explain", dialect_uri=EXPLAIN_DIALECT
    )
    interpreted = engine.evaluate(uri, instance, output="list", error_params=True)
    compiled = compile_evaluator(engine, uri).evaluate(
        instance, output="list", error_params=True
    )
    assert compiled == interpreted
    assert interpreted.errors is not None
    assert interpreted.errors[0]["error"].startswith("got ")


# --- the interpreter realizes a description only when it is rendered --------


def test_a_reported_description_is_realized_only_when_rendered() -> None:
    calls: list[int] = []

    def evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        def describe() -> tuple[LowerMessage, LowerParams | None]:
            calls.append(1)
            return MESSAGE, PARAMS

        ctx.report(describe)
        return False

    engine = create_engine()
    base = engine.dialects.get_dialect(DIALECT_2020_12)
    lazy = KeywordBehavior(id=EXPLAIN_VOCAB + "#lazy", evaluate=evaluate)
    engine.dialects.register_vocabulary(EXPLAIN_VOCAB, {"lazy": lazy})
    engine.dialects.register_dialect(
        EXPLAIN_DIALECT, [*base.vocabulary_uris, EXPLAIN_VOCAB]
    )
    uri = engine.register_schema(
        {"anyOf": [{"lazy": True}, {}]}, "urn:test:lazy", dialect_uri=EXPLAIN_DIALECT
    )
    # A dropped error (the losing branch) and a verdict-only evaluation never
    # render, so the description is never built.
    assert engine.evaluate(uri, [1, 2]).valid is True
    assert engine.evaluate(uri, [1, 2], output="list").valid is True
    lone = engine.register_schema(
        {"lazy": True}, "urn:test:lazy-lone", dialect_uri=EXPLAIN_DIALECT
    )
    assert engine.evaluate(lone, [1, 2]).valid is False
    assert calls == []
    result = engine.evaluate(lone, [1, 2], output="list")
    assert calls == [1]
    assert result.errors is not None
    assert result.errors[0]["error"] == "got [1, 2] (array)2"


def test_a_binding_in_a_reported_description_fails_loudly() -> None:
    # `lower` may name a binding; `evaluate` carries runtime values as
    # `Const`, since a record realizes with no bindings.
    def evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        ctx.report(lambda: (("first at ", Binding(0)), None))
        return False

    engine = create_engine()
    base = engine.dialects.get_dialect(DIALECT_2020_12)
    bound = KeywordBehavior(id=EXPLAIN_VOCAB + "#bound", evaluate=evaluate)
    engine.dialects.register_vocabulary(EXPLAIN_VOCAB, {"bound": bound})
    engine.dialects.register_dialect(
        EXPLAIN_DIALECT, [*base.vocabulary_uris, EXPLAIN_VOCAB]
    )
    uri = engine.register_schema(
        {"bound": True}, "urn:test:bound", dialect_uri=EXPLAIN_DIALECT
    )
    assert engine.evaluate(uri, 1).valid is False
    with pytest.raises(LookupError, match="Const"):
        engine.evaluate(uri, 1, output="list")


def test_describe_once_shares_a_description_per_value() -> None:
    calls: list[JsonValue] = []

    def build(value: JsonValue, instance: Expr) -> tuple[LowerMessage, LowerParams]:
        calls.append(value)
        return (("must be ", Const(value), ", got ", instance), {"limit": Const(value)})

    first = describe_once(build, 5)
    assert describe_once(build, 5) is first
    assert first() == first()
    # `1 == True` and `1 == 1.0`, yet each is its own description.
    describe_once(build, 1)
    describe_once(build, True)
    describe_once(build, 1.0)
    assert calls == [5, 1, True, 1.0]
    # An unhashable value is built per report, never cached.
    listed: JsonValue = [1, 2]
    thunk = describe_once(build, listed)
    assert thunk is not describe_once(build, listed)
    assert len(calls) == 4  # built lazily, when the thunk is called
    thunk()
    assert calls[-1] == [1, 2]


def test_every_helper_name_has_a_function() -> None:
    # A `Helper` the IR can name must be something `realize` can call.
    assert set(get_args(HelperName.__value__)) == set(HELPERS)
