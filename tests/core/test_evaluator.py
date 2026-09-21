# The M1 channel gate (DESIGN.md §4 rules 1-6, D5, D19, D20/P3): every rule
# exercised through a hand-written vocabulary so the evaluator is judged on
# its own, not through the real keywords that arrive in M2.

import re
from collections.abc import Mapping
from typing import cast

import pytest

from json_schema_engine.core.channel import TraceNode, materialize_path
from json_schema_engine.core.cursor import Cursor, child_cursor
from json_schema_engine.core.dialect import (
    CompiledRegex,
    DialectRegistry,
    KeywordBehavior,
    KeywordContext,
    Phase,
    StaticFacts,
    identifiers_2020,
    identifiers_legacy,
)
from json_schema_engine.core.errors import (
    InfiniteLoopError,
    InvalidSchemaError,
    KeywordContractError,
    MaxDepthExceededError,
    UndeclaredConsumptionError,
    UndeclaredProductionError,
    UnknownKeywordError,
)
from json_schema_engine.core.evaluator import EvalState, RecordPredicate, run_evaluation
from json_schema_engine.core.json_model import JsonValue, is_object
from json_schema_engine.core.registry import SchemaRegistry

VOCAB = "urn:test:vocab"
DIALECT = "urn:test:dialect"
PROPS_ID = "urn:test:props"


def _kid(name: str) -> str:
    return f"urn:test:{name}"


# --- the test vocabulary ---------------------------------------------------


def _annotate(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.annotate()
    return True


def _nothing(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    return True


def _map_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    names = tuple(value) if is_object(value) else ()
    return StaticFacts(subschemas=tuple((n,) for n in names), produces=(PROPS_ID,))


def _props(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    """Child applicator: applies each named subschema to the matching member."""
    instance = cursor.value
    if not is_object(instance) or not is_object(value):
        return True
    ok = True
    matched: list[str] = []
    for name in value:
        if name in instance:
            matched.append(name)
            if not ctx.apply(
                ("props", name), child_cursor(cursor, name, instance[name])
            ):
                ok = False
    if ok:
        ctx.produce(matched)
    return ok


def _list_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    count = len(value) if isinstance(value, list) else 0
    return StaticFacts(subschemas=tuple((i,) for i in range(count)))


def _any(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    """In-place applicator: every branch runs; any success accepts."""
    assert isinstance(value, list)
    ok = False
    for index in range(len(value)):
        if ctx.apply(("any", index), cursor):
            ok = True
    if not ok:
        ctx.error("no branch matched")
    return ok


def _all(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, list)
    ok = True
    for index in range(len(value)):
        if not ctx.apply(("all", index), cursor):
            ok = False
    return ok


def _consumer_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(consumes=(PROPS_ID,))


def _uneval(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    """Channel consumer: rejects any member no visible producer covered."""
    instance = cursor.value
    if not is_object(instance):
        return True
    covered: set[str] = set()
    for view in ctx.visible((PROPS_ID,)):
        names = cast(list[object], view.data)
        covered.update(str(n) for n in names)
    leftovers = sorted(set(instance) - covered)
    if leftovers and value is False:
        ctx.error("unevaluated: " + ", ".join(leftovers))
        return False
    return True


def _ref_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(references=(value,) if isinstance(value, str) else ())


def _ref(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, str)
    return ctx.apply_resolved(ctx.resolve_ref(value))


def _fail(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.error("always fails", {"why": value})
    return False


def _bad_accept(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.error("reported but accepted")
    return True


def _undeclared_produce(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.produce("x")
    return True


def _undeclared_read(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    ctx.visible((PROPS_ID,))
    return True


def _adjacent_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(consumes=(PROPS_ID,))


def _adjacent_count(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    """Annotates only if an adjacent producer is visible (then/else-style)."""
    if ctx.visible((PROPS_ID,), "adjacent"):
        ctx.annotate()
    return True


def _pattern_facts(value: JsonValue, _ctx: object) -> StaticFacts:
    return StaticFacts(regexes=(value,) if isinstance(value, str) else ())


def _pattern(value: JsonValue, cursor: Cursor, ctx: KeywordContext) -> bool:
    assert isinstance(value, str)
    if not isinstance(cursor.value, str):
        return True
    if ctx.compile_regex(value).search(cursor.value):
        return True
    ctx.error("pattern mismatch")
    return False


KEYWORDS: Mapping[str, KeywordBehavior] = {
    "$id": KeywordBehavior(_kid("$id"), _nothing, structural=True),
    "$anchor": KeywordBehavior(_kid("$anchor"), _nothing, structural=True),
    "$comment": KeywordBehavior(_kid("$comment"), _nothing, structural=True),
    "$defs": KeywordBehavior(_kid("$defs"), _nothing, _map_facts, structural=True),
    "title": KeywordBehavior(_kid("title"), _annotate),
    "note": KeywordBehavior(_kid("note"), _annotate),
    "props": KeywordBehavior(PROPS_ID, _props, _map_facts),
    "any": KeywordBehavior(_kid("any"), _any, _list_facts),
    "all": KeywordBehavior(_kid("all"), _all, _list_facts),
    "uneval": KeywordBehavior(
        _kid("uneval"), _uneval, _consumer_facts, phase=Phase.UNEVALUATED
    ),
    "adjacent": KeywordBehavior(_kid("adjacent"), _adjacent_count, _adjacent_facts),
    "$ref": KeywordBehavior(_kid("$ref"), _ref, _ref_facts),
    "fail": KeywordBehavior(_kid("fail"), _fail),
    "badAccept": KeywordBehavior(_kid("badAccept"), _bad_accept),
    "undeclaredProduce": KeywordBehavior(
        _kid("undeclaredProduce"), _undeclared_produce
    ),
    "undeclaredRead": KeywordBehavior(_kid("undeclaredRead"), _undeclared_read),
    "pattern": KeywordBehavior(_kid("pattern"), _pattern, _pattern_facts),
}


class _Regex:
    def __init__(self, pattern: str) -> None:
        self._compiled = re.compile(pattern)

    def search(self, text: str, /) -> bool:
        return self._compiled.search(text) is not None


def _compile_regex(pattern: str) -> CompiledRegex:
    return _Regex(pattern)


def make_registry(
    *, allow_unknown: bool = True, legacy: bool = False
) -> SchemaRegistry:
    dialects = DialectRegistry()
    dialects.register_vocabulary(VOCAB, KEYWORDS)
    dialects.register_dialect(
        DIALECT,
        [VOCAB],
        allow_unknown_keywords=allow_unknown,
        identifiers=identifiers_legacy if legacy else identifiers_2020,
        ref_ignores_siblings=legacy,
    )
    return SchemaRegistry(dialects, DIALECT)


def run(
    schema: JsonValue,
    instance: JsonValue,
    *,
    should_record: RecordPredicate | None = None,
    max_depth: int = 512,
    tracing: bool = False,
    registry: SchemaRegistry | None = None,
) -> tuple[bool, EvalState]:
    reg = registry or make_registry()
    uri = reg.register(schema, "https://channels.example/schema")
    return run_evaluation(
        reg,
        uri,
        instance,
        compile_regex=_compile_regex,
        should_record=should_record,
        max_depth=max_depth,
        tracing=tracing,
    )


def annotations(state: EvalState) -> list[tuple[str, str, JsonValue]]:
    return [
        (
            materialize_path(a.path_node) + "/" + a.keyword_name,
            a.cursor.pointer,
            a.value,
        )
        for a in state.root_annotations
    ]


PROFILE: JsonValue = {
    "title": "User profile",
    "props": {
        "id": {"title": "Identifier", "note": True},
        "displayName": {"title": "Display name"},
    },
    "$comment": "must never be collected",
}


# --- rules 1-3: frames, annotation records, merge/discard ----------------


def test_annotations_carry_paths_on_success() -> None:
    valid, state = run(PROFILE, {"id": "u1", "displayName": "Ada"})
    assert valid
    got = annotations(state)
    assert ("/props/id/note", "/id", True) in got
    assert ("/props/id/title", "/id", "Identifier") in got
    assert ("/title", "", "User profile") in got
    # props communicates matched names as dependency data, never annotation.
    assert not any(a.keyword_name == "props" for a in state.root_annotations)
    assert [d.data for d in state.root_dependencies] == [["id", "displayName"]]


def test_no_annotations_when_the_schema_fails() -> None:
    valid, state = run({"title": "t", "fail": 1}, 3)
    assert not valid
    assert state.root_annotations == []
    assert [e.message for e in state.errors] == ["always fails"]
    assert state.errors[0].params == {"why": 1}
    assert state.errors[0].keyword_name == "fail"


def test_comment_never_annotates() -> None:
    _, state = run(PROFILE, {"id": "u1"})
    assert not any(a.keyword_name == "$comment" for a in state.root_annotations)


def test_unknown_keyword_annotates_its_own_value() -> None:
    valid, state = run({"x-vendor-hint": {"cache": True}}, 42)
    assert valid
    assert annotations(state) == [("/x-vendor-hint", "", {"cache": True})]
    assert state.root_annotations[0].vocabulary_uri is None


def test_unknown_keyword_can_be_refused() -> None:
    with pytest.raises(UnknownKeywordError):
        run({"x-nope": 1}, 42, registry=make_registry(allow_unknown=False))


def test_failed_branch_annotations_are_dropped_successful_kept() -> None:
    schema: JsonValue = {
        "any": [
            {"pattern": "^a", "title": "starts with a"},
            {"pattern": "^b", "title": "starts with b"},
        ]
    }
    valid, state = run(schema, "abc")
    assert valid
    titles = [a for a in state.root_annotations if a.keyword_name == "title"]
    assert [a.value for a in titles] == ["starts with a"]
    assert materialize_path(titles[0].path_node) == "/any/0"
    assert titles[0].schema_ref.location == "https://channels.example/schema#/any/0"
    # Rule 6: the failed branch's error is irrelevant once `any` accepts.
    assert state.errors == []


def test_boolean_false_schema_reports_without_keyword() -> None:
    valid, state = run({"props": {"x": False}}, {"x": 1})
    assert not valid
    assert state.errors[0].keyword_name is None
    assert state.errors[0].cursor.pointer == "/x"
    assert materialize_path(state.errors[0].path_node) == "/props/x"


# --- rule 4: visibility ---------------------------------------------------


def test_failed_branch_does_not_mark_properties_evaluated() -> None:
    schema: JsonValue = {
        "any": [
            {"props": {"x": {"pattern": "^s"}}},
            {"props": {"y": {}}, "fail": 1},
        ],
        "uneval": False,
    }
    assert run(schema, {"x": "s", "y": 1})[0] is False
    assert run(schema, {"x": "s"})[0] is True


def test_cousin_records_are_invisible() -> None:
    # The producer sits under a child cursor; the consumer at the root sees
    # nothing, because rule 4 filters by cursor identity.
    schema: JsonValue = {"props": {"a": {"props": {"b": {}}}}, "uneval": False}
    valid, _ = run(schema, {"a": {"b": 1}, "c": 2})
    assert not valid
    assert run(schema, {"a": {"b": 1}})[0] is True


def test_in_place_merge_feeds_consumer() -> None:
    schema: JsonValue = {"all": [{"props": {"x": {}}}], "uneval": False}
    assert run(schema, {"x": 1})[0] is True
    assert run(schema, {"x": 1, "y": 2})[0] is False


def test_adjacent_scope_sees_only_own_schema_object() -> None:
    # Producer adjacent to the consumer: visible.
    _, state = run({"props": {"x": {}}, "adjacent": True}, {"x": 1})
    assert any(a.keyword_name == "adjacent" for a in state.root_annotations)
    # Producer merged from an in-place child: not adjacent.
    _, state = run({"all": [{"props": {"x": {}}}], "adjacent": True}, {"x": 1})
    assert not any(a.keyword_name == "adjacent" for a in state.root_annotations)


# --- rule 5 / D5: selection and elision ----------------------------------


def test_selection_never_starves_consumers() -> None:
    schema: JsonValue = {"all": [{"props": {"x": {}}}], "uneval": False, "title": "t"}
    nothing: RecordPredicate = lambda name, vocab: False  # noqa: E731
    valid, state = run(schema, {"x": 1}, should_record=nothing)
    assert valid
    assert state.root_annotations == []
    assert run(schema, {"x": 1, "y": 2}, should_record=nothing)[0] is False


def test_elision_drops_unconsumed_dependency_data() -> None:
    # No consumer registered: under elision the record is never created.
    schema: JsonValue = {"props": {"x": {}}}
    _, state = run(schema, {"x": 1}, should_record=lambda n, v: True)
    assert state.root_dependencies == []
    _, state = run(schema, {"x": 1})
    assert len(state.root_dependencies) == 1


def test_predicate_sees_name_and_vocabulary() -> None:
    seen: list[tuple[str, str | None]] = []

    def record(name: str, vocab: str | None) -> bool:
        seen.append((name, vocab))
        return True

    run({"title": "t", "x-unknown": 1}, 0, should_record=record)
    assert ("title", VOCAB) in seen
    assert ("x-unknown", None) in seen


# --- rule 6: relevance and the keyword contract --------------------------


def test_accepting_keyword_drops_sub_errors_and_can_retain_them() -> None:
    schema: JsonValue = {"any": [{"fail": 1}, {}]}
    valid, state = run(schema, 0)
    assert valid
    assert state.errors == []
    assert state.dropped_errors == []
    valid, state = run(schema, 0, tracing=True)
    assert [e.message for e in state.dropped_errors] == ["always fails"]


def test_rejecting_keyword_keeps_all_sub_errors() -> None:
    valid, state = run({"any": [{"fail": 1}, {"fail": 2}]}, 0)
    assert not valid
    assert [e.message for e in state.errors] == [
        "always fails",
        "always fails",
        "no branch matched",
    ]


def test_error_then_accept_is_a_contract_violation() -> None:
    with pytest.raises(KeywordContractError):
        run({"badAccept": 1}, 0)


def test_undeclared_production_is_loud() -> None:
    with pytest.raises(UndeclaredProductionError):
        run({"undeclaredProduce": 1}, 0)


def test_undeclared_consumption_is_loud_under_elision_only() -> None:
    schema: JsonValue = {"undeclaredRead": 1}
    with pytest.raises(UndeclaredConsumptionError):
        run(schema, 0, should_record=lambda n, v: True)
    assert run(schema, 0)[0] is True


# --- references, cycles, depth, D19 --------------------------------------


def test_ref_applies_in_place_with_reference_path() -> None:
    schema: JsonValue = {"$defs": {"t": {"title": "via ref"}}, "$ref": "#/$defs/t"}
    valid, state = run(schema, 0)
    assert valid
    assert annotations(state) == [("/$ref/title", "", "via ref")]
    assert state.root_annotations[0].schema_ref.location == (
        "https://channels.example/schema#/$defs/t"
    )


def test_ref_cycle_at_same_instance_location_is_loud() -> None:
    with pytest.raises(InfiniteLoopError):
        run({"$ref": "#"}, 0)


def test_recursion_through_children_is_not_a_cycle() -> None:
    schema: JsonValue = {"props": {"child": {"$ref": "#"}}}
    assert run(schema, {"child": {"child": {"child": {}}}})[0] is True


def test_depth_budget_is_typed() -> None:
    schema: JsonValue = {"props": {"child": {"$ref": "#"}}}
    deep: JsonValue = {}
    for _ in range(20):
        deep = {"child": deep}
    with pytest.raises(MaxDepthExceededError):
        run(schema, deep, max_depth=10)
    assert run(schema, deep, max_depth=100)[0] is True


def test_non_schema_reached_by_pointer_fails_loud_at_evaluation() -> None:
    # `x-data` is unknown, so the walk never sees the 5 inside it; applying
    # it through a pointer must still raise (D19 backstop).
    schema: JsonValue = {"x-data": {"n": 5}, "$ref": "#/x-data/n"}
    with pytest.raises(InvalidSchemaError):
        run(schema, 0)


def test_ref_ignores_siblings_in_legacy_dialects() -> None:
    reg = make_registry(legacy=True)
    schema: JsonValue = {"$defs": {"t": {}}, "$ref": "#/$defs/t", "fail": 1}
    valid, state = run(schema, 0, registry=reg)
    assert valid
    assert state.errors == []


# --- tracing (D6): the application tree and the retained records ----------


type Shape = tuple[str, str, bool, list[tuple[str, bool]], list[object]]


def shape(node: TraceNode) -> Shape:
    """A trace node as comparable data: path, cursor, verdict, keywords, children."""
    return (
        materialize_path(node.path_node),
        node.cursor.pointer,
        node.valid,
        [(k.name, k.valid) for k in node.keywords],
        [shape(child) for child in node.children],
    )


def test_tracing_is_off_by_default() -> None:
    valid, state = run({"title": "t"}, 0)
    assert valid
    assert state.trace_root is None
    assert state.all_annotations is None


def test_trace_tree_mirrors_nested_applications() -> None:
    schema: JsonValue = {
        "props": {"a": {"title": "a", "fail": 1}, "b": {"any": [{"fail": 1}, {}]}},
        "title": "root",
    }
    valid, state = run(schema, {"a": 1, "b": 2}, tracing=True)
    assert not valid
    assert state.trace_root is not None
    assert shape(state.trace_root) == (
        "",
        "",
        False,
        # Keywords trace in the dialect's evaluation order (registration
        # order here), not in the schema's key order.
        [("title", True), ("props", False)],
        [
            ("/props/a", "/a", False, [("title", True), ("fail", False)], []),
            (
                "/props/b",
                "/b",
                True,
                [("any", True)],
                [
                    ("/props/b/any/0", "/b", False, [("fail", False)], []),
                    ("/props/b/any/1", "/b", True, [], []),
                ],
            ),
        ],
    )


def test_trace_omits_structural_keywords_and_shows_unknown_ones_valid() -> None:
    schema: JsonValue = {
        "$id": "https://channels.example/traced",
        "$comment": "ignored",
        "$defs": {"t": {}},
        "x-unknown": 1,
        "title": "t",
    }
    _, state = run(schema, 0, tracing=True)
    assert state.trace_root is not None
    assert [(k.name, k.valid) for k in state.trace_root.keywords] == [
        ("title", True),
        ("x-unknown", True),
    ]


def test_boolean_schemas_trace_as_leaves() -> None:
    schema: JsonValue = {"props": {"yes": True, "no": False}}
    valid, state = run(schema, {"yes": 1, "no": 2}, tracing=True)
    assert not valid
    assert state.trace_root is not None
    assert [shape(c) for c in state.trace_root.children] == [
        ("/props/yes", "/yes", True, [], []),
        ("/props/no", "/no", False, [], []),
    ]


def test_ref_traces_one_node_for_the_target_under_the_ref_segment() -> None:
    schema: JsonValue = {"$defs": {"t": {"title": "via ref"}}, "$ref": "#/$defs/t"}
    _, state = run(schema, 0, tracing=True)
    assert state.trace_root is not None
    (child,) = state.trace_root.children
    assert materialize_path(child.path_node) == "/$ref"
    assert child.schema_ref.location == "https://channels.example/schema#/$defs/t"
    assert [(k.name, k.valid) for k in child.keywords] == [("title", True)]


def test_all_annotations_retains_discarded_frames() -> None:
    schema: JsonValue = {"any": [{"title": "lost", "fail": 1}, {"title": "kept"}]}
    valid, state = run(schema, 0, tracing=True)
    assert valid
    assert annotations(state) == [("/any/1/title", "", "kept")]
    assert state.all_annotations is not None
    assert [(a.value) for a in state.all_annotations] == ["lost", "kept"]
    # The retained record is the very object the frame held, so identity
    # comparison can tell relevant from dropped.
    assert state.all_annotations[1] is state.root_annotations[0]
    # Unknown keywords' annotations are retained too.
    _, state = run({"any": [{"x-a": 1, "fail": 1}]}, 0, tracing=True)
    assert state.all_annotations is not None
    assert [a.keyword_name for a in state.all_annotations] == ["x-a"]


def test_all_annotations_respects_the_record_predicate() -> None:
    schema: JsonValue = {"title": "t", "note": "n"}
    _, state = run(schema, 0, tracing=True, should_record=lambda n, v: n == "note")
    assert state.all_annotations is not None
    assert [a.keyword_name for a in state.all_annotations] == ["note"]


def test_dropped_errors_are_retained_only_when_tracing() -> None:
    schema: JsonValue = {"any": [{"fail": 1}, {}]}
    assert run(schema, 0)[1].dropped_errors == []
    _, state = run(schema, 0, tracing=True)
    assert [e.message for e in state.dropped_errors] == ["always fails"]
    assert state.errors == []
