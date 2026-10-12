"""Records → the located tree (records.py): `to_render_node`, and the
relevant level's pruning of record-free applications (D6)."""

import pytest

from json_schema_engine.core import JsonValue, create_engine
from json_schema_engine.core.channel import TraceNode
from json_schema_engine.core.evaluator import run_evaluation
from json_schema_engine.core.output import (
    RenderInput,
    RenderNode,
    render_detailed,
    render_hierarchical,
    render_list,
)
from json_schema_engine.core.records import (
    RecordSets,
    render_error,
    render_selected,
    to_render_node,
)


def _trees(
    schema: JsonValue, instance: JsonValue, *, annotations: bool
) -> tuple[RenderInput, RenderInput, TraceNode]:
    """One traced run, rendered into relevant-level inputs over the unpruned
    and the pruned tree, built as `assemble_evaluation` builds them."""
    engine = create_engine()
    uri = engine.register_schema(schema, "https://records.example/schema")
    valid, state = run_evaluation(
        engine.schemas,
        uri,
        instance,
        compile_regex=engine.regex_cache.compile,
        should_record=lambda keyword_name, vocabulary_uri: annotations,
        tracing=True,
    )
    root = state.trace_root
    assert root is not None
    errors = [render_error(e, error_params=False) for e in state.errors]
    selected = render_selected(state.root_annotations if valid else (), True)
    records = RecordSets(errors=state.errors, annotations=selected.records)

    def render_input(prune: bool) -> RenderInput:
        return RenderInput(
            errors=errors,
            dropped_errors=[],
            annotations=selected.units,
            dropped_annotations=[],
            root=to_render_node(root, records, prune_empty=prune),
        )

    return render_input(False), render_input(True), root


def _count(node: RenderNode) -> int:
    return 1 + sum(_count(child) for child in node.children)


def _count_trace(node: TraceNode) -> int:
    return 1 + sum(_count_trace(child) for child in node.children)


def _assert_pruned(node: RenderNode, *, is_root: bool = True) -> None:
    """Every surviving non-root node carries a record or a surviving child."""
    if not is_root:
        assert (
            node.errors
            or node.dropped_errors
            or node.annotations
            or node.dropped_annotations
            or node.children
        )
    for child in node.children:
        _assert_pruned(child, is_root=False)


GOLDEN: JsonValue = {
    "$defs": {
        "named": {
            "title": "a named thing",
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
    },
    "title": "root",
    "type": "object",
    "properties": {
        "item": {"$ref": "#/$defs/named"},
        "count": {"type": "integer"},
    },
}

CASES: list[tuple[str, JsonValue, JsonValue]] = [
    (
        # `/properties/a` is record-free but its child annotates;
        # `/properties/c` annotates; `/properties/d` is `true`: no
        # keywords, no records.
        "mixed-siblings",
        {
            "properties": {
                "a": {"properties": {"b": {"type": "string", "title": "B"}}},
                "c": {"title": "C"},
                "d": True,
            }
        },
        {"a": {"b": "x"}, "c": 1, "d": 2},
    ),
    (
        # A `false` schema's error (no keyword of its own) under a
        # record-free `$ref` hop; a valid sibling application.
        "false-under-ref",
        {
            "properties": {"a": {"$ref": "#/$defs/no"}, "b": {"type": "integer"}},
            "$defs": {"no": False},
        },
        {"a": 1, "b": 2},
    ),
    (
        # One of two applications under one keyword pruned: `detailed`'s
        # condensation replaces a single surviving child.
        "one-of-two-items",
        {"items": {"$ref": "#/$defs/p"}, "$defs": {"p": {"required": ["x"]}}},
        [{"x": 1}, {}],
    ),
    ("golden-invalid", GOLDEN, {"item": {"name": "widget"}, "count": "nope"}),
    ("golden-valid", GOLDEN, {"item": {"name": "widget"}, "count": 3}),
]


@pytest.mark.parametrize(
    ("schema", "instance"), [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
@pytest.mark.parametrize(
    "annotations", [False, True], ids=["no-annotations", "annotations"]
)
def test_pruned_tree_renders_the_same_relevant_level_documents(
    schema: JsonValue, instance: JsonValue, annotations: bool
) -> None:
    full, pruned, trace_root = _trees(schema, instance, annotations=annotations)
    assert render_hierarchical(pruned, "omit") == render_hierarchical(full, "omit")
    assert render_list(pruned, "omit") == render_list(full, "omit")
    assert render_detailed(pruned) == render_detailed(full)
    # Without pruning the tree mirrors the trace, application for application.
    assert _count(full.root) == _count_trace(trace_root)
    _assert_pruned(pruned.root)
    assert _count(pruned.root) <= _count(full.root)


def test_pruning_drops_record_free_applications_and_keeps_their_ancestors() -> None:
    full, pruned, _ = _trees(*CASES[0][1:], annotations=True)
    paths = {node.evaluation_path for node in _walk(pruned.root)}
    # `/properties/d` (a `true` schema) is gone; `/properties/a` stays for
    # the annotation below it.
    assert paths == {"", "/properties/a", "/properties/a/properties/b", "/properties/c"}
    assert {node.evaluation_path for node in _walk(full.root)} == paths | {
        "/properties/d"
    }


def test_root_survives_when_nothing_carries_a_record() -> None:
    full, pruned, _ = _trees({"properties": {"d": True}}, {"d": 1}, annotations=False)
    assert _count(full.root) == 2
    assert pruned.root.children == ()
    assert pruned.root.evaluation_path == ""
    assert pruned.root.valid is True
    assert render_list(pruned, "omit") == render_list(full, "omit")
    assert render_list(pruned, "omit") == {"valid": True, "details": []}


def test_a_dropped_record_keeps_its_application() -> None:
    # Any of the four sets counts: a verbose-level producer indexing
    # irrelevant records gets a tree that still holds their applications.
    engine = create_engine()
    uri = engine.register_schema(
        {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        "https://records.example/dropped",
    )
    valid, state = run_evaluation(
        engine.schemas, uri, 1, compile_regex=engine.regex_cache.compile, tracing=True
    )
    assert valid is True
    assert len(state.dropped_errors) == 1
    root = state.trace_root
    assert root is not None
    pruned = to_render_node(
        root, RecordSets(dropped_errors=state.dropped_errors), prune_empty=True
    )
    assert [c.evaluation_path for c in pruned.children] == ["/anyOf/0"]
    assert pruned.children[0].dropped_errors == (0,)
    bare = to_render_node(root, RecordSets(), prune_empty=True)
    assert bare.children == ()


def _walk(node: RenderNode) -> list[RenderNode]:
    found = [node]
    for child in node.children:
        found.extend(_walk(child))
    return found
