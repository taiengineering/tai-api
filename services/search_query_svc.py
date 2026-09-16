"""services.search_query_svc — lexical search over the compiled projection.

MASTER-WO-TAI-SEARCH-DICT-001 §49-63. Thin service layer over the
runtime-independent core in tools/search_dict/search_core.py.

Production tiers (T1-T3) are deterministic and offline-verified. Kiwi (T4) and
pg_trgm (T6) are runtime-injected hooks; when their dependencies are absent the
service returns the deterministic tiers only and reports which tiers ran, rather
than fabricating token/trigram results (WO §71/§73).
"""
from __future__ import annotations

import os
import threading

from tools.search_dict import search_core

_PROJECTION_PATH = os.environ.get(
    "TAI_SEARCH_PROJECTION",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "search_dict", "artifacts",
        "TAI_SEARCH_RUNTIME_PROJECTION_v1.json",
    ),
)

_engine = None
_lock = threading.Lock()


class SearchDictError(Exception):
    """Typed service error -> mapped to HTTPException in the router."""


def _get_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                if not os.path.exists(_PROJECTION_PATH):
                    raise SearchDictError(
                        f"runtime projection not found: {_PROJECTION_PATH}")
                _engine = search_core.load(_PROJECTION_PATH)
    return _engine


def lookup(q: str, limit: int = 10, subject_type: str | None = None) -> dict:
    if not q or not q.strip():
        raise SearchDictError("query 'q' is required")
    if limit < 1 or limit > 100:
        raise SearchDictError("limit must be between 1 and 100")
    eng = _get_engine()
    result = eng.search(q, limit=limit, subject_type=subject_type)
    # Report which tiers are active. T4/T6 only if runtime deps present.
    tiers = ["T1_EXACT", "T2_NORMALIZED_EXACT", "T3_EXPANSION"]
    try:
        import kiwipiepy  # noqa: F401
        tiers.append("T4_KIWI_TOKEN")
    except Exception:
        pass
    result["active_tiers"] = tiers
    return result


def health() -> dict:
    eng = _get_engine()
    n_terms = sum(
        1 for s in eng.subjects for t in s["terms"] if not t.get("non_production"))
    return {
        "snapshot": eng.snapshot,
        "subjects": len(eng.subjects),
        "indexed_terms": n_terms,
        "expansions": len(eng.expansions),
        "projection_path": _PROJECTION_PATH,
    }
