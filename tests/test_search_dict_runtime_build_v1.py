"""WO-TAI-SHARED-SEARCH-001 — smoke tests for the runtime build helper.

The helper (`scripts/build_search_dict_runtime.py`) is what the
Dockerfile now runs during image build to produce the runtime
projection + Kiwi user dictionary. These tests verify:

  1. deterministic build yields the two runtime files
  2. their SHAs match `BUILD_SHA256SUMS.txt` (the pinned manifest)
  3. the service can `health()` and `lookup()` against the produced
     projection (MSDS → CHEM_TERM/물질안전보건자료 EXACT)
  4. Kiwi optional tier degrades gracefully when the dict is absent
"""
from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "build_search_dict_runtime.py"
MANIFEST = REPO_ROOT / "tools" / "search_dict" / "artifacts" / "BUILD_SHA256SUMS.txt"


def _expected_shas() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 1)
        if len(parts) != 2:
            continue
        sha, name = parts[0], parts[1].strip().split("/")[-1]
        out[name] = sha
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def built_dir(tmp_path_factory):
    """Run the helper once per test module."""
    outdir = tmp_path_factory.mktemp("search-dict-runtime-out")
    tmpdir = tmp_path_factory.mktemp("search-dict-runtime-tmp")
    r = subprocess.run(
        [sys.executable, str(HELPER),
         "--outdir", str(outdir),
         "--tmpdir", str(tmpdir),
         "--seed", "seed_v2"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, (
        f"build helper failed rc={r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    return outdir


def test_helper_produces_two_runtime_files(built_dir):
    assert (built_dir / "TAI_SEARCH_RUNTIME_PROJECTION_v1.json").exists()
    assert (built_dir / "TAI_KIWI_USER_DICTIONARY_v1.txt").exists()


def test_helper_output_matches_pinned_manifest(built_dir):
    """SHA of both runtime files must equal the values pinned in
    BUILD_SHA256SUMS.txt. Any drift = compiler regression = STOP."""
    expected = _expected_shas()
    for fn in ("TAI_SEARCH_RUNTIME_PROJECTION_v1.json",
               "TAI_KIWI_USER_DICTIONARY_v1.txt"):
        assert fn in expected, f"manifest missing entry for {fn}"
        got = _sha256(built_dir / fn)
        assert got == expected[fn], (
            f"SHA drift for {fn}: built={got} expected={expected[fn]}"
        )


def test_service_can_load_built_projection(built_dir, monkeypatch):
    """search_query_svc.health() must return the pinned snapshot id,
    correct subject count, and token_tier=True (Kiwi dict is present).
    """
    monkeypatch.setenv("TAI_SEARCH_PROJECTION",
                       str(built_dir / "TAI_SEARCH_RUNTIME_PROJECTION_v1.json"))
    monkeypatch.setenv("TAI_SEARCH_KIWI_DICT",
                       str(built_dir / "TAI_KIWI_USER_DICTIONARY_v1.txt"))
    monkeypatch.delenv("TAI_SEARCH_SCRATCH_DSN", raising=False)

    # Reload the module so it picks up the env vars.
    if "services.search_query_svc" in sys.modules:
        del sys.modules["services.search_query_svc"]
    svc = importlib.import_module("services.search_query_svc")

    h = svc.health()
    assert h["snapshot"] == "SEARCH-DICT-LEGPROD-2026-09-16"
    assert h["subjects"] == 471
    # token_tier should be True when the Kiwi dict is present AND
    # kiwipiepy is importable. requirements.txt pins kiwipiepy, so
    # this is production-representative.
    assert h["token_tier"] is True
    # trigram_tier must be False when SCRATCH_DSN is unset — never a 503 cause.
    assert h["trigram_tier"] is False


def test_msds_lookup_hits_chem_term_exact(built_dir, monkeypatch):
    """MSDS query against CHEM_TERM subject_type must return the
    물질안전보건자료 subject as an EXACT match (CHEM-06 gate)."""
    monkeypatch.setenv("TAI_SEARCH_PROJECTION",
                       str(built_dir / "TAI_SEARCH_RUNTIME_PROJECTION_v1.json"))
    monkeypatch.setenv("TAI_SEARCH_KIWI_DICT",
                       str(built_dir / "TAI_KIWI_USER_DICTIONARY_v1.txt"))
    monkeypatch.delenv("TAI_SEARCH_SCRATCH_DSN", raising=False)

    if "services.search_query_svc" in sys.modules:
        del sys.modules["services.search_query_svc"]
    svc = importlib.import_module("services.search_query_svc")

    r = svc.lookup("MSDS", limit=3, subject_type="CHEM_TERM")
    hits = [it for it in r["items"] if it["subject_key"] == "물질안전보건자료"]
    assert hits, r
    assert hits[0]["match_type"] == "EXACT"


def test_missing_projection_raises_search_dict_error(monkeypatch, tmp_path):
    """Regression proof for the RC-A failure mode: pointing the env at
    a non-existent path must raise SearchDictError. The router turns
    that into HTTP 503. This is what production observed pre-fix."""
    monkeypatch.setenv("TAI_SEARCH_PROJECTION",
                       str(tmp_path / "does_not_exist.json"))
    monkeypatch.delenv("TAI_SEARCH_KIWI_DICT", raising=False)
    monkeypatch.delenv("TAI_SEARCH_SCRATCH_DSN", raising=False)

    if "services.search_query_svc" in sys.modules:
        del sys.modules["services.search_query_svc"]
    svc = importlib.import_module("services.search_query_svc")

    with pytest.raises(svc.SearchDictError):
        svc.health()


def test_kiwi_missing_dict_disables_t4(built_dir, monkeypatch, tmp_path):
    """PATCH-1 §A: if the Kiwi user dictionary is missing but the
    projection is present, T4 is explicitly disabled — no exception,
    no 503, but `token_tier=False`. Deterministic tiers must still
    function. Previously the code passed `user_dict_path=None` to
    `TokenTier` which let base Kiwi keep T4 nominally active — a
    false-positive readiness signal for SEARCH-01 acceptance."""
    monkeypatch.setenv("TAI_SEARCH_PROJECTION",
                       str(built_dir / "TAI_SEARCH_RUNTIME_PROJECTION_v1.json"))
    monkeypatch.setenv("TAI_SEARCH_KIWI_DICT",
                       str(tmp_path / "no-kiwi-dict.txt"))
    monkeypatch.delenv("TAI_SEARCH_SCRATCH_DSN", raising=False)

    if "services.search_query_svc" in sys.modules:
        del sys.modules["services.search_query_svc"]
    svc = importlib.import_module("services.search_query_svc")

    # health() must succeed — 503-triggering path is projection-missing,
    # not Kiwi-dict-missing.
    h = svc.health()
    assert h["snapshot"] == "SEARCH-DICT-LEGPROD-2026-09-16"
    # PATCH-1 §A: token_tier MUST report False when the user dictionary
    # is absent. This is the false-positive that PATCH-1 fixes.
    assert h["token_tier"] is False, h
    # And a deterministic (T1-T3) lookup still works.
    r = svc.lookup("MSDS", limit=3, subject_type="CHEM_TERM")
    assert any(it["subject_key"] == "물질안전보건자료" for it in r["items"]), r


def test_helper_fails_when_manifest_missing(tmp_path, monkeypatch):
    """PATCH-1 §B1: BUILD_SHA256SUMS.txt missing → helper returns
    non-zero. The Dockerfile RUN will abort image build."""
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    # Copy the compiler + normalize + seed into a fake repo layout so
    # `python3 tools/search_dict/build_dictionary.py build` still runs,
    # but with no BUILD_SHA256SUMS.txt in artifacts/.
    import shutil
    shutil.copytree(REPO_ROOT / "tools", fake_repo / "tools")
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    (fake_repo / "tools" / "search_dict" / "artifacts" / "BUILD_SHA256SUMS.txt").unlink()

    outdir = tmp_path / "out"
    tmpdir = tmp_path / "tmp"
    r = subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "build_search_dict_runtime.py"),
         "--outdir", str(outdir), "--tmpdir", str(tmpdir), "--seed", "seed_v2"],
        cwd=str(fake_repo), capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0, r.stdout
    assert "manifest not found" in (r.stdout + r.stderr).lower()


def test_helper_fails_when_manifest_missing_required_entry(tmp_path):
    """PATCH-1 §B2: BUILD_SHA256SUMS.txt exists but lacks a required
    runtime entry → helper returns non-zero. Canonical manifest in the
    real repo is NOT modified — the test operates on a fake repo copy.
    """
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    import shutil
    shutil.copytree(REPO_ROOT / "tools", fake_repo / "tools")
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    # Strip out the projection entry from the manifest.
    manifest = fake_repo / "tools" / "search_dict" / "artifacts" / "BUILD_SHA256SUMS.txt"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    kept = [l for l in lines if "TAI_SEARCH_RUNTIME_PROJECTION_v1.json" not in l]
    manifest.write_text("\n".join(kept) + "\n", encoding="utf-8")

    outdir = tmp_path / "out"
    tmpdir = tmp_path / "tmp"
    r = subprocess.run(
        [sys.executable, str(fake_repo / "scripts" / "build_search_dict_runtime.py"),
         "--outdir", str(outdir), "--tmpdir", str(tmpdir), "--seed", "seed_v2"],
        cwd=str(fake_repo), capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0, r.stdout
    msg = (r.stdout + r.stderr).lower()
    assert "missing required entries" in msg
    assert "tai_search_runtime_projection_v1.json" in msg
