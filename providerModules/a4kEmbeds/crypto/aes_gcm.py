# -*- coding: utf-8 -*-
"""Pure-Python AES-GCM decrypt (12-byte IV, 128-bit tag)."""

from __future__ import annotations

from providerModules.a4kEmbeds.crypto.pyaes.aes import AES

_BLOCK = 16
_TAG_LEN = 16


def _to_ints(data):
    return list(data)


def _from_ints(values):
    return bytes(values)


def _encrypt_block(aes, block):
    return _to_ints(aes.encrypt(_to_ints(block)))


def _xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _inc32(counter):
    out = bytearray(counter)
    carry = 1
    for index in range(15, 11, -1):
        value = out[index] + carry
        out[index] = value & 0xFF
        carry = value >> 8
        if not carry:
            break
    return bytes(out)


def _gf_mul_int(value, h_int):
    z = 0
    v = value
    for bit in range(128):
        if h_int & (1 << (127 - bit)):
            z ^= v
        if v & 1:
            v = (v >> 1) ^ 0xE1000000000000000000000000000000
        else:
            v >>= 1
    return z


def _ghash(h, data):
    h_int = int.from_bytes(h, "big")
    y = 0
    for offset in range(0, len(data), _BLOCK):
        block = data[offset : offset + _BLOCK]
        if len(block) < _BLOCK:
            block = block + b"\x00" * (_BLOCK - len(block))
        y ^= int.from_bytes(block, "big")
        y = _gf_mul_int(y, h_int)
    return y.to_bytes(_BLOCK, "big")


def _pad128(data):
    pad = (16 - (len(data) % 16)) % 16
    return data + b"\x00" * pad


def encrypt(key, iv, plaintext, aad=b""):
    """Encrypt with AES-GCM; returns ciphertext with 128-bit tag appended."""
    if len(iv) != 12:
        raise ValueError("cinejoy: GCM IV must be 12 bytes")

    aes = AES(key)
    h = _from_ints(aes.encrypt([0] * _BLOCK))
    j0 = iv + b"\x00\x00\x00\x01"

    ciphertext = bytearray()
    counter = j0
    for offset in range(0, len(plaintext), _BLOCK):
        counter = _inc32(counter)
        keystream = _from_ints(aes.encrypt(_to_ints(counter)))
        block = plaintext[offset : offset + _BLOCK]
        ciphertext.extend(_xor_bytes(block, keystream[: len(block)]))

    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    ghash_input = _pad128(aad) + _pad128(bytes(ciphertext)) + lengths
    s = _ghash(h, ghash_input)
    tag = _xor_bytes(s, _from_ints(aes.encrypt(_to_ints(j0))))
    return bytes(ciphertext) + tag


def decrypt(key, iv, ciphertext_with_tag, aad=b""):
    """Decrypt and verify AES-GCM ciphertext (tag appended)."""
    if len(iv) != 12:
        raise ValueError("cinejoy: GCM IV must be 12 bytes")
    if len(ciphertext_with_tag) < _TAG_LEN:
        raise ValueError("cinejoy: GCM ciphertext too short")

    tag = ciphertext_with_tag[-_TAG_LEN:]
    ciphertext = ciphertext_with_tag[:-_TAG_LEN]
    aes = AES(key)

    h = _from_ints(aes.encrypt([0] * _BLOCK))
    j0 = iv + b"\x00\x00\x00\x01"

    plain = bytearray()
    counter = j0
    for offset in range(0, len(ciphertext), _BLOCK):
        counter = _inc32(counter)
        keystream = _from_ints(aes.encrypt(_to_ints(counter)))
        block = ciphertext[offset : offset + _BLOCK]
        plain.extend(_xor_bytes(block, keystream[: len(block)]))

    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    ghash_input = _pad128(aad) + _pad128(ciphertext) + lengths
    s = _ghash(h, ghash_input)
    expected = _xor_bytes(s, _from_ints(aes.encrypt(_to_ints(j0))))

    if expected != tag:
        raise ValueError("cinejoy: GCM authentication failed")

    return bytes(plain)
