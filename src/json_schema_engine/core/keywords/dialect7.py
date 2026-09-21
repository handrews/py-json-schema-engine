# Assembly of the built-in draft-07 and draft-06 dialects (DESIGN.md D11,
# D18). These drafts predate vocabularies, so their keywords are grouped
# under registry-internal `urn:jse:vocab:draft-0X:*` names. Shared 2020-12
# and 2019-09 behaviors keep their ids; this draft's own keywords are
# `definitions`, `dependencies`, a `contains` without sibling bounds, and
# the draft-07 `$comment`/`if`/`then`/`else`/`readOnly`/`writeOnly`/
# `content*` that draft-06 lacks.
#
# Dependency direction: imports keyword modules and `dialect`. Called by
# `dialects.register_standard_dialects`.

from collections.abc import Callable, Mapping

from json_schema_engine.core.dialect import (
    DialectRegistry,
    KeywordBehavior,
    identifiers_legacy,
)
from json_schema_engine.core.keywords._ids import (
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
    VOCAB_APPLICATOR_06,
    VOCAB_APPLICATOR_07,
    VOCAB_CONTENT_07,
    VOCAB_CORE_06,
    VOCAB_CORE_07,
    VOCAB_FORMAT_06,
    VOCAB_FORMAT_07,
    VOCAB_META_DATA_06,
    VOCAB_META_DATA_07,
    VOCAB_VALIDATION_06,
    VOCAB_VALIDATION_07,
    keyword_id,
)
from json_schema_engine.core.keywords.applicator import APPLICATOR_VOCABULARY
from json_schema_engine.core.keywords.applicator_array import contains_behavior
from json_schema_engine.core.keywords.applicator_object import (
    OBJECT_APPLICATOR_VOCABULARY,
)
from json_schema_engine.core.keywords.core import (
    CORE_VOCABULARY,
    annotation_only,
    definitions,
    structural,
)
from json_schema_engine.core.keywords.legacy import (
    DEPENDENCIES_VOCABULARY,
    LEGACY_ARRAY_VOCABULARY,
)
from json_schema_engine.core.keywords.validation import VALIDATION_VOCABULARY

# draft-07 keyword sets ---------------------------------------------------

CORE_VOCABULARY_07: Mapping[str, KeywordBehavior] = {
    "$id": structural(keyword_id(VOCAB_CORE_07, "$id")),
    "$schema": structural(keyword_id(VOCAB_CORE_07, "$schema")),
    "$comment": structural(keyword_id(VOCAB_CORE_07, "$comment")),
    "definitions": definitions,
    # `$ref` is the same behavior; ignoring its siblings is the dialect's
    # `ref_ignores_siblings` option, honored by the registry and evaluator.
    "$ref": CORE_VOCABULARY["$ref"],
}

APPLICATOR_VOCABULARY_07: Mapping[str, KeywordBehavior] = (
    {
        name: APPLICATOR_VOCABULARY[name]
        for name in ("allOf", "anyOf", "oneOf", "not", "if", "then", "else")
    }
    | dict(OBJECT_APPLICATOR_VOCABULARY)
    | {
        "contains": contains_behavior(
            keyword_id(VOCAB_APPLICATOR_07, "contains"), sibling_bounds=False
        )
    }
    | dict(LEGACY_ARRAY_VOCABULARY)
    | dict(DEPENDENCIES_VOCABULARY)
)

# draft-07/06 predate minContains/maxContains/dependentRequired: those
# names are unknown keywords there, so registering the 2020-12 behaviors
# would enforce assertions these drafts do not have.
VALIDATION_VOCABULARY_07: Mapping[str, KeywordBehavior] = {
    name: behavior
    for name, behavior in VALIDATION_VOCABULARY.items()
    if name not in {"minContains", "maxContains", "dependentRequired"}
}

META_DATA_VOCABULARY_07: Mapping[str, KeywordBehavior] = {
    name: annotation_only(keyword_id(VOCAB_META_DATA_07, name))
    for name in ("title", "description", "default", "readOnly", "writeOnly", "examples")
}

FORMAT_07_ID = keyword_id(VOCAB_FORMAT_07, "format")
FORMAT_VOCABULARY_07: Mapping[str, KeywordBehavior] = {
    "format": annotation_only(FORMAT_07_ID)
}

type FormatBehaviorFactory = Callable[[str], KeywordBehavior]

CONTENT_VOCABULARY_07: Mapping[str, KeywordBehavior] = {
    name: annotation_only(keyword_id(VOCAB_CONTENT_07, name))
    for name in ("contentMediaType", "contentEncoding")
}

# draft-06 = draft-07 minus $comment, if/then/else, readOnly/writeOnly, and
# the content keywords (a compatible subset; D11).

CORE_VOCABULARY_06: Mapping[str, KeywordBehavior] = {
    "$id": structural(keyword_id(VOCAB_CORE_06, "$id")),
    "$schema": structural(keyword_id(VOCAB_CORE_06, "$schema")),
    "definitions": definitions,
    "$ref": CORE_VOCABULARY["$ref"],
}

APPLICATOR_VOCABULARY_06: Mapping[str, KeywordBehavior] = {
    name: behavior
    for name, behavior in APPLICATOR_VOCABULARY_07.items()
    if name not in {"if", "then", "else"}
}

META_DATA_VOCABULARY_06: Mapping[str, KeywordBehavior] = {
    name: annotation_only(keyword_id(VOCAB_META_DATA_06, name))
    for name in ("title", "description", "default", "examples")
}

FORMAT_06_ID = keyword_id(VOCAB_FORMAT_06, "format")
FORMAT_VOCABULARY_06: Mapping[str, KeywordBehavior] = {
    "format": annotation_only(FORMAT_06_ID)
}

VOCABULARIES_DRAFT_07: tuple[str, ...] = (
    VOCAB_CORE_07,
    VOCAB_APPLICATOR_07,
    VOCAB_VALIDATION_07,
    VOCAB_META_DATA_07,
    VOCAB_FORMAT_07,
    VOCAB_CONTENT_07,
)

VOCABULARIES_DRAFT_06: tuple[str, ...] = (
    VOCAB_CORE_06,
    VOCAB_APPLICATOR_06,
    VOCAB_VALIDATION_06,
    VOCAB_META_DATA_06,
    VOCAB_FORMAT_06,
)


def register_dialect_draft_07(
    dialects: DialectRegistry, *, format_behavior: FormatBehaviorFactory | None = None
) -> None:
    dialects.register_vocabulary(VOCAB_CORE_07, CORE_VOCABULARY_07)
    dialects.register_vocabulary(VOCAB_APPLICATOR_07, APPLICATOR_VOCABULARY_07)
    dialects.register_vocabulary(VOCAB_VALIDATION_07, VALIDATION_VOCABULARY_07)
    dialects.register_vocabulary(VOCAB_META_DATA_07, META_DATA_VOCABULARY_07)
    dialects.register_vocabulary(
        VOCAB_FORMAT_07,
        FORMAT_VOCABULARY_07
        if format_behavior is None
        else {"format": format_behavior(FORMAT_07_ID)},
    )
    dialects.register_vocabulary(VOCAB_CONTENT_07, CONTENT_VOCABULARY_07)
    dialects.register_dialect(
        DIALECT_DRAFT_07,
        VOCABULARIES_DRAFT_07,
        identifiers=identifiers_legacy,
        ref_ignores_siblings=True,
    )


def register_dialect_draft_06(
    dialects: DialectRegistry, *, format_behavior: FormatBehaviorFactory | None = None
) -> None:
    dialects.register_vocabulary(VOCAB_CORE_06, CORE_VOCABULARY_06)
    dialects.register_vocabulary(VOCAB_APPLICATOR_06, APPLICATOR_VOCABULARY_06)
    dialects.register_vocabulary(VOCAB_VALIDATION_06, VALIDATION_VOCABULARY_07)
    dialects.register_vocabulary(VOCAB_META_DATA_06, META_DATA_VOCABULARY_06)
    dialects.register_vocabulary(
        VOCAB_FORMAT_06,
        FORMAT_VOCABULARY_06
        if format_behavior is None
        else {"format": format_behavior(FORMAT_06_ID)},
    )
    dialects.register_dialect(
        DIALECT_DRAFT_06,
        VOCABULARIES_DRAFT_06,
        identifiers=identifiers_legacy,
        ref_ignores_siblings=True,
    )
