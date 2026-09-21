# The built-in dialects, registered together (DESIGN.md D11): 2020-12,
# 2019-09, draft-07, and draft-06 coexist in one registry, each with its
# own identifier syntax and `$ref` semantics (D18).
#
# Dependency direction: imports the per-draft assembly modules. The engine
# façade calls `register_standard_dialects`.

from json_schema_engine.core.dialect import DialectRegistry
from json_schema_engine.core.keywords.dialect7 import (
    register_dialect_draft_06,
    register_dialect_draft_07,
)
from json_schema_engine.core.keywords.dialect2019 import register_dialect_2019_09
from json_schema_engine.core.keywords.dialect2020 import register_dialect_2020_12


def register_standard_dialects(dialects: DialectRegistry) -> None:
    """Register every built-in vocabulary and dialect."""
    register_dialect_2020_12(dialects)
    register_dialect_2019_09(dialects)
    register_dialect_draft_07(dialects)
    register_dialect_draft_06(dialects)
