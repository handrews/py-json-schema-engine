# The evaluator-leg case runner shared by the four dialect legs (M9): for
# every suite case, the compiled evaluator's `Result` must equal the
# interpreter's — errors, annotations, dropped records, the output
# document, and the trace — for every non-flag format at both levels,
# under both optimization settings, or raise the same exception class.

from collections.abc import Callable
from pathlib import Path

from json_schema_engine.compiler import compile_evaluator
from json_schema_engine.core import JsonSchemaEngineError, Result, create_engine
from json_schema_engine.test_kit import SuiteCase, suite_remotes_loader

# (output, extra controls): the relevant level with error params and the
# trace, every format at its own level, and the verbose level.
DEMANDS: tuple[tuple[str, dict[str, bool]], ...] = (
    ("list", {"error_params": True, "trace": True}),
    ("hierarchical", {"verbose": True, "trace": True}),
    ("basic", {}),
    ("detailed", {}),
    ("verbose", {"error_params": True}),
)


def _outcome(run: Callable[[], Result]) -> tuple[str, object]:
    try:
        return ("result", run())
    except JsonSchemaEngineError as error:
        return ("raise", type(error).__name__)


def evaluator_case(
    case: SuiteCase, dialect: str, remotes_dir: Path, retrieval_uri: str
) -> None:
    engine = create_engine(
        default_dialect=dialect, loaders=[suite_remotes_loader(remotes_dir)]
    )
    uri = engine.load_schema(case.schema, retrieval_uri)
    expected = [
        _outcome(
            lambda output=output, extra=extra: engine.evaluate(
                uri, case.data, output=output, annotations=True, **extra
            )
        )
        for output, extra in DEMANDS
    ]
    for conservative in (False, True):
        evaluator = compile_evaluator(
            engine, uri, annotations=True, conservative=conservative
        )
        for (output, extra), want in zip(DEMANDS, expected, strict=True):
            got = _outcome(
                lambda output=output, extra=extra, evaluator=evaluator: (
                    evaluator.evaluate(case.data, output=output, **extra)
                )
            )
            assert got == want, (output, conservative, got, want)
