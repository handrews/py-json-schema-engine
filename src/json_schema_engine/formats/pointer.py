# JSON Pointer formats (M7): `json-pointer` (RFC 6901) and
# `relative-json-pointer` (draft-handrews-relative-json-pointer). Step 1
# (agent D) implements these.
#
# Dependency direction: standard library and this package's `anchored`.


def json_pointer(value: str) -> bool:
    """RFC 6901 `json-pointer`."""
    raise NotImplementedError


def relative_json_pointer(value: str) -> bool:
    """Relative JSON Pointer."""
    raise NotImplementedError
