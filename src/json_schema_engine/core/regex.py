# The engine's regex adapter (DESIGN.md P1, D20): dialect and backend
# selection, a per-engine compile cache, registration-time screening, and
# the ReDoS star-height screen. All ECMA-262 knowledge lives in the
# standalone `ecma_regex` package; this module only chooses and caches.
#
# Dependency direction: imports `errors` and the `ecma_regex` package. The
# engine façade owns one `RegexCache`; keywords see only `CompiledRegex`.

import re
from dataclasses import dataclass
from typing import Literal

import ecma_regex
from json_schema_engine.core.errors import UnsafeRegexError, UnsupportedPatternError

# `ecma262` is the default for every current draft; `python` hands the
# pattern to `re` untouched, for callers migrating schemas that only ever
# ran under Python (P1).
type RegexDialect = Literal["ecma262", "python"]
type RegexBackend = Literal["re", "regex"]


class _PythonRegex:
    """A Python-dialect pattern: `re` semantics, search-only like ECMA `test`.

    `compiled` is the backend pattern, exposed so the compiler tier can hand
    emitted code the object whose `search` it calls directly (M6).
    """

    __slots__ = ("compiled",)

    def __init__(self, pattern: str) -> None:
        self.compiled = re.compile(pattern)

    def search(self, text: str, /) -> bool:
        return self.compiled.search(text) is not None


class RegexCache:
    """Compile patterns under one dialect and backend, once each.

    A schema's patterns are compiled at registration (so an untranslatable
    one fails there, with its location) and then hit the cache on every
    evaluation.
    """

    def __init__(
        self, dialect: RegexDialect = "ecma262", backend: RegexBackend = "re"
    ) -> None:
        self.dialect: RegexDialect = dialect
        self.backend: RegexBackend = backend
        self._cache: dict[str, ecma_regex.EcmaRegex | _PythonRegex] = {}

    def compile(
        self, pattern: str, *, schema_location: str | None = None
    ) -> ecma_regex.EcmaRegex | _PythonRegex:
        """The compiled form of `pattern`; raises `UnsupportedPatternError`.

        `schema_location` only decorates the error: the registry passes the
        keyword's location at registration time, evaluation passes nothing.
        """
        cached = self._cache.get(pattern)
        if cached is not None:
            return cached
        try:
            compiled: ecma_regex.EcmaRegex | _PythonRegex
            if self.dialect == "python":
                compiled = _PythonRegex(pattern)
            else:
                compiled = ecma_regex.compile(pattern, backend=self.backend)
        except (ecma_regex.EcmaRegexError, re.error) as error:
            raise UnsupportedPatternError(
                f"cannot compile pattern {pattern!r} under the {self.dialect} "
                f"dialect with the {self.backend} backend: {error}",
                schema_location=schema_location,
            ) from error
        self._cache[pattern] = compiled
        return compiled


@dataclass(frozen=True, slots=True)
class UnsafeRegexReport:
    safe: bool
    reason: str | None = None


def detect_unsafe_regex(pattern: str) -> UnsafeRegexReport:
    """A conservative ReDoS screen: nested unbounded quantifiers (D20).

    Necessary, not sufficient, so it over-reports. Backs the opt-in
    `reject_unsafe_regex` engine option and is exported for a lint layer
    (D14). A pattern that does not parse as ECMA-262 is reported safe here:
    the compile step reports that failure with more detail.
    """
    try:
        parsed = ecma_regex.parse(pattern)
    except ecma_regex.EcmaRegexError:
        return UnsafeRegexReport(True)
    height = ecma_regex.star_height(parsed)
    if height >= 2:
        return UnsafeRegexReport(
            False, f"nested unbounded quantifiers (star height {height})"
        )
    return UnsafeRegexReport(True)


def reject_unsafe_regex(pattern: str, schema_location: str) -> None:
    """Raise `UnsafeRegexError` when the screen flags `pattern`."""
    report = detect_unsafe_regex(pattern)
    if not report.safe:
        raise UnsafeRegexError(
            f"pattern {pattern!r} rejected: {report.reason}",
            schema_location=schema_location,
        )
