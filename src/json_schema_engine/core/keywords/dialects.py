# The built-in dialects, registered together (DESIGN.md D11): 2020-12,
# 2019-09, draft-07, and draft-06 coexist in one registry, each with its
# own identifier syntax and `$ref` semantics (D18).
#
# Dependency direction: imports the per-draft assembly modules. The engine
# façade calls `register_standard_dialects`.

from collections.abc import Callable

from json_schema_engine.core.dialect import DialectRegistry, KeywordBehavior
from json_schema_engine.core.keywords.dialect7 import (
    register_dialect_draft_06,
    register_dialect_draft_07,
)
from json_schema_engine.core.keywords.dialect2019 import register_dialect_2019_09
from json_schema_engine.core.keywords.dialect2020 import register_dialect_2020_12

type FormatBehaviorFactory = Callable[[str], KeywordBehavior]
"""Builds each dialect's `format` behavior from that dialect's behavior id
(M7 `assert_formats`): the binding is replaced, the id is kept."""


def register_standard_dialects(
    dialects: DialectRegistry, *, format_behavior: FormatBehaviorFactory | None = None
) -> None:
    """Register every built-in vocabulary and dialect."""
    register_dialect_2020_12(dialects, format_behavior=format_behavior)
    register_dialect_2019_09(dialects, format_behavior=format_behavior)
    register_dialect_draft_07(dialects, format_behavior=format_behavior)
    register_dialect_draft_06(dialects, format_behavior=format_behavior)
