"""Static analyses over a parsed pattern: star height and match width."""

from __future__ import annotations

from .ast import (
    Alternation,
    Anchor,
    Backreference,
    CharClass,
    ClassEscape,
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

__all__ = ["is_fixed_width", "star_height", "width"]


def star_height(pattern: Pattern) -> int:
    """The nesting depth of unbounded quantifiers in ``pattern``.

    ``a`` is 0, ``a+`` is 1, ``(a+)+`` is 2. Bounded quantifiers such as
    ``a{2,3}`` do not count; ``a{2,}`` does. A star height of 2 or more is
    the classic screen for catastrophic backtracking (ReDoS): it is a
    necessary condition, not a sufficient one, so it over-reports.
    """
    return _height(pattern.root)


def _height(node: Node) -> int:
    match node:
        case Quantifier(target=target, max=None):
            return 1 + _height(target)
        case Quantifier(target=target):
            return _height(target)
        case Alternation(options=children):
            return max((_height(child) for child in children), default=0)
        case Concatenation(parts=children):
            return max((_height(child) for child in children), default=0)
        case Group(body=body) | Lookaround(body=body):
            return _height(body)
        case _:
            return 0


def width(node: Node) -> tuple[int, int | None]:
    """The ``(minimum, maximum)`` number of code points ``node`` consumes.

    ``maximum`` is ``None`` when it is unbounded or not statically known
    (a backreference). A node is fixed-width when the two are equal.
    """
    match node:
        case Literal() | Dot() | CharClass() | ClassEscape() | PropertyEscape():
            return 1, 1
        case Anchor() | WordBoundary() | Lookaround():
            return 0, 0
        case Backreference():
            return 0, None
        case Group(body=body):
            return width(body)
        case Concatenation(parts=parts):
            low = 0
            high: int | None = 0
            for part in parts:
                part_low, part_high = width(part)
                low += part_low
                high = None if high is None or part_high is None else high + part_high
            return low, high
        case Alternation(options=options):
            widths = [width(option) for option in options]
            low = min(bounds[0] for bounds in widths)
            high = (
                None
                if any(bounds[1] is None for bounds in widths)
                else max(bounds[1] for bounds in widths if bounds[1] is not None)
            )
            return low, high
        case Quantifier(target=target, min=minimum, max=maximum):
            target_low, target_high = width(target)
            if maximum is None or target_high is None:
                return target_low * minimum, None
            return target_low * minimum, target_high * maximum


def is_fixed_width(node: Node) -> bool:
    """Whether ``node`` always consumes the same number of code points."""
    low, high = width(node)
    return high is not None and low == high
