"""The ECMA-262 regular-expression AST.

Every node is a frozen, slotted dataclass, so trees are hashable, cheap,
and safe to share. The shape follows the ECMA-262 pattern grammar
(ECMA-262 22.2.1) rather than any host engine's internal form.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass

__all__ = [
    "Alternation",
    "Anchor",
    "AnchorKind",
    "Backreference",
    "CharClass",
    "ClassEscape",
    "ClassEscapeKind",
    "ClassItem",
    "ClassRange",
    "Concatenation",
    "Dot",
    "Flags",
    "Group",
    "Literal",
    "Lookaround",
    "LookaroundDirection",
    "Node",
    "Pattern",
    "PropertyEscape",
    "Quantifier",
    "WordBoundary",
]

AnchorKind = typing.Literal["start", "end"]
LookaroundDirection = typing.Literal["ahead", "behind"]
ClassEscapeKind = typing.Literal["d", "D", "w", "W", "s", "S"]


@dataclass(frozen=True, slots=True)
class Flags:
    """The subset of ECMA-262 RegExp flags this package models.

    ``unicode`` is always true: this package implements the ``u``-mode
    dialect only, which is the dialect JSON Schema's ``pattern`` keyword
    is specified against in practice.
    """

    ignore_case: bool = False
    multiline: bool = False
    dot_all: bool = False
    unicode: bool = True

    @property
    def source(self) -> str:
        """The flags as an ECMA-262 flag string, in canonical order."""
        letters = ""
        if self.dot_all:
            letters += "s"
        if self.ignore_case:
            letters += "i"
        if self.multiline:
            letters += "m"
        if self.unicode:
            letters += "u"
        return letters


@dataclass(frozen=True, slots=True)
class Literal:
    """A single code point matched literally."""

    code_point: int


@dataclass(frozen=True, slots=True)
class Dot:
    """``.`` -- every code point except a LineTerminator, unless ``s``."""


@dataclass(frozen=True, slots=True)
class Anchor:
    """``^`` or ``$``."""

    kind: AnchorKind


@dataclass(frozen=True, slots=True)
class WordBoundary:
    """``\\b`` (``negated=False``) or ``\\B`` (``negated=True``)."""

    negated: bool


@dataclass(frozen=True, slots=True)
class ClassEscape:
    """``\\d``, ``\\D``, ``\\w``, ``\\W``, ``\\s`` or ``\\S``."""

    kind: ClassEscapeKind


@dataclass(frozen=True, slots=True)
class PropertyEscape:
    """``\\p{...}`` / ``\\P{...}``.

    ``name`` is the property name (``"General_Category"``, ``"Script"``,
    ``"Script_Extensions"``, or a binary property name). ``value`` is the
    property value for the ``name=value`` form and ``None`` for the
    lone-name form (which is a General_Category value or a binary
    property).
    """

    name: str
    value: str | None
    negated: bool


@dataclass(frozen=True, slots=True)
class ClassRange:
    """An inclusive code-point range inside a character class."""

    low: int
    high: int


@dataclass(frozen=True, slots=True)
class CharClass:
    """``[...]`` or ``[^...]``."""

    negated: bool
    items: tuple[ClassItem, ...]


@dataclass(frozen=True, slots=True)
class Group:
    """``(...)``, ``(?<name>...)`` or ``(?:...)``.

    ``index`` is the one-based capture index, or ``None`` when the group
    is non-capturing.
    """

    body: Node
    capturing: bool
    index: int | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Backreference:
    """``\\1`` (``index``) or ``\\k<name>`` (``name``)."""

    index: int | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Lookaround:
    """``(?=)``, ``(?!)``, ``(?<=)`` or ``(?<!)``."""

    body: Node
    direction: LookaroundDirection
    negated: bool


@dataclass(frozen=True, slots=True)
class Quantifier:
    """``*``, ``+``, ``?``, ``{n}``, ``{n,}`` or ``{n,m}``.

    ``max`` is ``None`` for an unbounded quantifier.
    """

    target: Node
    min: int
    max: int | None
    greedy: bool


@dataclass(frozen=True, slots=True)
class Concatenation:
    """A sequence of terms. An empty tuple is the empty alternative."""

    parts: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Alternation:
    """``a|b|c``."""

    options: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Pattern:
    """A parsed pattern: its root node and the flags it was parsed with."""

    root: Node
    flags: Flags


type ClassItem = Literal | ClassRange | ClassEscape | PropertyEscape

type Node = (
    Alternation
    | Concatenation
    | Literal
    | Dot
    | Anchor
    | WordBoundary
    | Group
    | Backreference
    | Lookaround
    | Quantifier
    | CharClass
    | ClassEscape
    | PropertyEscape
)
