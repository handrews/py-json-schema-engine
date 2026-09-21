# IDNA2008 support (M7): the A-label check `hostname` applies to `xn--`
# labels and the `idn-hostname` predicate, both through the `idna` package
# (the optional `idna` extra; executed via its public API, never read).
# Without the extra, `a_label_ok` accepts any LDH-valid `xn--` label (a
# documented degradation) and the `idn-hostname` table entry is marked
# unavailable, so asserting it fails at registration.
#
# What the suite pins beyond what `idna` does per label: splitting on the
# four label separators before measuring anything; empty labels; the
# 253-octet total; and the domain-wide RFC 5893 bidi rule (a right-to-left
# label anywhere makes every label subject to the rule).
#
# Dependency direction: imports the standard library, the optional `idna`
# package, and core's `errors` only.

import re
import unicodedata
from importlib.util import find_spec

from json_schema_engine.core.errors import FormatUnavailableError

HAVE_IDNA = find_spec("idna") is not None
IDNA_EXTRA = (
    "idn-hostname needs the 'idna' extra: pip install 'json-schema-engine[idna]'"
)

# RFC 3490 §3.1 label separators: FULL STOP, IDEOGRAPHIC FULL STOP,
# FULLWIDTH FULL STOP, HALFWIDTH IDEOGRAPHIC FULL STOP.
_SEPARATORS = re.compile(
    "[.\N{IDEOGRAPHIC FULL STOP}\N{FULLWIDTH FULL STOP}"
    "\N{HALFWIDTH IDEOGRAPHIC FULL STOP}]"
)
_RTL = frozenset({"R", "AL", "AN"})

if HAVE_IDNA:
    import idna

    def _u_label(label: str) -> str | None:
        """Decode and validate an A-label, canonical form included."""
        try:
            return idna.ulabel(label)
        except (idna.IDNAError, UnicodeError, ValueError):
            return None

    def a_label_ok(label: str) -> bool:
        """Whether an `xn--` label (already LDH-valid) is a canonical A-label
        whose U-label satisfies IDNA2008."""
        lowered = label.lower()
        decoded = _u_label(lowered)
        if decoded is None:
            return False
        try:
            return idna.alabel(decoded) == lowered.encode("ascii")
        except (idna.IDNAError, UnicodeError, ValueError):
            return False

    def idn_hostname(value: str) -> bool:
        """RFC 5890/5891 internationalized hostname (with UTS 46 mapping)."""
        if not value:
            return False
        labels = _SEPARATORS.split(value)
        decoded: list[str] = []
        total = len(labels) - 1
        for label in labels:
            if not label:
                return False
            try:
                mapped = idna.uts46_remap(label, std3_rules=False, transitional=False)
                if not mapped:
                    return False
                ace = idna.alabel(mapped)
            except (idna.IDNAError, UnicodeError, ValueError):
                return False
            if mapped.lower().startswith("xn--"):
                if not a_label_ok(mapped):
                    return False
                u_label = _u_label(mapped.lower())
                if u_label is None:
                    return False
            else:
                u_label = mapped
            total += len(ace)
            decoded.append(u_label)
        if total > 253:
            return False
        # RFC 5893 §1.4: a domain with any RTL label is a "Bidi domain name"
        # and every label must satisfy the bidi rule.
        if any(unicodedata.bidirectional(c) in _RTL for u in decoded for c in u):
            for u_label in decoded:
                try:
                    if not idna.check_bidi(u_label, check_ltr=True):
                        return False
                except (idna.IDNAError, UnicodeError, ValueError):
                    return False
        return True

else:

    def a_label_ok(label: str) -> bool:
        """Without the extra: an LDH-valid A-label is accepted unchecked."""
        return True

    def idn_hostname(value: str) -> bool:
        """Unreachable: the table marks the entry unavailable without the extra."""
        raise FormatUnavailableError(IDNA_EXTRA)
