# Resource loading contract (DESIGN.md P4 loaders are sync-first; D17
# source positions arrive later).
#
# Dependency direction: imports `json_model` only. The engine façade drains
# unresolved references through these; nothing else knows about loading.

from collections.abc import Callable
from dataclasses import dataclass

from json_schema_engine.core.json_model import JsonValue


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """A resource a loader found.

    `uri` is the URI the document should be registered under, normally the
    one requested; a loader that followed a redirect may report where the
    document actually lives so aliases stay correct.
    """

    value: JsonValue
    uri: str


# A loader returns `None` for a URI it does not know: a miss is not an
# error, since the next loader may know it and evaluation reports a
# reference that is never satisfied only if it is actually followed.
type Loader = Callable[[str], LoadedDocument | None]
