# Tests for the M2 `unevaluatedItems` keyword (DESIGN.md §3, §4 rules 3, 4,
# 6) and for `unevaluatedProperties`'s newly widened `consumes` set now that
# `patternProperties`/`additionalProperties` exist (M1 covered only
# `properties`). `unevaluatedItems` mirrors the `unevaluatedProperties`
# exemplar already covered by `tests/core/keywords/test_applicator.py`, so
# these tests focus on what is new: folding `prefixItems`/`items`/`contains`
# coverage, merging it across `allOf` branches, dropping a failed `anyOf`
# branch's coverage, and a nested `unevaluatedItems` producing its own
# dependency record.
#
# `contains`'s partial-match tests reuse the structural discriminator from
# `test_applicator_array.py`: `{"items": False}` matches an array element iff
# it is itself an empty array.

import re

from json_schema_engine.core.dialect import (
    CompiledRegex,
    DialectRegistry,
    KeywordBehavior,
    identifiers_2020,
)
from json_schema_engine.core.evaluator import EvalState, run_evaluation
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.keywords._ids import (
    DIALECT_2020_12,
    VOCAB_APPLICATOR,
    VOCAB_UNEVALUATED,
)
from json_schema_engine.core.keywords.applicator import ALL_OF, ANY_OF
from json_schema_engine.core.keywords.applicator_array import (
    ARRAY_APPLICATOR_VOCABULARY,
)
from json_schema_engine.core.keywords.applicator_object import (
    OBJECT_APPLICATOR_VOCABULARY,
)
from json_schema_engine.core.keywords.unevaluated import (
    UNEVALUATED_ITEMS,
    UNEVALUATED_VOCABULARY,
)
from json_schema_engine.core.registry import SchemaRegistry

APPLICATOR_KEYWORDS: dict[str, KeywordBehavior] = {
    "allOf": ALL_OF,
    "anyOf": ANY_OF,
    **ARRAY_APPLICATOR_VOCABULARY,
    **OBJECT_APPLICATOR_VOCABULARY,
}


def make_registry() -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB_APPLICATOR, APPLICATOR_KEYWORDS)
    dialects.register_vocabulary(VOCAB_UNEVALUATED, UNEVALUATED_VOCABULARY)
    dialects.register_dialect(
        DIALECT_2020_12,
        [VOCAB_APPLICATOR, VOCAB_UNEVALUATED],
        allow_unknown_keywords=False,
        identifiers=identifiers_2020,
    )
    return SchemaRegistry(dialects, DIALECT_2020_12)


class _ReRegex:
    """A `CompiledRegex` over stdlib `re`, sufficient for these tests'
    plain `patternProperties` patterns (no ECMA-262 translation needed)."""

    def __init__(self, pattern: str) -> None:
        self._compiled = re.compile(pattern)

    def search(self, text: str) -> bool:
        return self._compiled.search(text) is not None


def _compile_regex(pattern: str) -> CompiledRegex:
    return _ReRegex(pattern)


def run(schema: JsonValue, instance: JsonValue) -> tuple[bool, EvalState]:
    registry = make_registry()
    uri = registry.register(schema, "https://unevaluated.example/schema")
    return run_evaluation(registry, uri, instance, compile_regex=_compile_regex)


# --- unevaluatedItems: individual producers -------------------------------


def test_unevaluated_items_folds_prefix_items_coverage() -> None:
    schema: JsonValue = {"prefixItems": [{}], "unevaluatedItems": False}
    assert run(schema, [1])[0] is True
    assert run(schema, [1, 2])[0] is False


def test_unevaluated_items_folds_items_coverage() -> None:
    # `items` (no sibling `prefixItems`) covers every index by itself, so
    # `unevaluatedItems: false` never finds anything left to reject.
    schema: JsonValue = {"items": {}, "unevaluatedItems": False}
    assert run(schema, [1, 2, 3])[0] is True
    assert run(schema, [])[0] is True


def test_unevaluated_items_folds_contains_matched_indexes() -> None:
    schema: JsonValue = {
        "contains": {"items": False},
        "unevaluatedItems": False,
    }
    # contains matches indexes 0 and 2 (the empty arrays); index 1 is left
    # unevaluated and unevaluatedItems: false rejects it.
    assert run(schema, [[], [1], []])[0] is False
    # Every element matches: contains produces True (whole-array shortcut),
    # so nothing is left unevaluated.
    assert run(schema, [[], []])[0] is True


# --- unevaluatedItems: combined within one schema object -------------------


def test_unevaluated_items_merges_prefix_items_and_contains_together() -> None:
    schema: JsonValue = {
        "prefixItems": [{}],
        "contains": {"items": False},
        "unevaluatedItems": False,
    }
    # index 0: covered by prefixItems (any value). index 1: an empty array,
    # covered by contains. Nothing left over.
    assert run(schema, [9, []])[0] is True
    # A third, non-empty-array element is covered by neither producer.
    assert run(schema, [9, [], [1, 2]])[0] is False


# --- unevaluatedItems: cross-application merging and relevance ------------


def test_unevaluated_items_merges_coverage_across_all_of_branches() -> None:
    # Same coverage as the combined test above, but split across two allOf
    # branches: their dependency records must both merge into the parent
    # frame (§4 rule 3) for unevaluatedItems to see the full picture.
    schema: JsonValue = {
        "allOf": [
            {"prefixItems": [{}]},
            {"contains": {"items": False}},
        ],
        "unevaluatedItems": False,
    }
    assert run(schema, [9, []])[0] is True
    assert run(schema, [9, [], [1, 2]])[0] is False


def test_unevaluated_items_ignores_coverage_from_a_failed_anyof_branch() -> None:
    # TS channels test, array-side: a failing branch's coverage must not
    # count, even though the branch as a whole never surfaces as an error
    # (anyOf accepts via its other branch).
    schema: JsonValue = {
        "anyOf": [
            {"prefixItems": [{}]},
            {"prefixItems": [{}, {}], "allOf": [False]},
        ],
        "unevaluatedItems": False,
    }
    assert run(schema, [1, 2])[0] is False
    assert run(schema, [1])[0] is True


def test_nested_unevaluated_items_produces_true_when_it_applied() -> None:
    # A nested unevaluatedItems, inside an allOf branch, merges its own
    # dependency record up to the root frame on success (§4 rule 3), the
    # same path test_applicator.py's properties test exercises.
    schema: JsonValue = {"allOf": [{"unevaluatedItems": {}}]}
    _, state = run(schema, [1, 2])
    produced = [
        d.data for d in state.root_dependencies if d.behavior_id == UNEVALUATED_ITEMS.id
    ]
    assert produced == [True]

    # An empty array: unevaluatedItems never applies, so it produces nothing.
    _, state = run(schema, [])
    assert not any(
        d.behavior_id == UNEVALUATED_ITEMS.id for d in state.root_dependencies
    )


def test_unevaluated_items_non_array_instance_passes() -> None:
    schema: JsonValue = {"unevaluatedItems": False}
    assert run(schema, {"a": 1})[0] is True
    assert run(schema, "string")[0] is True


# --- unevaluatedProperties: widened consumes (patternProperties, ----------
# --- additionalProperties) --------------------------------------------------


def test_unevaluated_properties_folds_pattern_properties_coverage() -> None:
    schema: JsonValue = {
        "patternProperties": {"^x": {}},
        "unevaluatedProperties": False,
    }
    assert run(schema, {"xa": 1})[0] is True
    assert run(schema, {"xa": 1, "other": 2})[0] is False


def test_unevaluated_properties_folds_additional_properties_coverage() -> None:
    # No sibling properties/patternProperties: additionalProperties alone
    # covers every member, so nothing is ever left unevaluated.
    schema: JsonValue = {
        "additionalProperties": {},
        "unevaluatedProperties": False,
    }
    assert run(schema, {"a": 1, "b": 2})[0] is True


def test_unevaluated_properties_merges_pattern_and_additional_properties() -> None:
    schema: JsonValue = {
        "patternProperties": {"^x": {}},
        "additionalProperties": {},
        "unevaluatedProperties": False,
    }
    assert run(schema, {"xa": 1, "other": 2})[0] is True
