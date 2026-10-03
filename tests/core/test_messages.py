# Error message building (DESIGN.md P18): the formatting helpers, and the
# guarantee that `realize` (the interpreter's side) produces exactly what
# the compiled evaluator builds from the same description.

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
    Const,
    LoweringContext,
    LowerMessage,
    LowerParams,
    cond,
    fail,
    helper,
    type_is,
)
from json_schema_engine.core.messages import (
    PREVIEW_LIMIT,
    apparent_type,
    duplicate_groups,
    index_ranges,
    name_list,
    preview,
    ranges,
    realize,
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
