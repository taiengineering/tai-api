"""Regression: deterministic build + validation invariants (WO §94/§121).

Builds the dictionary twice into temp dirs and asserts byte-identical artifacts,
and asserts the recorded golden SHAs are reproduced. If the golden SHAs change,
the seed changed — that is an intentional-change signal, not a flaky test.

Seed-aware: honors SEARCH_DICT_SEED env (default seed_v1); each seed has its
own golden SHA set. seed_v2 goldens are also mirrored in
tools/search_dict/artifacts/BUILD_SHA256SUMS.txt and are the authoritative
snapshot for SEARCH-DICT-LEGPROD-2026-09-16.
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "tools", "search_dict", "build_dictionary.py")

GOLDEN_BY_SEED = {
    "seed_v1": {
        "TAI_TERM_MASTER_v1.tsv":
            "44bb8b6c3f9245dad230443ecd9c7f25e25fbede124b352e80fe020d1d6afc12",
        "TAI_TERM_RELATIONS_v1.tsv":
            "7c8356b491b0b9b9e6fce215ea374ed82ceeef21c507c73f2686488331c7793c",
        "TAI_SEARCH_RUNTIME_PROJECTION_v1.json":
            "6bc0450767e3b12b0c8ef6798e1a2ab619356ac9f9912bc3448443d904103008",
        "TAI_KIWI_TERMS_v1.tsv":
            "96654eed6ba9cf93a8efe973a60d052f7021b4f1115ca25775a5d7a4eec8e987",
        "TAI_KIWI_USER_DICTIONARY_v1.txt":
            "953d67104e912980ae06afaa752d215bda81dbd22df08306044a79e044ed9a01",
    },
    "seed_v2": {
        "TAI_TERM_MASTER_v1.tsv":
            "236b3288fda16662bb5cdb1cad096e2e48ad97fb9800b1645241369591f7cb6c",
        "TAI_TERM_RELATIONS_v1.tsv":
            "2395054b487303ac455f66fc6f753fdf93e97b442463a61dc490558a4349b444",
        "TAI_SEARCH_RUNTIME_PROJECTION_v1.json":
            "104f04bb96b2b708dfd734fc73519b59bbc0f24525f7a90ba089a18e5edf0ace",
        "TAI_KIWI_TERMS_v1.tsv":
            "20e48580904e769a1d1473673459de39c2cd6e4a91979534cea17df6101a07e6",
        "TAI_KIWI_USER_DICTIONARY_v1.txt":
            "780213e9eaf5fe3f5741aae01b06a3609fcd693632ded26753e1b4715bb4c469",
    },
}
SEED = os.environ.get("SEARCH_DICT_SEED", "seed_v1")
GOLDEN = GOLDEN_BY_SEED[SEED]


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
        assert _sha(str(d / name)) == sha, (
            f"{name} drifted from {SEED} golden"
        )
