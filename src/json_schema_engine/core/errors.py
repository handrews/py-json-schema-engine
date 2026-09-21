# Every typed error the engine raises (DESIGN.md §2, module table).
#
# Dependency direction: the leaf of `core`. It imports nothing from the
# engine so that any module may raise these without creating a cycle.
#
# One root (`JsonSchemaEngineError`) lets an embedding application catch
# everything this library raises with a single `except` clause, and lets it
# distinguish engine faults from bugs (`TypeError`, `KeyError`) that must not
# be swallowed.


class JsonSchemaEngineError(Exception):
    """Root of every error raised by the engine.

    `schema_location` is the canonical `base_uri#pointer` of the schema
    position that provoked the error, when one applies. It lives on the root
    so that any error can gain a location without a class change; errors that
    are not about a schema position (`OutputOptionsError`) simply leave it
    `None`.
    """

    schema_location: str | None

    def __init__(self, message: str, *, schema_location: str | None = None) -> None:
        super().__init__(message)
        self.schema_location = schema_location


class InvalidSchemaError(JsonSchemaEngineError):
    """A keyword-claimed schema position holds neither an object nor a boolean.

    Raised by the registration walk and, as a lazy backstop, by schema
    application (D19): failing loud beats silently treating a string or a
    number as an empty schema that accepts everything.
    """


class UnknownDialectError(JsonSchemaEngineError):
    """A schema names a `$schema` dialect URI that no registered dialect claims."""


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
    """


class UnknownVocabularyError(JsonSchemaEngineError):
    """A metaschema's `$vocabulary` requires a vocabulary nobody registered.

    Only a vocabulary marked `true` (required) raises; an unknown optional
    vocabulary is skipped and its keywords fall to unknown-keyword handling,
    as the spec requires.
    """


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
