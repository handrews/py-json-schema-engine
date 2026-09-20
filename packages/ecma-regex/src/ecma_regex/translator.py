"""Translate a parsed ECMA-262 pattern into a Python backend pattern.

The translation is *semantic*, not textual: anywhere ECMA-262 and Python
disagree about what a construct means, the emitted pattern spells out the
ECMA-262 meaning in constructs the backend already has. See the README's
divergence table for the full list and for the handful of residual
differences that cannot be closed.
"""

from __future__ import annotations

import re
import typing
from dataclasses import dataclass

from .analysis import is_fixed_width
from .ast import (
    Alternation,
    Anchor,
    Backreference,
    CharClass,
    ClassEscape,
    ClassItem,
    ClassRange,
    Concatenation,
    Dot,
    Group,
    Literal,
    Lookaround,
    Node,
    Pattern,
    PropertyEscape,
    Quantifier,
    WordBoundary,
)
from .errors import UnsupportedPatternError
from .unicode_data import (
    DIGIT,
    LINE_TERMINATORS,
    WHITESPACE,
    WORD,
    PropertyNotComputableError,
    RangeList,
    complement,
    property_ranges,
    union,
)

__all__ = ["BackendName", "translate", "translate_flags"]

BackendName = typing.Literal["re", "regex"]

_ASCII_PRINTABLE = frozenset(chr(code) for code in range(0x21, 0x7F))
_OUTSIDE_META = frozenset("#$()*+.?[\\]^{|}")
_CLASS_META = frozenset("#-[\\]^")
_OUTSIDE_SAFE = _ASCII_PRINTABLE - _OUTSIDE_META
_CLASS_SAFE = _ASCII_PRINTABLE - _CLASS_META

_CLASS_ESCAPE_RANGES: dict[str, RangeList] = {
    "d": DIGIT,
    "D": complement(DIGIT),
    "w": WORD,
    "W": complement(WORD),
    "s": WHITESPACE,
    "S": complement(WHITESPACE),
}

#: Every code point; used where a set is universal.
_ANY = "[\\s\\S]"
#: Matches nothing; used for the empty character class ``[]``.
_NEVER = "(?!)"

_WORD_CLASS = "[0-9A-Za-z_]"
_WORD_BOUNDARY = (
    f"(?:(?<!{_WORD_CLASS})(?={_WORD_CLASS})|(?<={_WORD_CLASS})(?!{_WORD_CLASS}))"
)
_NOT_WORD_BOUNDARY = (
    f"(?:(?<={_WORD_CLASS})(?={_WORD_CLASS})|(?<!{_WORD_CLASS})(?!{_WORD_CLASS}))"
)


def _numeric_escape(code_point: int) -> str:
    if code_point <= 0xFF:
        return f"\\x{code_point:02x}"
    if code_point <= 0xFFFF:
        return f"\\u{code_point:04x}"
    return f"\\U{code_point:08x}"


def _escape_outside(code_point: int) -> str:
    character = chr(code_point)
    if character in _OUTSIDE_SAFE:
        return character
    if character in _OUTSIDE_META:
        return "\\" + character
    return _numeric_escape(code_point)


def _escape_in_class(code_point: int) -> str:
    character = chr(code_point)
    if character in _CLASS_SAFE:
        return character
    if character in _CLASS_META:
        return "\\" + character
    return _numeric_escape(code_point)


def _render_ranges(ranges: RangeList) -> str:
    pieces: list[str] = []
    for low, high in ranges:
        if low == high:
            pieces.append(_escape_in_class(low))
        elif high == low + 1:
            pieces.append(_escape_in_class(low))
            pieces.append(_escape_in_class(high))
        else:
            pieces.append(f"{_escape_in_class(low)}-{_escape_in_class(high)}")
    return "".join(pieces)


def _bracket(ranges: RangeList) -> str:
    if not ranges:
        return _NEVER
    if ranges == ((0, 0x10FFFF),):
        return _ANY
    return f"[{_render_ranges(ranges)}]"


def _python_group_name(name: str) -> str:
    """Map an ECMA group name to a Python identifier, injectively.

    ECMA-262 group names may contain ``$``, which Python's ``re`` rejects.
    Names that are already Python identifiers pass through unchanged; the
    rest are escaped character-by-character, so two distinct ECMA names
    never collide.
    """
    if name.isidentifier():
        return name
    escaped = "".join(
        character
        if character.isalnum() and character.isascii()
        else f"_{ord(character):x}_"
        for character in name
    )
    return f"_g{escaped}"


def translate_flags(pattern: Pattern) -> int:
    """Backend compile flags that cannot be expressed in the pattern text.

    Only ``re.IGNORECASE`` is ever returned: ``m`` and ``s`` are spelled
    out in the translated pattern, because Python's own ``MULTILINE`` and
    ``DOTALL`` use a narrower set of line terminators than ECMA-262 does.
    """
    return re.IGNORECASE if pattern.flags.ignore_case else 0


def translate(pattern: Pattern, *, backend: BackendName = "re") -> str:
    """Emit a backend pattern string with ECMA-262 semantics.

    The result is meant to be compiled with the flags returned by
    :func:`translate_flags`. Raises
    :class:`~ecma_regex.errors.UnsupportedPatternError` when the chosen
    backend cannot express the pattern -- a variable-width lookbehind on
    ``re``, or a Unicode property this package cannot compute.
    """
    return _Translator(backend=backend, pattern=pattern).emit_inner(pattern.root)


@dataclass(frozen=True, slots=True)
class _Translator:
    backend: BackendName
    pattern: Pattern

    # -- helpers --------------------------------------------------------

    def _unsupported(self, message: str) -> UnsupportedPatternError:
        # The AST carries no source offsets, so translation-time errors
        # report position 0. Parse-time errors carry real positions.
        return UnsupportedPatternError(message, 0)

    def _property(self, node: PropertyEscape) -> RangeList:
        try:
            ranges = property_ranges(node.name, node.value)
        except PropertyNotComputableError as error:
            raise self._unsupported(
                f"{error.description}; use the 'regex' backend"
            ) from error
        return complement(ranges) if node.negated else ranges

    def _class_escape_ranges(self, node: ClassEscape) -> RangeList:
        return _CLASS_ESCAPE_RANGES[node.kind]

    def _item_ranges(self, item: ClassItem) -> RangeList:
        match item:
            case Literal(code_point=code_point):
                return ((code_point, code_point),)
            case ClassRange(low=low, high=high):
                return ((low, high),)
            case ClassEscape():
                return self._class_escape_ranges(item)
            case PropertyEscape():
                return self._property(item)

    # -- emission -------------------------------------------------------

    def emit_inner(self, node: Node) -> str:
        """Emit ``node`` where a surrounding delimiter already exists.

        An alternation needs no ``(?:...)`` wrapper directly inside a
        group, a lookaround, or at the top level.
        """
        if isinstance(node, Alternation):
            return "|".join(self.emit_inner(option) for option in node.options)
        return self.emit(node)

    def emit(self, node: Node) -> str:
        match node:
            case Literal(code_point=code_point):
                return _escape_outside(code_point)
            case Dot():
                if self.pattern.flags.dot_all:
                    return _ANY
                return f"[^{_render_ranges(LINE_TERMINATORS)}]"
            case Anchor(kind=kind):
                return self._anchor(kind)
            case WordBoundary(negated=negated):
                return _NOT_WORD_BOUNDARY if negated else _WORD_BOUNDARY
            case ClassEscape():
                return _bracket(self._class_escape_ranges(node))
            case PropertyEscape():
                return self._property_escape(node)
            case CharClass():
                return self._char_class(node)
            case Group():
                return self._group(node)
            case Backreference(index=index, name=name):
                if name is not None:
                    return f"(?P={_python_group_name(name)})"
                return f"(?:\\{index})"
            case Lookaround():
                return self._lookaround(node)
            case Quantifier():
                return self._quantifier(node)
            case Concatenation(parts=parts):
                return "".join(self.emit(part) for part in parts)
            case Alternation():
                return f"(?:{self.emit_inner(node)})"

    def _anchor(self, kind: str) -> str:
        if not self.pattern.flags.multiline:
            return "\\A" if kind == "start" else "\\Z"
        terminators = _render_ranges(LINE_TERMINATORS)
        if kind == "start":
            return f"(?:\\A|(?<=[{terminators}]))"
        return f"(?:\\Z|(?=[{terminators}]))"

    def _property_escape(self, node: PropertyEscape) -> str:
        if self.backend == "regex":
            body = node.name if node.value is None else f"{node.name}={node.value}"
            return f"\\{'P' if node.negated else 'p'}{{{body}}}"
        return _bracket(self._property(node))

    def _char_class(self, node: CharClass) -> str:
        if self.backend == "regex" and any(
            isinstance(item, PropertyEscape) for item in node.items
        ):
            return self._char_class_native(node)
        ranges = union(*(self._item_ranges(item) for item in node.items))
        if node.negated:
            ranges = complement(ranges)
        return _bracket(ranges)

    def _char_class_native(self, node: CharClass) -> str:
        pieces: list[str] = []
        for item in node.items:
            if isinstance(item, PropertyEscape):
                body = item.name if item.value is None else f"{item.name}={item.value}"
                pieces.append(f"\\{'P' if item.negated else 'p'}{{{body}}}")
            else:
                pieces.append(_render_ranges(self._item_ranges(item)))
        return f"[{'^' if node.negated else ''}{''.join(pieces)}]"

    def _group(self, node: Group) -> str:
        body = self.emit_inner(node.body)
        if not node.capturing:
            return f"(?:{body})"
        if node.name is not None:
            return f"(?P<{_python_group_name(node.name)}>{body})"
        return f"({body})"

    def _lookaround(self, node: Lookaround) -> str:
        body = self.emit_inner(node.body)
        if node.direction == "ahead":
            return f"(?{'!' if node.negated else '='}{body})"
        if self.backend == "re" and not is_fixed_width(node.body):
            raise self._unsupported(
                "Python's 're' requires a fixed-width lookbehind; this "
                "lookbehind is variable-width. Use the 'regex' backend."
            )
        return f"(?<{'!' if node.negated else '='}{body})"

    def _quantifier(self, node: Quantifier) -> str:
        target = self.emit(node.target)
        if not _is_atomic(node.target):
            target = f"(?:{target})"
        return f"{target}{_repetition(node)}{'' if node.greedy else '?'}"


def _repetition(node: Quantifier) -> str:
    match (node.min, node.max):
        case (0, None):
            return "*"
        case (1, None):
            return "+"
        case (0, 1):
            return "?"
        case (minimum, None):
            return f"{{{minimum},}}"
        case (minimum, maximum) if minimum == maximum:
            return f"{{{minimum}}}"
        case (minimum, maximum):
            return f"{{{minimum},{maximum}}}"


def _is_atomic(node: Node) -> bool:
    """Whether ``node`` emits a single quantifiable token."""
    return isinstance(
        node,
        Literal
        | Dot
        | CharClass
        | ClassEscape
        | PropertyEscape
        | Group
        | Backreference
        | Alternation,
    )
