# -*- coding: utf-8 -*-
"""Pure-Python Cinejoy seal_request (P-256 ECDH + HKDF-SHA256 + AES-GCM).

Algorithm (oracle-confirmed against crush.wasm via wasmtime):
  1. nonce: 44 bytes; IV = nonce[32:44] (12 bytes).
  2. Ephemeral scalar: SHA256(b"lumen-gate-v2|ephemeral|" + nonce[:32] + counter_be)
     -> hash_to_scalar (bswap32 each uint32) with counter 0..255 until 0 < scalar < N.
  3. ECDH P-256 with server static key (key_id) -> 32-byte shared secret (x coord).
  4. HKDF-Extract: PRK = HMAC-SHA256(salt=ephemeral_public_65, IKM=shared_secret).
  5. HKDF-Expand (one block): key = HMAC-SHA256(PRK, info + 0x01), 32 bytes.
     - c2s info = b"lumen-gate-v2|c2s"
     - s2c info = b"lumen-gate-v2|s2c"
  6. Request AES-GCM: key=c2s, IV=nonce[32:44],
     AAD = b"lumen-gate-v2" + bytes([0, 1, key_id]) + ephemeral_public_65.
  7. POST body = [0x02, key_id, 0x04] + ephemeral_public[1:] + IV + ciphertext||tag.
  8. Packed header (98 B) = s2c || key_id || ephemeral_public_65 (returned to caller).
"""

from __future__ import annotations

import hashlib
import secrets
import struct

from providerModules.a4kEmbeds.crypto import aes_gcm_encrypt
from providerModules.a4kEmbeds.crypto.ecdh_p256 import (
    CURVE_ORDER,
    SERVER_PUBLIC_KEYS,
    generate_keypair_from_scalar,
    shared_secret,
)
from providerModules.a4kEmbeds.crypto.hkdf import derive as hkdf_derive

_PREFIX = b"lumen-gate-v2"
_EPHEMERAL_INFO = b"|ephemeral|"
_C2S_INFO = _PREFIX + b"|c2s"
_S2C_INFO = _PREFIX + b"|s2c"
_NONCE_LEN = 44
_HEADER_LEN = 98
_DEFAULT_KEY_ID = 1


def _bswap32(value: int) -> int:
    return struct.unpack(">I", struct.pack("<I", value & 0xFFFFFFFF))[0]


def _hash_to_scalar(digest: bytes) -> int:
    words = [_bswap32(struct.unpack_from("<I", digest, index * 4)[0]) for index in range(8)]
    scalar = 0
    for word in words:
        scalar = (scalar << 32) | word
    return scalar


def derive_ephemeral_scalar(nonce: bytes) -> int:
    """Deterministic ephemeral private scalar from the first 32 nonce bytes."""
    if len(nonce) < 32:
        raise ValueError("nonce must be at least 32 bytes")
    for counter in range(256):
        message = _PREFIX + _EPHEMERAL_INFO + nonce[:32] + struct.pack(">I", counter)
        digest = hashlib.sha256(message).digest()
        scalar = _hash_to_scalar(digest)
        if 0 < scalar < CURVE_ORDER:
            return scalar
    raise RuntimeError("cinejoy: failed to derive ephemeral scalar")


def _build_request_aad(key_id: int, ephemeral_public: bytes) -> bytes:
    return _PREFIX + bytes([0, 1, key_id]) + ephemeral_public


def _derive_direction_key(shared: bytes, ephemeral_public: bytes, info: bytes) -> bytes:
    return hkdf_derive(ephemeral_public, shared, info, 32)


def seal_request(plain: bytes, nonce: bytes | None = None, key_id: int = _DEFAULT_KEY_ID) -> dict:
    """Seal a request; returns response_key, key_id, ephemeral_public, body."""
    if key_id not in SERVER_PUBLIC_KEYS:
        raise ValueError(f"unknown cinejoy server key_id {key_id}")

    if nonce is None:
        nonce = secrets.token_bytes(_NONCE_LEN)
    if len(nonce) != _NONCE_LEN:
        raise ValueError(f"nonce must be {_NONCE_LEN} bytes")

    scalar = derive_ephemeral_scalar(nonce)
    private_key, ephemeral_public = generate_keypair_from_scalar(scalar)
    shared = shared_secret(private_key, key_id)

    c2s_key = _derive_direction_key(shared, ephemeral_public, _C2S_INFO)
    s2c_key = _derive_direction_key(shared, ephemeral_public, _S2C_INFO)

    iv = nonce[32:44]
    aad = _build_request_aad(key_id, ephemeral_public)
    ciphertext = aes_gcm_encrypt(c2s_key, iv, plain, aad)

    body = bytes([0x02, key_id, 0x04]) + ephemeral_public[1:] + iv + ciphertext
    if len(body) <= 67:
        raise RuntimeError("cinejoy: sealed body too short")

    return {
        "response_key": s2c_key,
        "key_id": key_id,
        "ephemeral_public": ephemeral_public,
        "body": body,
    }
