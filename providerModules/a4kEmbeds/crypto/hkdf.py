# -*- coding: utf-8 -*-
"""HKDF-SHA256 (RFC 5869) using stdlib hashlib/hmac."""

from __future__ import annotations

import hashlib
import hmac


def extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract: PRK = HMAC-SHA256(salt, IKM)."""
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand with 1-indexed counter bytes."""
    if length <= 0:
        raise ValueError("HKDF expand length must be positive")
    output = b""
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def derive(salt: bytes, ikm: bytes, info: bytes, length: int = 32) -> bytes:
    """Full HKDF-SHA256."""
    return expand(extract(salt, ikm), info, length)
