"""CHEM MSDS free-text search via the shared OpenSearch index.

Single DSL call replaces the N×M Supabase ilike loop in the search adapter.
Priority: NORMALIZED_EXACT(1000) > DICTIONARY_EXPANSION(100) > KIWI_TOKEN(10).

Each constant_score clause carries a named-query marker (_name) so the
response's matched_queries array can be used to attribute match_type to each
hit without a second round-trip.

Public API:
    search_by_q_os(plan, *, limit, offset, scope, _client=None) -> dict
        {"hits": [{"chem_id": str, "match_type": str, "matched_term": str}],
         "total": int}
"""
from __future__ import annotations

from typing import Any, Optional

from services.kosha_msds.search_adapter import (
    MATCH_DICTIONARY,
    MATCH_KIWI_TOKEN,
    MATCH_NORMALIZED_EXACT,
)
from services.shared_search.opensearch_client import (
    CURRENT_ALIAS,
    OpenSearchUnavailable,
    get_client,
)

# Cap total should-clauses to avoid query_too_large errors.
_MAX_CLAUSES = 30

# Named-query prefix tokens (split on ":" to recover them from matched_queries).
_PFX_NE = "NE"  # NORMALIZED_EXACT
_PFX_DE = "DE"  # DICTIONARY_EXPANSION
_PFX_KW = "KW"  # KIWI_TOKEN

_PFX_TO_MATCH_TYPE: dict[str, str] = {
    _PFX_NE: MATCH_NORMALIZED_EXACT,
    _PFX_DE: MATCH_DICTIONARY,
    _PFX_KW: MATCH_KIWI_TOKEN,
}


def _clause(term: str, name: str, boost: float) -> dict:
    """constant_score clause: term must match title or aliases (KO/EN fields)."""
    return {
        "constant_score": {
            "_name": name,
            "filter": {
                "bool": {
                    "should": [
                        {"term": {"title.raw": term}},
                        {"match": {"title": {"query": term, "analyzer": "tai_nori_search"}}},
                        {"term": {"aliases.raw": term}},
                        {"match": {"aliases": {"query": term, "analyzer": "tai_nori_search"}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "boost": boost,
        }
    }


def _build_dsl(plan: Any, *, from_: int, size: int) -> dict:
    """Build the OS request body for a CHEM free-text search."""
    clauses: list[dict] = []
    seen: set[str] = set()

    def _add(term: str, pfx: str, boost: float) -> None:
        t = (term or "").strip()
        if not t or t in seen or len(clauses) >= _MAX_CLAUSES:
            return
        seen.add(t)
        clauses.append(_clause(t, f"{pfx}:{t[:50]}", boost))

    _add(plan.normalized_query, _PFX_NE, 1000.0)
    for t in plan.expanded_terms or ():
        _add(t, _PFX_DE, 100.0)
    for t in plan.tokens or ():
        _add(t, _PFX_KW, 10.0)

    if not clauses:
        return {
            "query": {"match_none": {}},
            "from": from_,
            "size": size,
            "track_total_hits": True,
        }

    return {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"object_type": "CHEM"}},
                    {"term": {"publication_status": "PUBLISHED"}},
                    {"terms": {"visibility_scopes": ["PUBLIC"]}},
                ],
                "must": [
                    {"dis_max": {"queries": clauses}},
                ],
            }
        },
        "from": from_,
        "size": size,
        "track_total_hits": True,
    }


def _best_match(matched_queries: list[str], default_term: str) -> tuple[str, str]:
    """Return (match_type, matched_term) derived from OS named-query markers."""
    best_type = MATCH_KIWI_TOKEN
    best_term = default_term
    for mq in matched_queries or ():
        parts = mq.split(":", 1)
        if len(parts) != 2:
            continue
        pfx, term = parts
        mt = _PFX_TO_MATCH_TYPE.get(pfx)
        if mt is None:
            continue
        if mt == MATCH_NORMALIZED_EXACT:
            return mt, term
        if mt == MATCH_DICTIONARY and best_type == MATCH_KIWI_TOKEN:
            best_type, best_term = mt, term
    return best_type, best_term


def search_by_q_os(
    plan: Any,
    *,
    limit: int = 20,
    offset: int = 0,
    scope: Optional[str] = None,
    _client: Any = None,
) -> dict:
    """Execute a single OpenSearch query for CHEM free-text search.

    Args:
        plan:    SearchPlan from search_adapter.build_search_plan().
        limit:   Page size (passed as ``size`` to OS).
        offset:  Page offset (passed as ``from`` to OS).
        scope:   Publication scope hint (unused in the OS query itself;
                 scoped membership is enforced by the Supabase hydration step).
        _client: Injectable OpenSearch client for tests.

    Returns:
        {
          "hits": [{"chem_id": str, "match_type": str, "matched_term": str}],
          "total": int,
        }

    Raises:
        OpenSearchUnavailable: on connection or query failure.
    """
    dsl = _build_dsl(plan, from_=offset, size=limit)
    client = _client if _client is not None else get_client()

    try:
        resp = client.search(index=CURRENT_ALIAS, body=dsl)
    except OpenSearchUnavailable:
        raise
    except Exception as exc:
        raise OpenSearchUnavailable(f"CHEM OS search failed: {exc}") from exc

    hits_obj = resp.get("hits") or {}
    raw_hits: list[dict] = hits_obj.get("hits") or []
    total_obj = hits_obj.get("total") or {}
    total: int = (
        int(total_obj.get("value", 0))
        if isinstance(total_obj, dict)
        else int(total_obj or 0)
    )

    hits: list[dict] = []
    for h in raw_hits:
        src = h.get("_source") or {}
        chem_id: Optional[str] = src.get("source_key")  # 6-digit KOSHA chem_id
        if not chem_id:
            continue
        match_type, matched_term = _best_match(
            h.get("matched_queries") or [],
            plan.normalized_query,
        )
        hits.append({
            "chem_id": chem_id,
            "match_type": match_type,
            "matched_term": matched_term,
        })

    return {"hits": hits, "total": total}
