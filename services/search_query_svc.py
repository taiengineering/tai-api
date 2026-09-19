"""services.search_query_svc — lexical search over the compiled projection.

MASTER-WO-TAI-SEARCH-DICT-001 §49-63. Thin service layer over the
runtime-independent core in tools/search_dict/search_core.py.

Production tiers (T1-T3) are deterministic and offline-verified. Kiwi (T4) and
pg_trgm (T6) are runtime-injected via the ext module (WO-2 R3). When their
dependencies are absent the service returns the deterministic tiers only and
reports which tiers ran, rather than fabricating token/trigram results
(WO §71/§73).

Tier priority (WO §63, extended by WO-2 R3):
  EXACT > NORMALIZED_EXACT > PUNCTUATION > ABBREVIATION/ALIAS >
  SYNONYM > TOKEN > TRIGRAM
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from tools.search_dict import search_core

_PROJECTION_PATH = os.environ.get(
    "TAI_SEARCH_PROJECTION",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "search_dict", "artifacts",
        "TAI_SEARCH_RUNTIME_PROJECTION_v1.json",
    ),
)
_KIWI_DICT_PATH = os.environ.get(
    "TAI_SEARCH_KIWI_DICT",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "search_dict", "artifacts",
        "TAI_KIWI_USER_DICTIONARY_v1.txt",
    ),
)
_SCRATCH_DSN = os.environ.get("TAI_SEARCH_SCRATCH_DSN")

_engine = None
_token_tier = None
_trigram_tier = None
_lock = threading.Lock()


class SearchDictError(Exception):
    """Typed service error -> mapped to HTTPException in the router."""


def _get_projection() -> dict[str, Any]:
    if not os.path.exists(_PROJECTION_PATH):
        raise SearchDictError(
            f"runtime projection not found: {_PROJECTION_PATH}")
    with open(_PROJECTION_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = search_core.SearchEngine(_get_projection())
    return _engine


def _get_token_tier():
    """Lazy-init TokenTier (Tier 4). Returns None if kiwipiepy unavailable.

    WO-TAI-SHARED-SEARCH-001 PATCH-1 §A: the Kiwi user dictionary is
    treated as a REQUIRED T4 runtime artifact under the SEARCH-01
    production contract. If the dictionary is absent T4 is
    explicitly disabled (token_tier=False) — deterministic tiers
    (T1/T2/T2b/T3) continue serving. Previously the code passed
    `user_dict_path=None` which let base Kiwi keep T4 nominally
    active, causing `/search-dict/health` to report `token_tier=true`
    even when the user dictionary was missing. That was a false-
    positive readiness signal for SEARCH-01 acceptance.
    """
    global _token_tier
    if _token_tier is not None or _token_tier is False:
        return _token_tier or None
    with _lock:
        if _token_tier is None:
            # Explicit dict-missing check happens BEFORE the try/except
            # so the failure mode is auditable rather than absorbed as
            # a generic Exception.
            if not os.path.exists(_KIWI_DICT_PATH):
                _token_tier = False  # sentinel: dict missing, T4 disabled
                return None
            try:
                from tools.search_dict import search_runtime_ext as EXT
                _token_tier = EXT.TokenTier(
                    _get_projection(), user_dict_path=_KIWI_DICT_PATH,
                )
            except Exception:
                _token_tier = False  # sentinel: attempted, unavailable
    return _token_tier or None


def _get_trigram_tier():
    """Lazy-init TrigramTier (Tier 6). Returns None if scratch DSN unset or
    connect fails. Guardrail: TrigramTier itself refuses leg-prod DSN."""
    global _trigram_tier
    if _trigram_tier is not None or _trigram_tier is False:
        return _trigram_tier or None
    if not _SCRATCH_DSN:
        _trigram_tier = False
        return None
    with _lock:
        if _trigram_tier is None:
            try:
                from tools.search_dict import search_runtime_ext as EXT
                _trigram_tier = EXT.TrigramTier(_get_projection(), dsn=_SCRATCH_DSN)
            except Exception:
                _trigram_tier = False
    return _trigram_tier or None


# Tier priority (higher score wins). Mirrors search_core.MATCH_SCORE but with
# TOKEN and TRIGRAM below all deterministic tiers so an EXACT/NORMALIZED_EXACT/
# PUNCTUATION/ABBREVIATION hit always outranks a fuzzy fallback.
_FALLBACK_TOKEN_BASE = search_core.MATCH_SCORE["TOKEN"]      # 40
_FALLBACK_TRIGRAM_BASE = search_core.MATCH_SCORE["TRIGRAM"]  # 20


def lookup(q: str, limit: int = 10, subject_type: str | None = None) -> dict:
    if not q or not q.strip():
        raise SearchDictError("query 'q' is required")
    if limit < 1 or limit > 100:
        raise SearchDictError("limit must be between 1 and 100")
    eng = _get_engine()
    result = eng.search(q, limit=limit, subject_type=subject_type)
    items = list(result["items"])
    seen = {(it["subject_type"], it["subject_key"]) for it in items}

    active_tiers = ["T1_EXACT", "T2_NORMALIZED_EXACT", "T2b_PUNCTUATION",
                    "T3_EXPANSION"]

    # T4 (Kiwi TOKEN) — invoke when core didn't already fill `limit` results.
    # We over-emit up to limit*2 so the final rerank can pick winners across
    # tiers (WO-2 verification follow-up: always give TRIGRAM a chance to
    # rescue TYPO cases where TOKEN emits weak overlaps).
    if len(items) < limit:
        tok = _get_token_tier()
        if tok is not None:
            active_tiers.append("T4_KIWI_TOKEN")
            for c in tok.candidates(q, min_overlap=1):
                key = (c["subject_type"], c["subject_key"])
                if key in seen:
                    continue
                if subject_type and c["subject_type"] != subject_type:
                    continue
                items.append({
                    "subject_type": c["subject_type"],
                    "subject_key": c["subject_key"],
                    "display_name": c["subject_key"],
                    "matched_term": c["matched_term"],
                    "match_type": "TOKEN",
                    "score": _FALLBACK_TOKEN_BASE + c.get("score", c["overlap"]),
                })
                seen.add(key)
                if len(items) >= limit * 2:
                    break

    # T6 (pg_trgm) — ALWAYS invoke when scratch DSN is present. Even if TOKEN
    # filled the slots, a strong-sim TRIGRAM can outrank a weak TOKEN on the
    # final score-based rerank (WO-2 verification follow-up).
    trg = _get_trigram_tier()
    if trg is not None:
        active_tiers.append("T6_TRIGRAM")
        for c in trg.candidates(q, limit=limit):
            key = (c["subject_type"], c["subject_key"])
            if key in seen:
                continue
            if subject_type and c["subject_type"] != subject_type:
                continue
            items.append({
                "subject_type": c["subject_type"],
                "subject_key": c["subject_key"],
                "display_name": c["subject_key"],
                "matched_term": c["matched_term"],
                "match_type": "TRIGRAM",
                # Rebalanced multiplier (WO-2 verification follow-up):
                # base 30 + sim*50 → range 30..80. Strong-sim TRIGRAM
                # (sim>=0.44) beats weak TOKEN (overlap=2, ~42) and even
                # equal_compact TOKEN (~52) when sim>=0.5. Rescues cases
                # where Kiwi mistokenization inflates TOKEN score
                # (e.g., "건축본법" → noun-concat "건축법" spuriously
                # equal to subject `건축법`). For correct MORPHOLOGY hits,
                # TRIGRAM's top candidate is usually the same subject.
                "score": 30 + int(c["similarity"] * 50),
            })
            seen.add(key)

    items.sort(key=lambda x: (-x["score"], x["subject_key"]))
    result["items"] = items[:limit]
    result["active_tiers"] = active_tiers
    return result


def lookup_deterministic(
    q: str,
    limit: int = 20,
    subject_type: str | None = None,
) -> dict:
    """Deterministic-only dictionary lookup — no Kiwi, no pg_trgm.

    WO-TAI-SHARED-SEARCH-F3 §16.  Used by Shared Search runtime only.
    Returns the same dict shape as ``lookup()`` but restricted to
    tiers T1-T3 (EXACT, NORMALIZED_EXACT, PUNCTUATION, approved
    expansions).  Kiwi TOKEN and TRIGRAM are intentionally excluded.

    Existing ``lookup()`` is unchanged for legacy consumers.

    Returned match_type values will be a subset of:
        EXACT / NORMALIZED_EXACT / PUNCTUATION /
        ABBREVIATION_OF / SPACING_VARIANT_OF / PUNCTUATION_VARIANT_OF /
        SPELLING_VARIANT_OF / ENGLISH_OF / EXACT_ALIAS / SYNONYM_OF
    """
    if not q or not q.strip():
        raise SearchDictError("query 'q' is required")
    if limit < 1 or limit > 100:
        raise SearchDictError("limit must be between 1 and 100")
    eng = _get_engine()
    result = eng.search(q, limit=limit, subject_type=subject_type)
    items = list(result["items"])
    result["items"] = items
    result["active_tiers"] = ["T1_EXACT", "T2_NORMALIZED_EXACT",
                               "T2b_PUNCTUATION", "T3_EXPANSION"]
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
        "token_tier": _get_token_tier() is not None,
        "trigram_tier": _get_trigram_tier() is not None,
    }
