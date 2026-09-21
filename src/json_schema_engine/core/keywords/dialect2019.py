# Assembly of the built-in 2019-09 dialect (DESIGN.md D11, D18): the
# 2020-12 behaviors reused wherever the semantics are identical, plus this
# draft's own keywords — `$recursiveRef`/`$recursiveAnchor`, tuple-or-schema
# `items`, `additionalItems`, and consumers wired to those producers.
# A shared behavior keeps its 2020-12 id: identity is the semantic, not
# the draft that first named it.
#
# Dependency direction: imports keyword modules and `dialect`. Called by
# `dialects.register_standard_dialects`.

from collections.abc import Callable

from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    identifiers_2019,
)
from json_schema_engine.core.keywords._ids import (
    DIALECT_2019_09,
    VOCAB_APPLICATOR_2019,
    VOCAB_CONTENT_2019,
    VOCAB_CORE_2019,
    VOCAB_FORMAT_2019,
    VOCAB_META_DATA_2019,
    VOCAB_VALIDATION_2019,
    keyword_id,
)
from json_schema_engine.core.keywords.applicator import APPLICATOR_VOCABULARY
from json_schema_engine.core.keywords.applicator_array import CONTAINS, CONTAINS_ID
from json_schema_engine.core.keywords.applicator_object import (
    ADDITIONAL_PROPERTIES_ID,
    OBJECT_APPLICATOR_VOCABULARY,
    PATTERN_PROPERTIES_ID,
    PROPERTIES_ID,
)
from json_schema_engine.core.keywords.core import (
    CORE_VOCABULARY,
    annotation_only,
    recursive_anchor,
    recursive_ref,
)
from json_schema_engine.core.keywords.legacy import (
    ADDITIONAL_ITEMS_ID,
    ITEMS_LEGACY_ID,
    LEGACY_ARRAY_VOCABULARY,
)
from json_schema_engine.core.keywords.unevaluated import (
    unevaluated_items,
    unevaluated_properties,
)
from json_schema_engine.core.keywords.validation import VALIDATION_VOCABULARY

UNEVALUATED_PROPERTIES_2019_ID = keyword_id(
    VOCAB_APPLICATOR_2019, "unevaluatedProperties"
)
UNEVALUATED_ITEMS_2019_ID = keyword_id(VOCAB_APPLICATOR_2019, "unevaluatedItems")

CORE_VOCABULARY_2019 = {
    name: CORE_VOCABULARY[name]
    for name in (
        "$schema",
        "$id",
        "$anchor",
        "$vocabulary",
        "$comment",
        "$defs",
        "$ref",
    )
} | {"$recursiveRef": recursive_ref, "$recursiveAnchor": recursive_anchor}

# 2019-09 has no `unevaluated` vocabulary yet: both consumers live in the
# applicator vocabulary, reading this draft's producers.
APPLICATOR_VOCABULARY_2019 = (
    {
        name: APPLICATOR_VOCABULARY[name]
        for name in (
            "allOf",
            "anyOf",
            "oneOf",
            "not",
            "if",
            "then",
            "else",
            "dependentSchemas",
        )
    }
    | OBJECT_APPLICATOR_VOCABULARY
    | {"contains": CONTAINS}
    | LEGACY_ARRAY_VOCABULARY
    | {
        "unevaluatedProperties": unevaluated_properties(
            UNEVALUATED_PROPERTIES_2019_ID,
            (
                PROPERTIES_ID,
                PATTERN_PROPERTIES_ID,
                ADDITIONAL_PROPERTIES_ID,
                UNEVALUATED_PROPERTIES_2019_ID,
            ),
        ),
        "unevaluatedItems": unevaluated_items(
            UNEVALUATED_ITEMS_2019_ID,
            (
                ITEMS_LEGACY_ID,
                ADDITIONAL_ITEMS_ID,
                CONTAINS_ID,
                UNEVALUATED_ITEMS_2019_ID,
            ),
            ITEMS_LEGACY_ID,
        ),
    }
)

META_DATA_VOCABULARY_2019 = {
    name: annotation_only(keyword_id(VOCAB_META_DATA_2019, name))
    for name in (
        "title",
        "description",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
        "examples",
    )
}

FORMAT_2019_ID = keyword_id(VOCAB_FORMAT_2019, "format")
FORMAT_VOCABULARY_2019 = {"format": annotation_only(FORMAT_2019_ID)}

type FormatBehaviorFactory = Callable[[str], KeywordBehavior]

CONTENT_VOCABULARY_2019 = {
    name: annotation_only(keyword_id(VOCAB_CONTENT_2019, name))
    for name in ("contentMediaType", "contentEncoding", "contentSchema")
}

VOCABULARIES_2019_09: tuple[str, ...] = (
    VOCAB_CORE_2019,
    VOCAB_APPLICATOR_2019,
    VOCAB_VALIDATION_2019,
    VOCAB_META_DATA_2019,
    VOCAB_FORMAT_2019,
    VOCAB_CONTENT_2019,
)


def register_dialect_2019_09(
    dialects: DialectRegistry, *, format_behavior: FormatBehaviorFactory | None = None
) -> None:
    """Register the 2019-09 vocabularies and assemble the dialect."""
    dialects.register_vocabulary(VOCAB_CORE_2019, CORE_VOCABULARY_2019)
    dialects.register_vocabulary(VOCAB_APPLICATOR_2019, APPLICATOR_VOCABULARY_2019)
    dialects.register_vocabulary(VOCAB_VALIDATION_2019, VALIDATION_VOCABULARY)
    dialects.register_vocabulary(VOCAB_META_DATA_2019, META_DATA_VOCABULARY_2019)
    dialects.register_vocabulary(
        VOCAB_FORMAT_2019,
        FORMAT_VOCABULARY_2019
        if format_behavior is None
        else {"format": format_behavior(FORMAT_2019_ID)},
    )
    dialects.register_vocabulary(VOCAB_CONTENT_2019, CONTENT_VOCABULARY_2019)
    dialects.register_dialect(
        DIALECT_2019_09, VOCABULARIES_2019_09, identifiers=identifiers_2019
    )
