"""Regression: deterministic build + validation invariants (WO §94/§121).

Builds the dictionary twice into temp dirs and asserts byte-identical artifacts,
and asserts the recorded golden SHAs are reproduced. If the golden SHAs change,
the seed changed — that is an intentional-change signal, not a flaky test.
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "tools", "search_dict", "build_dictionary.py")

GOLDEN = {
    "TAI_TERM_MASTER_v1.tsv":
        "44bb8b6c3f9245dad230443ecd9c7f25e25fbede124b352e80fe020d1d6afc12",
    "TAI_TERM_RELATIONS_v1.tsv":
        "7c8356b491b0b9b9e6fce215ea374ed82ceeef21c507c73f2686488331c7793c",
    "TAI_SEARCH_RUNTIME_PROJECTION_v1.json":
        "5d6359f7afd3011e79e9069fc4d15fec4b4ec95253014f07b6c0a8687db794db",
    "TAI_KIWI_TERMS_v1.tsv":
        "96654eed6ba9cf93a8efe973a60d052f7021b4f1115ca25775a5d7a4eec8e987",
    "TAI_KIWI_USER_DICTIONARY_v1.txt":
        "953d67104e912980ae06afaa752d215bda81dbd22df08306044a79e044ed9a01",
}


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _build(outdir):
    subprocess.run([sys.executable, BUILD, "build", outdir], check=True,
                   cwd=ROOT, capture_output=True)


def test_validate_passes():
    r = subprocess.run([sys.executable, BUILD, "validate"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "VALIDATION PASS" in r.stdout


def test_build_is_byte_deterministic(tmp_path):
    d1 = tmp_path / "r1"
    d2 = tmp_path / "r2"
    d1.mkdir()
    d2.mkdir()
    _build(str(d1))
    _build(str(d2))
    for name in GOLDEN:
        assert _sha(str(d1 / name)) == _sha(str(d2 / name)), name


def test_build_matches_golden_sha(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _build(str(d))
    for name, sha in GOLDEN.items():
        assert _sha(str(d / name)) == sha, f"{name} drifted from golden"
