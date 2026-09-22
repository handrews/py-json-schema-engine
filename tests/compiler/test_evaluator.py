# `compile_evaluator` (DESIGN.md D1, D6, M9): the wrapper's contract beyond
# the suite legs — output controls are the engine's, the annotation
# selection is fixed at compile time and elided statically, records reach
# the interpreter's own renderers, positions decorate, the registry
# snapshot binds, and an island's exception class is the interpreter's.

import pytest

from json_schema_engine.compiler import compile_evaluator, explain_compilation
from json_schema_engine.core import (
    AnnotationSelection,
    JsonValue,
    OutputOptionsError,
    UnknownKeywordError,
    create_engine,
    parse_json_with_ranges,
)
from json_schema_engine.core.dialect import KeywordBehavior

URI = "https://evaluator.example/s"

SCHEMA: JsonValue = {
    "title": "root",
    "x-vendor": {"a": 1},
    "properties": {
        "a": {"type": "integer", "title": "a", "description": "the a"},
        "b": {"anyOf": [{"type": "string"}, {"minimum": 3}], "title": "b"},
    },
    "required": ["a"],
}


def _engine_and_evaluator(**options: object):
    engine = create_engine()
    uri = engine.register_schema(SCHEMA, URI)
    return engine, uri, compile_evaluator(engine, uri, **options)  # type: ignore[arg-type]


INSTANCES: tuple[JsonValue, ...] = (
    {"a": 1, "b": "x"},
    {"a": "x", "b": 1},
    {"b": 5},
    [],
    {"a": 2, "b": 9},
)


def test_every_non_flag_format_equals_the_interpreter() -> None:
    engine, uri, evaluator = _engine_and_evaluator(annotations=True)
    for instance in INSTANCES:
        for output in ("list", "hierarchical"):
            for verbose in (None, True):
                for trace in (False, True):
                    want = engine.evaluate(
                        uri,
                        instance,
                        output=output,
                        annotations=True,
                        error_params=True,
                        verbose=verbose,
                        trace=trace,
                    )
                    got = evaluator.evaluate(
                        instance,
                        output=output,
                        error_params=True,
                        verbose=verbose,
                        trace=trace,
                    )
                    assert got == want, (instance, output, verbose, trace)
        for output in ("basic", "detailed", "verbose"):
            want = engine.evaluate(
                uri, instance, output=output, annotations=True, error_params=True
            )
            assert (
                evaluator.evaluate(instance, output=output, error_params=True) == want
            )
        want = engine.evaluate(
            uri, instance, output="basic", annotations=True, trace=True
        )
        assert evaluator.evaluate(instance, output="basic", trace=True) == want


def test_output_controls_are_rejected_exactly_as_the_engine_rejects_them() -> None:
    _, _, evaluator = _engine_and_evaluator(annotations=True)
    with pytest.raises(OutputOptionsError):
        evaluator.evaluate({"a": 1}, output="flag")  # annotations with flag
    with pytest.raises(OutputOptionsError):
        evaluator.evaluate({"a": 1}, output="basic", verbose=True)
    with pytest.raises(OutputOptionsError):
        evaluator.evaluate({"a": 1}, output="verbose", verbose=False)
    _, _, plain = _engine_and_evaluator()
    assert plain.evaluate({"a": 1}, output="flag").valid is True
    assert plain.evaluate({"a": 1}, output="list").annotations is None


def test_selection_is_fixed_at_compile_time_and_elided_from_the_source() -> None:
    engine = create_engine()
    uri = engine.register_schema(SCHEMA, URI)
    selection = AnnotationSelection(
        keywords=frozenset({"title"}),
        keep=lambda unit: unit["annotation"] != "b",
    )
    evaluator = compile_evaluator(engine, uri, annotations=selection)
    # `description` is ruled out statically: its value never reaches the
    # module; `keep` runs at evaluation over the rendered unit.
    assert "the a" not in evaluator.source
    assert "root" in evaluator.source
    want = engine.evaluate(
        uri, {"a": 1, "b": "x"}, output="list", annotations=selection
    )
    got = evaluator.evaluate({"a": 1, "b": "x"}, output="list")
    assert got == want
    assert got.annotations is not None
    assert [u["annotation"] for u in got.annotations] == ["a", "root"]
    denied = compile_evaluator(
        engine,
        uri,
        annotations=AnnotationSelection(exclude_keywords=frozenset({"x-vendor"})),
    )
    # The keyword still appears in the trace (unknown keywords trace as
    # valid); its value never reaches the module.
    assert "{'a': 1}" in compile_evaluator(engine, uri, annotations=True).source
    assert "{'a': 1}" not in denied.source
    assert (
        compile_evaluator(engine, uri, annotations=False)
        .evaluate({"a": 1}, output="list")
        .annotations
        is None
    )


def test_verbose_level_carries_dropped_records() -> None:
    engine, uri, evaluator = _engine_and_evaluator(annotations=True)
    instance: JsonValue = {"a": 1, "b": 5}
    want = engine.evaluate(
        uri, instance, output="hierarchical", annotations=True, verbose=True
    )
    got = evaluator.evaluate(instance, output="hierarchical", verbose=True)
    assert got == want
    assert got.dropped_errors  # `anyOf`'s failed string branch
    relevant = evaluator.evaluate(instance, output="hierarchical")
    assert relevant.dropped_errors is None
    assert (
        relevant.output_document
        == engine.evaluate(
            uri, instance, output="hierarchical", annotations=True
        ).output_document
    )


def test_positions_decorate_through_the_engine() -> None:
    text = '{\n  "properties": {"a": {"type": "integer"}}\n}'
    engine = create_engine(loaders=[lambda uri: parse_json_with_ranges(text, uri)])
    uri = engine.load("https://evaluator.example/positioned")
    evaluator = compile_evaluator(engine, uri)
    want = engine.evaluate(uri, {"a": "x"}, output="list", positions=True)
    got = evaluator.evaluate({"a": "x"}, output="list", positions=True)
    assert got == want
    assert got.errors is not None and "source" in got.errors[0]


def test_the_artifact_binds_a_registry_snapshot() -> None:
    engine = create_engine()
    uri = engine.register_schema({"$ref": "https://evaluator.example/later"}, URI)
    evaluator = compile_evaluator(engine, uri)
    engine.register_schema({"type": "string"}, "https://evaluator.example/later")
    assert engine.evaluate(uri, 1).valid is False
    with pytest.raises(Exception):  # noqa: B017 - the snapshot cannot resolve it
        evaluator.evaluate(1, output="list")


def test_an_island_raises_the_interpreters_exception_class() -> None:
    engine = create_engine()
    engine.dialects.register_vocabulary(
        "urn:strict:vocab",
        {"strictKeyword": KeywordBehavior("urn:strict:k", lambda v, c, ctx: True)},
    )
    engine.dialects.register_dialect(
        "urn:strict:dialect",
        [
            *engine.dialects.get_dialect(
                "https://json-schema.org/draft/2020-12/schema"
            ).vocabulary_uris,
            "urn:strict:vocab",
        ],
        allow_unknown_keywords=False,
    )
    uri = engine.register_schema(
        {"$schema": "urn:strict:dialect", "properties": {"a": {"notAKeyword": 1}}}, URI
    )
    explanation = explain_compilation(compile_evaluator(engine, uri).plan)
    assert explanation.causes == {"unlowerable": 1}
    with pytest.raises(UnknownKeywordError):
        engine.evaluate(uri, {"a": 1}, output="list")
    with pytest.raises(UnknownKeywordError):
        compile_evaluator(engine, uri).evaluate({"a": 1}, output="list")
    assert compile_evaluator(engine, uri).evaluate({"b": 1}, output="list").valid
