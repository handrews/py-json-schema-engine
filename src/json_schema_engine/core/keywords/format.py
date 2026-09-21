# The `format` keyword, annotation-only (DESIGN.md D2, §3; M1 scope). The
# format-assertion vocabulary and the format table (M7) are a later
# milestone; for M1 `format` only records its own value as an annotation.
# analyze() declares the format name via `StaticFacts.formats` purely so a
# later registry pass can screen it against the table (M7) — it has no
# effect on M1 evaluation. `ctx.annotate()`/`return True` is written directly
# here rather than imported from `keywords/core.py`'s `annotation_only()`
# factory (owned by another concurrent session).
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and this
# package's `_ids`. Never imports the registry or evaluator.

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
)
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import VOCAB_FORMAT_ANNOTATION, keyword_id
from json_schema_engine.core.lowering import lower_nothing


def _format_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return StaticFacts(formats=(value,)) if isinstance(value, str) else StaticFacts()


def _format_evaluate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.annotate()
    return True


format_annotation = KeywordBehavior(
    id=keyword_id(VOCAB_FORMAT_ANNOTATION, "format"),
    evaluate=_format_evaluate,
    analyze=_format_analyze,
    lower=lower_nothing,
)

FORMAT_ANNOTATION_VOCABULARY = {"format": format_annotation}
