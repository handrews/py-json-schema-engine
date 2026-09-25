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
# Two kinds of input: the flat surface (units with the engine's native field
# names) and a located tree of schema applications (`RenderNode`), rendered
# by format name into each documented structure — IETF draft-03 §13 for
# `basic`/`detailed`/`verbose`, the machines-oriented output proposal for
# `list`/`hierarchical`, and the engine's own `trace`.

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from json_schema_engine.core.json_model import (
    JsonValue,
    escape_segment,
    unescape_segment,
)
from json_schema_engine.core.loader import SourceLocation
from json_schema_engine.core.uri import pointer_fragment

if TYPE_CHECKING:
    # Type-only: the trace's per-keyword verdict is plain data (name, valid)
    # and importing it at runtime would pull the record module in here.
    from json_schema_engine.core.channel import KeywordTrace


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


def render_flag(valid: bool) -> dict[str, bool]:
    """The `flag` document (IETF draft-03 §13.4.1 / machines-oriented proposal).

    `{valid}` — identical in both sources.
    """
    return {"valid": valid}


def render_basic(
    valid: bool,
    root_location: str,
    errors: Sequence[ErrorUnit],
    annotations: Sequence[AnnotationUnit],
) -> BasicOutputDocument:
    """Render the draft-03 `basic` document from the flat surface.

    `root_location` is the root schema's canonical location; `errors` and
    `annotations` are the relevant, already selected units. Per the official
    output-tests fixtures, `errors` is absent on success and `annotations`
    appears only when non-empty.
    """
    document: BasicOutputDocument = {
        "valid": valid,
        "keywordLocation": "",
        "absoluteKeywordLocation": root_location,
        "instanceLocation": "",
    }
    if valid:
        if annotations:
            document["annotations"] = [
                {
                    "keywordLocation": a["evaluationPath"],
                    "absoluteKeywordLocation": a["schemaLocation"],
                    "instanceLocation": a["inputLocation"],
                    "annotation": a["annotation"],
                }
                for a in annotations
            ]
    else:
        document["errors"] = [
            {
                "keywordLocation": e["evaluationPath"],
                "absoluteKeywordLocation": e["schemaLocation"],
                "instanceLocation": e["inputLocation"],
                "error": e["error"],
            }
            for e in errors
        ]
    return document


# --- the located tree ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RenderNode:
    """One schema application in a located evaluation tree (D6).

    What the document renderers need from any producer — the interpreter's
    trace (`records.to_render_node`) or a compiled artifact. Locations are
    absolute strings; records are indexes into the owning `RenderInput`'s
    flat unit sequences.

    Producers keep three invariants: a child's `evaluation_path` equals or
    extends its parent's; a unit indexed at a node has the node's
    `evaluation_path` (a boolean `false` schema) or extends it by exactly
    one escaped segment, the keyword; `keywords` lists the node's
    non-structural keyword evaluations in evaluation order.
    """

    evaluation_path: str
    schema_location: str
    input_location: str
    valid: bool
    keywords: tuple[KeywordTrace, ...]
    errors: tuple[int, ...]
    dropped_errors: tuple[int, ...]
    annotations: tuple[int, ...]
    dropped_annotations: tuple[int, ...]
    children: tuple[RenderNode, ...]


@dataclass(frozen=True, slots=True)
class RenderInput:
    """The flat surface plus its located tree: every tree renderer's input.

    The unit sequences are already relevant/irrelevant-partitioned and
    already selected (D5). `dropped_errors` and `dropped_annotations` are
    empty unless the producer retained irrelevant records (the verbose
    demand); relevant-level renderings never read them.
    """

    errors: Sequence[ErrorUnit]
    dropped_errors: Sequence[ErrorUnit]
    annotations: Sequence[AnnotationUnit]
    dropped_annotations: Sequence[AnnotationUnit]
    root: RenderNode


type IrrelevantRendering = Literal["omit", "mark"]
"""How `list`/`hierarchical` treat irrelevant records: `omit` drops them and
prunes the units left empty (the relevant level); `mark` keeps every unit
and renders them under `droppedErrors`/`droppedAnnotations` (verbose)."""


def _keyword_of(unit: ErrorUnit, node: RenderNode) -> str:
    """The keyword an error at `node` belongs to, decoded; `""` for a boolean
    `false` schema's error, which sits at the node itself."""
    rest = unit["evaluationPath"][len(node.evaluation_path) :]
    return "" if rest == "" else unescape_segment(rest[1:])


def _segments_below(child: RenderNode, parent_path: str) -> list[str]:
    rest = child.evaluation_path[len(parent_path) :]
    return [] if rest == "" else [unescape_segment(s) for s in rest[1:].split("/")]


def _first_segment_below(child: RenderNode, parent_path: str) -> str | None:
    """The applying keyword: the first segment of `child` below `parent_path`."""
    path = child.evaluation_path
    if len(path) == len(parent_path):
        return None
    end = path.find("/", len(parent_path) + 1)
    return unescape_segment(path[len(parent_path) + 1 : None if end == -1 else end])


def _pick[T](indexes: Sequence[int], units: Sequence[T]) -> list[T]:
    return [units[i] for i in indexes]


def _join_messages(errors: Sequence[ErrorUnit]) -> str:
    # A keyword may report several errors (`required`'s missing names); a
    # one-message-per-keyword field joins them.
    return "; ".join(e["error"] for e in errors)


# --- list / hierarchical (machines-oriented proposal) ----------------------


class OutputUnit(TypedDict):
    """One schema application in the `list`/`hierarchical` documents: its
    location plus errors and annotations keyed by keyword name.

    At the verbose level `droppedErrors`/`droppedAnnotations` mark irrelevant
    records (draft-03 §12.2): the proposal defines `droppedAnnotations` for a
    failed unit's own annotations, and the verbose level extends the marker
    to every irrelevant record. The markers classify records, not units: a
    unit's `valid`, even along its path, does not say whether it is
    relevant. `details` nests the sub-applications in `hierarchical`;
    `list` flattens them.
    """

    valid: bool
    evaluationPath: str
    schemaLocation: str
    instanceLocation: str
    errors: NotRequired[dict[str, str]]
    annotations: NotRequired[dict[str, JsonValue]]
    droppedErrors: NotRequired[dict[str, str]]
    droppedAnnotations: NotRequired[dict[str, JsonValue]]
    details: NotRequired[list[OutputUnit]]


class ListOutputDocument(TypedDict):
    """The `list` document: `valid` and a flat `details` list, one unit per
    schema application in pre-order (parents before children, siblings in
    evaluation order)."""

    valid: bool
    details: list[OutputUnit]


def _errors_by_keyword(errors: Sequence[ErrorUnit], node: RenderNode) -> dict[str, str]:
    by_keyword: dict[str, str] = {}
    for error in errors:
        key = _keyword_of(error, node)
        prior = by_keyword.get(key)
        by_keyword[key] = (
            error["error"] if prior is None else f"{prior}; {error['error']}"
        )
    return by_keyword


def _annotations_by_keyword(
    annotations: Sequence[AnnotationUnit],
) -> dict[str, JsonValue]:
    return {a["keyword"]: a["annotation"] for a in annotations}


def render_hierarchical(
    render_input: RenderInput, irrelevant: IrrelevantRendering
) -> OutputUnit:
    """Render the `hierarchical` document: one unit per application, nested.

    Irrelevant records render per `irrelevant`; at the relevant level a
    unit carrying nothing is omitted, but the root always remains. The
    proposal includes every unit and makes such pruning opt-in; pruning by
    default is this engine's relevant level (draft-03 §12.2, §13.4), and
    `mark` is the unpruned structure.
    """

    def unit_of(node: RenderNode) -> OutputUnit:
        return {
            "valid": node.valid,
            "evaluationPath": node.evaluation_path,
            "schemaLocation": node.schema_location,
            "instanceLocation": node.input_location,
        }

    def to_unit(node: RenderNode) -> OutputUnit | None:
        details = [u for u in map(to_unit, node.children) if u is not None]
        unit = unit_of(node)

        errors = _pick(node.errors, render_input.errors)
        if errors:
            unit["errors"] = _errors_by_keyword(errors, node)
        if irrelevant == "mark":
            dropped = _pick(node.dropped_errors, render_input.dropped_errors)
            if dropped:
                unit["droppedErrors"] = _errors_by_keyword(dropped, node)

        annotations = _pick(node.annotations, render_input.annotations)
        if annotations:
            unit["annotations"] = _annotations_by_keyword(annotations)
        if irrelevant == "mark":
            dropped_annotations = _pick(
                node.dropped_annotations, render_input.dropped_annotations
            )
            if dropped_annotations:
                unit["droppedAnnotations"] = _annotations_by_keyword(
                    dropped_annotations
                )

        if details:
            unit["details"] = details

        if (
            irrelevant == "omit"
            and "errors" not in unit
            and "annotations" not in unit
            and "details" not in unit
        ):
            return None
        return unit

    rendered = to_unit(render_input.root)
    return rendered if rendered is not None else unit_of(render_input.root)


def render_list(
    render_input: RenderInput, irrelevant: IrrelevantRendering
) -> ListOutputDocument:
    """Render the `list` document: the `hierarchical` units flattened under a
    root carrying only `valid` and `details`.

    At the relevant level only units that report an error or an annotation
    appear (the proposal's SHOULD); the verbose level includes every unit.
    """
    details: list[OutputUnit] = []

    def collect(unit: OutputUnit) -> None:
        children = unit.pop("details", None)
        if irrelevant == "mark" or "errors" in unit or "annotations" in unit:
            details.append(unit)
        for child in children or ():
            collect(child)

    collect(render_hierarchical(render_input, irrelevant))
    return {"valid": render_input.root.valid, "details": details}


# --- detailed / verbose (IETF draft-03 §13.4.3-13.4.4) ---------------------


class DetailedOutputUnit(TypedDict):
    """Output unit of IETF draft-03 §13.3 for `detailed` and `verbose`: one
    node per keyword evaluation or schema application, with a local
    `error`/`annotation` and nested results under `errors` (failed node) or
    `annotations` (successful node)."""

    valid: bool
    keywordLocation: str
    absoluteKeywordLocation: str
    instanceLocation: str
    error: NotRequired[str]
    annotation: NotRequired[JsonValue]
    errors: NotRequired[list[DetailedOutputUnit]]
    annotations: NotRequired[list[DetailedOutputUnit]]


def _attach_nested(unit: DetailedOutputUnit, nested: list[DetailedOutputUnit]) -> None:
    if not nested:
        return
    # §13.3.5: nested results key on the node's own result.
    if unit["valid"]:
        unit["annotations"] = nested
    else:
        unit["errors"] = nested


def _nested_of(unit: DetailedOutputUnit) -> list[DetailedOutputUnit]:
    nested = unit.get("errors")
    if nested is None:
        nested = unit.get("annotations")
    return nested if nested is not None else []


def _build_draft03_tree(
    render_input: RenderInput, level: Literal["relevant", "verbose"]
) -> DetailedOutputUnit:
    """The keyword-level tree: every schema application becomes a node whose
    children are one node per keyword evaluation, in evaluation order; each
    keyword node carries the keyword's own error or annotation and the
    applications it performed. The verbose level includes every record; a
    record is relevant exactly when every node on its path from the root
    shares the root's `valid` (§13.4.4), so no single node's `valid` marks
    it."""

    def build(node: RenderNode) -> DetailedOutputUnit:
        keyword_location = node.evaluation_path
        unit: DetailedOutputUnit = {
            "valid": node.valid,
            "keywordLocation": keyword_location,
            "absoluteKeywordLocation": node.schema_location,
            "instanceLocation": node.input_location,
        }
        errors = _pick(node.errors, render_input.errors)
        annotations = _pick(node.annotations, render_input.annotations)
        if level == "verbose":
            errors += _pick(node.dropped_errors, render_input.dropped_errors)
            annotations += _pick(
                node.dropped_annotations, render_input.dropped_annotations
            )
        # A boolean `false` schema's error belongs to the application itself.
        own = [e for e in errors if e["evaluationPath"] == keyword_location]
        if own:
            unit["error"] = _join_messages(own)

        # The first evaluation-path segment of a child application below its
        # parent names the applying keyword.
        children_of: dict[str | None, list[RenderNode]] = {}
        for child in node.children:
            children_of.setdefault(
                _first_segment_below(child, keyword_location), []
            ).append(child)

        nested: list[DetailedOutputUnit] = []
        for keyword in node.keywords:
            suffix = "/" + escape_segment(keyword.name)
            kw_location = keyword_location + suffix
            kw_unit: DetailedOutputUnit = {
                "valid": keyword.valid,
                "keywordLocation": kw_location,
                # `keywordLocation` is a plain-text pointer and
                # `absoluteKeywordLocation` a URI, so the same segment is
                # appended in two forms (P10).
                "absoluteKeywordLocation": node.schema_location
                + pointer_fragment(suffix),
                "instanceLocation": node.input_location,
            }
            kw_errors = [e for e in errors if e["evaluationPath"] == kw_location]
            if kw_errors:
                kw_unit["error"] = _join_messages(kw_errors)
            for annotation in annotations:
                if annotation["keyword"] == keyword.name:
                    kw_unit["annotation"] = annotation["annotation"]
                    break
            applied = children_of.pop(keyword.name, None)
            if applied is not None:
                _attach_nested(kw_unit, [build(c) for c in applied])
            nested.append(kw_unit)
        # Applications not attributable to a keyword entry (a custom keyword
        # applying with no segment of its own) stay under the application.
        for stray in children_of.values():
            nested.extend(build(c) for c in stray)
        _attach_nested(unit, nested)
        return unit

    return build(render_input.root)


def _condense(unit: DetailedOutputUnit, is_root: bool) -> DetailedOutputUnit | None:
    """§13.4.3: a node with no local result is removed when it has no
    children and replaced by its child when it has one; the root remains."""
    nested = [n for n in (_condense(c, False) for c in _nested_of(unit)) if n]
    local = "error" in unit or "annotation" in unit
    if not local and not is_root:
        if not nested:
            return None
        if len(nested) == 1:
            return nested[0]
    out: DetailedOutputUnit = {
        "valid": unit["valid"],
        "keywordLocation": unit["keywordLocation"],
        "absoluteKeywordLocation": unit["absoluteKeywordLocation"],
        "instanceLocation": unit["instanceLocation"],
    }
    if "error" in unit:
        out["error"] = unit["error"]
    if "annotation" in unit:
        out["annotation"] = unit["annotation"]
    _attach_nested(out, nested)
    return out


def render_detailed(render_input: RenderInput) -> DetailedOutputUnit:
    """The `detailed` document (§13.4.3): the condensed keyword-level tree of
    relevant results."""
    condensed = _condense(_build_draft03_tree(render_input, "relevant"), True)
    assert condensed is not None  # the root is never removed
    return condensed


def render_verbose(render_input: RenderInput) -> DetailedOutputUnit:
    """The `verbose` document (§13.4.4): the full keyword-level tree,
    irrelevant results included and told apart only by `valid` along each
    node's path from the root."""
    return _build_draft03_tree(render_input, "verbose")


# --- trace -----------------------------------------------------------------


class TraceUnit(TypedDict):
    """One schema application from a traced evaluation (`Result.trace`).

    The tree mirrors the evaluation exactly, including applications inside
    subtrees that passed, so a consumer can reconstruct application context
    (which `anyOf` branches an error competed against) without parsing
    location strings. `segments` are the evaluation-path segments below the
    parent application, decoded: the first is the applying keyword, any
    following are branch indexes or property names; empty at the root.
    `errorIndexes` index `Result.errors` of the same run and are populated
    only when the evaluation failed.
    """

    segments: list[str]
    schemaLocation: str
    inputLocation: str
    valid: bool
    errorIndexes: list[int]
    children: list[TraceUnit]


def render_trace(root: RenderNode) -> TraceUnit:
    """Render the located tree into the public trace."""

    def to_unit(node: RenderNode, parent_path: str) -> TraceUnit:
        return {
            "segments": _segments_below(node, parent_path),
            "schemaLocation": node.schema_location,
            "inputLocation": node.input_location,
            "valid": node.valid,
            "errorIndexes": list(node.errors),
            "children": [to_unit(c, node.evaluation_path) for c in node.children],
        }

    return to_unit(root, "")
