# Output demand and result assembly (DESIGN.md D6; §2 module table:
# "OutputFormat, EvaluateOptions, resolve_output_demand, assemble_result,
# Result"). `resolve_output_demand` is the one place every combination of
# output format and control is admitted or rejected, before any evaluation
# happens — so a caller never pays for a run whose result it cannot be
# given (D6). `assemble_result` is the one place a `Result` is built from
# the flat surface and the located tree, so presence rules have one owner
# regardless of what tier produced them.
#
# Dependency direction: imports `output` (units, `AnnotationSelection`,
# `RecordPredicate`, `RenderInput`/`RenderNode`, the format renderers) and
# `errors` (`OutputOptionsError`). No engine record, `Cursor`, or
# `SchemaRef` is named here — those stop at `records.py`.

from dataclasses import dataclass, field
from enum import StrEnum

from json_schema_engine.core.errors import OutputOptionsError
from json_schema_engine.core.output import (
    AnnotationsOption,
    AnnotationUnit,
    BasicOutputDocument,
    DetailedOutputUnit,
    ErrorUnit,
    IrrelevantRendering,
    ListOutputDocument,
    OutputUnit,
    RecordPredicate,
    RenderInput,
    RenderNode,
    TraceUnit,
    make_record_predicate,
    render_basic,
    render_detailed,
    render_hierarchical,
    render_list,
    render_trace,
    render_verbose,
)


class OutputFormat(StrEnum):
    """Output format names (D6), each fixing a document structure and field
    vocabulary: `flag`/`basic`/`detailed`/`verbose` from IETF draft-03 §13,
    `list`/`hierarchical` from the machines-oriented output proposal."""

    FLAG = "flag"
    BASIC = "basic"
    DETAILED = "detailed"
    VERBOSE = "verbose"
    LIST = "list"
    HIERARCHICAL = "hierarchical"


type OutputDocument = (
    BasicOutputDocument
    | DetailedOutputUnit
    | ListOutputDocument
    | OutputUnit
    | dict[str, bool]
)
"""The document each non-flag `OutputFormat` renders: `basic` →
`BasicOutputDocument`; `detailed`/`verbose` → `DetailedOutputUnit`; `list` →
`ListOutputDocument`; `hierarchical` → `OutputUnit`."""


@dataclass(frozen=True, slots=True)
class OutputDemand:
    """What an evaluation must produce for a resolved set of output options.

    `annotations` is the record-time gate (`make_record_predicate`, D5):
    `None` means "record nothing", which is also the presence rule for the
    result's annotation fields. It deliberately is not the raw
    `AnnotationsOption` — `assemble_result`'s caller still applies the full
    selection (including `keep`) when rendering — but nothing downstream of
    `resolve_output_demand` should re-derive the gate. `verbose` is the
    verbose level (irrelevant records rendered, marked); `tracing` means the
    located tree is built: every format but `flag` and `basic`, or `trace`.
    """

    format: OutputFormat
    annotations: RecordPredicate | None
    error_params: bool
    verbose: bool
    tracing: bool


def resolve_output_demand(
    *,
    output: str | OutputFormat = OutputFormat.FLAG,
    annotations: AnnotationsOption = False,
    error_params: bool = False,
    verbose: bool | None = None,
    trace: bool = False,
    positions: bool = False,
) -> OutputDemand:
    """Admit or reject a combination of output options before evaluation (D6).

    `flag` carries no records, so every control is rejected with it.
    `verbose=True` is rejected for `basic` and `detailed`, relevant-level
    formats by definition (IETF draft-03 §13.4); `verbose=False` contradicts
    the `verbose` format. Everything else is admitted.
    """
    try:
        output_format = OutputFormat(output)
    except ValueError:
        raise OutputOptionsError(f"unknown output format {output!r}") from None

    if output_format is OutputFormat.FLAG:
        requested: tuple[tuple[str, bool], ...] = (
            ("annotations", annotations is not False),
            ("error_params", error_params),
            ("verbose", verbose is True),
            ("trace", trace),
            ("positions", positions),
        )
        for name, requested_on in requested:
            if requested_on:
                raise OutputOptionsError(
                    f"'{name}' has no effect with output \"flag\", which carries "
                    'no records (the minimal level); choose "basic" or another '
                    "format"
                )
        return OutputDemand(
            format=output_format,
            annotations=None,
            error_params=False,
            verbose=False,
            tracing=False,
        )

    if verbose is True and output_format in (OutputFormat.BASIC, OutputFormat.DETAILED):
        raise OutputOptionsError(
            f"'verbose' does not apply to output \"{output_format}\", a "
            "relevant-level format by definition (IETF draft-03 §13.4); use "
            '"verbose", or "list"/"hierarchical" with verbose=True'
        )
    if verbose is False and output_format is OutputFormat.VERBOSE:
        raise OutputOptionsError(
            'output "verbose" is the verbose level by definition; verbose=False '
            "contradicts it"
        )

    return OutputDemand(
        format=output_format,
        annotations=make_record_predicate(annotations),
        error_params=error_params,
        verbose=output_format is OutputFormat.VERBOSE or verbose is True,
        tracing=output_format is not OutputFormat.BASIC or trace,
    )


@dataclass(frozen=True, slots=True)
class UnitSets:
    """The flat surface as one evaluation produced it.

    `annotations` is empty on an invalid run or when none are selected, and
    the dropped pair is empty unless irrelevant records were retained (the
    verbose demand).
    """

    errors: list[ErrorUnit] = field(default_factory=list[ErrorUnit])
    dropped_errors: list[ErrorUnit] = field(default_factory=list[ErrorUnit])
    annotations: list[AnnotationUnit] = field(default_factory=list[AnnotationUnit])
    dropped_annotations: list[AnnotationUnit] = field(
        default_factory=list[AnnotationUnit]
    )


@dataclass(frozen=True, slots=True)
class Result:
    """The result of an evaluation (D6).

    Presence rules: `errors` iff invalid; `annotations` iff valid and
    annotations were selected (independent of whether anything survived);
    `dropped_errors` at the verbose level; `dropped_annotations` at the
    verbose level when annotations were selected; `trace` when requested,
    its `errorIndexes` referencing `errors` on this result;
    `output_document` in the requested format's structure, `None` for
    `flag` (which carries nothing beyond `valid`; `render_flag` exists for
    callers that want that document directly).
    """

    valid: bool
    errors: list[ErrorUnit] | None
    annotations: list[AnnotationUnit] | None
    output_document: OutputDocument | None
    dropped_errors: list[ErrorUnit] | None = None
    dropped_annotations: list[AnnotationUnit] | None = None
    trace: TraceUnit | None = None


def assemble_result(
    demand: OutputDemand,
    valid: bool,
    units: UnitSets,
    root: RenderNode | None,
    root_location: str,
    trace: bool,
) -> Result:
    """Assemble a `Result` from the flat surface and, when the demand built
    one, the located tree (D6).

    `root` is required whenever `demand.tracing`; `root_location` is the
    root schema's canonical location (the `basic` document's own). The unit
    lists are placed on the result as they are — selection (D5), `keep`
    included, was applied by whoever rendered them.
    """
    if demand.format is OutputFormat.FLAG:
        return Result(valid, None, None, None)

    selected = demand.annotations is not None
    errors = None if valid else units.errors
    annotations = units.annotations if valid and selected else None
    dropped_errors = units.dropped_errors if demand.verbose else None
    dropped_annotations = (
        units.dropped_annotations if demand.verbose and selected else None
    )

    render_input: RenderInput | None = None
    if demand.tracing:
        if root is None:
            raise ValueError("a tracing demand needs the located tree's root")
        render_input = RenderInput(
            errors=units.errors,
            dropped_errors=units.dropped_errors,
            annotations=units.annotations,
            dropped_annotations=units.dropped_annotations,
            root=root,
        )
    rendered_trace = (
        render_trace(render_input.root) if trace and render_input is not None else None
    )

    irrelevant: IrrelevantRendering = "mark" if demand.verbose else "omit"
    document: OutputDocument
    if demand.format is OutputFormat.BASIC:
        document = render_basic(valid, root_location, units.errors, units.annotations)
    else:
        assert render_input is not None
        if demand.format is OutputFormat.LIST:
            document = render_list(render_input, irrelevant)
        elif demand.format is OutputFormat.HIERARCHICAL:
            document = render_hierarchical(render_input, irrelevant)
        elif demand.format is OutputFormat.DETAILED:
            document = render_detailed(render_input)
        else:
            document = render_verbose(render_input)

    return Result(
        valid,
        errors,
        annotations,
        document,
        dropped_errors=dropped_errors,
        dropped_annotations=dropped_annotations,
        trace=rendered_trace,
    )
