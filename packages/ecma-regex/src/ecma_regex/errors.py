"""Exceptions raised by :mod:`ecma_regex`."""

from __future__ import annotations

__all__ = [
    "EcmaRegexError",
    "EcmaRegexSyntaxError",
    "UnsupportedPatternError",
]


class EcmaRegexError(Exception):
    """Base class for every error this package raises.

    ``position`` is a zero-based index into the source pattern (or, for
    flag errors, into the flag string).
    """

    __slots__ = ("message", "position")

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position


class EcmaRegexSyntaxError(EcmaRegexError):
    """The pattern is not a valid ECMA-262 pattern under ``u`` semantics."""


class UnsupportedPatternError(EcmaRegexError):
    """The pattern is valid ECMA-262 but cannot be translated faithfully.

    Raised, for example, for a variable-width lookbehind on the ``re``
    backend, or for a Unicode property whose membership this package cannot
    compute from the standard library.
    """
