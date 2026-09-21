# Resource loading contract (DESIGN.md P4 loaders are sync-first; D17
# source positions arrive later).
#
# Dependency direction: imports `json_model` only. The engine façade drains
# unresolved references through these; nothing else knows about loading.

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from json_schema_engine.core.json_model import JsonValue


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
    """The engine's own concrete `LoadedResource`, for loaders that want one."""

    value: JsonValue
    uri: str


# A loader returns `None` for a URI it does not know: a miss is not an
# error, since the next loader may know it and evaluation reports a
# reference that is never satisfied only if it is actually followed.
type Loader = Callable[[str], LoadedResource | None]
