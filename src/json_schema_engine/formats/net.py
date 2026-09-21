# Network formats (M7): `ipv4` and `ipv6` (RFC 2673 dotted-quad and RFC
# 4291 §2.2, through the standard library's `ipaddress`, which the suite's
# fixtures verified exact once IPv6 zone ids are rejected), `hostname`
# (RFC 1123 §2.1 with `xn--` labels checked through `idna_`), `email`
# (RFC 5321 §4.1.2 `Mailbox`), and `idn_email` (RFC 6531's
# internationalized `Mailbox`).
#
# Dependency direction: imports the standard library and this package's
# `_abnf` and `idna_` only.

import ipaddress

from json_schema_engine.formats import idna_
from json_schema_engine.formats._abnf import anchored as _anchored


def ipv4(value: str) -> bool:
    """RFC 2673 §3.2 dotted-quad: four decimal octets, no leading zeros."""
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def ipv6(value: str) -> bool:
    """RFC 4291 §2.2 text form; zone ids are not part of the address."""
    if "%" in value:
        return False
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return False
    return True


# RFC 1123 §2.1 / RFC 952: a label starts and ends with a letter or
# digit, with letters, digits, and hyphens (never underscore) in
# between, at most 63 characters long.
_HOSTNAME_LABEL = _anchored(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def hostname(value: str) -> bool:
    """RFC 1123 §2.1 hostname; `xn--` labels through `idna_.a_label_ok`."""
    if not value or len(value) > 253:
        return False
    for label in value.split("."):
        if not _HOSTNAME_LABEL.match(label):
            return False
        if label[:4].casefold() == "xn--" and not idna_.a_label_ok(label):
            return False
    return True


# RFC 5321 §4.1.2's `Mailbox` alphabets, transcribed as ABNF fragments:
# `atext` (Dot-string's alphabet), `qtextSMTP` and `quoted-pairSMTP`
# (Quoted-string's alphabet). `email` uses these ASCII-only fragments
# directly; `idn_email` widens `atext`/`qtextSMTP` with RFC 6531's
# UTF8-non-ascii (any scalar value outside ASCII — lone surrogates are
# excluded, since UTF-8 can never encode one) while leaving
# `quoted-pairSMTP` ASCII-only, per RFC 6531 §3.3.
_ATEXT = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]"
_QTEXT = r"[\x20\x21\x23-\x5B\x5D-\x7E]"
_QUOTED_PAIR = r"\\[\x20-\x7E]"
_NON_ASCII_SCALAR = r"[^\x00-\x7F\uD800-\uDFFF]"

_DOT_STRING = _anchored(rf"{_ATEXT}+(?:\.{_ATEXT}+)*")
_QUOTED_STRING = _anchored(rf'"(?:{_QTEXT}|{_QUOTED_PAIR})*"')

_ATEXT_IDN = rf"(?:{_ATEXT}|{_NON_ASCII_SCALAR})"
_QTEXT_IDN = rf"(?:{_QTEXT}|{_NON_ASCII_SCALAR})"
_DOT_STRING_IDN = _anchored(rf"{_ATEXT_IDN}+(?:\.{_ATEXT_IDN}+)*")
_QUOTED_STRING_IDN = _anchored(rf'"(?:{_QTEXT_IDN}|{_QUOTED_PAIR})*"')

# `idn_email`'s Domain alternative asks only that non-ASCII characters be
# admitted where `hostname` would otherwise reject them (RFC 6531 §3.3:
# no IDNA validation, no normalization) — a lenient, `hostname`-shaped
# label rule: 1-63 code points, `[A-Za-z0-9-]` or any non-ASCII scalar,
# never a leading/trailing hyphen.
_IDN_LABEL_EDGE = rf"(?:[A-Za-z0-9]|{_NON_ASCII_SCALAR})"
_IDN_LABEL_MID = rf"(?:[A-Za-z0-9-]|{_NON_ASCII_SCALAR})"
_IDN_HOSTNAME_LABEL = _anchored(
    rf"{_IDN_LABEL_EDGE}(?:{_IDN_LABEL_MID}{{0,61}}{_IDN_LABEL_EDGE})?"
)


def _split_mailbox(value: str) -> tuple[str, str] | None:
    """Local-part and Domain/address-literal, split at the `@` that ends
    the local part.

    A quoted local part is scanned to its closing `"`, honoring `\\`
    pairs so an escaped quote (or an escaped `@`) never ends it early,
    and the `@` must immediately follow that quote. An unquoted local
    part is split at its first `@`: `atext` never contains `@`, so a
    second, later `@` can only ever land in the domain — exactly where
    splitting at the first `@` already puts it — and fails domain
    validation there regardless.
    """
    if value.startswith('"'):
        i = 1
        n = len(value)
        while i < n and value[i] != '"':
            i += 2 if value[i] == "\\" else 1
        if i >= n or i + 1 >= n or value[i + 1] != "@":
            return None
        return value[: i + 1], value[i + 2 :]
    local, sep, domain = value.partition("@")
    if not sep:
        return None
    return local, domain


def _address_literal(inner: str) -> bool:
    """A bracketed Domain's content: an IPv6-address-literal (`IPv6:` tag,
    matched case-insensitively) or a plain ipv4 literal.
    General-address-literal (any other tag) is never accepted."""
    if inner[:5].casefold() == "ipv6:":
        return ipv6(inner[5:])
    return ipv4(inner)


def _domain(value: str) -> bool:
    if value.startswith("[") and value.endswith("]") and len(value) >= 2:
        return _address_literal(value[1:-1])
    return hostname(value)


def _idn_domain(value: str) -> bool:
    if value.startswith("[") and value.endswith("]") and len(value) >= 2:
        return _address_literal(value[1:-1])
    if not value or len(value) > 253:
        return False
    return all(_IDN_HOSTNAME_LABEL.match(label) for label in value.split("."))


def email(value: str) -> bool:
    """RFC 5321 §4.1.2 `Mailbox`."""
    split = _split_mailbox(value)
    if split is None:
        return False
    local, domain = split
    if not domain:
        return False
    valid_local = bool(
        _QUOTED_STRING.match(local)
        if local.startswith('"')
        else _DOT_STRING.match(local)
    )
    return valid_local and _domain(domain)


def idn_email(value: str) -> bool:
    """RFC 6531 internationalized `Mailbox`."""
    split = _split_mailbox(value)
    if split is None:
        return False
    local, domain = split
    if not domain:
        return False
    valid_local = bool(
        _QUOTED_STRING_IDN.match(local)
        if local.startswith('"')
        else _DOT_STRING_IDN.match(local)
    )
    return valid_local and _idn_domain(domain)
