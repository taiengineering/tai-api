"""
SEED-128-CBC 복호화 — cryptography (algorithms.SEED) 사용.
"""
from __future__ import annotations

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def seed_cbc_decrypt(key: bytes, iv: bytes, encrypted: bytes) -> bytes:
    """SEED-128-CBC 복호화 + PKCS5 언패딩."""
    if len(key) != 16:
        raise ValueError("SEED key must be 16 bytes")
    if len(iv) != 16:
        raise ValueError("SEED IV must be 16 bytes")
    cipher = Cipher(algorithms.SEED(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted) + decryptor.finalize()
    return _pkcs5_unpad(decrypted)


def seed_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """SEED-128-CBC 암호화 + PKCS5 패딩."""
    padded = _pkcs5_pad(plaintext)
    cipher = Cipher(algorithms.SEED(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _pkcs5_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        return data
    return data[:-pad_len]


def _pkcs5_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)
