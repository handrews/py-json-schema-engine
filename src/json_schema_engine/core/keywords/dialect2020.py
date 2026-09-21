# Assembly of the built-in 2020-12 dialect from its vocabularies (DESIGN.md
# D2, D11): the same public registry surface an extension author uses, so
# nothing about the built-in drafts is privileged.
#
# Dependency direction: imports every keyword module and `dialect`. The
# `dialects.register_standard_dialects` calls this; keyword modules never
# import this.

from json_schema_engine.core.dialect import DialectRegistry, identifiers_2020
from json_schema_engine.core.keywords._ids import (
    DIALECT_2020_12,
    VOCAB_APPLICATOR,
    VOCAB_CONTENT,
    VOCAB_CORE,
    VOCAB_FORMAT_ANNOTATION,
    VOCAB_META_DATA,
    VOCAB_UNEVALUATED,
    VOCAB_VALIDATION,
)
from json_schema_engine.core.keywords.applicator import APPLICATOR_VOCABULARY
from json_schema_engine.core.keywords.applicator_array import (
    ARRAY_APPLICATOR_VOCABULARY,
)
from json_schema_engine.core.keywords.applicator_object import (
    OBJECT_APPLICATOR_VOCABULARY,
)
from json_schema_engine.core.keywords.content import CONTENT_VOCABULARY
from json_schema_engine.core.keywords.core import CORE_VOCABULARY
from json_schema_engine.core.keywords.format import FORMAT_ANNOTATION_VOCABULARY
from json_schema_engine.core.keywords.meta_data import META_DATA_VOCABULARY
from json_schema_engine.core.keywords.unevaluated import UNEVALUATED_VOCABULARY
from json_schema_engine.core.keywords.validation import VALIDATION_VOCABULARY

# Vocabulary order is evaluation order within a phase: core first so `$ref`
# applies before assertions report, applicators before validation so a
# child's records exist when siblings run. Within `unevaluated`, phase 1
# ordering already guarantees it runs last.
VOCABULARIES_2020_12: tuple[str, ...] = (
    VOCAB_CORE,
    VOCAB_APPLICATOR,
    VOCAB_VALIDATION,
    VOCAB_UNEVALUATED,
    VOCAB_META_DATA,
    VOCAB_FORMAT_ANNOTATION,
    VOCAB_CONTENT,
)


def register_dialect_2020_12(dialects: DialectRegistry) -> None:
    """Register the 2020-12 vocabularies and assemble the dialect."""
    dialects.register_vocabulary(VOCAB_CORE, CORE_VOCABULARY)
    # One vocabulary, three modules: in-place, object, and array applicators
    # are split by keyword class so each can grow on its own.
    dialects.register_vocabulary(
        VOCAB_APPLICATOR,
        {
            **APPLICATOR_VOCABULARY,
            **OBJECT_APPLICATOR_VOCABULARY,
            **ARRAY_APPLICATOR_VOCABULARY,
        },
    )
    dialects.register_vocabulary(VOCAB_VALIDATION, VALIDATION_VOCABULARY)
    dialects.register_vocabulary(VOCAB_UNEVALUATED, UNEVALUATED_VOCABULARY)
    dialects.register_vocabulary(VOCAB_META_DATA, META_DATA_VOCABULARY)
    dialects.register_vocabulary(VOCAB_FORMAT_ANNOTATION, FORMAT_ANNOTATION_VOCABULARY)
    dialects.register_vocabulary(VOCAB_CONTENT, CONTENT_VOCABULARY)
    dialects.register_dialect(
        DIALECT_2020_12, VOCABULARIES_2020_12, identifiers=identifiers_2020
    )
