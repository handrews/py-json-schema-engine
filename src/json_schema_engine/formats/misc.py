# `uuid` (RFC 4122 §3) and `regex` (ECMA-262 syntax, through `ecma_regex`).
# Step 1 (agent D) implements these.
#
# Dependency direction: standard library, `ecma_regex`, this package's
# `anchored`.


def uuid(value: str) -> bool:
    """RFC 4122 §3 string form: 8-4-4-4-12 hexadecimal digits."""
    raise NotImplementedError


def regex(value: str) -> bool:
    """A syntactically valid ECMA-262 regular expression."""
    raise NotImplementedError
