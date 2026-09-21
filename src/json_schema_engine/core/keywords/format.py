# The `format` keyword (DESIGN.md D2, §3; M1 annotation, M7 assertion).
#
# Two behaviors. `format_annotation` is the default in every standard
# dialect: it records its value and asserts nothing (the suite's mandatory
# `format.json` legs require exactly that). `asserting_format(...)` closes
# over a format table and asserts; it exists in two postures:
#
# - the 2020-12 format-assertion VOCABULARY (`refuse_unknown=True`): a
#   name the table lacks is refused at registration (`UnknownFormatError`),
#   because the metaschema promised assertion for every format;
# - the engine's `assert_formats` option (`refuse_unknown=False`): best
#   effort across every standard dialect, an unknown name annotates only.
#
# Single-table contract: `lower()` resolves the name against the table the
# behavior closed over, and the compiler's runtime resolves it against the
# compiling engine's table. Those are the same table for the two instances
# the engine makes; a custom dialect that wires `asserting_format` with a
# foreign table must drop `lower` (interpret) or expect `FormatTableError`.
#
# Dependency direction: imports `cursor`, `dialect`, `formats` (the table
# contract, never a table), `errors`, `json_model`, `lowering`, and this
# package's `_ids`. Never imports the registry or evaluator.

from collections.abc import Mapping

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
)
from json_schema_engine.core.errors import FormatUnavailableError, UnknownFormatError
from json_schema_engine.core.formats import FormatTable, applies_to
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import (
    VOCAB_FORMAT_ANNOTATION,
    VOCAB_FORMAT_ASSERTION,
    keyword_id,
)
from json_schema_engine.core.lowering import (
    Const,
    LoweringContext,
    and_,
    fail,
    format_test,
    lower_nothing,
    not_,
    type_is,
    when,
)


def _format_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.annotate()
    return True


# Annotation-only: no facts. A `formats` fact means "this keyword tests the
# name against the engine's table", which only the asserting behavior does.
format_annotation = KeywordBehavior(
    id=keyword_id(VOCAB_FORMAT_ANNOTATION, "format"),
    evaluate=_format_evaluate,
    lower=lower_nothing,
)

FORMAT_ANNOTATION_VOCABULARY = {"format": format_annotation}

FORMAT_ASSERTION_ID = keyword_id(VOCAB_FORMAT_ASSERTION, "format")


def _message(name: str) -> str:
    return f"must match format '{name}'"


def asserting_format(
    behavior_id: str, table: FormatTable, *, refuse_unknown: bool
) -> KeywordBehavior:
    """A `format` that asserts through `table` (M7).

    Annotates first (the annotation is the keyword's value, as in the
    annotation-only behavior), then asserts when the table knows the name
    and the instance is of a type the format constrains. An `unavailable`
    entry is refused at registration under both postures.
    """

    def analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
        if not isinstance(value, str):
            return StaticFacts()  # the metaschema's concern
        definition = table.get(value)
        if definition is None:
            if refuse_unknown:
                raise UnknownFormatError(
                    f"format {value!r} is not in the engine's format table"
                )
            return StaticFacts()
        if definition.unavailable is not None:
            raise FormatUnavailableError(
                f"format {value!r} is unavailable: {definition.unavailable}"
            )
        # Exactly the names `lower` emits a `FormatTest` for, so the plan's
        # format list equals the artifact's used-format set.
        return StaticFacts(formats=(value,))

    def evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
        ctx.annotate()
        if not isinstance(value, str):
            return True
        definition = table.get(value)
        if definition is None:
            return True
        if definition.unavailable is not None:  # pragma: no cover - refused earlier
            raise FormatUnavailableError(
                f"format {value!r} is unavailable: {definition.unavailable}"
            )
        instance = cursor.value
        if not applies_to(definition.types, instance) or definition.test(instance):
            return True
        ctx.error(_message(value), {"format": value})
        return False

    def lower(value: JsonValue, lctx: LoweringContext) -> None:
        if not isinstance(value, str):
            return
        definition = table.get(value)
        if definition is None or definition.unavailable is not None:
            return
        instance = lctx.instance
        lctx.emit(
            when(
                and_(
                    type_is(instance, *definition.types),
                    not_(format_test(value, instance)),
                ),
                (fail((_message(value),), {"format": Const(value)}),),
            )
        )

    return KeywordBehavior(
        id=behavior_id, evaluate=evaluate, analyze=analyze, lower=lower
    )


def format_assertion_vocabulary(table: FormatTable) -> Mapping[str, KeywordBehavior]:
    """The 2020-12 format-assertion vocabulary over `table` (refuses unknown names)."""
    return {"format": asserting_format(FORMAT_ASSERTION_ID, table, refuse_unknown=True)}
