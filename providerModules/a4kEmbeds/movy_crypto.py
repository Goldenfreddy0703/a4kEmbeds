# -*- coding: utf-8 -*-
"""Decrypt api.wecollege.net enc=2 source payloads (movy.sx)."""

from __future__ import annotations

import base64

_SHA = [
    0x428A2F98,
    0x71374491,
    0xB5C0FBCF,
    0xE9B5DBA5,
    0x3956C25B,
    0x59F111F1,
    0x923F82A4,
    0xAB1C5ED5,
    0xD807AA98,
    0x12835B01,
    0x243185BE,
    0x550C7DC3,
    0x72BE5D74,
    0x80DEB1FE,
    0x9BDC06A7,
    0xC19BF174,
]
_MAGIC = bytes([109, 118, 109, 49])  # mvm1


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return _u32(a * b)


def _signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value & 0x80000000:
        return value - 0x100000000
    return value


def _final_mix(value: int) -> int:
    value = _u32(value)
    value ^= value >> 16
    value = _imul(value, 0x85EBCA6B)
    value ^= value >> 13
    value = _imul(value, 0xC2B2AE35)
    value ^= value >> 16
    return _u32(value)


def _js_rotate(value: int, bits: int) -> int:
    value = _u32(value)
    bits &= 31
    if bits == 0:
        return value
    left = _u32(_signed32(value) << bits)
    return _u32(left | (value >> (32 - bits)))


def _l_predicate(index: int) -> bool:
    return (index * (index + 1) & 1) == 0


def _rc4_sbox(key: str) -> list[int]:
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + ord(key[i % len(key)])) & 255
        state[i], state[j] = state[j], state[i]
    return state


def _seed_acc_rc4(seed: str) -> int:
    acc = 0x67452301
    for index, ch in enumerate(seed):
        acc = _js_rotate(_u32(acc ^ _imul(ord(ch), _SHA[index & 15])), 5)
    return _final_mix(acc)


def _fnv1a(seed: str) -> int:
    acc = 0x811C9DC5
    for ch in seed:
        acc = _imul(acc ^ ord(ch), 0x1000193)
    return _final_mix(acc)


def _init_state(seed: str, media_id: int) -> tuple[dict[int, int] | list[int], int]:
    length = len(seed)
    if (length * (length + 1) & 1) == 1:
        return _rc4_sbox(seed), _seed_acc_rc4(seed)

    table: dict[int, int] = {}
    rolling = _final_mix(_fnv1a(seed) ^ _final_mix(_u32(media_id) ^ 0x9E3779B9))
    for index in range(8):
        if _l_predicate(index):
            slot = rolling % 61
            rolling = _js_rotate(_u32(rolling + 0x9E3779B9), 7 + (7 & index))
            table[slot] = _u32(rolling ^ _final_mix(rolling))
            rolling = _final_mix(_u32(rolling + slot))
        else:
            table[index] = _SHA[index & 15]
    return table, _final_mix(0xA5A5A5A5 ^ rolling)


def _next_word(state: dict[int, int] | list[int], acc: int, counter: int) -> int:
    slot = acc % 61
    if isinstance(state, list):
        base = state[slot]
        in_slot = True
    else:
        base = state.get(slot, 0)
        in_slot = slot in state
    mixed = _imul(0x9E3779B9, counter + 1)
    xor_term = base ^ mixed
    if in_slot:
        word = _u32(acc | xor_term)
    else:
        word = _u32(acc ^ xor_term)
    word = _js_rotate(_u32(word + acc), slot & 31) ^ _js_rotate(
        acc, 31 & _imul(slot, 7)
    )
    acc = _final_mix(_u32(word + 0x9E3779B9))
    state[slot] = acc
    return acc


def _keystream(seed: str, media_id: int, length: int) -> bytes:
    state, acc = _init_state(seed, media_id)
    out = bytearray()
    counter = 0
    while len(out) < length:
        acc = _next_word(state, acc, counter)
        counter += 1
        out.append(acc & 255)
        if len(out) < length:
            out.append((acc >> 8) & 255)
        if len(out) < length:
            out.append((acc >> 16) & 255)
        if len(out) < length:
            out.append((acc >> 24) & 255)
    return bytes(out)


def _b64url_decode(payload: str) -> bytes:
    padded = payload.replace("-", "+").replace("_", "/")
    pad_len = 4 * ((len(padded) + 3) // 4)
    padded = padded.ljust(pad_len, "=")
    return base64.b64decode(padded)


def decrypt_sources(payload: str, seed: str, media_id: int) -> str:
    data = bytearray(_b64url_decode(payload))
    stream = _keystream(seed, media_id, len(data))
    for index, value in enumerate(stream):
        data[index] ^= value
    if bytes(data[:4]) != _MAGIC:
        raise ValueError("movy: decrypt failed (bad seed or tampered payload)")
    return bytes(data[4:]).decode("utf-8")
