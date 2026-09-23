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

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from typing import Any, Final

from json_schema_engine.core.dialect import Dialect, DialectRegistry, IdentifierFacts
from json_schema_engine.core.errors import (
    DuplicateAnchorError,
    DuplicateResourceError,
    InvalidIdentifierError,
    InvalidSchemaError,
    JsonSchemaEngineError,
    MaxDepthExceededError,
    ReadOnlyRegistryError,
    UnknownDialectError,
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
from json_schema_engine.core.loader import RangeLookup, SourceLocation, SourceRange
from json_schema_engine.core.locations import LocationChain, LocationHop
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


_MISSING: Final = object()


@dataclass(slots=True)
class _Registration:
    """The undo journal for one registration (DESIGN.md §7).

    Registration is all-or-nothing. A walk that raised part-way used to
    leave the document registered and evaluable, missing every anchor and
    sub-resource past the failure point, with partial contributions to
    `_produced_ids`/`_consumed_ids` — which feed D5's elision predicate,
    so the failure surfaced as a wrong answer rather than a loud one.

    Journaled writes rather than a snapshot of the indexes, so the cost is
    O(this document's writes) with no term in registry size: every lookup
    may lazily register a bundled metaschema, and an O(registry) copy would
    tax that path exactly as it grows.

    `writes` holds `(index, key, prior)` for the dict indexes, with
    `_MISSING` for a key that was absent. Restoring the prior value rather
    than deleting the key is load-bearing twice over: a re-registration
    rebinds entries an *earlier* registration owns (`_claim_resource`
    allows an equal document, `_claim_anchor` only rejects collisions
    inside the current walk), and `_documents` is ordered, which
    `resources()` promises and delete-then-reinsert would break.

    `adds` holds `(index, member)` for the set indexes, recorded only when
    the member was new — a union cannot say who added what.
    """

    writes: list[tuple[dict[str, Any], str, Any]] = field(
        default_factory=list[tuple[dict[str, Any], str, Any]]
    )
    adds: list[tuple[set[str], str]] = field(default_factory=list[tuple[set[str], str]])

    def undo(self) -> None:
        """Put every index back the way this registration found it."""
        # Reverse order: one key can be written twice in a walk (an object
        # carrying `$anchor` and `$dynamicAnchor` under one name), and only
        # the first record holds the value from before this registration.
        #
        # `pop`/`discard` rather than `del`/`remove`: this runs with an
        # exception already in flight, and raising a second one here would
        # replace the failure being reported.
        for index, key, prior in reversed(self.writes):
            if prior is _MISSING:
                index.pop(key, None)
            else:
                index[key] = prior
        for members, member in self.adds:
            members.discard(member)


@dataclass(frozen=True, slots=True)
class RootIdentity:
    """What a document would register as, worked out without registering it.

    `identify` returns this so a caller that must act *before* the walk —
    `validate_schemas`, which refuses to register a document that fails its
    metaschema — can name the same resource and dialect the registration
    would have named, rather than guessing from the retrieval URI.
    """

    base_uri: str
    dialect_uri: str
    dialect: Dialect
    root_ids: IdentifierFacts
    retrieval_resource: str


@dataclass(frozen=True, slots=True)
class DocumentLocation:
    """Where a schema resource lives: its document, and its parent resource.

    `(document_uri, pointer)` is the flat D17 bridge — the outermost
    registered document and the pointer from that document's root. It is
    what a source-range lookup needs, and all `Engine.locate` reads.

    `(parent_uri, parent_pointer)` is the single `$id` hop a P11 location
    chain follows: the resource lexically enclosing this one, and the
    pointer to this resource's root *within that parent* rather than within
    the document. A root resource is its own parent with an empty pointer,
    which is how a chain knows it has finished.

    Carrying the parent here rather than in a second map is what keeps
    `snapshot()` correct for free: it already copies this one, and a
    snapshot can still grow resources afterwards through lazy bundled
    registration.
    """

    document_uri: str
    pointer: str
    parent_uri: str
    parent_pointer: str
    # The `$id` exactly as written at this resource's root, when it has
    # one. A relative `$id` resolves to a URI that appears nowhere in the
    # document, so this is the only way back to the text.
    declared_id: str | None = None


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
        # The undo journal of the registration in progress, or `None` when
        # none is. Doubles as the "a registration is in flight" flag that
        # `_canonical` reads before starting a lazy bundled one.
        self._journal: _Registration | None = None
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

    def _put[V](self, index: dict[str, V], key: str, value: V) -> None:
        """Write an index entry, journaled so it can be undone (§7).

        The journal is handed the index object itself rather than a name
        for it, so `_Registration.undo` needs no table mapping names back
        to attributes: the writer already holds the one it means.
        """
        if self._journal is not None:
            self._journal.writes.append((index, key, index.get(key, _MISSING)))
        index[key] = value

    def _add(self, index: set[str], member: str) -> None:
        """Add a set member, journaled when it is genuinely new.

        Recording only new members is what makes `_produced_ids` and
        `_consumed_ids` undoable: they are unions, so the key alone cannot
        say whether this registration put it there.
        """
        if member not in index:
            if self._journal is not None:
                self._journal.adds.append((index, member))
            index.add(member)

    def _resource_dialect(
        self,
        node: Mapping[str, JsonValue],
        base_uri: str,
        inherited: Dialect,
        where: str,
    ) -> Dialect:
        """The dialect governing a resource rooted at `node` (P14).

        `$schema` is permitted at the root of *any* schema resource
        (2020-12 core §8.1.1), so an embedded `$id` resource that declares
        one is governed by it rather than by its document's. Honored under
        every dialect: draft-07/06 predate the formal notion of a schema
        resource and say only that `$schema` SHOULD be at the document
        root, which is silence rather than prohibition.

        Resolved against this resource's own base — the base in force where
        `$schema` is written, and the embedded analogue of
        `effective_dialect_uri` resolving against the retrieval URI. The
        root cannot do the same: there the dialect must be known before the
        identifiers can be read, so the `$id`-derived base does not exist
        yet.
        """
        declared = node.get("$schema")
        if not isinstance(declared, str):
            return inherited
        uri = _resource_of(resolve(base_uri, declared))
        if uri == inherited.uri:
            # The common embedded `$schema`: the dialect already in force,
            # spelled out. No lookup, no rebind.
            return inherited
        if not self._dialects.has_dialect(uri):
            # Carrying the URI, because the engine can often assemble this
            # dialect from a metaschema and register again; the registry
            # holds no loaders and genuinely cannot.
            raise UnknownDialectError(
                f"embedded schema resource '{base_uri}' declares unknown "
                f"dialect '{uri}'",
                schema_location=where,
                dialect_uri=uri,
            )
        return self._dialects.get_dialect(uri)

    def _dialect_after(self, base_uri: str, current: Dialect) -> Dialect:
        """The dialect of a base that navigation has just entered (P14).

        Falls back to the dialect already in force when registration never
        indexed that base. Pointer navigation deliberately ignores
        `ref_ignores_siblings` (D18), so it can reach a lexical base the
        walk never minted; the enclosing dialect is the one that base
        *would* have been walked under, so the fallback is both right and
        non-raising.

        A plain dict read rather than `dialect_for`, on purpose: that would
        raise for an unindexed base — this exists so a mixed-dialect fix
        cannot start raising where nothing raised before — and its
        `_canonical` would try to register a bundled metaschema in the
        middle of a navigation. Aliases cannot apply: a base minted
        lexically from `$id` is already the canonical form the walk keyed
        `_document_dialects` by.
        """
        uri = self._document_dialects.get(base_uri)
        return current if uri is None else self._dialects.get_dialect(uri)

    def _check_embedded_id(self, base_id: str, dialect: Dialect, where: str) -> None:
        """Refuse an embedded `$id` that cannot name a new resource.

        Reached only when the dialect's extractor handed this string back as
        a *base URI*: `identifiers_legacy` turns `#name` into an anchor and
        never arrives here, which is exactly the per-dialect distinction
        that makes both of these errors, and neither of them draft-07's
        problem.

        Checked against the text the author wrote, before `resolve` — both
        cases otherwise land back on the enclosing resource's own URI and
        surface as a duplicate of an `$id` that does not exist.
        """
        if base_id in ("", "#"):
            raise InvalidIdentifierError(
                f"'$id': {base_id!r} resolves to the enclosing resource and "
                "identifies nothing new",
                schema_location=where,
            )
        if split_fragment(base_id)[1]:
            raise InvalidIdentifierError(
                f"'$id': {base_id!r} has a non-empty fragment; under dialect "
                f"'{dialect.uri}' an '$id' sets a base URI, and a base URI "
                "cannot carry one (the plain-name form is '$anchor' here)",
                schema_location=where,
            )

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
        self._put(self._documents, base_uri, node)

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
        self._put(self._anchors, key, here)

    def _register(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None,
        get_range: RangeLookup | None,
    ) -> str:
        """Index a document, all of it or none of it (§7, `_Registration`)."""
        # Saving the caller's journal and claim sets rather than asserting
        # they are empty is the re-entrancy guard. A walk never calls back
        # in here, but a custom `KeywordBehavior.analyze` or a custom
        # dialect's identifier extractor is arbitrary caller code, and one
        # that registers a schema must become its own transaction rather
        # than clobbering this one's.
        outer = (self._journal, self._claimed_resources, self._claimed_anchors)
        journal = self._journal = _Registration()
        self._claimed_resources = set()
        self._claimed_anchors = set()
        try:
            return self._index(schema, retrieval_uri, dialect_uri, get_range)
        except BaseException as error:
            # `BaseException`, because a walk can raise far more than a
            # typed engine error: `_step` raises bare `KeyError`/`TypeError`,
            # `RecursionError` can fire anywhere, and caller code runs
            # inside the walk. A half-indexed document is equally wrong
            # whichever of them got us here, and the bare `raise` below
            # means nothing is swallowed.
            try:
                # The only moment the chain and the source position can be
                # read: they are derived from indexes the undo is about to
                # remove. In a `try`, so a bug in the description cannot
                # cost the rollback.
                if isinstance(error, JsonSchemaEngineError):
                    self._describe(error)
            finally:
                journal.undo()
            raise
        finally:
            self._journal, self._claimed_resources, self._claimed_anchors = outer
            # Un-clearing is impossible and unnecessary: the memo is a pure
            # derived cache (D8), so "cleared, rebuilt on demand" is always
            # a correct state. Cleared on both paths, because caller code
            # inside the walk can memoize an answer computed against the
            # half-built index that the rollback then takes away.
            self._reference_memo.clear()

    def identify(
        self, schema: JsonValue, retrieval_uri: str, dialect_uri: str | None
    ) -> RootIdentity:
        """Resolve a document's canonical base URI and dialect, registering
        nothing. Raises `UnknownDialectError` for an unregistered dialect,
        exactly as registering it would."""
        effective = effective_dialect_uri(
            schema, retrieval_uri, dialect_uri, self._default_dialect_uri
        )
        dialect = self._dialects.get_dialect(effective)
        retrieval_resource = _resource_of(retrieval_uri)
        root_ids = dialect.identifiers_of(schema)
        base_uri = retrieval_resource
        if root_ids.base_id is not None:
            base_uri = _resource_of(resolve(base_uri, root_ids.base_id))
        return RootIdentity(base_uri, effective, dialect, root_ids, retrieval_resource)

    def _index(
        self,
        schema: JsonValue,
        retrieval_uri: str,
        dialect_uri: str | None,
        get_range: RangeLookup | None,
    ) -> str:
        identity = self.identify(schema, retrieval_uri, dialect_uri)
        effective_dialect = identity.dialect_uri
        dialect = identity.dialect
        root_ids = identity.root_ids
        retrieval_resource = identity.retrieval_resource
        base_uri = identity.base_uri
        if base_uri != retrieval_resource:
            # Journaled like the rest: this runs *before* the claim below,
            # so a duplicate root used to leave an alias behind.
            self._put(self._aliases, retrieval_resource, base_uri)
        # A resource-level error names the bare resource URI, as the other
        # document-scoped errors do (`SchemaValidationError`).
        self._claim_resource(base_uri, schema, base_uri)
        self._put(self._document_dialects, base_uri, effective_dialect)
        # A root is its own parent: the terminating case for a chain.
        self._put(
            self._resource_locations,
            base_uri,
            DocumentLocation(base_uri, "", base_uri, "", root_ids.base_id),
        )
        if get_range is not None:
            self._put(self._document_ranges, base_uri, get_range)
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
            self._check_embedded_id(ids.base_id, dialect, claimed_at)
            # The enclosing resource and the pointer to this one within it,
            # captured before the rebinding discards both (P11).
            parent_uri, parent_pointer = base_uri, pointer
            base_uri = _resource_of(resolve(base_uri, ids.base_id))
            pointer = ""
            # `$schema` governs the resource it roots, not the document
            # (P14). Everything below this line — the identifiers minted
            # *into* this resource, `ref_only`, the keyword table, and the
            # recursion — is the inner dialect's.
            dialect = self._resource_dialect(node, base_uri, dialect, claimed_at)
            # The boundary was the parent's call: its `$id` syntax decided a
            # resource starts here at all, and a relative `$schema` has no
            # base to resolve against until it has. What is minted *into*
            # the resource is the new dialect's, so the identifiers are read
            # again — the inner extractor's own `base_id` is never used.
            ids = replace(dialect.identifiers(node), base_id=ids.base_id)
            self._claim_resource(base_uri, node, claimed_at)
            self._put(self._document_dialects, base_uri, dialect.uri)
            self._put(
                self._resource_locations,
                base_uri,
                DocumentLocation(
                    document_uri, doc_pointer, parent_uri, parent_pointer, ids.base_id
                ),
            )
        # A `$schema` where no resource starts is ignored, not refused.
        # The spec forbids the placement, but refusing it is strict-mode
        # hygiene, which D14 keeps opt-in — and it is load-bearing in the
        # wild: `{"$schema": X, "not": {"$schema": X}}` is how Bowtie spells
        # "allows nothing" for every dialect it tests.
        here = SchemaRef(node, base_uri, pointer)
        for anchor in ids.anchors:
            self._claim_anchor(f"{base_uri}#{anchor}", here)
        # A dynamic anchor is also a plain anchor for `$ref`; only the
        # dynamic index takes part in `$dynamicRef` rebinding (D8).
        if ids.dynamic_anchor is not None:
            key = f"{base_uri}#{ids.dynamic_anchor}"
            self._claim_anchor(key, here)
            self._put(self._dynamic_anchors, key, here)
        if ids.recursive_anchor and pointer == "":
            self._add(self._recursive_roots, base_uri)

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
            for behavior_id in facts.produces:
                self._add(self._produced_ids, behavior_id)
            for behavior_id in facts.consumes:
                self._add(self._consumed_ids, behavior_id)
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
                    self._add(
                        self._pending_resources,
                        _resource_of(resolve(base_uri, reference)),
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
            # A lookup made while a registration is in flight — the
            # diagnostic capture on its way out, or caller code inside a
            # walk — must not start a second one: it would write indexes
            # the rollback about to run knows nothing about. Tested last,
            # so an already-registered resource never reaches it.
            and self._journal is None
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

    def source_of(self, location: str) -> SourceLocation | None:
        """Where a schema location sits in its document (D17).

        The containing document, the document-rooted pointer, and the
        source range when that document's loader reported positions.
        `None` for a resource this registry has no location for.
        `Engine.locate` is this method; it lives here because the registry
        owns all three pieces, and because a failing registration has to
        capture one before its rollback takes the indexes away.
        """
        position = self.position_of(location)
        if position is None:
            return None
        resource, within = position
        entry = self.document_location(resource)
        if entry is None:
            return None
        pointer = entry.pointer + within
        source: SourceLocation = {
            "documentUri": entry.document_uri,
            "pointer": pointer,
        }
        found = self.range(entry.document_uri, pointer)
        if found is not None:
            source["range"] = found
        return source

    def _describe(self, error: JsonSchemaEngineError) -> None:
        """Record what the indexes know about a failure, before the undo.

        A rolled-back registration's resources are gone by the time the
        error reaches a caller, so this is the only moment its chain (P11)
        and its source position (D17) can be derived. Each is filled only
        when still empty: an inner frame's answer is the more specific one.
        """
        location = error.schema_location
        if location is None:
            return
        if error.location_chain is None:
            chain = self.location_chain(location)
            if chain:
                error.location_chain = chain
        if error.schema_source is None:
            error.schema_source = self.source_of(location)

    def take_unresolved(self) -> list[str]:
        """External resources referenced but not registered; drained per call."""
        missing = sorted(r for r in self._pending_resources if not self.has(r))
        self._pending_resources.clear()
        return missing

    def restore_unresolved(self, uris: Iterable[str]) -> None:
        """Put drained resources back on the pending list.

        `take_unresolved` empties the set before its caller has fetched
        anything, so a fetch that raises would otherwise drop every URI the
        loop had not reached yet — permanently, since a later drain has no
        record of them. The engine hands back what it did not get to.
        """
        self._pending_resources.update(uris)

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

    def location_chain(self, location: str) -> LocationChain:
        """The chain of enclosing `$id` resources for a schema location (P11).

        Innermost first: the position, then each resource that lexically
        contains the previous one, ending at a root. A position in a plain
        single-resource document gives one hop, so the common case costs a
        tuple and says nothing a reader did not already have.

        Empty when the location's resource is unknown here — including a
        lexical base that pointer navigation minted but registration never
        indexed, which a draft-07 `$ref` sibling can produce. "No chain"
        and "a chain of one" must not be confused: the latter asserts that
        the position sits in a root resource, and saying that falsely is
        the very thing this exists to stop.

        Diagnostic only; nothing on the evaluation path calls it. Like any
        other lookup it may lazily register a bundled metaschema.
        """
        position = self.position_of(location)
        if position is None:
            return ()
        resource, pointer = position
        if resource not in self._resource_locations:
            return ()

        hops = [LocationHop(resource, pointer, self._declared_id(resource))]
        seen = {resource}
        current = resource
        while (entry := self._resource_locations.get(current)) is not None:
            # A root is its own parent. The `seen` test is defense in
            # depth: P12 rejects the duplicate `$id` that could once make
            # this relation cyclic, so a repeat should now be unreachable.
            if entry.parent_uri == current or entry.parent_uri in seen:
                break
            hops.append(
                LocationHop(
                    entry.parent_uri,
                    entry.parent_pointer,
                    self._declared_id(entry.parent_uri),
                )
            )
            seen.add(entry.parent_uri)
            current = entry.parent_uri
        hops[-1] = replace(hops[-1], retrieval_uri=self._retrieval_uri(hops[-1]))
        return tuple(hops)

    def position_of(self, location: str) -> tuple[str, str] | None:
        """Split a schema location into its resource and plain-text pointer.

        An anchor-shaped fragment is resolved through the anchor index, so
        `urn:x#spot` answers the same position as the pointer that names
        the same node — an anchor is a fragment, not a pointer, and
        percent-decoding one yields a string with no leading `/` that no
        pointer walk could use.

        `None` when an anchor names nothing. An unknown *resource* is not
        this method's business: the caller knows whether it wants one.
        """
        resource, fragment = _split(location)
        resource = self._canonical(resource)
        if fragment and not fragment.startswith("/"):
            hit = self._anchors.get(f"{resource}#{fragment}")
            if hit is None:
                return None
            return hit.base_uri, hit.pointer
        return resource, fragment or ""

    def _declared_id(self, resource_uri: str) -> str | None:
        entry = self._resource_locations.get(resource_uri)
        return None if entry is None else entry.declared_id

    def _retrieval_uri(self, outermost: LocationHop) -> str | None:
        """The name the outermost resource was fetched under, when it
        differs from the `$id` it declares — the one hop a reader can
        match against what they actually passed to `register_schema`."""
        for retrieval, canonical in self._aliases.items():
            if canonical == outermost.resource_uri:
                return retrieval
        return None

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
        dialect = self.dialect_for(resource)
        identifiers = dialect.identifiers
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
                # The enclosing dialect's syntax decides whether this `$id`
                # starts a resource, exactly as in the walk; the resource it
                # starts governs every step after it (P14).
                base_id = identifiers(node).base_id
                if base_id is not None:
                    base_uri = _resource_of(resolve(base_uri, base_id))
                    pointer = ""
                    dialect = self._dialect_after(base_uri, dialect)
                    identifiers = dialect.identifiers
        return SchemaRef(node, base_uri, pointer)

    def child(self, ref: SchemaRef, segments: Sequence[str | int]) -> SchemaRef:
        """Descend from a schema position into keyword or index children.

        Maintains the canonical location and the lexical base, so a child
        that declares `$id` starts a new resource with an empty pointer.
        """
        dialect = self.dialect_for(ref.base_uri)
        identifiers = dialect.identifiers
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
                    dialect = self._dialect_after(base_uri, dialect)
                    identifiers = dialect.identifiers
        return SchemaRef(node, base_uri, pointer)


def attach_location_chain(
    registry: SchemaRegistry, error: JsonSchemaEngineError
) -> None:
    """Fill in an error's `location_chain` as it leaves the engine (P11).

    Only a registry can build a chain, and no raise site has one — the
    evaluator, the regex screen and a keyword's `analyze()` all hold a
    location and nothing else. Doing it here instead of threading a
    registry into all of them also fixes the chain at the moment of
    failure, rather than whenever someone later thinks to ask.

    A no-op without a location, or when an inner frame already attached
    one, so nesting these is harmless: `load_schema` and `_fetch` route
    through `register_schema`, and `_maybe_validate` through `evaluate`.

    A free function beside the registry rather than in the engine because
    the compiled tier needs it too — the evaluator artifact's entry and the
    flag tier's interpreter trampolines — and that runtime depends on the
    registry, not the engine.
    """
    if error.location_chain is not None or error.schema_location is None:
        return
    chain = registry.location_chain(error.schema_location)
    if chain:
        error.location_chain = chain


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
