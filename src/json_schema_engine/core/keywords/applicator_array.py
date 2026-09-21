# Array child applicators (DESIGN.md D2, §3): `prefixItems`, `items`, and
# `contains` apply subschemas to array elements and communicate which
# indexes they covered as dependency data (§4 rule 6; draft-03 Appendix D),
# which `unevaluatedItems` folds (M2).
#
# Dependency-data shapes, shared with `unevaluatedItems`:
#   prefixItems  -> True when it covered the whole array, else the largest
#                   applied index (an int)
#   items        -> True (it applied to at least one element past the prefix)
#   contains     -> True when every element matched, else list[int] of the
#                   matched indexes
#
# Dependency direction: imports `cursor`, `dialect`, `json_model`, and
# `_ids`. Never the evaluator or the registry.

from json_schema_engine.core.dialect import KeywordBehavior
from json_schema_engine.core.keywords._ids import VOCAB_APPLICATOR, keyword_id

PREFIX_ITEMS_ID = keyword_id(VOCAB_APPLICATOR, "prefixItems")
ITEMS_ID = keyword_id(VOCAB_APPLICATOR, "items")
CONTAINS_ID = keyword_id(VOCAB_APPLICATOR, "contains")


ARRAY_APPLICATOR_VOCABULARY: dict[str, KeywordBehavior] = {}
