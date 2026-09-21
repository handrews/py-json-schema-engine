# Resource loading contract (DESIGN.md P4 loaders are sync-first; D17
# source positions arrive later).
#
# Dependency direction: imports `json_model` only. The engine façade drains
# unresolved references through these; nothing else knows about loading.

from collections.abc import Callable
from dataclasses import dataclass
from typing import NotRequired, Protocol, TypedDict

from json_schema_engine.core.json_model import JsonValue


class SourcePosition(TypedDict):
    """A point in source text: 1-based line and column, 0-based offset."""

    line: int
    column: int
    offset: int


class SourceSpan(TypedDict):
    start: SourcePosition
    end: SourcePosition


class SourceRange(TypedDict):
    """Where a value sits in its document (D17).

    `key` is present for an object member: diagnostics about a missing or
    extra property point at the key, those about a value at the value, and
    SARIF/LSP-class consumers want both.
    """

    value: SourceSpan
    key: NotRequired[SourceSpan]


class SourceLocation(TypedDict):
    """A schema location translated back to its document (D17).

    `pointer` is document-rooted, unlike a `schemaLocation`, which is
    resource-rooted; `range` is present when the document's loader reported
    positions.
    """

    documentUri: str
    pointer: str
    range: NotRequired[SourceRange]


# A loader's position capability: the range of a document-rooted JSON
# Pointer, or None when it does not know. A function rather than a map so a
# loader may keep a parse tree and answer lazily.
type RangeLookup = Callable[[str], SourceRange | None]


class LoadedResource(Protocol):
    """What the engine needs from a loader's result: the value and its URI.

    A Protocol rather than a class so that a loader written without any
    dependency on the engine (the test-kit's suite remotes loader, a
    framework's own document type) satisfies the contract structurally.
    """

    @property
    def value(self) -> JsonValue: ...

    @property
    def uri(self) -> str:
        """The URI to register the document under, normally the one requested.

        A loader that followed a redirect reports where the document
        actually lives so aliases stay correct.
        """
        ...


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """The engine's own concrete `LoadedResource`, for loaders that want one.

    `get_range` is the optional position capability (D17). It is read off
    any loaded resource with `getattr`, since a Protocol cannot declare an
    optional member, so a resource type without it stays valid.
    """

    value: JsonValue
    uri: str
    get_range: RangeLookup | None = None


# A loader returns `None` for a URI it does not know: a miss is not an
# error, since the next loader may know it and evaluation reports a
# reference that is never satisfied only if it is actually followed.
type Loader = Callable[[str], LoadedResource | None]
