"""SEED-128-CBC roundtrip (cryptography)."""
import base64

from utils.seed_cipher import seed_cbc_decrypt, seed_cbc_encrypt


def test_seed_roundtrip():
    key = base64.b64decode("LgqoiwzrCXTSm8/DE70f0Q==")
    iv = b"SASKGINICIS00000"
    plain = "Hong Gildong".encode("utf-8")
    enc = seed_cbc_encrypt(key, iv, plain)
    out = seed_cbc_decrypt(key, iv, enc)
    assert out == plain
