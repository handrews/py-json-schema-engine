# URI-family formats (M7): `uri`, `uri-reference` (RFC 3986), `iri`,
# `iri-reference` (RFC 3987), and `uri-template` (RFC 6570), as ABNF
# transcriptions over `_abnf`'s shared fragments.
#
# Dependency direction: standard library and this package's `_abnf`.

import re

from json_schema_engine.formats._abnf import (
    ALPHA,
    DIGIT,
    IPRIVATE,
    IPV4ADDRESS,
    IPV6ADDRESS,
    IPVFUTURE,
    PCT_ENCODED,
    SUB_DELIMS,
    UCSCHAR,
    UNRESERVED,
)
from json_schema_engine.formats._abnf import anchored as _anchored


def _grammar(
    ucschar: str | None, iprivate: str | None
) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build the anchored (`URI`, `URI-reference`) patterns.

    `ucschar`/`iprivate` are `None` for the plain RFC 3986 grammar, or the
    `_abnf` fragments of the same name to build the RFC 3987 IRI grammar
    instead: `iunreserved` folds `ucschar` in everywhere `unreserved` is
    used (host reg-name, userinfo, path/query/fragment via `pchar`), and
    `iprivate` is additionally admitted in `iquery` only (RFC 3987 §2.2:
    `ifragment` has no `iprivate` alternative).
    """
    unreserved = UNRESERVED if ucschar is None else f"(?:{UNRESERVED}|{ucschar})"
    pchar = f"(?:{unreserved}|{PCT_ENCODED}|{SUB_DELIMS}|:|@)"
    reg_name = f"(?:{unreserved}|{PCT_ENCODED}|{SUB_DELIMS})*"
    userinfo = f"(?:{unreserved}|{PCT_ENCODED}|{SUB_DELIMS}|:)*"
    ip_literal = rf"\[(?:{IPV6ADDRESS}|{IPVFUTURE})\]"
    host = f"(?:{ip_literal}|{IPV4ADDRESS}|{reg_name})"
    port = f"{DIGIT}*"
    authority = f"(?:{userinfo}@)?{host}(?::{port})?"

    segment = f"{pchar}*"
    segment_nz = f"{pchar}+"
    # `segment-nz-nc`: a non-zero-length segment without a colon.
    segment_nz_nc = f"(?:{unreserved}|{PCT_ENCODED}|{SUB_DELIMS}|@)+"
    path_abempty = f"(?:/{segment})*"
    path_absolute = f"/(?:{segment_nz}(?:/{segment})*)?"
    path_rootless = f"{segment_nz}(?:/{segment})*"
    path_noscheme = f"{segment_nz_nc}(?:/{segment})*"
    path_empty = ""

    query_alts = [pchar, "/", r"\?"]
    if iprivate is not None:
        query_alts.append(iprivate)
    query = f"(?:{'|'.join(query_alts)})*"
    fragment = rf"(?:{pchar}|/|\?)*"

    scheme = f"{ALPHA}[A-Za-z0-9+.-]*"

    hier_part = (
        f"(?://{authority}{path_abempty}|{path_absolute}|{path_rootless}|{path_empty})"
    )
    relative_part = (
        f"(?://{authority}{path_abempty}|{path_absolute}|{path_noscheme}|{path_empty})"
    )

    uri_grammar = rf"{scheme}:{hier_part}(?:\?{query})?(?:#{fragment})?"
    relative_ref = rf"{relative_part}(?:\?{query})?(?:#{fragment})?"
    uri_reference_grammar = f"(?:{uri_grammar}|{relative_ref})"

    return _anchored(uri_grammar), _anchored(uri_reference_grammar)


URI_RE, URI_REFERENCE_RE = _grammar(None, None)
IRI_RE, IRI_REFERENCE_RE = _grammar(UCSCHAR, IPRIVATE)


def uri(value: str) -> bool:
    """RFC 3986 `URI`."""
    return URI_RE.match(value) is not None


def uri_reference(value: str) -> bool:
    """RFC 3986 `URI-reference`."""
    return URI_REFERENCE_RE.match(value) is not None


def iri(value: str) -> bool:
    """RFC 3987 `IRI`."""
    return IRI_RE.match(value) is not None


def iri_reference(value: str) -> bool:
    """RFC 3987 `IRI-reference`."""
    return IRI_REFERENCE_RE.match(value) is not None


# RFC 6570 §2 URI Template grammar:
#   URI-Template  = *( literal / expression )
#   expression    = "{" [ operator ] variable-list "}"
#   operator      = op-level2 / op-level3 / op-reserve
#   variable-list = varspec *( "," varspec )
#   varspec       = varname [ modifier-level4 ]
#   varname       = varchar *( ["."] varchar )
#   varchar       = ALPHA / DIGIT / "_" / pct-encoded
#   modifier-level4 = prefix / explode
#   prefix        = ":" max-length      ; max-length = %x31-39 0*3DIGIT
#   explode       = "*"
# `literal` is RFC 6570 §2.1's set, widened per the suite: %x26-3B (rather
# than the RFC's lone %x26) so an apostrophe is a valid literal character
# (fixture `a'b`); ucschar/iprivate are folded in unconditionally, since
# this format doesn't distinguish an ASCII vs. internationalized tier the
# way `uri`/`iri` do.
_LITERAL_ASCII = r"\x21\x23-\x24\x26-\x3B\x3D\x3F-\x5B\x5D\x5F\x61-\x7A\x7E"
_LITERAL = f"(?:{PCT_ENCODED}|[{_LITERAL_ASCII}]|{UCSCHAR}|{IPRIVATE})"
_VARCHAR = f"(?:{PCT_ENCODED}|[A-Za-z0-9_])"
_VARNAME = f"{_VARCHAR}(?:\\.?{_VARCHAR})*"
_OPERATOR = "[+#./;?&=,!@|]"
_VARSPEC = f"{_VARNAME}(?::[1-9][0-9]{{0,3}}|\\*)?"
_EXPRESSION = rf"\{{(?:{_OPERATOR})?{_VARSPEC}(?:,{_VARSPEC})*\}}"
URI_TEMPLATE_RE = _anchored(f"(?:{_LITERAL}|{_EXPRESSION})*")


def uri_template(value: str) -> bool:
    """RFC 6570 `URI-Template`."""
    return URI_TEMPLATE_RE.match(value) is not None
