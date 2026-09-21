# The formats-leg case runner shared by the four dialect legs (M7): one
# engine with the dialect's standard table and `assert_formats=True`, both
# compiled artifacts and (for a static plan) a standalone module, cached
# per suite group; every case is checked on the interpreter, under
# hierarchical+verbose output, and on each compiled surface.

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from json_schema_engine.compiler import (
    StandaloneUnsupportedError,
    compile_validator,
    emit_standalone,
)
from json_schema_engine.core import Engine, JsonValue, create_engine
from json_schema_engine.core.formats import FormatTable
from json_schema_engine.test_kit import SuiteCase, suite_remotes_loader

type Validator = Callable[[JsonValue], bool]


@dataclass(frozen=True, slots=True)
class Prepared:
    engine: Engine
    uri: str
    fast: Validator
    conservative: Validator
    standalone: Validator | None


_CACHE: dict[tuple[str, str, str], Prepared] = {}


def _standalone(engine: Engine, uri: str) -> Validator | None:
    try:
        source = emit_standalone(engine, uri)
    except StandaloneUnsupportedError:
        return None
    namespace: dict[str, object] = {}
    exec(compile(source, "<standalone>", "exec"), namespace)
    return cast(Validator, namespace["validate"])


def prepare(
    case: SuiteCase,
    dialect: str,
    table: FormatTable,
    remotes_dir: Path,
    retrieval_uri: str,
    *,
    assert_formats: bool = True,
) -> Prepared:
    key = (dialect, case.file, case.group)
    prepared = _CACHE.get(key)
    if prepared is None:
        engine = create_engine(
            default_dialect=dialect,
            loaders=[suite_remotes_loader(remotes_dir)],
            formats=table,
            assert_formats=assert_formats,
        )
        uri = engine.load_schema(case.schema, retrieval_uri)
        prepared = Prepared(
            engine,
            uri,
            compile_validator(engine, uri).validate,
            compile_validator(engine, uri, conservative=True).validate,
            _standalone(engine, uri),
        )
        _CACHE[key] = prepared
    return prepared


def formats_case(
    case: SuiteCase,
    dialect: str,
    table: FormatTable,
    remotes_dir: Path,
    retrieval_uri: str,
    *,
    assert_formats: bool = True,
) -> None:
    prepared = prepare(
        case, dialect, table, remotes_dir, retrieval_uri, assert_formats=assert_formats
    )
    engine, uri = prepared.engine, prepared.uri
    assert engine.evaluate(uri, case.data).valid is case.valid
    verbose = engine.evaluate(
        uri, case.data, output="hierarchical", verbose=True, annotations=True
    )
    assert verbose.valid is case.valid
    assert prepared.fast(case.data) is case.valid, "compiled"
    assert prepared.conservative(case.data) is case.valid, "compiled (conservative)"
    if prepared.standalone is not None:
        assert prepared.standalone(case.data) is case.valid, "standalone"
