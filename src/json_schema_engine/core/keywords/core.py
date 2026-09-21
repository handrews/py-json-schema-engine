# Core vocabulary keywords (DESIGN.md D2, D18, §3): the `structural` and
# `annotation_only` keyword-class factories, and `$ref` as the EXEMPLAR of
# the reference class.

from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.dialect import (
    AnalyzeContext,
    AnalyzeFn,
    KeywordBehavior,
    KeywordContext,
    StaticFacts,
)
from json_schema_engine.core.errors import InvalidSchemaError
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import VOCAB_CORE, keyword_id

_EMPTY_FACTS = StaticFacts()


def _true(_value: JsonValue, _cursor: Cursor, _ctx: KeywordContext) -> bool:
    """Evaluation for a keyword that never fails and never annotates."""
    return True


def self_position(_value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    """Static facts for a keyword whose own value is a subschema (`if`, `not`)."""
    return StaticFacts(subschemas=((),))


def map_positions(value: JsonValue) -> StaticFacts:
    """Static facts for a keyword whose value is a name-keyed map of subschemas."""
    if not is_object(value):
        return _EMPTY_FACTS
    return StaticFacts(subschemas=tuple((name,) for name in value))


def structural(behavior_id: str, analyze: AnalyzeFn | None = None) -> KeywordBehavior:
    """An identifier/reserved keyword: no evaluation behavior, no annotation."""
    return KeywordBehavior(behavior_id, _true, analyze=analyze, structural=True)


def annotation_only(behavior_id: str) -> KeywordBehavior:
    """EXEMPLAR (annotation-only class): the keyword's value is its annotation."""

    def _evaluate(_value: JsonValue, _cursor: Cursor, ctx: KeywordContext) -> bool:
        ctx.annotate()
        return True

    return KeywordBehavior(behavior_id, _evaluate)


def inert_subschema(behavior_id: str) -> KeywordBehavior:
    """A keyword whose value is a subschema position, applied by a sibling.

    The value is registered (for identifier indexing and transitive
    loading) but this behavior itself never applies it — a driving sibling
    keyword (`if` for `then`/`else`) owns the application.
    """
    return KeywordBehavior(behavior_id, _true, analyze=self_position, structural=True)


def _defs_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return map_positions(value)


def _ref_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not isinstance(value, str):
        return _EMPTY_FACTS
    return StaticFacts(references=(value,))


def _ref_evaluate(value: JsonValue, _cursor: Cursor, ctx: KeywordContext) -> bool:
    if not isinstance(value, str):
        raise InvalidSchemaError("'$ref' value must be a string")
    return ctx.apply_resolved(ctx.resolve_ref(value))


# EXEMPLAR (reference class): resolve against the lexical base, apply the
# target at the same cursor. The engine owns the evaluation-path extension
# and the frame, so the behavior itself is one line.
ref = KeywordBehavior(
    keyword_id(VOCAB_CORE, "$ref"), _ref_evaluate, analyze=_ref_analyze
)


def _dynamic_ref_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not isinstance(value, str):
        return _EMPTY_FACTS
    return StaticFacts(references=(value,), dynamic_scope_sensitive=True)


def _dynamic_ref_evaluate(
    value: JsonValue, _cursor: Cursor, ctx: KeywordContext
) -> bool:
    if not isinstance(value, str):
        raise InvalidSchemaError("'$dynamicRef' value must be a string")
    return ctx.apply_resolved(ctx.resolve_dynamic(value))


# D8: the lexical target must exist; a plain-name fragment minted by a
# `$dynamicAnchor` then rebinds to the outermost dynamic scope that carries
# the same anchor. The engine owns the scope stack; the keyword only asks.
dynamic_ref = KeywordBehavior(
    keyword_id(VOCAB_CORE, "$dynamicRef"),
    _dynamic_ref_evaluate,
    analyze=_dynamic_ref_analyze,
)


CORE_VOCABULARY: dict[str, KeywordBehavior] = {
    "$schema": structural(keyword_id(VOCAB_CORE, "$schema")),
    "$id": structural(keyword_id(VOCAB_CORE, "$id")),
    "$anchor": structural(keyword_id(VOCAB_CORE, "$anchor")),
    "$dynamicAnchor": structural(keyword_id(VOCAB_CORE, "$dynamicAnchor")),
    "$vocabulary": structural(keyword_id(VOCAB_CORE, "$vocabulary")),
    "$comment": structural(keyword_id(VOCAB_CORE, "$comment")),
    "$defs": structural(keyword_id(VOCAB_CORE, "$defs"), analyze=_defs_analyze),
    "$ref": ref,
    "$dynamicRef": dynamic_ref,
}
