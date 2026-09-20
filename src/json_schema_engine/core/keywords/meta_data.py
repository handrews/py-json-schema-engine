# Meta-data vocabulary keywords (DESIGN.md §3): every member is
# annotation-only, so this module is a thin instantiation of the
# `annotation_only` exemplar from `core.py` — no keyword-specific semantics.

from json_schema_engine.core.dialect import KeywordBehavior
from json_schema_engine.core.keywords._ids import VOCAB_META_DATA, keyword_id
from json_schema_engine.core.keywords.core import annotation_only

META_DATA_VOCABULARY: dict[str, KeywordBehavior] = {
    name: annotation_only(keyword_id(VOCAB_META_DATA, name))
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
