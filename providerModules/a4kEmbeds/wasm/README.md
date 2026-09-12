# Cinejoy seal (pure Python)

`seal_request` is implemented in `seal_pure.py` using vendored crypto only:

- P-256 ECDH (`crypto/ecdh_p256.py` + vendored `python-ecdsa`)
- HKDF-SHA256 (`crypto/hkdf.py`)
- AES-GCM encrypt (`crypto/aes_gcm.py` + vendored `pyaes`)

`crush_seal.py` is a thin wrapper exported to `cinejoy_api.py`.

Dev-only wasmtime oracle: `scripts/crush_oracle.py` + `scripts/crush.wasm`.
