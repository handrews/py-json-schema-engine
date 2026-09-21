# The standard format tables (DESIGN.md M7): membership per dialect,
# entry shape, import paths, `format_table_for`, and the behavior without
# the `idna` extra (a subprocess that hides the package).

import importlib
import subprocess
import sys
import textwrap

import pytest

from json_schema_engine.core import (
    DIALECT_2019_09,
    DIALECT_2020_12,
    DIALECT_DRAFT_06,
    DIALECT_DRAFT_07,
)
from json_schema_engine.formats import (
    FORMATS_2019_09,
    FORMATS_2020_12,
    FORMATS_DRAFT_06,
    FORMATS_DRAFT_07,
    format_table_for,
)

NAMES_2020_12 = {
    "date-time",
    "date",
    "time",
    "duration",
    "email",
    "idn-email",
    "hostname",
    "idn-hostname",
    "ipv4",
    "ipv6",
    "uri",
    "uri-reference",
    "iri",
    "iri-reference",
    "uuid",
    "uri-template",
    "json-pointer",
    "relative-json-pointer",
    "regex",
}


def test_membership_per_dialect() -> None:
    assert set(FORMATS_2020_12) == NAMES_2020_12
    assert FORMATS_2019_09 is FORMATS_2020_12
    assert set(FORMATS_DRAFT_07) == NAMES_2020_12 - {"uuid", "duration"}
    assert set(FORMATS_DRAFT_06) == {
        "date-time",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "uri",
        "uri-reference",
        "uri-template",
        "json-pointer",
    }


def test_entries_are_string_formats_with_resolving_import_paths() -> None:
    for name, definition in FORMATS_2020_12.items():
        assert definition.types == ("string",), name
        assert definition.import_path is not None, name
        module_name, _, attribute = definition.import_path.partition(":")
        assert (
            getattr(importlib.import_module(module_name), attribute) is definition.test
        )


@pytest.mark.parametrize(
    ("uri", "table"),
    [
        (DIALECT_2020_12, FORMATS_2020_12),
        (DIALECT_2019_09, FORMATS_2019_09),
        (DIALECT_DRAFT_07, FORMATS_DRAFT_07),
        (DIALECT_DRAFT_07 + "#", FORMATS_DRAFT_07),
        (DIALECT_DRAFT_06, FORMATS_DRAFT_06),
    ],
)
def test_format_table_for(uri: str, table: object) -> None:
    assert format_table_for(uri) is table


def test_format_table_for_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="no standard format table"):
        format_table_for("urn:x:dialect")


def test_tables_are_read_only() -> None:
    with pytest.raises(TypeError):
        FORMATS_2020_12["x"] = FORMATS_2020_12["ipv4"]  # type: ignore[index]


WITHOUT_IDNA = textwrap.dedent(
    """
    import sys
    sys.modules["idna"] = None  # make `import idna` fail as if uninstalled
    from json_schema_engine.core import FormatUnavailableError, create_engine
    from json_schema_engine.formats import FORMATS_2020_12, idna_, net
    assert idna_.HAVE_IDNA is False
    entry = FORMATS_2020_12["idn-hostname"]
    assert entry.unavailable is not None and "idna" in entry.unavailable
    assert FORMATS_2020_12["idn-email"].unavailable is None
    assert net.hostname("xn--X") is True   # documented degradation
    assert net.hostname("-bad") is False
    for assert_formats in (False, True):
        engine = create_engine(
            formats=FORMATS_2020_12, assert_formats=assert_formats
        )
        try:
            engine.register_schema({"format": "idn-hostname"}, "https://x/s")
        except FormatUnavailableError as error:
            assert "idna" in str(error)
            assert assert_formats or error.schema_location == "https://x/s#/format"
        else:
            if assert_formats:
                raise AssertionError("asserting an unavailable format must fail")
    print("ok")
    """
)


def test_without_the_idna_extra() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", WITHOUT_IDNA],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "ok"
