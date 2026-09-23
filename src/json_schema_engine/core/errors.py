# Every typed error the engine raises (DESIGN.md §2, module table).
#
# Dependency direction: all but a leaf of `core`. It imports `locations`
# (which imports only `uri`) and `loader` (which imports only `json_model`);
# none of them imports this module, so any module may still raise these
# without creating a cycle.
#
# One root (`JsonSchemaEngineError`) lets an embedding application catch
# everything this library raises with a single `except` clause, and lets it
# distinguish engine faults from bugs (`TypeError`, `KeyError`) that must not
# be swallowed.

from json_schema_engine.core.loader import SourceLocation
from json_schema_engine.core.locations import LocationChain, format_location_chain


class JsonSchemaEngineError(Exception):
    """Root of every error raised by the engine.

    `schema_location` is the canonical `base_uri#pointer` of the schema
    position that provoked the error, when one applies. It lives on the root
    so that any error can gain a location without a class change; errors that
    are not about a schema position (`OutputOptionsError`) simply leave it
    `None`.

    `location_chain` is that position's enclosing `$id` resources (P11),
    which only a registry can work out — so unlike `schema_location` it is
    never passed at construction. The engine fills it in as the error
    leaves a public entry point, which also freezes it at the moment of
    failure rather than at the moment someone asks.

    `schema_source` is the same position seen physically (D17): the
    document it lives in, the pointer from that document's root, and the
    source range when a loader reported one. It is captured rather than
    looked up because a failed registration is rolled back (§7), so by the
    time the error surfaces there is no longer a registered document for
    `Engine.locate` to find.

    `str()` appends the chain only when it has more than one hop. A chain
    of one says nothing the location did not, so a single-resource
    document's message is exactly what it always was.
    """

    schema_location: str | None
    location_chain: LocationChain | None
    schema_source: SourceLocation | None

    def __init__(self, message: str, *, schema_location: str | None = None) -> None:
        super().__init__(message)
        self.schema_location = schema_location
        self.location_chain = None
        self.schema_source = None

    def __str__(self) -> str:
        message = super().__str__()
        chain = self.location_chain
        if chain is None or len(chain) <= 1:
            return message
        return format_location_chain(chain, message=message)


class JsonSyntaxError(JsonSchemaEngineError, ValueError):
    """`parse_json_with_ranges` met text that is not an RFC 8259 document.

    Carries the 1-based `line` and `column` and the 0-based `offset` of
    the first offending character. Also a `ValueError`, so callers that
    treat any bad input alike need no engine-specific clause.
    """

    line: int
    column: int
    offset: int

    def __init__(self, message: str, *, line: int, column: int, offset: int) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.offset = offset


class InvalidSchemaError(JsonSchemaEngineError):
    """A keyword-claimed schema position holds neither an object nor a boolean.

    Raised by the registration walk and, as a lazy backstop, by schema
    application (D19): failing loud beats silently treating a string or a
    number as an empty schema that accepts everything.
    """


class InvalidIdentifierError(JsonSchemaEngineError):
    """An `$id` cannot identify the resource it claims to start.

    Two syntactic refusals, both about the string the author wrote rather
    than the URI it would resolve to:

    * a non-empty fragment — `$id` sets a base URI under this dialect, and
      a base URI cannot carry one. The plain-name form is `$anchor`.
    * `""` or `"#"` — resolves to the enclosing resource and identifies
      nothing new.

    Per dialect, which is the point: draft-07/06 read `#name` as an anchor
    and never reach the first rule, so the same document is legal there and
    refused under 2019-09/2020-12. Both cases used to fall through to
    `resolve`, land back on the enclosing resource's own URI, and surface
    as `DuplicateResourceError` — a true sentence about a URI the author
    never wrote, blaming a second `$id` that does not exist.
    """


class DuplicateResourceError(JsonSchemaEngineError):
    """Two different schemas claim the same resource URI (P12).

    Either one document mints an `$id` twice, or a later registration would
    rebind a URI an earlier one already bound to a different schema. The
    spec is silent here, but two resources cannot share an identity: one
    would silently shadow the other, and a `$ref` to that URI would resolve
    to whichever the walk reached last.

    Re-registering an equal document is not a duplicate; it is a no-op.
    """


class DuplicateAnchorError(JsonSchemaEngineError):
    """Two different schema objects claim the same anchor in one resource.

    Covers `$anchor`, `$dynamicAnchor`, and the draft-07/06 `$id: "#name"`
    form alike, including one name claimed by an `$anchor` on one object and
    a `$dynamicAnchor` on another: because a dynamic anchor is also a plain
    anchor (D8), that case leaves `$ref` and `$dynamicRef` resolving the
    same fragment to *different* schemas.

    The spec calls a duplicate anchor undefined behavior and permits an
    implementation to reject it, which is what this engine does. One object
    carrying both `$anchor` and `$dynamicAnchor` with the same name names
    itself twice and is fine.
    """


class ReadOnlyRegistryError(JsonSchemaEngineError):
    """Registration attempted on a compiled artifact's registry snapshot."""


class UnknownDialectError(JsonSchemaEngineError):
    """A schema names a `$schema` dialect URI that no registered dialect claims.

    `dialect_uri` is set only when the demand came from the root of an
    *embedded* schema resource, mid-walk (P14). The registry holds no
    loaders, but the engine can often assemble that dialect from a
    metaschema and register the document again — and because registration
    is all-or-nothing (P13), the second attempt starts from the state the
    first one found rather than from a half-indexed registry.
    """

    dialect_uri: str | None

    def __init__(
        self,
        message: str,
        *,
        schema_location: str | None = None,
        dialect_uri: str | None = None,
    ) -> None:
        super().__init__(message, schema_location=schema_location)
        self.dialect_uri = dialect_uri


class UnknownKeywordError(JsonSchemaEngineError):
    """A schema uses a keyword its dialect does not define and does not permit.

    Only dialects that refuse unknown keywords raise this; the default is to
    treat an unknown keyword as annotation-only (§3).
    """


class UndeclaredProductionError(JsonSchemaEngineError):
    """A keyword called `ctx.produce()` without declaring its id in `produces`.

    Declarations are what let the interpreter elide dependency records that
    nothing consumes (D5), so an undeclared producer would silently lose its
    data under elision rather than fail (channel rule 2).
    """


class UndeclaredConsumptionError(JsonSchemaEngineError):
    """A keyword called `ctx.visible()` for an id absent from its `consumes`.

    The mirror of `UndeclaredProductionError`: an undeclared consumer would
    see an empty channel instead of an error once elision is on (D5).
    """


class KeywordContractError(JsonSchemaEngineError):
    """A keyword reported an error through `ctx.error()` yet accepted the input.

    Relevance (channel rule 6) drops the errors of accepting evaluations, so
    such an error would vanish from the output; the contract violation is
    reported instead of the phantom error.
    """


class InfiniteLoopError(JsonSchemaEngineError):
    """A schema was re-entered at the same instance location without progress.

    The `$ref` cycle guard, keyed by (schema location, cursor identity) — see
    §5 and the suite's `infinite-loop-detection.json`.
    """


class MaxDepthExceededError(JsonSchemaEngineError):
    """Registration or evaluation nested deeper than `max_depth` allows (P3).

    Raised before CPython's own recursion limit can fire, so a hostile schema
    surfaces as a typed engine error rather than a `RecursionError` from an
    arbitrary frame.
    """


class OutputOptionsError(JsonSchemaEngineError):
    """The requested combination of output format, level, and controls is invalid.

    Raised before evaluation (D6) so a caller never pays for a run whose
    result it cannot be given.
    """


class UnsupportedPatternError(JsonSchemaEngineError):
    """A regex could not be translated into the configured backend's dialect.

    Raised at registration (P1) rather than on the hot path: a pattern that
    cannot be honoured must not quietly match nothing.
    """


class UnsafeRegexError(JsonSchemaEngineError):
    """A regex failed the star-height screen while `reject_unsafe_regex` is on.

    Opt-in ReDoS defense (D20); neither `re` nor `regex` is linear-time, so
    rejection at registration is the only bound available.
    """


class UnresolvableReferenceError(JsonSchemaEngineError):
    """A reference could not be resolved to a schema.

    Covers a reference that does not form a usable absolute URI, a target
    document that was never registered and no loader supplied, and a pointer
    or anchor that names nothing in an otherwise known resource.

    `schema_location` says where the failure happened; these say what was
    attempted, which is the other half of the answer whenever the base a
    reference resolved against is not the one the author had in mind:

    * `reference` -- the reference exactly as written in the schema.
    * `resolved_against` -- the base URI in force at that position, which
      may be an embedded `$id` a reader never knew was there.
    * `resolved_to` -- the absolute URI the two produced.

    All three are `None` when the failure had no reference in play, such as
    a resource asked for by a caller rather than by a schema.
    """

    reference: str | None
    resolved_against: str | None
    resolved_to: str | None

    def __init__(
        self,
        message: str,
        *,
        schema_location: str | None = None,
        reference: str | None = None,
        resolved_against: str | None = None,
        resolved_to: str | None = None,
    ) -> None:
        super().__init__(message, schema_location=schema_location)
        self.reference = reference
        self.resolved_against = resolved_against
        self.resolved_to = resolved_to


class UnknownVocabularyError(JsonSchemaEngineError):
    """A metaschema's `$vocabulary` requires a vocabulary nobody registered.

    Only a vocabulary marked `true` (required) raises; an unknown optional
    vocabulary is skipped and its keywords fall to unknown-keyword handling,
    as the spec requires.
    """


class UnknownFormatError(JsonSchemaEngineError):
    """A `format` names a format the engine's table lacks, under the
    format-assertion vocabulary (which promised assertion for every name)."""


class FormatUnavailableError(JsonSchemaEngineError):
    """A `format` names a table entry that cannot run in this environment
    (an optional extra is missing); asserting it is refused at registration."""


class FormatsRequiredError(JsonSchemaEngineError):
    """A format table is needed but none was configured: `assert_formats`
    without `formats=`, or a metaschema declaring the format-assertion
    vocabulary on an engine without a table."""


class SchemaValidationError(JsonSchemaEngineError):
    """A registered document fails its own metaschema (`validate_schemas`).

    `errors` are the list-format units of the failed evaluation, so the
    caller can report exactly which keyword values were malformed.
    """

    errors: list[object]

    def __init__(
        self,
        message: str,
        errors: list[object],
        *,
        schema_location: str | None = None,
    ) -> None:
        super().__init__(message, schema_location=schema_location)
        self.errors = errors
