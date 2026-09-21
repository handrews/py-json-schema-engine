# The compiled-leg case runner shared by the four dialect legs (M6): the
# interpreter's verdict (or exception class) must equal the compiled
# validator's, under both optimization settings.

from collections.abc import Callable
from pathlib import Path

from json_schema_engine.compiler import compile_validator
from json_schema_engine.core import JsonSchemaEngineError, create_engine
from json_schema_engine.test_kit import SuiteCase, suite_remotes_loader


def _outcome(run: Callable[[], bool]) -> tuple[str, object]:
    try:
        return ("valid", run())
    except JsonSchemaEngineError as error:
        return ("raise", type(error).__name__)


def compiled_case(
    case: SuiteCase, dialect: str, remotes_dir: Path, retrieval_uri: str
) -> None:
    engine = create_engine(
        default_dialect=dialect, loaders=[suite_remotes_loader(remotes_dir)]
    )
    uri = engine.load_schema(case.schema, retrieval_uri)
    expected = _outcome(lambda: engine.evaluate(uri, case.data).valid)
    assert expected == ("valid", case.valid)
    for conservative in (False, True):
        validate = compile_validator(engine, uri, conservative=conservative).validate
        assert _outcome(lambda validate=validate: validate(case.data)) == expected, (
            conservative
        )
