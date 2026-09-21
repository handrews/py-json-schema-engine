"""Channel data: path materialization, record identity, frame shape (§4, P6, P7)."""

import pytest

from json_schema_engine.core.channel import (
    AnnotationRecord,
    DependencyRecord,
    ErrorRecord,
    Frame,
    PathNode,
    TraceNode,
    materialize_path,
)
from json_schema_engine.core.cursor import child_cursor, root_cursor
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.ref import SchemaRef

SCHEMA_REF = SchemaRef({"type": "string"}, "https://example.com/s", "/$defs/a")


def path_of(*segments: str) -> PathNode | None:
    node: PathNode | None = None
    for segment in segments:
        node = PathNode(node, segment)
    return node


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        ((), ""),
        (("properties",), "/properties"),
        (("properties", "a"), "/properties/a"),
        (("allOf", "0", "properties", "b"), "/allOf/0/properties/b"),
        (("$ref", "properties", "x"), "/$ref/properties/x"),
        # Segments arrive pre-escaped, so a member name containing `/` is
        # already `~1` by the time it becomes a node.
        (("properties", "a~1b"), "/properties/a~1b"),
        (("properties", "m~0n"), "/properties/m~0n"),
        # An empty property name is a legal segment.
        (("properties", ""), "/properties/"),
    ],
)
def test_path_node_materialize(segments, expected):
    node = path_of(*segments)
    assert materialize_path(node) == expected
    if node is not None:
        assert node.materialize() == expected


def test_materialize_path_of_the_root_application_is_empty():
    assert materialize_path(None) == ""


def test_path_nodes_are_shared_not_copied():
    # Sibling keywords hang off one parent node; materialization walks up,
    # so a shared prefix is stored once however wide the schema is.
    parent = PathNode(None, "properties")
    left = PathNode(parent, "a")
    right = PathNode(parent, "b")
    assert left.parent is right.parent is parent
    assert left.materialize() == "/properties/a"
    assert right.materialize() == "/properties/b"


def test_path_node_is_frozen_and_identity_keyed():
    node = PathNode(None, "properties")
    twin = PathNode(None, "properties")
    assert node != twin
    assert len({node, twin}) == 2
    with pytest.raises(AttributeError):
        node.segment = "items"


def make_annotation(
    *,
    keyword_name: str = "title",
    vocabulary_uri: str | None = "https://json-schema.org/vocab/meta-data",
    value: JsonValue = "A title",
) -> AnnotationRecord:
    return AnnotationRecord(
        behavior_id=f"https://json-schema.org/keyword/{keyword_name}",
        keyword_name=keyword_name,
        vocabulary_uri=vocabulary_uri,
        schema_ref=SCHEMA_REF,
        path_node=PathNode(None, "properties"),
        cursor=root_cursor({"a": 1}),
        value=value,
    )


def test_annotation_record_holds_the_keywords_own_value():
    record = make_annotation()
    assert record.value == "A title"
    assert record.keyword_name == "title"
    assert record.schema_ref.location == "https://example.com/s#/$defs/a"


def test_records_with_identical_fields_are_distinct():
    # Records are identity-keyed (P7): the evaluator keeps them in lists and
    # filters by object identity, never by value.
    left = make_annotation()
    right = make_annotation()
    assert left != right
    assert len({left, right}) == 2
    assert left == left


def test_unknown_keyword_annotation_has_no_vocabulary():
    record = make_annotation(vocabulary_uri=None, keyword_name="x-vendor")
    assert record.vocabulary_uri is None


def test_dependency_record_carries_arbitrary_python_data():
    # Dependency data is internal and never rendered, so it is not a
    # JsonValue: `unevaluatedProperties` consumes a set of names.
    cursor = root_cursor({"a": 1})
    record = DependencyRecord(
        behavior_id="https://json-schema.org/keyword/properties",
        keyword_name="properties",
        vocabulary_uri="https://json-schema.org/vocab/applicator",
        schema_ref=SCHEMA_REF,
        path_node=None,
        cursor=cursor,
        data={"a", "b"},
    )
    assert record.data == {"a", "b"}
    assert record.cursor is cursor


def test_dependency_records_are_filtered_by_cursor_identity():
    # A stand-in for channel rule 4: the real filter lives in the evaluator,
    # but it can only work if equal-looking cursors stay distinct keys.
    parent = root_cursor({"a": 1, "b": 2})
    here = child_cursor(parent, "a", 1)
    cousin = child_cursor(root_cursor({"a": 1, "b": 2}), "a", 1)
    records = [
        DependencyRecord(
            behavior_id="id",
            keyword_name="k",
            vocabulary_uri=None,
            schema_ref=SCHEMA_REF,
            path_node=None,
            cursor=cursor,
            data=name,
        )
        for cursor, name in ((here, "mine"), (cousin, "cousin"))
    ]
    visible = [r for r in records if r.cursor is here]
    assert [r.data for r in visible] == ["mine"]


def test_error_record_names_no_keyword_for_a_boolean_false_schema():
    record = ErrorRecord(
        behavior_id=None,
        keyword_name=None,
        vocabulary_uri=None,
        schema_ref=SchemaRef(False, "https://example.com/s", "/$defs/never"),
        path_node=PathNode(None, "$defs"),
        cursor=root_cursor(1),
        message="schema is false",
    )
    assert record.keyword_name is None
    assert record.params is None


def test_error_record_params_are_separate_from_the_message():
    record = ErrorRecord(
        behavior_id="https://json-schema.org/keyword/maxLength",
        keyword_name="maxLength",
        vocabulary_uri="https://json-schema.org/vocab/validation",
        schema_ref=SCHEMA_REF,
        path_node=None,
        cursor=root_cursor("abcd"),
        message="string is longer than 3 characters",
        params={"limit": 3, "length": 4},
    )
    assert record.params == {"limit": 3, "length": 4}


def test_frame_starts_empty_and_each_frame_gets_its_own_lists():
    first = Frame()
    second = Frame()
    assert first.annotations == []
    assert first.dependencies == []
    first.annotations.append(make_annotation())
    assert second.annotations == []


def test_frame_merge_is_a_list_extension():
    # Rule 3 in miniature: on success a frame's records move to its parent.
    parent = Frame()
    child = Frame()
    child.annotations.append(make_annotation())
    parent.annotations.extend(child.annotations)
    assert len(parent.annotations) == 1
    assert parent.annotations[0] is child.annotations[0]


def test_trace_node_stub():
    cursor = root_cursor({"a": 1})
    node = TraceNode(schema_ref=SCHEMA_REF, path_node=None, cursor=cursor)
    child = TraceNode(
        schema_ref=SCHEMA_REF, path_node=PathNode(None, "a"), cursor=cursor
    )
    node.children.append(child)
    assert node.children == [child]
    assert node.keyword_results == []
    assert node != child
