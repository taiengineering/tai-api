#!/usr/bin/env python3
"""Build the TAI search-dictionary runtime projection during image build.

WO-TAI-SHARED-SEARCH-001 remediation for RC-A (projection artifact not
tracked in repo; production /search-dict/* returns HTTP 503).

Wraps `tools/search_dict/build_dictionary.py build` and copies exactly
the two runtime files the service needs into the target dir:

    TAI_SEARCH_RUNTIME_PROJECTION_v1.json   (services/search_query_svc.py:30)
    TAI_KIWI_USER_DICTIONARY_v1.txt         (services/search_query_svc.py:38)

Deterministic — same input tree yields byte-identical output. The
expected SHA is pinned in tools/search_dict/artifacts/BUILD_SHA256SUMS.txt.
This helper verifies that both files' SHAs match the manifest before
copying; a mismatch aborts the build with a non-zero exit.

The upstream BUILD_SHA256SUMS.txt on disk is NOT overwritten — it
carries commentary and extract-input SHAs that the raw build does not
emit.

Usage (from repo root):

    python3 scripts/build_search_dict_runtime.py \
        --outdir tools/search_dict/artifacts \
        --tmpdir /tmp/tai-search-dict-build \
        --seed   seed_v2
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


RUNTIME_FILES = (
    "TAI_SEARCH_RUNTIME_PROJECTION_v1.json",
    "TAI_KIWI_USER_DICTIONARY_v1.txt",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_manifest(manifest_path: Path) -> dict[str, str]:
    """Return {filename: sha256} for lines that look like `<sha>  <name>`."""
    expected: dict[str, str] = {}
    if not manifest_path.exists():
        return expected
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 1)
        if len(parts) != 2:
            continue
        sha, name = parts[0], parts[1].strip()
        # manifest lists relative paths; keep just the basename.
        expected[name.split("/")[-1]] = sha
    return expected


def build_runtime(outdir: Path, tmpdir: Path, seed: str) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    build_dictionary = repo_root / "tools" / "search_dict" / "build_dictionary.py"
    if not build_dictionary.exists():
        print(f"ERROR: {build_dictionary} not found", file=sys.stderr)
        return 2

    # Manifest lives at the canonical repo path regardless of where the
    # runtime files are written to. During Docker build this happens
    # to be the same as outdir, but local `--outdir /tmp/...` runs
    # still get real verification.
    manifest_path = repo_root / "tools" / "search_dict" / "artifacts" / "BUILD_SHA256SUMS.txt"
    expected = _parse_manifest(manifest_path)
    for fn in RUNTIME_FILES:
        if fn not in expected:
            print(f"WARN: no expected SHA for {fn} in manifest; verification skipped for it",
                  file=sys.stderr)

    tmpdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["SEARCH_DICT_SEED"] = seed
    print(f"[build] seed={seed} outdir={outdir} tmpdir={tmpdir}")
    r = subprocess.run(
        [sys.executable, str(build_dictionary), "build", str(tmpdir)],
        cwd=str(repo_root), env=env,
    )
    if r.returncode != 0:
        print(f"ERROR: build_dictionary exited {r.returncode}", file=sys.stderr)
        return r.returncode

    outdir.mkdir(parents=True, exist_ok=True)
    for fn in RUNTIME_FILES:
        src = tmpdir / fn
        if not src.exists():
            print(f"ERROR: build did not produce {src}", file=sys.stderr)
            return 3
        got = _sha256(src)
        exp = expected.get(fn)
        if exp is not None and exp != got:
            print(f"ERROR: SHA mismatch for {fn}: got {got} expected {exp}",
                  file=sys.stderr)
            return 4
        dst = outdir / fn
        shutil.copyfile(src, dst)
        print(f"[copy] {fn}  sha256={got[:12]}...  → {dst}")

    print("[ok] runtime projection + kiwi dict written; BUILD_SHA256SUMS.txt untouched")
    return 0


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--outdir", default="tools/search_dict/artifacts",
                   help="Where to place the two runtime files.")
    p.add_argument("--tmpdir", default="/tmp/tai-search-dict-build",
                   help="Scratch dir for the full build output set.")
    p.add_argument("--seed", default="seed_v2",
                   help="SEARCH_DICT_SEED module name.")
    args = p.parse_args(argv)
    return build_runtime(Path(args.outdir).resolve(),
                         Path(args.tmpdir).resolve(),
                         args.seed)


if __name__ == "__main__":
    sys.exit(main())
