"""MSDS OpenSearch query adapter — WO-WWW-PERF-004-P0S-OS-IMPL-001.

Replaces Supabase display-view search paths that cause 57014 timeout.

Returns (chem_ids_page, total) for the caller's (limit, offset) window.
source_key = chem_id (6-digit KOSHA ID). Caller hydrates via
SupabaseMsdsReadStore.hydrate_chem_ids() — the P0-A fast path.

Priority for single-call params:
  chem_id > cas_no > ke_no > en_no > un_no > q/name_ko/name_en

track_total_hits=true breaks the 200-doc-per-tier cap inherited from
the shared SharedRetrievalEngine and gives accurate pagination totals.

CAS_NO NOTE: after STAGE 1 OS rebuild, CAS appears in aliases and
cas_no queries work. Until rebuild, cas_no returns 0 results (no
timeout, no crash — correct fail-closed behaviour).
"""
from __future__ import annotations

import logging
from typing import Optional

from services.shared_search.opensearch_client import CURRENT_ALIAS, get_client

logger = logging.getLogger(__name__)

_CHEM_BASE_FILTER: list[dict] = [
    {"term": {"publication_status": "PUBLISHED"}},
    {"term": {"visibility_scopes": "PUBLIC"}},
    {"term": {"object_type": "CHEM"}},
]

_MIN_CHEM_DOCS = 15_000  # snapshot gate minimum


def os_chem_available(client=None) -> bool:
    """Snapshot gate: True when OS has >= _MIN_CHEM_DOCS CHEM documents.

    Fail-soft: exceptions are caught and treated as unavailable so the
    caller can decide whether to fall back or raise 503.
    """
    try:
        if client is None:
            client = get_client()
        resp = client.count(
            index=CURRENT_ALIAS,
            body={"query": {"bool": {"filter": _CHEM_BASE_FILTER}}},
        )
        return int(resp.get("count", 0)) >= _MIN_CHEM_DOCS
    except Exception as exc:
        logger.warning("MSDS OS availability check failed: %s", exc)
        return False


def search_os(
    *,
    q: Optional[str] = None,
    chem_id: Optional[str] = None,
    cas_no: Optional[str] = None,
    ke_no: Optional[str] = None,
    en_no: Optional[str] = None,
    un_no: Optional[str] = None,
    name_ko: Optional[str] = None,
    name_en: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    client=None,
) -> tuple[list[str], int]:
    """Execute MSDS search against OpenSearch.

    Returns (ordered_chem_ids, total). Caller hydrates via P0-A.

    For identifier params (chem_id, cas_no, ke_no, en_no, un_no): exact
    keyword filter on source_key / aliases.raw. No scoring, sorted by
    source_key for determinism.

    For text params (q, name_ko, name_en): BM25 + Nori multi_match on
    title^5/aliases^4/search_text. Sorted by _score DESC, source_key ASC.

    track_total_hits=true ensures accurate totals beyond 10 000 hits.
    """
    if client is None:
        client = get_client()

    sort: list[dict]
    query_body: dict

    if chem_id:
        query_body = {
            "bool": {
                "filter": _CHEM_BASE_FILTER + [{"term": {"source_key": chem_id}}]
            }
        }
        sort = [{"source_key": "asc"}]
    elif cas_no:
        query_body = {
            "bool": {
                "filter": _CHEM_BASE_FILTER + [{"term": {"aliases.raw": cas_no}}]
            }
        }
        sort = [{"source_key": "asc"}]
    elif ke_no:
        query_body = {
            "bool": {
                "filter": _CHEM_BASE_FILTER + [{"term": {"aliases.raw": ke_no}}]
            }
        }
        sort = [{"source_key": "asc"}]
    elif en_no:
        query_body = {
            "bool": {
                "filter": _CHEM_BASE_FILTER + [{"term": {"aliases.raw": en_no}}]
            }
        }
        sort = [{"source_key": "asc"}]
    elif un_no:
        query_body = {
            "bool": {
                "filter": _CHEM_BASE_FILTER + [{"term": {"aliases.raw": un_no}}]
            }
        }
        sort = [{"source_key": "asc"}]
    else:
        text = (q or name_ko or name_en or "").strip()
        if not text:
            query_body = {"bool": {"filter": _CHEM_BASE_FILTER}}
            sort = [{"source_key": "asc"}]
        else:
            query_body = {
                "bool": {
                    "filter": _CHEM_BASE_FILTER,
                    "must": [{
                        "multi_match": {
                            "query": text,
                            "fields": ["title^5", "aliases^4", "search_text"],
                            "type": "best_fields",
                            "analyzer": "tai_nori_search",
                        }
                    }],
                }
            }
            sort = [{"_score": "desc"}, {"source_key": "asc"}]

    body: dict = {
        "query": query_body,
        "sort": sort,
        "from": offset,
        "size": limit,
        "track_total_hits": True,
        "_source": ["source_key"],
    }

    resp = client.search(index=CURRENT_ALIAS, body=body)
    hits_obj = resp.get("hits") or {}
    total_raw = hits_obj.get("total") or {}
    total = (
        total_raw.get("value", 0)
        if isinstance(total_raw, dict)
        else int(total_raw or 0)
    )
    source_keys = [
        (h.get("_source") or {}).get("source_key", "")
        for h in (hits_obj.get("hits") or [])
    ]
    return [sk for sk in source_keys if sk], total
