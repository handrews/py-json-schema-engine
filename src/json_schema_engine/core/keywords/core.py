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
    SubschemaApplication,
)
from json_schema_engine.core.errors import InvalidSchemaError
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.keywords._ids import (
    VOCAB_CORE,
    VOCAB_CORE_07,
    VOCAB_CORE_2019,
    keyword_id,
)
from json_schema_engine.core.lowering import (
    HERE,
    LoweringContext,
    annotate,
    apply,
    lower_nothing,
)

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
    return KeywordBehavior(
        behavior_id, _true, analyze=analyze, structural=True, lower=lower_nothing
    )


def annotation_only(behavior_id: str) -> KeywordBehavior:
    """EXEMPLAR (annotation-only class): the keyword's value is its annotation."""

    def _evaluate(_value: JsonValue, _cursor: Cursor, ctx: KeywordContext) -> bool:
        ctx.annotate()
        return True

    def _lower(_value: JsonValue, lctx: LoweringContext) -> None:
        # Asserts nothing; the evaluator tier records the annotation (M9).
        lctx.emit(annotate())

    return KeywordBehavior(behavior_id, _evaluate, lower=_lower)


def inert_subschema(behavior_id: str) -> KeywordBehavior:
    """A keyword whose value is a subschema position, applied by a sibling.

    The value is registered (for identifier indexing and transitive
    loading) but this behavior itself never applies it — a driving sibling
    keyword (`if` for `then`/`else`) owns the application.
    """
    return KeywordBehavior(
        behavior_id, _true, analyze=self_position, structural=True, lower=lower_nothing
    )


def _defs_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    return map_positions(value)


def _ref_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not isinstance(value, str):
        return _EMPTY_FACTS
    return StaticFacts(
        references=(value,),
        applications=(
            SubschemaApplication(
                (), "in_place", conditional=False, asserts=True, ref=value
            ),
        ),
    )


def _ref_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if isinstance(value, str):
        lctx.emit(apply((), HERE, ref=value))


def _ref_evaluate(value: JsonValue, _cursor: Cursor, ctx: KeywordContext) -> bool:
    if not isinstance(value, str):
        raise InvalidSchemaError("'$ref' value must be a string")
    return ctx.apply_resolved(ctx.resolve_ref(value))


# EXEMPLAR (reference class): resolve against the lexical base, apply the
# target at the same cursor. The engine owns the evaluation-path extension
# and the frame, so the behavior itself is one line.
ref = KeywordBehavior(
    keyword_id(VOCAB_CORE, "$ref"),
    _ref_evaluate,
    analyze=_ref_analyze,
    lower=_ref_lower,
)


def _dynamic_ref_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not isinstance(value, str):
        return _EMPTY_FACTS
    # The application carries the `resolution` fact (M9): the planner
    # resolves the site at plan time when every path agrees on the target
    # and islands it otherwise; `dynamic_scope_sensitive` still says the
    # keyword needs discharging — a dynamic keyword without such a fact
    # islands unconditionally.
    return StaticFacts(
        references=(value,),
        dynamic_scope_sensitive=True,
        applications=(
            SubschemaApplication(
                (),
                "in_place",
                conditional=False,
                asserts=True,
                ref=value,
                resolution="dynamic",
            ),
        ),
    )


def _dynamic_ref_lower(value: JsonValue, lctx: LoweringContext) -> None:
    # Lowers exactly like `$ref`: the plan holds the resolved target.
    if isinstance(value, str):
        lctx.emit(apply((), HERE, ref=value, resolution="dynamic"))


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
    lower=_dynamic_ref_lower,
)


def _recursive_ref_analyze(value: JsonValue, _ctx: AnalyzeContext) -> StaticFacts:
    if not isinstance(value, str):
        return _EMPTY_FACTS
    return StaticFacts(
        references=(value,),
        dynamic_scope_sensitive=True,
        applications=(
            SubschemaApplication(
                (),
                "in_place",
                conditional=False,
                asserts=True,
                ref=value,
                resolution="recursive",
            ),
        ),
    )


def _recursive_ref_lower(value: JsonValue, lctx: LoweringContext) -> None:
    if isinstance(value, str):
        lctx.emit(apply((), HERE, ref=value, resolution="recursive"))


def _recursive_ref_evaluate(
    value: JsonValue, _cursor: Cursor, ctx: KeywordContext
) -> bool:
    if not isinstance(value, str):
        raise InvalidSchemaError("'$recursiveRef' value must be a string")
    return ctx.apply_resolved(ctx.resolve_recursive(value))


# 2019-09's degenerate case of `$dynamicRef` (D8): rebinding is all or
# nothing on a resource root's `$recursiveAnchor: true` rather than a name.
recursive_ref = KeywordBehavior(
    keyword_id(VOCAB_CORE_2019, "$recursiveRef"),
    _recursive_ref_evaluate,
    analyze=_recursive_ref_analyze,
    lower=_recursive_ref_lower,
)

# Indexed by the registration walk through the 2019-09 identifier
# extractor; the keyword itself evaluates to nothing.
recursive_anchor = structural(keyword_id(VOCAB_CORE_2019, "$recursiveAnchor"))

# draft-07/06's `$defs`: a map of schemas reachable only by reference.
definitions = structural(
    keyword_id(VOCAB_CORE_07, "definitions"), analyze=_defs_analyze
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
