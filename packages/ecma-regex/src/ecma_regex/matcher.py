"""Compiled ECMA-262 regular expressions."""

from __future__ import annotations

import importlib
import re
import typing
from dataclasses import dataclass

from .errors import UnsupportedPatternError
from .parser import parse
from .translator import BackendName, translate, translate_flags

__all__ = ["CompiledPattern", "EcmaRegex", "compile"]


class CompiledPattern(typing.Protocol):
    """The slice of a compiled backend pattern this package relies on."""

    def search(self, string: str, /) -> object | None: ...


class _RegexModule(typing.Protocol):
    def compile(self, pattern: str, flags: int = 0, /) -> CompiledPattern: ...


@dataclass(frozen=True, slots=True)
class EcmaRegex:
    """An ECMA-262 pattern compiled for a Python backend.

    Nothing here is cached: build one of these once per pattern and hold
    on to it, or put your own cache in front of :func:`compile`.
    """

    pattern: str
    """The original ECMA-262 pattern source."""

    flags: str
    """The original ECMA-262 flag string."""

    translated: str
    """The backend pattern that was compiled."""

    backend: BackendName
    """Which backend compiled it."""

    compiled: CompiledPattern
    """The underlying ``re.Pattern`` (or ``regex`` equivalent)."""

    def search(self, string: str) -> bool:
        """Whether the pattern matches anywhere in ``string``.

        These are ``RegExp.prototype.test`` semantics: the match is
        unanchored, and only the yes/no answer is reported. JSON Schema's
        ``pattern`` and ``patternProperties`` are defined this way.
        """
        return self.compiled.search(string) is not None


def _compile_with_backend(
    backend: BackendName, source: str, flags: int
) -> CompiledPattern:
    if backend == "re":
        return re.compile(source, flags)
    try:
        module = typing.cast(_RegexModule, importlib.import_module("regex"))
    except ImportError as error:  # pragma: no cover - depends on the env
        raise ImportError(
            "the 'regex' backend needs the optional dependency: "
            "install 'ecma-regex[regex]'"
        ) from error
    return module.compile(source, flags)


def compile(
    pattern: str,
    *,
    flags: str = "",
    backend: BackendName = "re",
) -> EcmaRegex:
    """Parse, translate and compile ``pattern`` in one step.

    Raises :class:`~ecma_regex.errors.EcmaRegexSyntaxError` for an invalid
    pattern and :class:`~ecma_regex.errors.UnsupportedPatternError` for a
    valid pattern the backend cannot express.
    """
    parsed = parse(pattern, flags=flags)
    translated = translate(parsed, backend=backend)
    try:
        compiled = _compile_with_backend(backend, translated, translate_flags(parsed))
    except re.error as error:  # pragma: no cover - a translator bug
        raise UnsupportedPatternError(
            f"the {backend!r} backend rejected the translation {translated!r}: {error}",
            0,
        ) from error
    return EcmaRegex(
        pattern=pattern,
        flags=flags,
        translated=translated,
        backend=backend,
        compiled=compiled,
    )
