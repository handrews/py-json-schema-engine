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
VOCAB_FORMAT_ASSERTION = "https://json-schema.org/draft/2020-12/vocab/format-assertion"
VOCAB_CONTENT = "https://json-schema.org/draft/2020-12/vocab/content"

DIALECT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


def keyword_id(vocabulary_uri: str, name: str) -> str:
    """The stable identity of a keyword: its vocabulary URI plus its name."""
    return f"{vocabulary_uri}#{name}"


# The 2019-09 core vocabulary, named here because a `$vocabulary`-assembled
# dialect that includes it inherits 2019-09 identifier syntax (D18).
VOCAB_CORE_2019 = "https://json-schema.org/draft/2019-09/vocab/core"

# 2019-09 vocabularies (D11): real URIs, declared by that draft's metaschema.
VOCAB_APPLICATOR_2019 = "https://json-schema.org/draft/2019-09/vocab/applicator"
VOCAB_VALIDATION_2019 = "https://json-schema.org/draft/2019-09/vocab/validation"
VOCAB_META_DATA_2019 = "https://json-schema.org/draft/2019-09/vocab/meta-data"
VOCAB_FORMAT_2019 = "https://json-schema.org/draft/2019-09/vocab/format"
VOCAB_CONTENT_2019 = "https://json-schema.org/draft/2019-09/vocab/content"
DIALECT_2019_09 = "https://json-schema.org/draft/2019-09/schema"

# draft-07 and draft-06 predate vocabularies, so these names exist only
# inside the dialect registry (D11, D2: dialects are ordered vocabulary
# sets, so every keyword needs a vocabulary to belong to).
VOCAB_CORE_07 = "urn:jse:vocab:draft-07:core"
VOCAB_APPLICATOR_07 = "urn:jse:vocab:draft-07:applicator"
VOCAB_VALIDATION_07 = "urn:jse:vocab:draft-07:validation"
VOCAB_META_DATA_07 = "urn:jse:vocab:draft-07:meta-data"
VOCAB_FORMAT_07 = "urn:jse:vocab:draft-07:format"
VOCAB_CONTENT_07 = "urn:jse:vocab:draft-07:content"
VOCAB_CORE_06 = "urn:jse:vocab:draft-06:core"
VOCAB_APPLICATOR_06 = "urn:jse:vocab:draft-06:applicator"
VOCAB_VALIDATION_06 = "urn:jse:vocab:draft-06:validation"
VOCAB_META_DATA_06 = "urn:jse:vocab:draft-06:meta-data"
VOCAB_FORMAT_06 = "urn:jse:vocab:draft-06:format"
# The in-the-wild `$schema` spelling carries a trailing `#`; dialect URIs
# compare fragment-free, so both spellings name these.
DIALECT_DRAFT_07 = "http://json-schema.org/draft-07/schema"
DIALECT_DRAFT_06 = "http://json-schema.org/draft-06/schema"
