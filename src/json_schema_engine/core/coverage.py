# Evaluated-coverage folds (DESIGN.md §4 rule 4, D9a; M9): how a consumer
# turns the dependency data it can see into "which names/indexes are
# covered". One implementation serves both tiers: the interpreter's
# `unevaluated*` keywords fold their visible records, and a compiled
# artifact's tracked consumer folds its region channel through the same
# functions (bound as runtime helpers), so the two cannot drift.
#
# Entries are `(behavior_id, data)` pairs in production order; `data` has
# the producers' shapes: `list[str]` (names), `True` (everything),
# `int` (the largest applied index, from the prefix producer), `list[int]`
# (matched indexes, from `contains`). Entries whose producer is not in
# `consumes` are ignored, and shapes a half does not speak are skipped.
#
# Dependency direction: a leaf; imports nothing from the engine.

from collections.abc import Collection, Iterable
from typing import cast


def fold_name_coverage(
    entries: Iterable[tuple[str, object]], consumes: Collection[str]
) -> set[str]:
    """The names covered by the visible name producers."""
    covered: set[str] = set()
    for behavior_id, data in entries:
        if behavior_id in consumes and isinstance(data, list):
            for name in cast(list[object], data):
                if isinstance(name, str):
                    covered.add(name)
    return covered


def fold_index_coverage(
    entries: Iterable[tuple[str, object]],
    length: int,
    consumes: Collection[str],
    contains_id: str | None,
    prefix_id: str | None,
) -> tuple[int, set[int]]:
    """`(covered_prefix, covered)`: every index below the prefix is
    covered, plus the individual indexes in the set."""
    covered_prefix = 0
    covered: set[int] = set()
    for behavior_id, data in entries:
        if behavior_id not in consumes:
            continue
        if behavior_id == contains_id:
            if data is True:
                covered_prefix = length
            elif isinstance(data, list):
                for index in cast(list[object], data):
                    if isinstance(index, int):
                        covered.add(index)
        elif data is True:
            covered_prefix = length
        elif behavior_id == prefix_id and isinstance(data, int):
            covered_prefix = max(covered_prefix, data + 1)
    return covered_prefix, covered
