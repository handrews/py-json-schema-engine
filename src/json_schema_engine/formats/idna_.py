# IDNA2008 support (M7 Step 2 completes this module): the A-label check
# `hostname` applies to `xn--` labels and the `idn-hostname` predicate,
# both through the `idna` package (the optional `idna` extra; executed via
# its public API, never read). Without the extra, `a_label_ok` accepts
# any LDH-valid `xn--` label (a documented degradation) and the
# `idn-hostname` entry is marked unavailable so asserting it fails at
# registration.
#
# Dependency direction: imports the standard library, the optional `idna`
# package, and core's `errors` only.

from importlib.util import find_spec

from json_schema_engine.core.errors import FormatUnavailableError

HAVE_IDNA = find_spec("idna") is not None
IDNA_EXTRA = (
    "idn-hostname needs the 'idna' extra: pip install 'json-schema-engine[idna]'"
)


def a_label_ok(label: str) -> bool:
    """Whether an `xn--` label decodes to a valid IDNA2008 U-label and is
    in canonical form. Step 2 implements this; until then, and whenever
    the extra is absent, an LDH-valid A-label is accepted unchecked."""
    return True


def idn_hostname(value: str) -> bool:
    """RFC 5890/5891 internationalized hostname (Step 2)."""
    raise FormatUnavailableError(IDNA_EXTRA)
