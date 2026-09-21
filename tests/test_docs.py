# Documentation is executed (DESIGN.md M8): every ```python block in the
# READMEs and under docs/ runs here, so an example that stops working
# fails CI instead of misleading a reader. The blocks on one page run in
# order in one namespace — a page reads top to bottom like a script, and a
# later block may use names an earlier one defined. Examples assert what
# they claim; a block that must not run uses another fence tag.

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted(
    [
        ROOT / "README.md",
        *(ROOT / "packages").glob("*/README.md"),
        *(ROOT / "docs").rglob("*.md"),
    ]
)
# One tag per purpose: `python` runs; the others are display only.
DISPLAY_TAGS = frozenset({"sh", "text", "json", "jsonc", "toml", "yaml"})
_FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def fenced_blocks(page: Path) -> list[tuple[str, str]]:
    """`(tag, code)` for every fenced block on the page, in order."""
    return [
        (match.group(1).strip(), match.group(2))
        for match in _FENCE.finditer(page.read_text(encoding="utf-8"))
    ]


def _page_id(page: Path) -> str:
    return str(page.relative_to(ROOT))


@pytest.mark.parametrize("page", PAGES, ids=_page_id)
def test_python_blocks_run(page: Path) -> None:
    namespace: dict[str, object] = {"__name__": f"docs_{page.stem}"}
    for index, (tag, code) in enumerate(fenced_blocks(page)):
        if tag != "python":
            assert tag in DISPLAY_TAGS, (
                f"{_page_id(page)} block {index}: fence tag {tag!r}; "
                f"use `python` for runnable code or one of {sorted(DISPLAY_TAGS)}"
            )
            continue
        try:
            exec(compile(code, f"{_page_id(page)}#block{index}", "exec"), namespace)
        except Exception as error:
            pytest.fail(
                f"{_page_id(page)} block {index} raised "
                f"{type(error).__name__}: {error}\n{code}"
            )


def test_the_readme_is_covered() -> None:
    assert ROOT / "README.md" in PAGES
    assert any(page.parent.parent.name == "packages" for page in PAGES)
