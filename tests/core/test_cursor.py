"""Cursor: lazy JSON Pointer materialization and identity semantics (P7)."""

import pytest

from json_schema_engine.core.cursor import Cursor, child_cursor, root_cursor


def test_root_cursor_pointer_is_empty():
    root = root_cursor({"a": 1})
    assert root.pointer == ""
    assert root.parent is None
    assert root.segment is None


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        ([], ""),
        (["a"], "/a"),
        (["a", "b"], "/a/b"),
        ([0], "/0"),
        (["items", 0, "x"], "/items/0/x"),
        # RFC 6901 escaping of the two special characters, in keys that the
        # suite really uses.
        (["m~n"], "/m~0n"),
        (["a/b"], "/a~1b"),
        (["~1"], "/~01"),
        (["a/b", "c~d"], "/a~1b/c~0d"),
        # An empty member name is a legal pointer segment.
        ([""], "/"),
        (["", ""], "//"),
        # Property names that are prototype traps in JavaScript and ordinary
        # keys in Python (DESIGN.md §5).
        (["__proto__"], "/__proto__"),
        (["constructor", "toString"], "/constructor/toString"),
    ],
)
def test_pointer_materialization(segments, expected):
    cursor = root_cursor(None)
    for segment in segments:
        cursor = child_cursor(cursor, segment, None)
    assert cursor.pointer == expected


def test_pointer_is_cached_and_stable():
    root = root_cursor({"a": {"b": 1}})
    child = child_cursor(root, "a", {"b": 1})
    grandchild = child_cursor(child, "b", 1)
    first = grandchild.pointer
    assert first == "/a/b"
    assert grandchild.pointer is first
    # Materializing a descendant fills the ancestors in on the way back down.
    assert child.pointer == "/a"
    assert root.pointer == ""


def test_pointer_materializes_from_a_partially_cached_chain():
    root = root_cursor(None)
    mid = child_cursor(root, "a", None)
    assert mid.pointer == "/a"
    deep = child_cursor(child_cursor(mid, "b", None), "c", None)
    assert deep.pointer == "/a/b/c"


def test_deep_chains_do_not_exhaust_the_interpreter_stack():
    # Instance depth is attacker-controlled and is not covered by the
    # evaluator's depth budget, so materialization must not recurse.
    cursor = root_cursor(None)
    for i in range(5000):
        cursor = child_cursor(cursor, i, None)
    assert cursor.pointer.startswith("/0/1/2/")
    assert cursor.pointer.endswith("/4999")


def test_structurally_identical_cursors_are_distinct_dict_keys():
    # Channel rule 4 filters dependency records by cursor identity, so two
    # cursors over the same value at the same location must never collapse
    # into one: that is exactly what would make a cousin schema's records
    # visible to `unevaluatedProperties`.
    value = {"a": 1}
    left = child_cursor(root_cursor(value), "a", 1)
    right = child_cursor(root_cursor(value), "a", 1)

    assert left.pointer == right.pointer
    assert left.value == right.value
    assert left != right
    assert left is not right

    seen = {left: "left", right: "right"}
    assert len(seen) == 2
    assert seen[left] == "left"
    assert seen[right] == "right"
    assert len({left, right}) == 2


def test_a_cursor_equals_only_itself():
    cursor = root_cursor(None)
    assert cursor == cursor
    assert cursor != root_cursor(None)
    assert hash(cursor) == hash(cursor)


def test_in_place_application_reuses_the_very_same_cursor():
    # `$ref`, `allOf`, and `if` apply to the same cursor object; only child
    # applicators build new ones. The distinction is the whole basis of rule 4.
    root = root_cursor({"a": 1})
    in_place = root
    child = child_cursor(root, "a", 1)
    assert in_place is root
    assert child is not root
    assert child.parent is root


def test_segment_keeps_string_and_index_apart():
    root = root_cursor([{"0": "x"}])
    element = child_cursor(root, 0, {"0": "x"})
    member = child_cursor(element, "0", "x")
    assert element.segment == 0
    assert isinstance(element.segment, int)
    assert member.segment == "0"
    assert isinstance(member.segment, str)
    assert member.pointer == "/0/0"


def test_cursor_dataclass_shape():
    cursor = Cursor(1, root_cursor(None), "a")
    assert cursor.value == 1
    assert cursor.segment == "a"
    # `slots=True`: no instance `__dict__` to carry stray attributes.
    assert not hasattr(cursor, "__dict__")
