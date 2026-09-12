# -*- coding: utf-8 -*-
"""Bundled crypto for Cinejoy (no external pip dependencies)."""

import os
import sys

_CRYPTO_DIR = os.path.dirname(os.path.abspath(__file__))
if _CRYPTO_DIR not in sys.path:
    sys.path.insert(0, _CRYPTO_DIR)

from providerModules.a4kEmbeds.crypto.aes_gcm import decrypt as aes_gcm_decrypt
from providerModules.a4kEmbeds.crypto.aes_gcm import encrypt as aes_gcm_encrypt

__all__ = ["aes_gcm_decrypt", "aes_gcm_encrypt"]
