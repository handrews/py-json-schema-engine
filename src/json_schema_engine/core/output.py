# Output rendering surfaces (DESIGN.md D5 annotation selection; D6 output;
# P6 records vs. units; §2 module table: "Units, AnnotationSelection,
# make_record_predicate, the format renderers. Engine-free.").
#
# Dependency direction: imports only `json_model` (for `JsonValue`) plus the
# standard library. Nothing here touches `Cursor`, `SchemaRef`, or any record
# type (P6) — this module consumes plain strings and `TypedDict` units, never
# engine records, so any producer of a `RenderInput` (the interpreter today,
# a compiled artifact from M6) renders through the same code path.
#
# M1 scope (DESIGN.md §6): `flag`, `basic`, and `list` only. `RenderInput`
# carries a `tree` placeholder and the M5 formats
# (`detailed`/`verbose`/`hierarchical`) are rejected by `result.py`'s
# `resolve_output_demand`, never reaching this module — but the surfaces
# below (the unit shapes, `AnnotationSelection`, the six-member
# `OutputFormat`) are already the ones M5 extends, not ones M5 replaces.

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NotRequired, TypedDict

from json_schema_engine.core.json_model import (
    JsonValue,
    escape_segment,
    unescape_segment,
)
from json_schema_engine.core.loader import SourceLocation


class ErrorUnit(TypedDict):
    """One rendered assertion failure, native field names (D6, D13).

    `keyword`, `vocabulary`, and `params` appear only with the `error_params`
    control; `keyword`/`vocabulary` are additionally absent when the
    rejecting schema was boolean `false`, which names no keyword.
    """

    evaluationPath: str
    schemaLocation: str
    inputLocation: str
    error: str
    keyword: NotRequired[str]
    vocabulary: NotRequired[str]
    params: NotRequired[dict[str, JsonValue]]
    # Schema-side source position, present with the `positions` option (D17).
    source: NotRequired[SourceLocation]


class AnnotationUnit(TypedDict):
    """One rendered annotation: a keyword's own value at a location (D6, §4 rule 2)."""

    evaluationPath: str
    schemaLocation: str
    inputLocation: str
    keyword: str
    annotation: JsonValue
    vocabulary: NotRequired[str]
    source: NotRequired[SourceLocation]


@dataclass(frozen=True, slots=True)
class AnnotationSelection:
    """Which annotations reach output (D5): a control independent of format and level.

    The allow-lists (`keywords`, `vocabularies`) are OR'd together; when both
    are `None` every keyword is allowed. The deny-lists subtract from that
    result. `keep` runs last, over the fully rendered `AnnotationUnit`, so it
    can inspect the annotation's own value — something no earlier stage
    (keyword name, vocabulary URI) has access to.
    """

    keywords: frozenset[str] | None = None
    vocabularies: frozenset[str] | None = None
    exclude_keywords: frozenset[str] = frozenset()
    exclude_vocabularies: frozenset[str] = frozenset()
    keep: Callable[[AnnotationUnit], bool] | None = None


type AnnotationsOption = bool | AnnotationSelection
"""`False` (nothing), `True` (everything), or a filtered `AnnotationSelection`."""

type RecordPredicate = Callable[[str, str | None], bool]
"""`(keyword_name, vocabulary_uri) -> bool`, evaluated at record time.

`None` (returned by `make_record_predicate` for `annotations=False`) means
"record nothing": the interpreter never allocates an `AnnotationRecord` for a
keyword this predicate would reject, which is the annotation-elision half of
D5. The predicate never sees `AnnotationSelection.keep` — see
`make_record_predicate`.
"""


def make_record_predicate(selection: AnnotationsOption) -> RecordPredicate | None:
    """Build the record-time gate for `selection` (D5).

    `None` means "record nothing" (`annotations=False`); otherwise every
    keyword/vocabulary the allow/deny lists would keep is recorded. `keep`
    is deliberately not consulted here: it runs only at render time, over the
    rendered unit, which is data this predicate never has. Recording the
    superset `keep` might later narrow is correct; eliding on its behalf
    would not be — a keyword `keep` would have allowed could otherwise vanish
    before `keep` ever saw it.
    """
    if selection is False:
        return None
    if selection is True:
        return lambda keyword_name, vocabulary_uri: True

    allow_active = selection.keywords is not None or selection.vocabularies is not None
    allow_keywords = selection.keywords or frozenset()
    allow_vocabularies = selection.vocabularies or frozenset()
    deny_keywords = selection.exclude_keywords
    deny_vocabularies = selection.exclude_vocabularies

    def predicate(keyword_name: str, vocabulary_uri: str | None) -> bool:
        if (
            allow_active
            and keyword_name not in allow_keywords
            and not (
                vocabulary_uri is not None and vocabulary_uri in allow_vocabularies
            )
        ):
            return False
        if keyword_name in deny_keywords:
            return False
        return not (vocabulary_uri is not None and vocabulary_uri in deny_vocabularies)

    return predicate


def select_units(
    units: Sequence[AnnotationUnit], selection: AnnotationsOption
) -> list[AnnotationUnit]:
    """Apply the full selection (D5), including `keep`, to already-rendered units.

    Used at render time, when a `RenderInput`'s annotations were recorded
    under a broader (or identical) predicate than the caller now wants to
    render with — e.g. a retaining evaluator recording everything so several
    later renders can each apply their own `selection`.
    """
    predicate = make_record_predicate(selection)
    if predicate is None:
        return []
    selected = [
        unit for unit in units if predicate(unit["keyword"], unit.get("vocabulary"))
    ]
    keep = selection.keep if isinstance(selection, AnnotationSelection) else None
    if keep is not None:
        selected = [unit for unit in selected if keep(unit)]
    return selected


class BasicErrorUnit(TypedDict):
    """One error of the IETF draft-03 §13.4.2 `basic` document."""

    keywordLocation: str
    absoluteKeywordLocation: str
    instanceLocation: str
    error: str


class BasicAnnotationUnit(TypedDict):
    """One annotation of the IETF draft-03 §13.4.2 `basic` document."""

    keywordLocation: str
    absoluteKeywordLocation: str
    instanceLocation: str
    annotation: JsonValue


class BasicOutputDocument(TypedDict):
    """IETF draft-03 §13.4.2 `basic`: a root unit with a flat list.

    Each format fixes its own document structure and field vocabulary (D6):
    this one speaks the draft's names, while the flat `Result.errors` and
    `Result.annotations` surface keeps the engine's native names. `errors`
    appears only on an invalid result and `annotations` only on a valid one,
    never both.
    """

    valid: bool
    keywordLocation: str
    absoluteKeywordLocation: str
    instanceLocation: str
    errors: NotRequired[list[BasicErrorUnit]]
    annotations: NotRequired[list[BasicAnnotationUnit]]


class OutputUnit(TypedDict):
    """One schema application in the machines-oriented `list`/`hierarchical`
    documents: its location plus errors and annotations keyed by keyword.

    `droppedErrors`/`droppedAnnotations` and nested `details` arrive with the
    verbose level and `hierarchical` in M5.
    """

    valid: bool
    evaluationPath: str
    schemaLocation: str
    instanceLocation: str
    errors: NotRequired[dict[str, str]]
    annotations: NotRequired[dict[str, JsonValue]]


class ListOutputDocument(TypedDict):
    """The machines-oriented `list` document: `valid` and a flat `details`.

    One unit per schema application that has relevant records, in
    application order (parents before children, siblings in evaluation
    order).
    """

    valid: bool
    details: list[OutputUnit]


@dataclass(frozen=True, slots=True)
class RenderInput:
    """The input every document renderer consumes (engine-free, D6).

    `errors` and `annotations` are already the relevant, already-selected
    units a caller wants rendered — selection (D5) is applied before a
    `RenderInput` is built, in `result.py`. `root_location` is the root
    schema's canonical location, which the draft-03 documents put on their
    root unit.

    `error_keywords` and `annotation_keywords` run parallel to the unit
    lists and name the keyword each unit belongs to (`None` for a boolean
    `false` schema's error, which has none). The `list` document groups by
    application and cannot recover that from a unit's path alone. When they
    are omitted, the last path segment is taken as the keyword. `tree` is
    the M5 located application tree; M1 never populates it.
    """

    valid: bool
    errors: Sequence[ErrorUnit]
    annotations: Sequence[AnnotationUnit]
    root_location: str
    error_keywords: Sequence[str | None] | None = None
    annotation_keywords: Sequence[str | None] | None = None
    tree: object | None = None


def render_flag(valid: bool) -> dict[str, bool]:
    """The `flag` document (IETF draft-03 §13.4.1 / machines-oriented proposal).

    `{valid}` — identical in both sources.
    """
    return {"valid": valid}


def render_basic(render_input: RenderInput) -> BasicOutputDocument:
    """Render the draft-03 `basic` document."""
    document: BasicOutputDocument = {
        "valid": render_input.valid,
        "keywordLocation": "",
        "absoluteKeywordLocation": render_input.root_location,
        "instanceLocation": "",
    }
    if render_input.valid:
        if render_input.annotations:
            document["annotations"] = [
                {
                    "keywordLocation": a["evaluationPath"],
                    "absoluteKeywordLocation": a["schemaLocation"],
                    "instanceLocation": a["inputLocation"],
                    "annotation": a["annotation"],
                }
                for a in render_input.annotations
            ]
    else:
        document["errors"] = [
            {
                "keywordLocation": e["evaluationPath"],
                "absoluteKeywordLocation": e["schemaLocation"],
                "instanceLocation": e["inputLocation"],
                "error": e["error"],
            }
            for e in render_input.errors
        ]
    return document


def _parent_of(location: str, keyword: str | None) -> str:
    """The application's location, given a unit's location and its keyword."""
    if keyword is None:
        return location
    suffix = "/" + escape_segment(keyword)
    return location[: -len(suffix)] if location.endswith(suffix) else location


def _keyword_of(location: str, keyword: str | None) -> str:
    if keyword is not None:
        return keyword
    return unescape_segment(location.rsplit("/", 1)[-1]) if "/" in location else ""


def render_list(render_input: RenderInput) -> ListOutputDocument:
    """Render the machines-oriented `list` document from flat units.

    Units are grouped by the schema application they belong to. The flat
    lists are in encounter order, and a keyword's own error is recorded
    after its sub-applications' errors, so a group is ordered by the first
    appearance of any unit in its subtree: that reproduces the application
    tree's pre-order without the tree.
    """
    groups: dict[tuple[str, str, str], OutputUnit] = {}
    first_seen: dict[tuple[str, str, str], int] = {}
    index = 0

    def group_for(
        unit: ErrorUnit | AnnotationUnit, keyword: str | None, valid: bool
    ) -> OutputUnit:
        nonlocal index
        key = (
            _parent_of(unit["evaluationPath"], keyword),
            _parent_of(unit["schemaLocation"], keyword),
            unit["inputLocation"],
        )
        group = groups.get(key)
        if group is None:
            group = OutputUnit(
                valid=valid,
                evaluationPath=key[0],
                schemaLocation=key[1],
                instanceLocation=key[2],
            )
            groups[key] = group
            first_seen[key] = index
        index += 1
        return group

    error_keywords = render_input.error_keywords
    for position, error in enumerate(render_input.errors):
        keyword = error_keywords[position] if error_keywords is not None else None
        if keyword is None and error_keywords is None:
            keyword = _keyword_of(error["evaluationPath"], None)
        group = group_for(error, keyword, False)
        by_keyword = group.setdefault("errors", {})
        name = keyword if keyword is not None else ""
        prior = by_keyword.get(name)
        by_keyword[name] = (
            error["error"] if prior is None else f"{prior}; {error['error']}"
        )

    annotation_keywords = render_input.annotation_keywords
    for position, annotation in enumerate(render_input.annotations):
        keyword = (
            annotation_keywords[position]
            if annotation_keywords is not None
            else annotation["keyword"]
        )
        group = group_for(annotation, keyword, True)
        group.setdefault("annotations", {})[annotation["keyword"]] = annotation[
            "annotation"
        ]

    def order(key: tuple[str, str, str]) -> tuple[int, int]:
        path = key[0]
        earliest = min(
            seen
            for other, seen in first_seen.items()
            if other[0] == path or other[0].startswith(path + "/") or path == ""
        )
        return (earliest, len(path))

    details = [groups[key] for key in sorted(groups, key=order)]
    return {"valid": render_input.valid, "details": details}
