# The emitter (DESIGN.md D9, D10): inlining and the loop-nesting cap,
# constant-set membership rendering, boolean folds, the draft-07 `$ref`
# gate, and the `conservative` configuration — through a hand-registered
# vocabulary where the built-in keywords do not yet reach a shape.

import ast

import pytest

from json_schema_engine.compiler import compile_validator
from json_schema_engine.core import (
    DIALECT_2020_12,
    DIALECT_DRAFT_07,
    Engine,
    JsonValue,
    create_engine,
)
from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
    SubschemaApplication,
)
from json_schema_engine.core.json_model import is_object
from json_schema_engine.core.lowering import (
    HERE,
    INSTANCE,
    Binding,
    ForEachKey,
    LoweringContext,
    apply,
    child,
    fail,
    in_consts,
    not_,
    type_is,
    when,
)

VOCAB = "urn:test:emit"
DIALECT = "urn:test:emit-dialect"


def _sweep_analyze(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(
        subschemas=((),),
        applications=(SubschemaApplication((), "child_sweep", False, True),),
    )


def _sweep_evaluate(_value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    instance = cursor.value
    if not is_object(instance):
        return True
    ok = True
    for name, member in instance.items():
        if not ctx.apply(("sweep",), child_cursor(cursor, name, member)):
            ok = False
    return ok


def _sweep_lower(_value: JsonValue, lctx: LoweringContext) -> None:
    binding = lctx.binding()
    lctx.emit(
        when(
            type_is(lctx.instance, "object"),
            (
                ForEachKey(
                    lctx.instance,
                    binding,
                    (apply((), child(HERE, Binding(binding))),),
                ),
            ),
        )
    )


def _one_of_consts_evaluate(
    value: JsonValue, cursor: Cursor, ctx: KeywordContext
) -> bool:
    from json_schema_engine.core.json_model import json_equal

    assert isinstance(value, list)
    if any(json_equal(cursor.value, v) for v in value):
        return True
    ctx.error("not one of")
    return False


def _one_of_consts_lower(value: JsonValue, lctx: LoweringContext) -> None:
    assert isinstance(value, list)
    lctx.emit(when(not_(in_consts(INSTANCE, tuple(value))), (fail(("not one of",)),)))


def engine_with_test_vocabulary() -> Engine:
    engine = create_engine()
    engine.dialects.register_vocabulary(
        VOCAB,
        {
            "sweep": KeywordBehavior(
                "urn:test:sweep", _sweep_evaluate, _sweep_analyze, lower=_sweep_lower
            ),
            "oneOfConsts": KeywordBehavior(
                "urn:test:oneOfConsts",
                _one_of_consts_evaluate,
                lower=_one_of_consts_lower,
            ),
        },
    )
    base = engine.dialects.get_dialect(DIALECT_2020_12)
    engine.dialects.register_dialect(DIALECT, [*base.vocabulary_uris, VOCAB])
    return engine


def compile_test_schema(schema: JsonValue, *, conservative: bool = False):
    engine = engine_with_test_vocabulary()
    uri = engine.register_schema(schema, "https://emit.example/s", DIALECT)
    return engine, uri, compile_validator(engine, uri, conservative=conservative)


def _function_count(source: str) -> int:
    return sum(isinstance(n, ast.FunctionDef) for n in ast.parse(source).body)


def test_single_use_children_inline_until_the_loop_cap() -> None:
    # A chain of 24 nested sweeps, each a single-use child: inlining would
    # nest 24 loops, past CPython's block cap. The emitter refuses at the
    # cap and hoists the rest into their own functions.
    schema: JsonValue = {"type": "string"}
    for _ in range(24):
        schema = {"sweep": schema}
    engine, uri, compiled = compile_test_schema(schema)
    functions = _function_count(compiled.source)
    assert 2 < functions < 24  # some inlined, some hoisted, plus validate
    deep: JsonValue = "leaf"
    for _ in range(24):
        deep = {"k": deep}
    assert compiled.validate(deep) is True
    # The leaf test lives 24 levels down: a non-string there fails.
    bad: JsonValue = 1
    for _ in range(24):
        bad = {"k": bad}
    assert compiled.validate(bad) is False
    assert engine.evaluate(uri, deep).valid and not engine.evaluate(uri, bad).valid


def test_conservative_disables_inlining() -> None:
    schema: JsonValue = {"properties": {"a": {"properties": {"b": {"type": "string"}}}}}
    _, _, fast = compile_test_schema(schema)
    _, _, slow = compile_test_schema(schema, conservative=True)
    assert _function_count(fast.source) == 2  # u0 + validate
    assert _function_count(slow.source) == 4
    probes: list[JsonValue] = [{"a": {"b": "x"}}, {"a": {"b": 1}}, {"a": 1}, 1]
    for instance in probes:
        assert fast.validate(instance) == slow.validate(instance)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["a", "b", "c"], "type(v) is str and v in k0"),
        (["a"], "type(v) is str and v == 'a'"),
        ([1, 2.5], "(type(v) is int or type(v) is float) and v in k0"),
        (
            [1, "a"],
            "(type(v) is int or type(v) is float) and v == 1 "
            "or (type(v) is str and v == 'a')",
        ),
        ([None, True], "v is None or v is True"),
        ([[1], {"k": 2}], "H_EQ(v, k0) or H_EQ(v, k1)"),
        ([], "False"),
    ],
)
def test_constant_set_membership_rendering(
    values: list[JsonValue], expected: str
) -> None:
    _, _, compiled = compile_test_schema({"oneOfConsts": values})
    assert expected in compiled.source
    _, _, conservative = compile_test_schema({"oneOfConsts": values}, conservative=True)
    assert " in k" not in conservative.source


def test_constant_set_membership_agrees_with_the_interpreter() -> None:
    values: list[JsonValue] = [1, 2.5, "a", None, True, [1], {"k": 2}]
    engine, uri, compiled = compile_test_schema({"oneOfConsts": values})
    probes: list[JsonValue] = [
        1,
        1.0,
        2.5,
        "a",
        None,
        True,
        False,
        [1],
        {"k": 2},
        {"k": 2.0},
        "b",
        3,
        [1, 1],
    ]
    for probe in probes:
        assert compiled.validate(probe) == engine.evaluate(uri, probe).valid, probe


def test_boolean_subschemas_fold_to_literals() -> None:
    engine, uri, compiled = compile_test_schema(
        {"properties": {"yes": True, "no": False}, "anyOf": [False, True]}
    )
    assert "u1" not in compiled.source
    assert compiled.validate({"yes": 1}) is True
    assert compiled.validate({"no": 1}) is False
    assert engine.evaluate(uri, {"no": 1}).valid is False
    _, _, never = compile_test_schema({"anyOf": [False]})
    assert never.validate(1) is False


def test_draft7_ref_with_siblings_emits_only_the_ref() -> None:
    engine = create_engine(default_dialect=DIALECT_DRAFT_07)
    uri = engine.register_schema(
        {
            "$ref": "#/definitions/a",
            "type": "string",
            "definitions": {"a": {"type": "integer"}},
        },
        "https://emit.example/legacy",
    )
    compiled = compile_validator(engine, uri)
    assert "is str" not in compiled.source
    assert compiled.validate(1) is True and compiled.validate("s") is False


def test_hoisted_regexes_and_constants_are_shared() -> None:
    _, _, compiled = compile_test_schema(
        {"properties": {"a": {"pattern": "^x"}, "b": {"pattern": "^x"}}}
    )
    assert compiled.source.count("R.re['^x']") == 1
