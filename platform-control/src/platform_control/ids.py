from __future__ import annotations

import os
import time

_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(value: int, length: int) -> str:
    encoded: list[str] = []
    for _ in range(length):
        encoded.append(_CROCKFORD_BASE32[value & 0x1F])
        value >>= 5
    return "".join(reversed(encoded)).lower()


def generate_ulid() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    randomness = int.from_bytes(os.urandom(10), byteorder="big")
    combined = (timestamp_ms << 80) | randomness
    return _encode_base32(combined, 26)


_ALLOWED_PREFIXES = frozenset(
    {
        "art",
        "auth",
        "cap",
        "evt",
        "exp",
        "jur",
        "pjob",
        "run",
        "src",
        "sv",
        "whr",
    }
)


def generate_prefixed_id(prefix: str) -> str:
    """Generate a ULID-based ID with a domain prefix (e.g. ``src_…``).

    Allowed prefixes: ``art``, ``auth``, ``cap``, ``evt``, ``exp``,
    ``jur``, ``pjob``, ``run``, ``src``, ``sv``, ``whr``.
    """
    if prefix not in _ALLOWED_PREFIXES:
        raise ValueError(
            f"Unknown ID prefix {prefix!r}. Allowed: {', '.join(sorted(_ALLOWED_PREFIXES))}."
        )
    return f"{prefix}_{generate_ulid()}"
