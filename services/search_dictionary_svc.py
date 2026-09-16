"""services.search_dictionary_svc — dictionary metadata / census surface.

MASTER-WO-TAI-SEARCH-DICT-001. Read-only metadata about the compiled dictionary.
Never writes to any production DB (HARD STOP). Build/validation is performed by
tools/search_dict/build_dictionary.py as an offline, deterministic step; this
service only reports the compiled result that ships with the runtime projection.
"""
from __future__ import annotations

import os

from services.search_query_svc import _get_engine, SearchDictError  # noqa: F401

_ARTIFACT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "search_dict", "artifacts",
)
_SHA_MANIFEST = os.path.join(_ARTIFACT_DIR, "BUILD_SHA256SUMS.txt")


def census() -> dict:
    eng = _get_engine()
    by_type: dict[str, int] = {}
    for s in eng.subjects:
        for t in s["terms"]:
            if t.get("non_production"):
                continue
            by_type[t["term_type"]] = by_type.get(t["term_type"], 0) + 1
    manifest = {}
    if os.path.exists(_SHA_MANIFEST):
        with open(_SHA_MANIFEST, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    sha, _, name = line.partition("  ")
                    manifest[name] = sha
    return {
        "snapshot": eng.snapshot,
        "subjects": len(eng.subjects),
        "term_type_distribution": dict(sorted(by_type.items())),
        "build_sha256": manifest,
    }
