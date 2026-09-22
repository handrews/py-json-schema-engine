# Embedded-resource location chains (DESIGN.md §2 module table; P11).
#
# Dependency direction: a near-leaf. It imports `uri` and nothing else, so
# that `errors` may import it without the error module gaining a dependency
# on anything that could import back.
#
# A canonical `base_uri#pointer` names a position exactly, and still does
# not locate it. In a compound document the base may be an embedded `$id`
# the reader never knew was there, and a relative `$id` resolves to a URI
# that appears nowhere in their file. A chain walks outward from the
# position through each enclosing resource, so the reader can get from the
# error back to the text they registered.

from dataclasses import dataclass
from itertools import pairwise

from json_schema_engine.core.uri import schema_location


@dataclass(frozen=True, slots=True)
class LocationHop:
    """One resource on the path from a position out to its document.

    `pointer` is a plain-text JSON Pointer from this resource's root to
    whatever the hop *below* names: for the first hop, the position itself;
    for every later hop, the root of the resource the previous hop
    describes. One rule, so there is no special case at either end — an
    error at a resource root simply gives the first hop an empty pointer.

    `declared_id` is the `$id` exactly as the author wrote it, which is the
    only way a reader searching the file can find a relative one:
    `"$id": "sub/"` is what is in the text, `https://x.example/sub/` is
    what the engine resolved it to. `retrieval_uri` is set only on the
    outermost hop, and only when the document was fetched under a name
    different from the `$id` it declares.
    """

    resource_uri: str
    pointer: str
    declared_id: str | None = None
    retrieval_uri: str | None = None

    @property
    def location(self) -> str:
        """This hop's canonical schema location (P10).

        A URI, so it can be pasted into a `$ref` or handed to
        `Engine.locate` — which is how a caller gets a source range for a
        hop without the chain having to carry one.
        """
        return schema_location(self.resource_uri, self.pointer)


# Innermost first: the order a reader reads it, and the order it prints.
# A tuple rather than a parent-linked node (`Cursor`, `PathNode`) because a
# chain is built once, on demand, and every consumer iterates it — there is
# no structure-sharing to win.
type LocationChain = tuple[LocationHop, ...]


def format_location_chain(chain: LocationChain, *, message: str | None = None) -> str:
    """Render a chain for a person.

    A one-hop chain formats to exactly `chain[0].location` — the same
    string the position would have printed anyway, since both go through
    `uri.schema_location`. That is deliberate: the overwhelmingly common
    single-resource case must not pay for a feature it does not use.

    Beyond one hop, each enclosing resource gets an indented line naming
    where the resource below it sits. The `$id` as written is shown only
    when it differs from the URI it produced, which is exactly when a
    reader would otherwise be searching the file for a string that is not
    in it.
    """
    if not chain:
        return message or ""
    lines = [chain[0].location]
    for below, hop in pairwise(chain):
        line = f"  in {hop.resource_uri} at {hop.pointer or '/'}"
        if below.declared_id is not None and below.declared_id != below.resource_uri:
            line += f' (written as "{below.declared_id}")'
        lines.append(line)
    if chain[-1].retrieval_uri is not None:
        lines.append(f"  retrieved as {chain[-1].retrieval_uri}")
    if message is not None:
        return "\n".join([message, *(f"  {line}" for line in lines)])
    return "\n".join(lines)
