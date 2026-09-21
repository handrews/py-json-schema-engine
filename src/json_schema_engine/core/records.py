# Records → units and the located tree (DESIGN.md P6; §2 module table:
# "Records → located units and RenderInput"). This is the one place an
# engine record (`channel.py`'s `AnnotationRecord`/`ErrorRecord`, both
# identity-keyed and holding live `Cursor`/`SchemaRef` objects) turns into a
# `TypedDict` unit from `output.py`, and the one place the evaluator's
# `TraceNode` tree becomes the string-located `RenderNode` tree the document
# renderers consume — after this point nothing downstream touches a record
# again.
#
# Dependency direction: imports `channel`, `cursor` (via the `Cursor.pointer`
# property, not the module itself), `json_model` (for `escape_segment`), and
# `output` (the unit types, `RenderNode`, and the selection helpers). The
# evaluator (which owns the live records) imports this; this module never
# imports the evaluator back.

from collections.abc import Sequence
from dataclasses import dataclass

from json_schema_engine.core.channel import (
    AnnotationRecord,
    ErrorRecord,
    PathNode,
    TraceNode,
    materialize_path,
)
from json_schema_engine.core.json_model import escape_segment
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationsOption,
    AnnotationUnit,
    ErrorUnit,
    RenderNode,
    make_record_predicate,
)
from json_schema_engine.core.ref import SchemaRef


def _keyword_suffix(keyword_name: str | None) -> str:
    """The `/`-prefixed, escaped keyword segment, or `""` when there is none.

    A record's `path_node`/`schema_ref` locate the *schema object*; sibling
    keywords share them (channel.py). The keyword's own segment is appended
    here, at render time, once per unit — which is why several annotation
    records with different `keyword_name`s can hold the very same
    `path_node`.
    """
    return "" if keyword_name is None else "/" + escape_segment(keyword_name)


def _evaluation_path(path_node: PathNode | None, keyword_name: str | None) -> str:
    return materialize_path(path_node) + _keyword_suffix(keyword_name)


def _schema_location(schema_ref: SchemaRef, keyword_name: str | None) -> str:
    return schema_ref.location + _keyword_suffix(keyword_name)


def render_error(record: ErrorRecord, *, error_params: bool) -> ErrorUnit:
    """Render one error record into its native unit (D6, D13).

    `keyword_name` is `None` for a boolean `false` schema, which has no
    keyword to name or suffix onto the path; `error_params` adds `keyword`,
    `vocabulary` (when known), and `params` (defaulting to `{}` when the
    keyword reported none) so a compatibility adapter can rebuild another
    library's error shape from the parts (D13).
    """
    unit: ErrorUnit = {
        "evaluationPath": _evaluation_path(record.path_node, record.keyword_name),
        "schemaLocation": _schema_location(record.schema_ref, record.keyword_name),
        "inputLocation": record.cursor.pointer,
        "error": record.message,
    }
    if error_params:
        if record.keyword_name is not None:
            unit["keyword"] = record.keyword_name
        if record.vocabulary_uri is not None:
            unit["vocabulary"] = record.vocabulary_uri
        unit["params"] = dict(record.params) if record.params is not None else {}
    return unit


def render_annotation(record: AnnotationRecord) -> AnnotationUnit:
    """Render one annotation record into its native unit (D6, §4 rule 2)."""
    unit: AnnotationUnit = {
        "evaluationPath": _evaluation_path(record.path_node, record.keyword_name),
        "schemaLocation": _schema_location(record.schema_ref, record.keyword_name),
        "inputLocation": record.cursor.pointer,
        "keyword": record.keyword_name,
        "annotation": record.value,
    }
    if record.vocabulary_uri is not None:
        unit["vocabulary"] = record.vocabulary_uri
    return unit


@dataclass(frozen=True, slots=True)
class SelectedAnnotations:
    """The survivors of a selection: records and their units, positionally
    paired, so the located tree can attribute a unit through its record."""

    records: list[AnnotationRecord]
    units: list[AnnotationUnit]


def render_selected(
    records: Sequence[AnnotationRecord], selection: AnnotationsOption
) -> SelectedAnnotations:
    """Render `records` into units, applying the full selection including `keep` (D5).

    Each candidate is rendered at most once, and `keep` only ever sees a
    fully rendered unit — the same object `select_units` would apply `keep`
    to, so recording under `make_record_predicate` (which never consults
    `keep`) and rendering here can never disagree about what `keep` decides.
    """
    predicate = make_record_predicate(selection)
    kept: list[AnnotationRecord] = []
    units: list[AnnotationUnit] = []
    if predicate is None:
        return SelectedAnnotations(kept, units)
    keep = selection.keep if isinstance(selection, AnnotationSelection) else None
    for record in records:
        if not predicate(record.keyword_name, record.vocabulary_uri):
            continue
        unit = render_annotation(record)
        if keep is not None and not keep(unit):
            continue
        kept.append(record)
        units.append(unit)
    return SelectedAnnotations(kept, units)


# --- the located tree ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecordSets:
    """The record sequences the flat surface was rendered from, positionally
    paired with the unit sequences a `RenderInput` carries."""

    errors: Sequence[ErrorRecord] = ()
    dropped_errors: Sequence[ErrorRecord] = ()
    annotations: Sequence[AnnotationRecord] = ()
    dropped_annotations: Sequence[AnnotationRecord] = ()


def _index_by_path(
    records: Sequence[AnnotationRecord] | Sequence[ErrorRecord],
) -> dict[int, list[int]]:
    """Positions of `records` grouped by the identity of their path node.

    Records attach to applications by path-node identity (P7): every
    application mints its own `PathNode`, so identity is finer than the
    evaluation-path string (repeated applications of one keyword share the
    string but not the node). A custom keyword applying with no segment of
    its own shares its parent's node and therefore its parent's group.
    """
    at: dict[int, list[int]] = {}
    for position, record in enumerate(records):
        at.setdefault(id(record.path_node), []).append(position)
    return at


def to_render_node(root: TraceNode, records: RecordSets) -> RenderNode:
    """Adapt the interpreter's trace into the located tree.

    Every location is materialized once per application; the index lists
    point into the unit sequences paired with `records`.
    """
    errors_at = _index_by_path(records.errors)
    dropped_errors_at = _index_by_path(records.dropped_errors)
    annotations_at = _index_by_path(records.annotations)
    dropped_annotations_at = _index_by_path(records.dropped_annotations)

    def to_node(node: TraceNode) -> RenderNode:
        key = id(node.path_node)
        return RenderNode(
            evaluation_path=materialize_path(node.path_node),
            schema_location=node.schema_ref.location,
            input_location=node.cursor.pointer,
            valid=node.valid,
            keywords=tuple(node.keywords),
            errors=tuple(errors_at.get(key, ())),
            dropped_errors=tuple(dropped_errors_at.get(key, ())),
            annotations=tuple(annotations_at.get(key, ())),
            dropped_annotations=tuple(dropped_annotations_at.get(key, ())),
            children=tuple(to_node(child) for child in node.children),
        )

    return to_node(root)
