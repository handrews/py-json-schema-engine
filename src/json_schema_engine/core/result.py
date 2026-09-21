# Output demand and result assembly (DESIGN.md D6; §2 module table:
# "OutputFormat, EvaluateOptions, resolve_output_demand, assemble_result,
# Result"). `resolve_output_demand` is the one place every combination of
# output format and control is admitted or rejected, before any evaluation
# happens — so a caller never pays for a run whose result it cannot be
# given (D6). `assemble_result` is the one place a `Result` is built from a
# `RenderInput`, so presence rules have one owner regardless of what tier
# produced the render input.
#
# Dependency direction: imports `output` (units, `AnnotationSelection`,
# `RecordPredicate`, `RenderInput`, the format renderers) and `errors`
# (`OutputOptionsError`). No engine record, `Cursor`, or `SchemaRef` is
# named here — those stop at `records.py`.

from dataclasses import dataclass, replace
from enum import StrEnum

from json_schema_engine.core.errors import OutputOptionsError
from json_schema_engine.core.output import (
    AnnotationsOption,
    AnnotationUnit,
    BasicOutputDocument,
    ErrorUnit,
    ListOutputDocument,
    RecordPredicate,
    RenderInput,
    make_record_predicate,
    render_basic,
    render_list,
    select_units,
)


class OutputFormat(StrEnum):
    """Output format names (D6): `flag`/`basic`/`detailed`/`verbose` from IETF
    draft-03 §13, `list`/`hierarchical` from the machines-oriented output
    proposal. M1 implements `flag`, `basic`, and `list`; the rest are named
    here so the surface never has to be widened, only unlocked, at M5.
    """

    FLAG = "flag"
    BASIC = "basic"
    DETAILED = "detailed"
    VERBOSE = "verbose"
    LIST = "list"
    HIERARCHICAL = "hierarchical"


# Whole formats M5 adds. Distinct from the M5-deferred *controls* (`trace`,
# `positions`, and the verbose *level* of `list`), which apply to formats M1
# already implements.
_DEFERRED_FORMATS = frozenset(
    {OutputFormat.DETAILED, OutputFormat.VERBOSE, OutputFormat.HIERARCHICAL}
)


@dataclass(frozen=True, slots=True)
class OutputDemand:
    """What an evaluation must produce for a resolved set of output options.

    `annotations` is the record-time gate (`make_record_predicate`, D5):
    `None` means "record nothing". It deliberately is not the raw
    `AnnotationsOption` — `assemble_result` still needs the raw selection
    (including `keep`) to render, and callers pass it separately, but nothing
    downstream of `resolve_output_demand` should re-derive the gate.
    """

    format: OutputFormat
    annotations: RecordPredicate | None
    error_params: bool
    verbose: bool
    tracing: bool


def _reject_deferred(name: str) -> None:
    raise OutputOptionsError(
        f"'{name}' is not implemented in this milestone (M1 ships flag, basic, "
        "and list; it lands in M5)"
    )


def resolve_output_demand(
    *,
    output: str | OutputFormat = OutputFormat.FLAG,
    annotations: AnnotationsOption = False,
    error_params: bool = False,
    verbose: bool = False,
    trace: bool = False,
    positions: bool = False,
) -> OutputDemand:
    """Admit or reject a combination of output options before evaluation (D6).

    Every combination is either supported now, rejected because it can never
    be (an unknown format name, `verbose` on `basic`, or any control on
    `flag`, which carries no records), or rejected as "not implemented in
    this milestone" because M5 has not landed yet (`detailed`/`verbose`/
    `hierarchical`, `trace`, `positions`, and the verbose level of `list`).
    The two kinds of rejection carry distinct wording so a caller can tell
    "never" from "not yet".
    """
    try:
        output_format = OutputFormat(output)
    except ValueError:
        raise OutputOptionsError(f"unknown output format {output!r}") from None

    if output_format is OutputFormat.FLAG:
        requested: tuple[tuple[str, bool], ...] = (
            ("annotations", annotations is not False),
            ("error_params", error_params),
            ("verbose", verbose),
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

    if output_format in _DEFERRED_FORMATS:
        raise OutputOptionsError(
            f'output "{output_format}" is not implemented in this milestone '
            "(M1 ships flag, basic, and list; detailed/verbose/hierarchical "
            "land in M5)"
        )

    if trace:
        _reject_deferred("trace")

    if verbose:
        if output_format is OutputFormat.BASIC:
            raise OutputOptionsError(
                "'verbose' does not apply to output \"basic\", a relevant-level "
                "format by definition (IETF draft-03 §13.4)"
            )
        # Only `list` remains, and only its verbose level is deferred.
        _reject_deferred("verbose")

    return OutputDemand(
        format=output_format,
        annotations=make_record_predicate(annotations),
        error_params=error_params,
        verbose=False,
        tracing=False,
    )


@dataclass(frozen=True, slots=True)
class Result:
    """The result of an evaluation (D6).

    `errors` is present (non-`None`) iff the result is invalid; `annotations`
    is present iff the result is valid and annotations were selected
    (`selection is not False`), independent of whether anything survived
    selection. `output_document` is `None` for `flag` — flag carries nothing
    beyond `valid` itself, so `render_flag` exists for callers that want that
    document directly rather than through a `Result`.
    """

    valid: bool
    errors: list[ErrorUnit] | None
    annotations: list[AnnotationUnit] | None
    output_document: BasicOutputDocument | ListOutputDocument | dict[str, bool] | None


def assemble_result(
    demand: OutputDemand, render_input: RenderInput, selection: AnnotationsOption
) -> Result:
    """Assemble a `Result` from a flat `RenderInput` (D6).

    `selection` is the raw `AnnotationsOption` (not `demand.annotations`,
    which only ever gates recording, D5): this is where the full selection,
    `keep` included, is applied to `render_input.annotations` before either
    the flat `Result.annotations` or the rendered document sees it.
    """
    if demand.format is OutputFormat.FLAG:
        return Result(render_input.valid, None, None, None)

    selection_active = selection is not False
    selected_annotations = (
        select_units(render_input.annotations, selection)
        if render_input.valid and selection_active
        else []
    )
    working_input = replace(render_input, annotations=selected_annotations)

    errors = None if working_input.valid else list(working_input.errors)
    annotations = (
        selected_annotations if working_input.valid and selection_active else None
    )

    document: BasicOutputDocument | ListOutputDocument
    if demand.format is OutputFormat.BASIC:
        document = render_basic(working_input)
    elif demand.format is OutputFormat.LIST:
        document = render_list(working_input)
    else:  # pragma: no cover - resolve_output_demand rejects every other format
        raise OutputOptionsError(
            f"output format {demand.format!r} is not implemented in this milestone"
        )

    return Result(working_input.valid, errors, annotations, document)
