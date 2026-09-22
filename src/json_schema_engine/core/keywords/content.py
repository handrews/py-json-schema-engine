# Content vocabulary keywords (DESIGN.md D2, §3; 2020-12 §8.5). All three
# are annotation-only: `contentMediaType`, `contentEncoding`, and
# `contentSchema` are interpreted by an out-of-band decoder, never applied to
# the instance by this engine. `contentSchema`'s *value* is itself a schema
# (§8.5: "MUST be applied ... after decoding ... according to the fully
# decoded value" — a step outside this engine's evaluation), so its
# analyze() declares an empty-relative subschema position purely so the
# registration walk indexes `$id`/`$anchor` inside it; evaluate() still only
# annotates and never calls `ctx.apply()` on it.
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
from json_schema_engine.core.keywords._ids import VOCAB_CONTENT, keyword_id
from json_schema_engine.core.lowering import LoweringContext, annotate

_CONTENT_SCHEMA_FACTS = StaticFacts(subschemas=((),))


def _annotate_lower(_value: JsonValue, lctx: LoweringContext) -> None:
    lctx.emit(annotate())


def _annotate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.annotate()
    return True


def _content_schema_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return _CONTENT_SCHEMA_FACTS


content_media_type = KeywordBehavior(
    id=keyword_id(VOCAB_CONTENT, "contentMediaType"),
    evaluate=_annotate,
    lower=_annotate_lower,
)
content_encoding = KeywordBehavior(
    id=keyword_id(VOCAB_CONTENT, "contentEncoding"),
    evaluate=_annotate,
    lower=_annotate_lower,
)
content_schema = KeywordBehavior(
    id=keyword_id(VOCAB_CONTENT, "contentSchema"),
    evaluate=_annotate,
    analyze=_content_schema_analyze,
    lower=_annotate_lower,
)

CONTENT_VOCABULARY = {
    "contentMediaType": content_media_type,
    "contentEncoding": content_encoding,
    "contentSchema": content_schema,
}
