# The API reference is complete (DESIGN.md M8): every name a public package
# exports through `__all__` appears, backticked, under that package's
# heading in docs/reference.md. A page that lists every export cannot
# silently fall behind a new one.

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "reference.md"
PACKAGES = (
    "json_schema_engine.core",
    "json_schema_engine.core.lowering",
    "json_schema_engine.compiler",
    "json_schema_engine.formats",
    "ecma_regex",
)


def _section(text: str, package: str) -> str | None:
    """The text under the `## <package>` heading, up to the next `## `."""
    heading = re.compile(rf"^## +`?{re.escape(package)}`?[ \t]*$", re.MULTILINE)
    match = heading.search(text)
    if match is None:
        return None
    rest = text[match.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    return rest if following is None else rest[: following.start()]


def _documented(section: str, name: str) -> bool:
    # `name`, `name(...)`, `name[...]`, `name.attr`, or `name: type`.
    return re.search(rf"`{re.escape(name)}(?:`|[(\[.: ])", section) is not None


@pytest.mark.parametrize("package", PACKAGES)
def test_every_export_is_documented(package: str) -> None:
    assert PAGE.exists(), "docs/reference.md is missing"
    text = PAGE.read_text(encoding="utf-8")
    section = _section(text, package)
    assert section is not None, f"docs/reference.md has no '## {package}' heading"
    module = importlib.import_module(package)
    exported: list[str] = list(module.__all__)
    missing = [name for name in exported if not _documented(section, name)]
    assert not missing, f"{package}: undocumented exports {missing}"
