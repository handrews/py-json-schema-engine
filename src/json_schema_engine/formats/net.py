# Network formats (M7): `ipv4` and `ipv6` (RFC 2673 dotted-quad and RFC
# 4291 §2.2, through the standard library's `ipaddress`, which the suite's
# fixtures verified exact once IPv6 zone ids are rejected), `hostname`
# (RFC 1123 §2.1 with A-labels checked through `idna_`), `email` (RFC 5321
# §4.1.2 Mailbox), and `idn-email` (RFC 6531).
#
# Dependency direction: imports the standard library, this package's
# `idna_`, and core's `formats` contract only.

import ipaddress


def ipv4(value: str) -> bool:
    """RFC 2673 §3.2 dotted-quad: four decimal octets, no leading zeros."""
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def ipv6(value: str) -> bool:
    """RFC 4291 §2.2 text form; zone ids are not part of the address."""
    raise NotImplementedError


def hostname(value: str) -> bool:
    """RFC 1123 §2.1 hostname; `xn--` labels through `idna_.a_label_ok`."""
    raise NotImplementedError


def email(value: str) -> bool:
    """RFC 5321 §4.1.2 `Mailbox`."""
    raise NotImplementedError


def idn_email(value: str) -> bool:
    """RFC 6531 internationalized `Mailbox`."""
    raise NotImplementedError
