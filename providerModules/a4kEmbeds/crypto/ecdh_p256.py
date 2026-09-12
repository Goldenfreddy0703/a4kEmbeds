# -*- coding: utf-8 -*-
"""P-256 ECDH helpers (vendored python-ecdsa)."""

from __future__ import annotations

from providerModules.a4kEmbeds.crypto.ecdsa import NIST256p, SigningKey, VerifyingKey
from providerModules.a4kEmbeds.crypto.ecdsa.ecdh import ECDH

# Embedded server static public keys from crush.wasm data section (key_id index).
SERVER_PUBLIC_KEYS = {
    1: bytes.fromhex(
        "0483c7a82132b8516e3eb4061b82e9c881cc585593a4709001131bff7443eabc1"
        "701c1f0d50e23ac02b0b9a5979903dbd7e9055aab5e4a5532132d1d200707f5f2"
    ),
}

CURVE_ORDER = NIST256p.order


def generate_keypair_from_scalar(scalar: int) -> tuple[SigningKey, bytes]:
    """Return (SigningKey, 65-byte uncompressed public key 0x04||X||Y)."""
    if scalar <= 0 or scalar >= CURVE_ORDER:
        raise ValueError("invalid P-256 scalar")
    private_key = SigningKey.from_secret_exponent(scalar, curve=NIST256p)
    public_key = private_key.get_verifying_key().to_string("uncompressed")
    return private_key, public_key


def shared_secret(ephemeral_private: SigningKey, key_id: int) -> bytes:
    """ECDH shared secret (32-byte x coordinate) with server key_id."""
    server_bytes = SERVER_PUBLIC_KEYS.get(key_id)
    if not server_bytes:
        raise ValueError(f"unknown cinejoy server key_id {key_id}")
    server_key = VerifyingKey.from_string(server_bytes, curve=NIST256p)
    ecdh = ECDH(curve=NIST256p, private_key=ephemeral_private, public_key=server_key)
    return ecdh.generate_sharedsecret_bytes()
