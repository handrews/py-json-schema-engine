# Vocabulary URIs and the keyword-id convention shared by every keyword
# module (DESIGN.md D2): a keyword's id is `<vocabulary URI>#<name>`.
#
# Dependency direction: imports nothing. Every keyword module imports this.

VOCAB_CORE = "https://json-schema.org/draft/2020-12/vocab/core"
VOCAB_APPLICATOR = "https://json-schema.org/draft/2020-12/vocab/applicator"
VOCAB_VALIDATION = "https://json-schema.org/draft/2020-12/vocab/validation"
VOCAB_UNEVALUATED = "https://json-schema.org/draft/2020-12/vocab/unevaluated"
VOCAB_META_DATA = "https://json-schema.org/draft/2020-12/vocab/meta-data"
VOCAB_FORMAT_ANNOTATION = (
    "https://json-schema.org/draft/2020-12/vocab/format-annotation"
)
VOCAB_CONTENT = "https://json-schema.org/draft/2020-12/vocab/content"

DIALECT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


def keyword_id(vocabulary_uri: str, name: str) -> str:
    """The stable identity of a keyword: its vocabulary URI plus its name."""
    return f"{vocabulary_uri}#{name}"


# The 2019-09 core vocabulary, named here because a `$vocabulary`-assembled
# dialect that includes it inherits 2019-09 identifier syntax (D18).
VOCAB_CORE_2019 = "https://json-schema.org/draft/2019-09/vocab/core"
