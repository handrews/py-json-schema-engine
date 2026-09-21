# RFC 3986 §5 reference resolution and fragment handling (DESIGN.md §2
# module table; §5 "must not be relearned").
#
# Dependency direction: a leaf. Imports only `re` from the standard library;
# the registry and the reference keywords build on it.
#
# Implemented from the RFC — Appendix B's parser, §5.2.3 merge, §5.2.4
# remove_dot_segments, §5.2.2 transform, §5.3 recomposition — rather than
# through `urllib.parse`, because that module gets two cases wrong that
# JSON Schema depends on:
#
#   * `urljoin("urn:uuid:deadbeef", "#/$defs/x")` returns `"#/$defs/x"`.
#     `urljoin` only merges paths for schemes on a hard-coded "uses_relative"
#     list, and `urn` is not on it — yet `$ref: "#/$defs/x"` inside a schema
#     identified by a `urn:` `$id` is ordinary, legal JSON Schema.
#   * `urldefrag` cannot tell an absent fragment from an empty one, and the
#     difference is load-bearing: `$ref: "#"` is the root schema of the
#     current resource, while a bare URI with no `#` is a document reference.
#
# Percent-encoding is passed through untouched: this module performs no
# normalization beyond the RFC's own algorithm. Case normalization of scheme
# and host, and percent-encoding normalization, are deliberately out of scope
# for now — the registry compares identifiers as the schema author wrote
# them, which matches every current implementation's observable behavior.

import re

# RFC 3986 Appendix B, verbatim. It matches any string, so parsing never
# fails; an unusable result is the caller's judgment to make (see `resolve`).
# DOTALL because a fragment may legally contain a newline that `.` would
# otherwise stop at, silently truncating it.
_URI_REFERENCE = re.compile(
    r"^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?", re.DOTALL
)

# RFC 3986 §3.1. Anchored but unterminated: it answers "does a scheme come
# first", not "is the whole string a URI".
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+\-.]*:")


class _Parts:
    """One parsed URI reference. `None` means the component was absent.

    Absence is distinct from emptiness for every component: `file:///x` has
    an empty authority, `foo:` has an empty path, and `a#` has an empty
    fragment — none of which is the same as not having one (§5.2.2 branches
    on "defined", not on "non-empty").
    """

    __slots__ = ("authority", "fragment", "path", "query", "scheme")

    def __init__(self, uri: str) -> None:
        m = _URI_REFERENCE.match(uri)
        assert m is not None, "Appendix B's pattern matches every string"
        self.scheme: str | None = m.group(2)
        self.authority: str | None = m.group(4)
        self.path: str = m.group(5) or ""
        self.query: str | None = m.group(7)
        self.fragment: str | None = m.group(9)


def remove_dot_segments(path: str) -> str:
    """Apply RFC 3986 §5.2.4 to a path.

    The output buffer holds whole segments including their leading `/`, so
    `..` pops one segment rather than scanning backwards through characters.
    """
    out: list[str] = []
    while path:
        if path.startswith("../"):
            path = path[3:]
        elif path.startswith("./"):
            path = path[2:]
        elif path.startswith("/./"):
            path = "/" + path[3:]
        elif path == "/.":
            path = "/"
        elif path.startswith("/../") or path == "/..":
            # `"/.."[4:]` is `""`, so one expression covers both forms.
            path = "/" + path[4:]
            if out:
                # Popping past the root is a no-op, not an error: §5.4.2's
                # `../../../g` resolves to `/g`, it does not fail.
                out.pop()
        elif path in (".", ".."):
            path = ""
        else:
            start = 1 if path.startswith("/") else 0
            end = path.find("/", start)
            if end == -1:
                out.append(path)
                path = ""
            else:
                out.append(path[:end])
                path = path[end:]
    return "".join(out)


def merge(base_authority: str | None, base_path: str, ref_path: str) -> str:
    """Apply RFC 3986 §5.2.3 to a relative path.

    A base with an authority but no path behaves as if its path were `/`;
    otherwise the reference replaces everything after the base's last `/`.
    """
    if base_authority is not None and base_path == "":
        return "/" + ref_path
    cut = base_path.rfind("/")
    return base_path[: cut + 1] + ref_path if cut >= 0 else ref_path


def resolve(base: str, ref: str) -> str:
    """Resolve `ref` against `base` per RFC 3986 §5.2.2, strict mode.

    Strict mode means a reference that carries its own scheme is never merged
    with the base, even when the two schemes agree: `http:g` against
    `http://a/b/c/d;p?q` is `http:g`. The RFC's non-strict allowance exists
    for legacy parsers, and JSON Schema has no such history.

    The result is only as absolute as the inputs: resolving a relative
    reference against a relative base yields a relative reference rather than
    an error, because the RFC's transform is defined for that case. Deciding
    that a schema needed an absolute URI is the registry's job, and the error
    it raises there (`UnresolvableReferenceError`) can name the schema
    location, which this function cannot.
    """
    r = _Parts(ref)
    b = _Parts(base)

    if r.scheme is not None:
        scheme, authority = r.scheme, r.authority
        path, query = remove_dot_segments(r.path), r.query
    elif r.authority is not None:
        scheme, authority = b.scheme, r.authority
        path, query = remove_dot_segments(r.path), r.query
    elif r.path == "":
        scheme, authority = b.scheme, b.authority
        # An empty reference keeps the base's path *and* its query unless the
        # reference supplies one; only the fragment is taken from `ref`.
        path = b.path
        query = r.query if r.query is not None else b.query
    else:
        scheme, authority = b.scheme, b.authority
        path = remove_dot_segments(
            r.path if r.path.startswith("/") else merge(b.authority, b.path, r.path)
        )
        query = r.query

    return _recompose(scheme, authority, path, query, r.fragment)


def _recompose(
    scheme: str | None,
    authority: str | None,
    path: str,
    query: str | None,
    fragment: str | None,
) -> str:
    """Rebuild a URI from its components (RFC 3986 §5.3)."""
    parts: list[str] = []
    if scheme is not None:
        parts.append(scheme + ":")
    if authority is not None:
        parts.append("//" + authority)
    parts.append(path)
    if query is not None:
        parts.append("?" + query)
    if fragment is not None:
        parts.append("#" + fragment)
    return "".join(parts)


def split_fragment(uri: str) -> tuple[str, str | None]:
    """Split `uri` into its fragment-free part and its fragment.

    The fragment is `None` when the URI has no `#` at all and `""` when it
    has a `#` with nothing after it — the distinction `urldefrag` destroys
    and `$ref: "#"` depends on.

    The fragment is returned exactly as written, still percent-encoded. The
    caller knows whether it is a JSON Pointer or a plain-name anchor, and
    therefore whether and when to decode it.
    """
    cut = uri.find("#")
    return (uri, None) if cut == -1 else (uri[:cut], uri[cut + 1 :])


def strip_fragment(uri: str) -> str:
    """Return `uri` without its fragment, `#` included."""
    return split_fragment(uri)[0]


def has_scheme(uri: str) -> bool:
    """Return whether `uri` begins with a scheme, i.e. is not a relative reference."""
    return _SCHEME.match(uri) is not None


def is_absolute(uri: str) -> bool:
    """Return whether `uri` is an absolute URI: a scheme and no fragment (§4.3).

    This is the shape a canonical base URI must have — `SchemaRef.base_uri`
    holds one — so identifiers never carry a fragment that a later pointer
    would have to compete with.
    """
    return has_scheme(uri) and "#" not in uri
