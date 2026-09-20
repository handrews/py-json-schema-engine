# Records → units (DESIGN.md P6; §2 module table: "Records → located units
# and RenderInput"). This is the one place an engine record (`channel.py`'s
# `AnnotationRecord`/`ErrorRecord`, both identity-keyed and holding live
# `Cursor`/`SchemaRef` objects) turns into a `TypedDict` unit from
# `output.py` — after this point nothing downstream touches a record again.
#
# Dependency direction: imports `channel`, `cursor` (via the `Cursor.pointer`
# property, not the module itself), `json_model` (for `escape_segment`), and
# `output` (the unit types and `AnnotationSelection`/`make_record_predicate`).
# The evaluator (which owns the live records) imports this; this module
# never imports the evaluator back.

from collections.abc import Sequence

from json_schema_engine.core.channel import (
    AnnotationRecord,
    ErrorRecord,
    PathNode,
    materialize_path,
)
from json_schema_engine.core.json_model import escape_segment
from json_schema_engine.core.output import (
    AnnotationSelection,
    AnnotationsOption,
    AnnotationUnit,
    ErrorUnit,
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


def render_selected(
    records: Sequence[AnnotationRecord], selection: AnnotationsOption
) -> list[AnnotationUnit]:
    """Render `records` into units, applying the full selection including `keep` (D5).

    Each candidate is rendered at most once, and `keep` only ever sees a
    fully rendered unit — the same object `select_units` would apply `keep`
    to, so recording under `make_record_predicate` (which never consults
    `keep`) and rendering here can never disagree about what `keep` decides.
    """
    predicate = make_record_predicate(selection)
    if predicate is None:
        return []
    keep = selection.keep if isinstance(selection, AnnotationSelection) else None
    units: list[AnnotationUnit] = []
    for record in records:
        if not predicate(record.keyword_name, record.vocabulary_uri):
            continue
        unit = render_annotation(record)
        if keep is not None and not keep(unit):
            continue
        units.append(unit)
    return units
