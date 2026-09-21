# The complete 2020-12 keyword set (DESIGN.md D12): the suite leg derives
# its unsupported-keyword list as this census minus what the dialect binds,
# so a keyword the engine does not know yet cannot slip through the
# unknown-keyword annotation path and silently pass a case it should fail.

ALL_2020_12: frozenset[str] = frozenset(
    {
        # core
        "$schema",
        "$id",
        "$anchor",
        "$dynamicAnchor",
        "$ref",
        "$dynamicRef",
        "$vocabulary",
        "$comment",
        "$defs",
        # applicator
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
        "dependentSchemas",
        "prefixItems",
        "items",
        "contains",
        "properties",
        "patternProperties",
        "additionalProperties",
        "propertyNames",
        # unevaluated
        "unevaluatedItems",
        "unevaluatedProperties",
        # validation
        "type",
        "enum",
        "const",
        "multipleOf",
        "maximum",
        "exclusiveMaximum",
        "minimum",
        "exclusiveMinimum",
        "maxLength",
        "minLength",
        "pattern",
        "maxItems",
        "minItems",
        "uniqueItems",
        "maxContains",
        "minContains",
        "maxProperties",
        "minProperties",
        "required",
        "dependentRequired",
        # format-annotation
        "format",
        # content
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
        # meta-data
        "title",
        "description",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
        "examples",
    }
)
