# Schema registration and static reference resolution (DESIGN.md D2, D18,
# D19, P3, §5).
#
# The registration walk descends only into *schema positions*: it asks each
# keyword behavior's `analyze()` for its subschema positions rather than
# hard-coding them, so an `$id` inside `enum` data is never an identifier
# and a custom applicator registered through the dialect registry gets
# correct identifier handling for free.
#
# Dependency direction: imports `dialect`, `ref`, `uri`, `json_model`, and
# `errors`. The evaluator and the engine façade build on this.

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass

from json_schema_engine.core.dialect import Dialect, DialectRegistry
from json_schema_engine.core.errors import (
    DuplicateAnchorError,
    DuplicateResourceError,
    InvalidSchemaError,
    JsonSchemaEngineError,
    MaxDepthExceededError,
    ReadOnlyRegistryError,
    UnresolvableReferenceError,
)
from json_schema_engine.core.json_model import (
    JsonValue,
    escape_segment,
    is_object,
    json_equal,
    json_type_of,
    unescape_segment,
)
from json_schema_engine.core.loader import RangeLookup, SourceRange
from json_schema_engine.core.ref import SchemaRef
from json_schema_engine.core.uri import (
    pointer_from_fragment,
    resolve,
    schema_location,
    split_fragment,
    strip_fragment,
)

# Chosen below CPython's default recursion limit so the typed error fires
# before a `RecursionError`, while staying generous for real documents (P3).
DEFAULT_MAX_DEPTH = 512

type RegexHook = Callable[[str, str], None]


@dataclass(frozen=True, slots=True)
class DynamicReference:
    """A `$dynamicRef` split into its lexical target and, when the
    reference is scope-dependent, the anchor name it rebinds through."""

    lexical: SchemaRef
    anchor: str | None


@dataclass(frozen=True, slots=True)
class RecursiveReference:
    """A `$recursiveRef` split into its lexical target and whether the
    2019-09 all-or-nothing rebinding applies."""

    lexical: SchemaRef
    recursive: bool


@dataclass(frozen=True, slots=True)
class DocumentLocation:
    """Where a schema resource physically lives (D17 bridge).

    The registered document containing it and the JSON Pointer from that
    document's root to the resource's root.
    """

    document_uri: str
    pointer: str


def _resource_of(uri: str) -> str:
    return strip_fragment(uri)


def effective_dialect_uri(
    schema: JsonValue,
    retrieval_uri: str,
    dialect_uri: str | None,
    default_dialect_uri: str,
) -> str:
    """The dialect a document is registered under, fragment-free.

    `$schema` wins when present, then the caller's `dialect_uri`, then the
    default. `…/draft-07/schema#` names the same dialect as the bare form.
    """
    effective = _resource_of(dialect_uri or default_dialect_uri)
    if is_object(schema):
        declared = schema.get("$schema")
        if isinstance(declared, str):
            effective = _resource_of(resolve(retrieval_uri, declared))
    return effective


def _split(uri: str) -> tuple[str, str | None]:
    """Resource and percent-decoded fragment.

    A JSON Pointer travels percent-encoded inside a URI fragment (RFC 6901
    §6), so `#/a%22b` names the member `a"b`; decoding here, once, keeps
    `uri.split_fragment` a pure RFC 3986 operation.

    `pointer_from_fragment` is the inverse of the `pointer_fragment` that
    built the location on the way out (P10), so a location the engine
    emitted resolves back to the position it came from. An anchor name
    cannot contain a character either function touches, so running a
    fragment through it before the anchor/pointer split is harmless.
    """
    resource, fragment = split_fragment(uri)
    return resource, None if fragment is None else pointer_from_fragment(fragment)


class SchemaRegistry:
    """Schema registration, identifier indexing, and reference resolution."""

    def __init__(
        self,
        dialects: DialectRegistry,
        default_dialect_uri: str,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        bundled: Mapping[str, JsonValue] | None = None,
    ) -> None:
        self._dialects = dialects
        self._default_dialect_uri = _resource_of(default_dialect_uri)
        self._max_depth = max_depth
        # Trusted resources (the standard metaschemas) registered on first
        # use rather than up front: an engine is often created per
        # evaluation, and walking eight documents each time would cost more
        # than every evaluation that never references one.
        self._bundled: Mapping[str, JsonValue] = bundled or {}
        self._documents: dict[str, JsonValue] = {}
        self._anchors: dict[str, SchemaRef] = {}
        self._dynamic_anchors: dict[str, SchemaRef] = {}
        self._recursive_roots: set[str] = set()
        # Unions of `StaticFacts.produces`/`consumes` over every registered
        # keyword occurrence: `produce()`'s declaration guard and the
        # elision predicate's "someone might read this" side (D5).
        self._produced_ids: set[str] = set()
        self._consumed_ids: set[str] = set()
        self._document_dialects: dict[str, str] = {}
        self._resource_locations: dict[str, DocumentLocation] = {}
        # Position lookups by document URI (D17): only the outermost
        # registration installs one; embedded resources map back to their
        # document through `_resource_locations`.
        self._document_ranges: dict[str, RangeLookup] = {}
        # Retrieval URI -> declared `$id` base when they differ: the
        # document must be reachable under both, but anchors and lexical
        # bases live under `$id`.
        self._aliases: dict[str, str] = {}
        # External resources seen in reference values, drained by the
        # engine's load loop (P4).
        self._pending_resources: set[str] = set()
        # Scope-independent reference resolutions (D8), memoized per
        # (kind, base, ref); cleared whenever a registration could change one.
        self._reference_memo: dict[
            tuple[str, str, str], DynamicReference | RecursiveReference
        ] = {}
        # Identifiers claimed by the registration currently in progress
        # (P12). Scoped to one `_register`, because claiming a URI or an
        # anchor a *previous* registration claimed is a re-registration,
        # while claiming one twice in a single document is the duplicate.
        # An attribute rather than a `_walk` parameter is safe: a walk never
        # calls `_canonical` or `_register`, so registration is not
        # re-entrant.
        self._claimed_resources: set[str] = set()
        self._claimed_anchors: set[str] = set()
        # Called for every regex a keyword declares during a walk. The
        # engine installs this after its trusted metaschemas register, so
        # the D20 screen applies only to caller schemas.
        self.on_regex: RegexHook | None = None
        # A compiled artifact's snapshot refuses registration (M6).
        self._read_only = False

    def snapshot(self) -> "SchemaRegistry":
        """A frozen copy of this registry for a compiled artifact to bind (M6).

        Index copies are shallow (documents are shared, never mutated), so
        a `register` on the live registry after compilation cannot change
        what an artifact's islands resolve. The copy refuses `register`;
        lazy bundled metaschemas still register into the copy's own
        indexes, since that mutates nothing the live registry sees.
        """
        copy = SchemaRegistry(
            self._dialects.snapshot(),
            self._default_dialect_uri,
            max_depth=self._max_depth,
            bundled=self._bundled,
        )
        copy._documents = dict(self._documents)
        copy._anchors = dict(self._anchors)
        copy._dynamic_anchors = dict(self._dynamic_anchors)
        copy._recursive_roots = set(self._recursive_roots)
        copy._produced_ids = set(self._produced_ids)
        copy._consumed_ids = set(self._consumed_ids)
        copy._document_dialects = dict(self._document_dialects)
        copy._resource_locations = dict(self._resource_locations)
        copy._document_ranges = dict(self._document_ranges)
        copy._aliases = dict(self._aliases)
        copy._read_only = True
        return copy

    # --- registration ----------------------------------------------------

    def register(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None = None,
        get_range: RangeLookup | None = None,
    ) -> str:
        """Register a schema document and return its canonical base URI.

        The dialect comes from `$schema` when present (and must already be
        registered), else `dialect_uri`, else the registry default. Dialect
        URIs compare fragment-free: `…/draft-07/schema#` names the same
        dialect as the bare form.
        """
        if self._read_only:
            raise ReadOnlyRegistryError(
                "this schema registry is a compiled artifact's snapshot; "
                "register on the engine before compiling"
            )
        return self._register(schema, retrieval_uri, dialect_uri, get_range)

    def _claim_resource(self, base_uri: str, node: JsonValue, where: str) -> None:
        """Bind a resource URI to a schema, or refuse to shadow another (P12).

        `where` is the location to blame: the `$id`-bearing position for an
        embedded resource, the bare resource URI for a document root.

        The claimed-here check comes first because two *identical*
        subschemas claiming one `$id` are still two resources; only a
        re-registration of the same document may rebind, and then only to an
        equal schema.
        """
        if base_uri in self._claimed_resources:
            raise DuplicateResourceError(
                f"resource '{base_uri}' is claimed twice in one document",
                schema_location=where,
            )
        existing = self._documents.get(base_uri)
        if existing is not None and not json_equal(existing, node):
            raise DuplicateResourceError(
                f"resource '{base_uri}' is already registered as a different schema",
                schema_location=where,
            )
        self._claimed_resources.add(base_uri)
        self._documents[base_uri] = node

    def _claim_anchor(self, key: str, here: SchemaRef) -> None:
        """Bind an anchor key, or refuse to shadow another object's (P12).

        `here` is one `SchemaRef` per schema object, so an object carrying
        both `$anchor` and `$dynamicAnchor` under one name claims the same
        key with the same value and is allowed; two different objects are
        not. Keying on `_anchors`, which `$dynamicAnchor` also writes,
        catches a plain/dynamic collision across the two indexes (D8).
        """
        if key in self._claimed_anchors and self._anchors[key] is not here:
            raise DuplicateAnchorError(
                f"anchor '{key}' is claimed by two schemas in one resource",
                schema_location=here.location,
            )
        self._claimed_anchors.add(key)
        self._anchors[key] = here

    def _register(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None,
        get_range: RangeLookup | None,
    ) -> str:
        self._reference_memo.clear()
        self._claimed_resources.clear()
        self._claimed_anchors.clear()
        effective_dialect = effective_dialect_uri(
            schema, retrieval_uri, dialect_uri, self._default_dialect_uri
        )
        dialect = self._dialects.get_dialect(effective_dialect)

        retrieval_resource = _resource_of(retrieval_uri)
        base_uri = retrieval_resource
        root_ids = dialect.identifiers_of(schema)
        if root_ids.base_id is not None:
            base_uri = _resource_of(resolve(base_uri, root_ids.base_id))
        if base_uri != retrieval_resource:
            self._aliases[retrieval_resource] = base_uri
        # A resource-level error names the bare resource URI, as the other
        # document-scoped errors do (`SchemaValidationError`).
        self._claim_resource(base_uri, schema, base_uri)
        self._document_dialects[base_uri] = effective_dialect
        self._resource_locations[base_uri] = DocumentLocation(base_uri, "")
        if get_range is not None:
            self._document_ranges[base_uri] = get_range
        self._walk(schema, base_uri, "", base_uri, "", dialect, 0)
        return base_uri

    def _walk(
        self,
        node: JsonValue,
        base_uri: str,
        pointer: str,
        document_uri: str,
        doc_pointer: str,
        dialect: Dialect,
        depth: int,
    ) -> None:
        if depth > self._max_depth:
            raise MaxDepthExceededError(
                f"schema nesting exceeds max_depth ({self._max_depth})",
                schema_location=schema_location(base_uri, pointer),
            )
        if isinstance(node, bool):
            return
        if not is_object(node):
            raise InvalidSchemaError(
                f"non-schema value ({json_type_of(node).value}) in schema position",
                schema_location=schema_location(base_uri, pointer),
            )

        ids = dialect.identifiers(node)
        if pointer != "" and ids.base_id is not None:
            claimed_at = schema_location(base_uri, pointer)
            base_uri = _resource_of(resolve(base_uri, ids.base_id))
            pointer = ""
            self._claim_resource(base_uri, node, claimed_at)
            self._document_dialects[base_uri] = dialect.uri
            self._resource_locations[base_uri] = DocumentLocation(
                document_uri, doc_pointer
            )
        here = SchemaRef(node, base_uri, pointer)
        for anchor in ids.anchors:
            self._claim_anchor(f"{base_uri}#{anchor}", here)
        # A dynamic anchor is also a plain anchor for `$ref`; only the
        # dynamic index takes part in `$dynamicRef` rebinding (D8).
        if ids.dynamic_anchor is not None:
            key = f"{base_uri}#{ids.dynamic_anchor}"
            self._claim_anchor(key, here)
            self._dynamic_anchors[key] = here
        if ids.recursive_anchor and pointer == "":
            self._recursive_roots.add(base_uri)

        # draft-07/06 (D18, owner ruling): a `$ref` makes every sibling act
        # as if absent — at registration as much as at evaluation, so no
        # identifier, subschema, or pattern inside a sibling is ever seen.
        # Pointer references into a sibling still resolve, since pointer
        # navigation reads the document rather than this index.
        ref_only = dialect.ref_ignores_siblings and "$ref" in node
        for name, value in node.items():
            if ref_only and name != "$ref":
                continue
            entry = dialect.keywords.get(name)
            if entry is None:
                continue
            try:
                facts = entry.behavior.facts(value, node)
            except JsonSchemaEngineError as error:
                # `analyze()` has no location of its own (an unknown or
                # unavailable format, M7): attach the keyword's.
                if error.schema_location is None:
                    error.schema_location = schema_location(
                        base_uri, f"{pointer}/{escape_segment(name)}"
                    )
                raise
            self._produced_ids.update(facts.produces)
            self._consumed_ids.update(facts.consumes)
            if self.on_regex is not None and facts.regexes:
                keyword_location = schema_location(
                    base_uri, f"{pointer}/{escape_segment(name)}"
                )
                for regex in facts.regexes:
                    self.on_regex(regex, keyword_location)
            for reference in facts.references:
                # Unresolvable now is not an error: evaluation reports it if
                # the reference is actually followed.
                with suppress(ValueError):
                    self._pending_resources.add(
                        _resource_of(resolve(base_uri, reference))
                    )
            for rel_path in facts.subschemas:
                child: JsonValue = value
                suffix = "/" + escape_segment(name)
                for segment in rel_path:
                    child = _step(child, segment)
                    suffix += "/" + escape_segment(str(segment))
                self._walk(
                    child,
                    base_uri,
                    pointer + suffix,
                    document_uri,
                    doc_pointer + suffix,
                    dialect,
                    depth + 1,
                )

    # --- lookups ---------------------------------------------------------

    def _canonical(self, resource_uri: str) -> str:
        if (
            resource_uri not in self._documents
            and resource_uri not in self._aliases
            and resource_uri in self._bundled
        ):
            self._register_bundled(resource_uri)
        return self._aliases.get(resource_uri, resource_uri)

    def _register_bundled(self, resource_uri: str) -> None:
        # The D20 screen is for caller schemas; a trusted resource's own
        # patterns are not its business, so the hook is off for the walk.
        hook, self.on_regex = self.on_regex, None
        try:
            self._register(self._bundled[resource_uri], resource_uri, None, None)
        finally:
            self.on_regex = hook

    def is_bundled(self, resource_uri: str) -> bool:
        return resource_uri in self._bundled

    def has(self, resource_uri: str) -> bool:
        """True if a resource is registered, aliased, or bundled."""
        return (
            resource_uri in self._documents
            or resource_uri in self._aliases
            or resource_uri in self._bundled
        )

    def document(self, resource_uri: str) -> JsonValue | None:
        """The schema node at a resource's root, if registered."""
        return self._documents.get(self._canonical(resource_uri))

    def document_location(self, resource_uri: str) -> DocumentLocation | None:
        return self._resource_locations.get(self._canonical(resource_uri))

    def range(self, document_uri: str, pointer: str) -> SourceRange | None:
        """The source range of a document-rooted pointer, if its loader knows."""
        lookup = self._document_ranges.get(document_uri)
        return None if lookup is None else lookup(pointer)

    def take_unresolved(self) -> list[str]:
        """External resources referenced but not registered; drained per call."""
        missing = sorted(r for r in self._pending_resources if not self.has(r))
        self._pending_resources.clear()
        return missing

    def dynamic_anchor(self, resource_uri: str, name: str) -> SchemaRef | None:
        """The `$dynamicAnchor` target for a name in a resource (D8)."""
        return self._dynamic_anchors.get(f"{self._canonical(resource_uri)}#{name}")

    def has_recursive_root(self, resource_uri: str) -> bool:
        return self._canonical(resource_uri) in self._recursive_roots

    def dynamic_reference(self, ref: str, current_base: str) -> DynamicReference:
        """The scope-independent half of `$dynamicRef` resolution (D8).

        The lexical target must exist (`UnresolvableReferenceError`
        otherwise). `anchor` is the `$dynamicAnchor` name the reference
        rebinds through, or `None` when the reference behaves exactly like
        `$ref`: an empty or pointer fragment, or a lexical resource that
        does not mint the anchor (the bookending rule). Shared by the
        interpreter's scope walk and the planner's plan-time analysis so
        the two tiers cannot drift.
        """
        key = ("dynamic", current_base, ref)
        hit = self._reference_memo.get(key)
        if hit is not None:
            assert isinstance(hit, DynamicReference)
            return hit
        lexical = self.resolve_ref(ref, current_base)
        resource, fragment = split_fragment(resolve(current_base, ref))
        anchor: str | None = None
        if (
            fragment
            and not fragment.startswith("/")
            and self.dynamic_anchor(resource, fragment) is not None
        ):
            anchor = fragment
        result = DynamicReference(lexical, anchor)
        self._reference_memo[key] = result
        return result

    def recursive_reference(self, ref: str, current_base: str) -> RecursiveReference:
        """The scope-independent half of `$recursiveRef` resolution (D8):
        rebinding applies only to a fragment-free reference whose lexical
        resource has `$recursiveAnchor: true` at its root."""
        key = ("recursive", current_base, ref)
        hit = self._reference_memo.get(key)
        if hit is not None:
            assert isinstance(hit, RecursiveReference)
            return hit
        lexical = self.resolve_ref(ref, current_base)
        resource, fragment = split_fragment(resolve(current_base, ref))
        result = RecursiveReference(
            lexical, not fragment and self.has_recursive_root(resource)
        )
        self._reference_memo[key] = result
        return result

    def produced_ids(self) -> frozenset[str]:
        """Behavior ids some registered keyword declares it produces under."""
        return frozenset(self._produced_ids)

    def consumed_ids(self) -> frozenset[str]:
        """Behavior ids some registered keyword declares it consumes."""
        return frozenset(self._consumed_ids)

    def is_produced(self, behavior_id: str) -> bool:
        return behavior_id in self._produced_ids

    def is_consumed(self, behavior_id: str) -> bool:
        return behavior_id in self._consumed_ids

    def dialect_uri_for(self, base_uri: str) -> str:
        """The dialect URI a resource was registered under."""
        uri = self._document_dialects.get(self._canonical(base_uri))
        if uri is None:
            raise UnresolvableReferenceError(f"unknown schema '{base_uri}'")
        return uri

    def dialect_for(self, base_uri: str) -> Dialect:
        """The dialect a resource was registered under."""
        return self._dialects.get_dialect(self.dialect_uri_for(base_uri))

    def resources(self) -> Iterator[str]:
        """Every registered resource URI, in registration order."""
        return iter(self._documents)

    # --- resolution ------------------------------------------------------

    def root_ref(self, uri: str) -> SchemaRef:
        """Resolve a URI to a schema position; fragment-free means the root."""
        resource, fragment = _split(uri)
        if fragment:
            return self.resolve_ref(uri, self._canonical(resource))
        resource = self._canonical(resource)
        node = self._documents.get(resource)
        if node is None:
            raise UnresolvableReferenceError(
                f"unknown schema '{resource}'", reference=uri, resolved_to=resource
            )
        return SchemaRef(node, resource, "")

    def resolve_ref(self, ref: str, current_base: str) -> SchemaRef:
        """Resolve a reference value against the referring schema's base.

        Raises `UnresolvableReferenceError` when the resource, anchor, or
        pointer target does not exist.
        """
        resolved = resolve(current_base, ref)
        resource, fragment = _split(resolved)
        resource = self._canonical(resource)
        # Every exit below reports the attempt, not just the miss: when a
        # reference resolves against an embedded `$id`, the URI that failed
        # can look unrelated to anything the author wrote.
        attempt: dict[str, str] = {
            "reference": ref,
            "resolved_against": current_base,
            "resolved_to": resolved,
        }

        if fragment and not fragment.startswith("/"):
            hit = self._anchors.get(f"{resource}#{fragment}")
            if hit is None:
                raise UnresolvableReferenceError(
                    f"unknown anchor '{resource}#{fragment}'", **attempt
                )
            return hit

        root = self._documents.get(resource)
        if root is None:
            raise UnresolvableReferenceError(f"unknown schema '{resource}'", **attempt)
        if not fragment:
            return SchemaRef(root, resource, "")

        # JSON Pointer navigation, tracking identifier-induced base changes
        # on the way, per the target document's dialect (D18).
        identifiers = self.dialect_for(resource).identifiers
        node: JsonValue = root
        base_uri = resource
        pointer = ""
        # The document-rooted prefix matched so far, for the error below.
        # `pointer` cannot serve: it resets at every embedded `$id`.
        walked = ""
        for raw_segment in fragment[1:].split("/"):
            segment = unescape_segment(raw_segment)
            try:
                node = _step(node, segment)
            except (KeyError, IndexError, ValueError, TypeError):
                # Which step failed, and what it was standing on. Without
                # them `#/a/b/c/d` failing at `b` reads exactly like the
                # same pointer failing at `d`.
                matched = walked or "the root"
                raise UnresolvableReferenceError(
                    f"pointer '{fragment}' not found in '{resource}': "
                    f"no {segment!r} at {matched} "
                    f"({json_type_of(node).value})",
                    **attempt,
                ) from None
            pointer += "/" + escape_segment(segment)
            walked += "/" + escape_segment(segment)
            if is_object(node):
                base_id = identifiers(node).base_id
                if base_id is not None:
                    base_uri = _resource_of(resolve(base_uri, base_id))
                    pointer = ""
        return SchemaRef(node, base_uri, pointer)

    def child(self, ref: SchemaRef, segments: Sequence[str | int]) -> SchemaRef:
        """Descend from a schema position into keyword or index children.

        Maintains the canonical location and the lexical base, so a child
        that declares `$id` starts a new resource with an empty pointer.
        """
        identifiers = self.dialect_for(ref.base_uri).identifiers
        node = ref.node
        base_uri = ref.base_uri
        pointer = ref.pointer
        for segment in segments:
            node = _step(node, segment)
            pointer += "/" + escape_segment(str(segment))
            if is_object(node):
                base_id = identifiers(node).base_id
                if base_id is not None:
                    base_uri = _resource_of(resolve(base_uri, base_id))
                    pointer = ""
        return SchemaRef(node, base_uri, pointer)


def _step(node: JsonValue, segment: str | int) -> JsonValue:
    """One JSON Pointer step. Raises the container's natural error on a miss."""
    if isinstance(node, list):
        index = int(segment) if isinstance(segment, str) else segment
        if index < 0:
            raise IndexError(segment)
        return node[index]
    if isinstance(node, dict):
        return node[str(segment)]
    raise TypeError(f"cannot step into {json_type_of(node).value}")
