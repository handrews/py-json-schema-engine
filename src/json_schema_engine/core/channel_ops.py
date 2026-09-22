# The record operations a compiled evaluator artifact performs on a shared
# `EvalState` (M9): one function per thing emitted code needs to do to the
# channel and the trace, so emitted code contains no record semantics of
# its own and interpreted islands, running on the same state, land their
# records in the same lists and tree. Every name here is a runtime helper
# with a `json_schema_engine.core` import path (the standalone convention).
#
# A "site" is `(behavior_id, keyword_name, vocabulary_uri, schema_ref)`:
# the identity a record carries, hoisted once per keyword occurrence by the
# compiler; a unit's own site has three `None`s.
#
# Dependency direction: imports `channel`, `cursor`, `evaluator`, `ref`,
# and `json_model` only.

from collections.abc import Mapping

from json_schema_engine.core.channel import (
    AnnotationRecord,
    ErrorRecord,
    KeywordTrace,
    PathNode,
    TraceNode,
)
from json_schema_engine.core.cursor import Cursor
from json_schema_engine.core.evaluator import EvalState
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.ref import SchemaRef

type Site = tuple[str | None, str | None, str | None, SchemaRef]


def emit_error(
    state: EvalState,
    site: Site,
    path_node: PathNode | None,
    cursor: Cursor,
    message: str,
    params: Mapping[str, JsonValue] | None,
) -> None:
    behavior_id, keyword_name, vocabulary_uri, schema_ref = site
    state.errors.append(
        ErrorRecord(
            behavior_id=behavior_id,
            keyword_name=keyword_name,
            vocabulary_uri=vocabulary_uri,
            schema_ref=schema_ref,
            path_node=path_node,
            cursor=cursor,
            message=message,
            params=params,
        )
    )


def emit_annotation(
    state: EvalState,
    site: Site,
    path_node: PathNode | None,
    cursor: Cursor,
    value: JsonValue,
) -> None:
    behavior_id, keyword_name, vocabulary_uri, schema_ref = site
    assert behavior_id is not None and keyword_name is not None
    state.record_annotation(
        AnnotationRecord(
            behavior_id=behavior_id,
            keyword_name=keyword_name,
            vocabulary_uri=vocabulary_uri,
            schema_ref=schema_ref,
            path_node=path_node,
            cursor=cursor,
            value=value,
        )
    )


def trace_enter(
    state: EvalState, site: Site, path_node: PathNode | None, cursor: Cursor
) -> TraceNode | None:
    """Open the application's trace node when tracing (islands nest under
    it, since the state's trace stack is shared)."""
    if not state.tracing:
        return None
    return state.trace_enter(site[3], path_node, cursor)


def trace_keywords(node: TraceNode | None, *pairs: object) -> None:
    """`(name, verdict, name, verdict, ...)` for the application's
    non-structural keywords in dialect order, then its unknown keywords."""
    if node is None:
        return
    for index in range(0, len(pairs), 2):
        name = pairs[index]
        verdict = pairs[index + 1]
        assert isinstance(name, str) and isinstance(verdict, bool)
        node.keywords.append(KeywordTrace(name, verdict))


def trace_exit(state: EvalState, node: TraceNode | None, valid: bool) -> None:
    if node is not None:
        state.trace_exit(node, valid)


def apply_true(
    state: EvalState, site: Site, path_node: PathNode | None, cursor: Cursor
) -> bool:
    """Applying the boolean schema `true`: a traced, always-accepting node."""
    if state.tracing:
        state.trace_exit(state.trace_enter(site[3], path_node, cursor), True)
    return True


def apply_false(
    state: EvalState, site: Site, path_node: PathNode | None, cursor: Cursor
) -> bool:
    """Applying the boolean schema `false`: one error, a traced node."""
    state.errors.append(
        ErrorRecord(
            behavior_id=None,
            keyword_name=None,
            vocabulary_uri=None,
            schema_ref=site[3],
            path_node=path_node,
            cursor=cursor,
            message="schema is false",
        )
    )
    if state.tracing:
        state.trace_exit(state.trace_enter(site[3], path_node, cursor), False)
    return False


def error_mark(state: EvalState) -> int:
    return len(state.errors)


def drop_errors(state: EvalState, mark: int) -> None:
    """Rule 6: an accepting keyword's sub-evaluation errors are irrelevant
    (retained as dropped when tracing)."""
    if len(state.errors) > mark:
        state.drop_errors_from(mark)


def annotation_mark(state: EvalState) -> int:
    return len(state.frames[0].annotations)


def cut_annotations(state: EvalState, mark: int) -> None:
    """Rule 3: a failed application's annotations never merge. Compiled
    applications are strictly nested, so the failed one's records are a
    contiguous suffix of the root frame."""
    del state.frames[0].annotations[mark:]
