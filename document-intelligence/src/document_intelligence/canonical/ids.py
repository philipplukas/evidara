"""Deterministic and random ID helpers for canonical entities and events."""

import hashlib
from uuid import uuid4

_CROCKFORD_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def stable_prefixed_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(_join_parts(parts).encode("utf-8")).digest()[:16]
    return f"{prefix}_{_encode_128_bits(digest)}"


def random_prefixed_id(prefix: str) -> str:
    return f"{prefix}_{_encode_128_bits(uuid4().bytes)}"


def _join_parts(parts: tuple[str, ...]) -> str:
    return "||".join(str(part) for part in parts)


def _encode_128_bits(raw_bytes: bytes) -> str:
    value = int.from_bytes(raw_bytes, "big")
    output = []
    for _ in range(26):
        output.append(_CROCKFORD_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(output))
