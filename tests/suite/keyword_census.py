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

# The complete 2019-09 keyword set: 2020-12's set minus the 2020-12-only
# core/applicator keywords, plus the 2019-09 keywords they replaced.
# `definitions` and `dependencies` are not 2019-09 keywords (they were
# renamed to `$defs`/`dependentSchemas`+`dependentRequired` in 2019-09
# already; the old names only reappear in draft-07 and earlier).
ALL_2019_09: frozenset[str] = frozenset(
    (ALL_2020_12 - {"$dynamicRef", "$dynamicAnchor", "prefixItems"})
    | {"$recursiveRef", "$recursiveAnchor", "additionalItems"}
)

# The complete draft-07 keyword set (draft-07 metaschema).
ALL_DRAFT7: frozenset[str] = frozenset(
    {
        "$id",
        "$schema",
        "$ref",
        "$comment",
        "definitions",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
        "items",
        "additionalItems",
        "contains",
        "properties",
        "patternProperties",
        "additionalProperties",
        "propertyNames",
        "dependencies",
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
        "maxProperties",
        "minProperties",
        "required",
        "format",
        "contentMediaType",
        "contentEncoding",
        "title",
        "description",
        "default",
        "readOnly",
        "writeOnly",
        "examples",
    }
)

# The complete draft-06 keyword set: draft-07 minus the keywords draft-07
# introduced (draft-06 metaschema).
ALL_DRAFT6: frozenset[str] = frozenset(
    ALL_DRAFT7
    - {
        "$comment",
        "if",
        "then",
        "else",
        "readOnly",
        "writeOnly",
        "contentMediaType",
        "contentEncoding",
    }
)
