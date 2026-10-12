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
# property, not the module itself), `ref` (for `SchemaRef.location`), and
# `output` (the unit types, `RenderNode`, the selection helpers, and the
# keyword-suffix memo). The evaluator (which owns the live records) imports
# this; this module never imports the evaluator back.

from collections.abc import Sequence
from dataclasses import dataclass

from json_schema_engine.core.channel import (
    AnnotationRecord,
    ErrorRecord,
    PathNode,
    TraceNode,
    materialize_path,
)
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationsOption,
    AnnotationUnit,
    ErrorUnit,
    RenderNode,
    keyword_suffixes,
    make_record_predicate,
)
from json_schema_engine.core.ref import SchemaRef

# A record's `path_node`/`schema_ref` locate the *schema object*; sibling
# keywords share them (channel.py). The keyword's own segment is appended at
# render time, once per unit — which is why several annotation records with
# different `keyword_name`s can hold the very same `path_node`. `keyword_name`
# is `None` for a boolean `false` schema, which has no keyword to name, so
# the unit sits at the application's own location. Both forms of the
# segment come from `keyword_suffixes` (P10): plain text for the
# `evaluationPath`, fragment-encoded for the `schemaLocation`, which is a
# URI an unknown keyword's name (whatever the schema author wrote — a space,
# a `%`) must not break.


def _evaluation_path(path_node: PathNode | None, keyword_name: str | None) -> str:
    path = materialize_path(path_node)
    if keyword_name is None:
        return path
    return path + keyword_suffixes(keyword_name)[0]


def _schema_location(schema_ref: SchemaRef, keyword_name: str | None) -> str:
    location = schema_ref.location
    if keyword_name is None:
        return location
    return location + keyword_suffixes(keyword_name)[1]


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


def to_render_node(
    root: TraceNode, records: RecordSets, *, prune_empty: bool = False
) -> RenderNode:
    """Adapt the interpreter's trace into the located tree.

    Every location is materialized once per application; the index lists
    point into the unit sequences paired with `records`.

    With `prune_empty`, an application with no record in any of the four
    sets, at itself or anywhere below, is left out together with its
    subtree; the root always remains. That is the tree the relevant level
    renders: `hierarchical`/`list` omit a unit with nothing to report and
    `detailed` condenses one away, so the pruned tree renders to the same
    documents while its size follows the records rather than the
    applications. The verbose level and `trace` render every application
    and take the whole tree. Children are filtered, never reordered, and a
    kept application keeps its parent, so the `RenderNode` invariants hold
    either way.
    """
    errors_at = _index_by_path(records.errors)
    dropped_errors_at = _index_by_path(records.dropped_errors)
    annotations_at = _index_by_path(records.annotations)
    dropped_annotations_at = _index_by_path(records.dropped_annotations)

    def to_node(node: TraceNode) -> RenderNode | None:
        # Children first, then the record test, and only then the
        # locations: a pruned application never materializes anything.
        # The generator over `map` is deliberate: it keeps two frames per
        # level, which is what lets the P3 backstop in `assemble_evaluation`
        # see a chain the compiled tier could evaluate but the stack cannot
        # rebuild (tests/compiler/test_depth_parity.py pins it).
        children = (
            tuple(child for child in map(to_node, node.children) if child is not None)
            if node.children
            else ()
        )
        key = id(node.path_node)
        errors = errors_at.get(key)
        dropped_errors = dropped_errors_at.get(key)
        annotations = annotations_at.get(key)
        dropped_annotations = dropped_annotations_at.get(key)
        if (
            prune_empty
            and not children
            and errors is None
            and dropped_errors is None
            and annotations is None
            and dropped_annotations is None
        ):
            return None
        return _render_node(
            node, errors, dropped_errors, annotations, dropped_annotations, children
        )

    rendered = to_node(root)
    if rendered is None:
        # Nothing anywhere: the root alone, with every child pruned.
        rendered = _render_node(root, None, None, None, None, ())
    return rendered


def _render_node(
    node: TraceNode,
    errors: list[int] | None,
    dropped_errors: list[int] | None,
    annotations: list[int] | None,
    dropped_annotations: list[int] | None,
    children: tuple[RenderNode, ...],
) -> RenderNode:
    return RenderNode(
        evaluation_path=materialize_path(node.path_node),
        schema_location=node.schema_ref.location,
        input_location=node.cursor.pointer,
        valid=node.valid,
        keywords=tuple(node.keywords),
        errors=tuple(errors) if errors else (),
        dropped_errors=tuple(dropped_errors) if dropped_errors else (),
        annotations=tuple(annotations) if annotations else (),
        dropped_annotations=tuple(dropped_annotations) if dropped_annotations else (),
        children=children,
    )
