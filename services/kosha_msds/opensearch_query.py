"""MSDS OpenSearch query adapter — WO-WWW-PERF-004-P0S.

PATCH-01~06: WO-WWW-PERF-004-P0S-OS-PATCH-001.

source_key = chem_id (6-digit KOSHA ID). Caller hydrates via
SupabaseMsdsReadStore.hydrate_chem_ids() — the P0-A fast path.

Snapshot gate (PATCH-02): check_snapshot_gate() compares OS CHEM doc
count against DB kosha_msds_seo_preview_current count. Cached 5 min.
Raises MsdsSnapshotGateError on divergence or lookup failure (fail-closed).

CAS gate (PATCH-03): KOSHA_MSDS_CAS_INDEX_READY env var (default false)
gates cas_no queries. Until OS is rebuilt with CAS in aliases, cas_no
requests return MsdsCasIndexNotReadyError → 503 instead of silently
returning 0 results.

AND filters (PATCH-04): all structured params combined as AND filter
clauses — no if/elif priority chain.

Search semantics (PATCH-05):
  - name_ko/name_en: Nori match on title; sorted source_key ASC
  - q: BM25 multi_match on title^5/aliases^4/search_text; sorted _score DESC

Deep pagination guard (PATCH-06): offset + limit > _DEEP_PAGINATION_LIMIT
(9,900) raises MsdsPaginationDepthExceededError — stays within OS default
max_result_window=10,000.

track_total_hits=true gives accurate pagination totals.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from services.shared_search.opensearch_client import CURRENT_ALIAS, get_client

logger = logging.getLogger(__name__)

_CHEM_BASE_FILTER: list[dict] = [
    {"term": {"publication_status": "PUBLISHED"}},
    {"term": {"visibility_scopes": "PUBLIC"}},
    {"term": {"object_type": "CHEM"}},
]

_DEEP_PAGINATION_LIMIT = 9_900
_SNAPSHOT_CACHE_TTL = 300        # 5 minutes
_SNAPSHOT_COUNT_TOLERANCE = 50   # allow ±50 docs during re-index window
_CAS_INDEX_ENV_VAR = "KOSHA_MSDS_CAS_INDEX_READY"


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class MsdsOsError(Exception):
    """Base for MSDS OpenSearch-path errors. All subclasses map to 503."""


class MsdsSnapshotGateError(MsdsOsError):
    """OS CHEM count diverges from DB, or either lookup failed (fail-closed)."""


class MsdsCasIndexNotReadyError(MsdsOsError):
    """CAS alias index not yet rebuilt; queries must be rejected until ready."""


class MsdsPaginationDepthExceededError(MsdsOsError):
    """offset + limit > 9,900: would exceed OS max_result_window."""


# ---------------------------------------------------------------------------
# Snapshot gate (PATCH-02)
# ---------------------------------------------------------------------------

_snapshot_cache_lock = threading.Lock()
_snapshot_cache: dict = {}


def _cas_index_ready() -> bool:
    val = os.environ.get(_CAS_INDEX_ENV_VAR, "").strip().lower()
    return val in ("1", "true", "yes")


def _get_db_chem_count(sb=None) -> Optional[int]:
    try:
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        from services.kosha_msds.read import SEO_PREVIEW_CURRENT_VIEW
        r = (
            sb.table(SEO_PREVIEW_CURRENT_VIEW)
            .select("chem_id", count="exact")
            .limit(1)
            .execute()
        )
        return int(getattr(r, "count", None) or 0)
    except Exception as exc:
        logger.warning("MSDS DB CHEM count failed: %s", exc)
        return None


def _get_os_chem_count(client=None) -> Optional[int]:
    try:
        if client is None:
            client = get_client()
        resp = client.count(
            index=CURRENT_ALIAS,
            body={"query": {"bool": {"filter": _CHEM_BASE_FILTER}}},
        )
        return int(resp.get("count", 0))
    except Exception as exc:
        logger.warning("MSDS OS CHEM count failed: %s", exc)
        return None


def _set_snapshot_cache(*, ok: bool, reason: Optional[str], ts: float) -> None:
    with _snapshot_cache_lock:
        _snapshot_cache.update({"ok": ok, "reason": reason, "ts": ts})


def check_snapshot_gate(*, client=None, sb=None) -> None:
    """Verify OS CHEM doc count matches DB published CHEM count.

    Raises MsdsSnapshotGateError when:
    - Either count lookup fails (fail-closed)
    - |OS_count - DB_count| > _SNAPSHOT_COUNT_TOLERANCE

    Result is cached for _SNAPSHOT_CACHE_TTL seconds (5 minutes).
    Call _clear_snapshot_cache() in tests to force a re-check.
    """
    now = time.monotonic()
    with _snapshot_cache_lock:
        cached = dict(_snapshot_cache)

    if cached and (now - cached.get("ts", 0)) < _SNAPSHOT_CACHE_TTL:
        if not cached.get("ok"):
            raise MsdsSnapshotGateError(cached.get("reason", "snapshot gate fail (cached)"))
        return

    db_count = _get_db_chem_count(sb=sb)
    os_count = _get_os_chem_count(client=client)

    if db_count is None:
        reason = "DB CHEM count lookup failed"
        _set_snapshot_cache(ok=False, reason=reason, ts=now)
        raise MsdsSnapshotGateError(reason)

    if os_count is None:
        reason = "OS CHEM count lookup failed"
        _set_snapshot_cache(ok=False, reason=reason, ts=now)
        raise MsdsSnapshotGateError(reason)

    diff = abs(os_count - db_count)
    if diff > _SNAPSHOT_COUNT_TOLERANCE:
        reason = (
            f"OS/DB CHEM count divergence: OS={os_count} DB={db_count} "
            f"diff={diff} (tolerance {_SNAPSHOT_COUNT_TOLERANCE})"
        )
        _set_snapshot_cache(ok=False, reason=reason, ts=now)
        raise MsdsSnapshotGateError(reason)

    _set_snapshot_cache(ok=True, reason=None, ts=now)


def _clear_snapshot_cache() -> None:
    """Reset the snapshot gate cache. For tests only."""
    with _snapshot_cache_lock:
        _snapshot_cache.clear()


def os_chem_available(client=None) -> bool:
    """Count-based availability gate (kept for backwards compatibility).

    Returns True when OS has >= 15,000 CHEM docs.
    For a freshness-aware gate use check_snapshot_gate() instead.
    """
    count = _get_os_chem_count(client=client)
    return (count or 0) >= 15_000


# ---------------------------------------------------------------------------
# Search (PATCH-03..06)
# ---------------------------------------------------------------------------


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

    PATCH-03: cas_no raises MsdsCasIndexNotReadyError unless
    KOSHA_MSDS_CAS_INDEX_READY=true.

    PATCH-04: all structured params are AND filter clauses (no if/elif).

    PATCH-05: name_ko/name_en → Nori match on title, source_key ASC sort;
              q → BM25 multi_match, _score DESC sort.

    PATCH-06: offset + limit > 9,900 → MsdsPaginationDepthExceededError.

    track_total_hits=true ensures accurate totals beyond 10,000 hits.
    """
    if client is None:
        client = get_client()

    # PATCH-06: deep pagination guard
    if offset + limit > _DEEP_PAGINATION_LIMIT:
        raise MsdsPaginationDepthExceededError(
            f"offset({offset}) + limit({limit}) = {offset + limit} "
            f"exceeds {_DEEP_PAGINATION_LIMIT}"
        )

    # PATCH-03: CAS index guard
    if cas_no and not _cas_index_ready():
        raise MsdsCasIndexNotReadyError(
            f"cas_no search requires {_CAS_INDEX_ENV_VAR}=true "
            "(set after OS STAGE 1 rebuild with CAS in aliases)"
        )

    # PATCH-04: AND filter builder — all identifier params as filter clauses
    filters: list[dict] = list(_CHEM_BASE_FILTER)
    if chem_id:
        filters.append({"term": {"source_key": chem_id}})
    if cas_no:
        filters.append({"term": {"aliases.raw": cas_no}})
    if ke_no:
        filters.append({"term": {"aliases.raw": ke_no}})
    if en_no:
        filters.append({"term": {"aliases.raw": en_no}})
    if un_no:
        filters.append({"term": {"aliases.raw": un_no}})

    # PATCH-05: text must clauses
    must_clauses: list[dict] = []
    text_q = (q or "").strip()

    if name_ko:
        must_clauses.append({
            "match": {
                "title": {"query": name_ko, "analyzer": "tai_nori_search"}
            }
        })
    if name_en:
        must_clauses.append({
            "match": {
                "title": {"query": name_en, "analyzer": "tai_nori_search"}
            }
        })
    if text_q:
        must_clauses.append({
            "multi_match": {
                "query": text_q,
                "fields": ["title^5", "aliases^4", "search_text"],
                "type": "best_fields",
                "analyzer": "tai_nori_search",
            }
        })

    query_body: dict
    sort: list[dict]

    if must_clauses:
        query_body = {"bool": {"filter": filters, "must": must_clauses}}
        # Score-ranked only when q is present; name_ko/name_en → deterministic order
        sort = (
            [{"_score": "desc"}, {"source_key": "asc"}]
            if text_q
            else [{"source_key": "asc"}]
        )
    else:
        query_body = {"bool": {"filter": filters}}
        sort = [{"source_key": "asc"}]

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
