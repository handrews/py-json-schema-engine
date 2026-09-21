# URI-family formats (M7): `uri`, `uri-reference` (RFC 3986), `iri`,
# `iri-reference` (RFC 3987), and `uri-template` (RFC 6570). Step 1 (agent
# B) implements these over `_abnf`.
#
# Dependency direction: standard library, this package's `_abnf` and
# `anchored`.


def uri(value: str) -> bool:
    """RFC 3986 `URI`."""
    raise NotImplementedError


def uri_reference(value: str) -> bool:
    """RFC 3986 `URI-reference`."""
    raise NotImplementedError


def iri(value: str) -> bool:
    """RFC 3987 `IRI`."""
    raise NotImplementedError


def iri_reference(value: str) -> bool:
    """RFC 3987 `IRI-reference`."""
    raise NotImplementedError


def uri_template(value: str) -> bool:
    """RFC 6570 `URI-Template`."""
    raise NotImplementedError
