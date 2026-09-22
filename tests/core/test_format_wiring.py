# The `format` keyword's wiring (DESIGN.md M7): the two postures of
# `asserting_format`, the engine options, the format-assertion vocabulary,
# the `FormatsRequiredError` rulings, type scoping, error params, and the
# lowered IR shape — through a tiny local table, independent of the real
# predicates.

from pathlib import Path
from typing import Any, cast

import pytest

from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
    FormatDefinition,
    FormatsRequiredError,
    FormatUnavailableError,
    JsonValue,
    UnknownFormatError,
    create_engine,
)
from json_schema_engine.core.keywords.format import (
    FORMAT_ASSERTION_ID,
    asserting_format,
)
from json_schema_engine.core.lowering import (
    INSTANCE,
    Annotate,
    Const,
    Fail,
    FormatTest,
    If,
    Logic,
    Not,
    TypeIs,
)
from json_schema_engine.test_kit import suite_remotes_loader

from .keywords.lowering_helpers import lower

REMOTES_DIR = Path(__file__).resolve().parents[2] / "test-suite" / "remotes"
FA_TRUE = "http://localhost:1234/draft2020-12/format-assertion-true.json"
FA_FALSE = "http://localhost:1234/draft2020-12/format-assertion-false.json"


def _is_ipv4(value: object) -> bool:
    parts = str(value).split(".")
    return len(parts) == 4 and all(p.isdigit() and int(p) < 256 for p in parts)


def _is_int32(value: object) -> bool:
    return isinstance(value, int | float) and -(2**31) <= value < 2**31


TABLE = {
    "ipv4": FormatDefinition(_is_ipv4),
    "int32": FormatDefinition(_is_int32, types=("integer",)),
    "idn-thing": FormatDefinition(lambda v: True, unavailable="needs the 'x' extra"),
}


def test_default_engine_is_annotation_only() -> None:
    engine = create_engine()
    uri = engine.register_schema({"format": "ipv4"}, "https://fmt.example/s")
    result = engine.evaluate(uri, "nope", output="list", annotations=True)
    assert result.valid is True
    assert result.annotations is not None
    assert [a["annotation"] for a in result.annotations] == ["ipv4"]
    assert engine.formats is None


def test_assert_formats_requires_a_table() -> None:
    with pytest.raises(FormatsRequiredError, match="formats="):
        create_engine(assert_formats=True)


def test_assert_formats_asserts_known_names_in_every_dialect() -> None:
    engine = create_engine(formats=TABLE, assert_formats=True)
    assert engine.formats is TABLE
    for declared in (
        None,
        DIALECT_2019_09,
        "http://json-schema.org/draft-07/schema#",
        "http://json-schema.org/draft-06/schema#",
    ):
        schema: dict[str, JsonValue] = {"format": "ipv4"}
        if declared is not None:
            schema["$schema"] = declared
        uri = engine.register_schema(schema, f"https://fmt.example/{declared}")
        assert engine.evaluate(uri, "127.0.0.1").valid is True
        result = engine.evaluate(uri, "nope", output="list", error_params=True)
        assert result.valid is False
        assert result.errors is not None
        (error,) = result.errors
        assert error["error"] == "must match format 'ipv4'"
        assert error.get("params") == {"format": "ipv4"}
        assert error.get("keyword") == "format"


def test_assert_formats_is_best_effort_for_unknown_names() -> None:
    engine = create_engine(formats=TABLE, assert_formats=True)
    uri = engine.register_schema({"format": "no-such"}, "https://fmt.example/u")
    result = engine.evaluate(uri, "anything", output="list", annotations=True)
    assert result.valid is True
    assert result.annotations is not None
    assert [a["annotation"] for a in result.annotations] == ["no-such"]


def test_assertion_annotates_as_well() -> None:
    engine = create_engine(formats=TABLE, assert_formats=True)
    uri = engine.register_schema({"format": "ipv4"}, "https://fmt.example/a")
    result = engine.evaluate(uri, "1.2.3.4", output="list", annotations=True)
    assert result.annotations is not None
    assert [a["annotation"] for a in result.annotations] == ["ipv4"]


def test_type_scoping() -> None:
    engine = create_engine(formats=TABLE, assert_formats=True)
    uri = engine.register_schema({"format": "ipv4"}, "https://fmt.example/t")
    probes: list[JsonValue] = [42, None, [], {}, True]
    for instance in probes:
        assert engine.evaluate(uri, instance).valid is True
    uri = engine.register_schema({"format": "int32"}, "https://fmt.example/i")
    assert engine.evaluate(uri, 2**31).valid is False
    assert engine.evaluate(uri, 5).valid is True
    assert engine.evaluate(uri, 5.0).valid is True
    assert engine.evaluate(uri, 5.5).valid is True  # not an integer: vacuous
    assert engine.evaluate(uri, "5").valid is True


@pytest.mark.parametrize("assert_formats", [False, True])
def test_unavailable_entry_is_refused_at_registration(assert_formats: bool) -> None:
    # Under the vocabulary (a metaschema with core + format-assertion only)
    # and under `assert_formats` (the standard dialect) alike.
    schema: JsonValue = (
        {"$schema": FA_TRUE, "format": "idn-thing"}
        if not assert_formats
        else {"properties": {"a": {"format": "idn-thing"}}}
    )
    engine = create_engine(
        formats=TABLE,
        assert_formats=assert_formats,
        loaders=[suite_remotes_loader(REMOTES_DIR)],
    )
    with pytest.raises(FormatUnavailableError, match="'x' extra") as excinfo:
        engine.load_schema(schema, "https://fmt.example/unavailable")
    expected_location = (
        "https://fmt.example/unavailable#/format"
        if not assert_formats
        else "https://fmt.example/unavailable#/properties/a/format"
    )
    assert excinfo.value.schema_location == expected_location


def test_vocabulary_refuses_unknown_names_with_a_location() -> None:
    engine = create_engine(formats=TABLE, loaders=[suite_remotes_loader(REMOTES_DIR)])
    with pytest.raises(UnknownFormatError) as excinfo:
        engine.load_schema(
            {"$schema": FA_FALSE, "format": "no-such"}, "https://fmt.example/refused"
        )
    assert excinfo.value.schema_location == "https://fmt.example/refused#/format"


@pytest.mark.parametrize("metaschema", [FA_TRUE, FA_FALSE])
def test_vocabulary_asserts_under_both_metaschemas(metaschema: str) -> None:
    # The boolean only governs refusal of unknown vocabularies; a present
    # format-assertion vocabulary asserts either way.
    engine = create_engine(formats=TABLE, loaders=[suite_remotes_loader(REMOTES_DIR)])
    uri = engine.load_schema(
        {"$schema": metaschema, "format": "ipv4"}, "https://fmt.example/vocab"
    )
    assert engine.evaluate(uri, "127.0.0.1").valid is True
    assert engine.evaluate(uri, "not-an-ipv4").valid is False
    assert engine.evaluate(uri, 42).valid is True


@pytest.mark.parametrize("metaschema", [FA_TRUE, FA_FALSE])
def test_vocabulary_without_a_table_is_a_clear_error(metaschema: str) -> None:
    engine = create_engine(loaders=[suite_remotes_loader(REMOTES_DIR)])
    with pytest.raises(FormatsRequiredError, match="formats=") as excinfo:
        engine.load_schema(
            {"$schema": metaschema, "format": "ipv4"}, "https://fmt.example/none"
        )
    assert excinfo.value.schema_location == metaschema


def test_lowered_shape() -> None:
    behavior = asserting_format(FORMAT_ASSERTION_ID, TABLE, refuse_unknown=False)
    # The keyword annotates first (its own value), then asserts (M9).
    annotation, stmt = lower(behavior, "ipv4")
    assert annotation == Annotate()
    assert isinstance(stmt, If)
    assert stmt.cond == Logic(
        "and", (TypeIs(INSTANCE, ("string",)), Not(FormatTest("ipv4", INSTANCE)))
    )
    assert stmt.then == (
        Fail(("must match format 'ipv4'",), {"format": Const("ipv4")}),
    )
    assert lower(behavior, "no-such") == (Annotate(),)
    assert lower(behavior, 5) == (Annotate(),)
    _, int32 = lower(behavior, "int32")
    assert isinstance(int32, If)
    assert isinstance(int32.cond, Logic)
    assert int32.cond.parts[0] == TypeIs(INSTANCE, ("integer",))


def test_facts_report_only_table_names() -> None:
    lenient = asserting_format(FORMAT_ASSERTION_ID, TABLE, refuse_unknown=False)
    assert lenient.facts("ipv4", {}).formats == ("ipv4",)
    assert lenient.facts("no-such", {}).formats == ()
    strict = asserting_format(FORMAT_ASSERTION_ID, TABLE, refuse_unknown=True)
    with pytest.raises(UnknownFormatError):
        strict.facts("no-such", {})
    assert strict.facts(5, {}).formats == ()


def test_dialect_bindings_keep_their_ids() -> None:
    engine = create_engine(formats=TABLE, assert_formats=True)
    plain = create_engine()
    for dialect in (DIALECT_2019_09, DIALECT_DRAFT_07, DIALECT_DRAFT_06):
        asserting = engine.dialects.get_dialect(dialect).keywords["format"]
        annotating = plain.dialects.get_dialect(dialect).keywords["format"]
        assert asserting.behavior.id == annotating.behavior.id
        assert asserting.behavior.lower is not annotating.behavior.lower
    keywords = cast(
        dict[str, Any], engine.dialects.get_dialect(DIALECT_DRAFT_07).keywords
    )
    assert "format" in keywords
