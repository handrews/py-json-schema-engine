# The evaluated-coverage folds (M9): one implementation for both tiers.

from json_schema_engine.core.coverage import fold_index_coverage, fold_name_coverage

NAMES = "urn:p"
CONTAINS = "urn:c"
PREFIX = "urn:pre"
ITEMS = "urn:i"


def test_name_fold_reads_only_consumed_name_lists() -> None:
    entries = [
        (NAMES, ["a", "b"]),
        ("urn:other", ["z"]),
        (NAMES, True),
        (NAMES, [1, "c"]),
    ]
    assert fold_name_coverage(entries, {NAMES}) == {"a", "b", "c"}


def test_index_fold_merges_prefix_items_and_contains() -> None:
    entries = [(PREFIX, 1), (CONTAINS, [3]), ("urn:other", True)]
    consumes = {PREFIX, CONTAINS, ITEMS}
    assert fold_index_coverage(entries, 5, consumes, CONTAINS, PREFIX) == (2, {3})
    assert fold_index_coverage([(ITEMS, True)], 5, consumes, CONTAINS, PREFIX) == (
        5,
        set(),
    )
    assert fold_index_coverage([(CONTAINS, True)], 4, consumes, CONTAINS, PREFIX) == (
        4,
        set(),
    )
    assert fold_index_coverage([], 4, consumes, CONTAINS, PREFIX) == (0, set())
