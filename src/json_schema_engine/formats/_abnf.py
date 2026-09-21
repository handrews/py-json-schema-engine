# Shared RFC 3986/3987 ABNF fragments (M7): plain string pieces composed
# by the URI family and reused by `uri-template`. Step 1 (agent B) fills
# this module; the names below are the contract the other modules import.
#
# Dependency direction: standard library only.

import re


def anchored(fragment: str) -> re.Pattern[str]:
    """Compile an ABNF fragment as a whole-string match (`\\A`…`\\Z`)."""
    return re.compile(rf"\A(?:{fragment})\Z")


ALPHA = "[A-Za-z]"
DIGIT = "[0-9]"
HEXDIG = "[0-9A-Fa-f]"

# RFC 3986 §2.1 `pct-encoded = "%" HEXDIG HEXDIG`.
PCT_ENCODED = f"%{HEXDIG}{{2}}"
# RFC 3986 §2.3 `unreserved = ALPHA / DIGIT / "-" / "." / "_" / "~"`.
UNRESERVED = "[A-Za-z0-9._~-]"
# RFC 3986 §2.2 `sub-delims`.
SUB_DELIMS = "[!$&'()*+,;=]"

# RFC 3986 App. A `dec-octet`: a decimal octet, no leading zeros (other
# than the single digit "0" itself).
DEC_OCTET = "(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])"
# RFC 3986 App. A `IPv4address = dec-octet "." dec-octet "." dec-octet "." dec-octet`.
IPV4ADDRESS = rf"{DEC_OCTET}\.{DEC_OCTET}\.{DEC_OCTET}\.{DEC_OCTET}"

# RFC 3986 App. A `h16 = 1*4HEXDIG` (a 16-bit field, hex, up to 4 digits).
H16 = f"{HEXDIG}{{1,4}}"
# RFC 3986 App. A `ls32 = ( h16 ":" h16 ) / IPv4address` (the low-order 32
# bits of an IPv6 address, as two h16 fields or an embedded IPv4address).
LS32 = f"(?:{H16}:{H16}|{IPV4ADDRESS})"

# RFC 3986 App. A `IPv6address`, spelled out as its nine alternatives
# (each bracketed prefix run is `*N( h16 ":" ) h16`, made optional as a
# whole so the run itself, not just its last field, can be absent).
IPV6ADDRESS = (
    rf"(?:{H16}:){{6}}{LS32}"
    rf"|::(?:{H16}:){{5}}{LS32}"
    rf"|(?:{H16})?::(?:{H16}:){{4}}{LS32}"
    rf"|(?:(?:{H16}:){{0,1}}{H16})?::(?:{H16}:){{3}}{LS32}"
    rf"|(?:(?:{H16}:){{0,2}}{H16})?::(?:{H16}:){{2}}{LS32}"
    rf"|(?:(?:{H16}:){{0,3}}{H16})?::{H16}:{LS32}"
    rf"|(?:(?:{H16}:){{0,4}}{H16})?::{LS32}"
    rf"|(?:(?:{H16}:){{0,5}}{H16})?::{H16}"
    rf"|(?:(?:{H16}:){{0,6}}{H16})?::"
)

# RFC 3986 App. A `IPvFuture = "v" 1*HEXDIG "." 1*( unreserved / sub-delims / ":" )`.
IPVFUTURE = rf"[vV]{HEXDIG}+\.(?:{UNRESERVED}|{SUB_DELIMS}|:)+"

# RFC 3987 §2.2 `ucschar`: most of the non-ASCII BMP plus planes 1-14 of
# the supplementary planes, excluding surrogates, noncharacters, and the
# handful of reserved/private blocks the RFC carves out.
UCSCHAR = (
    "[\u00a0-\ud7ff\uf900-\ufdcf\ufdf0-\uffef"
    "\U00010000-\U0001fffd\U00020000-\U0002fffd\U00030000-\U0003fffd"
    "\U00040000-\U0004fffd\U00050000-\U0005fffd\U00060000-\U0006fffd"
    "\U00070000-\U0007fffd\U00080000-\U0008fffd\U00090000-\U0009fffd"
    "\U000a0000-\U000afffd\U000b0000-\U000bfffd\U000c0000-\U000cfffd"
    "\U000d0000-\U000dfffd\U000e1000-\U000efffd]"
)

# RFC 3987 §2.2 `iprivate = %xE000-F8FF / %xF0000-FFFFD / %x100000-10FFFD`
# (the BMP Private Use Area, then the two supplementary private-use planes).
IPRIVATE = "[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]"
