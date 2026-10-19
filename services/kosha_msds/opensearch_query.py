"""MSDS OpenSearch query adapter — WO-WWW-PERF-004-P0S.

PATCH-01~06: WO-WWW-PERF-004-P0S-OS-PATCH-001.
PATCH-003C~G: WO-WWW-PERF-004-P0S-PATCH-003.

source_key = chem_id (6-digit KOSHA ID). Caller hydrates via
SupabaseMsdsReadStore.hydrate_chem_ids() — the P0-A fast path.

Snapshot gate (PATCH-02 → PATCH-003B): check_snapshot_gate() now
validates a registered SnapshotProof (membership-level parity) rather
than comparing counts. The current gate state (snapshot_id,
physical_index, outbox_wm) is cached for 60 s. Raises
MsdsSnapshotGateError when no valid proof covers the current state
(fail-closed).

CAS gate (PATCH-03): KOSHA_MSDS_CAS_INDEX_READY env var (default false)
gates cas_no queries. Until OS is rebuilt with CAS in aliases, cas_no
requests return MsdsCasIndexNotReadyError → 503 instead of silently
returning 0 results.

AND filters (PATCH-04): all structured params combined as AND filter
clauses — no if/elif priority chain.

Search semantics (PATCH-05 / PATCH-003C/D):
  - name_ko: wildcard on title.raw (keyword) for ILIKE substring semantics,
    case_insensitive=True; sorted source_key ASC
  - name_en: match on summary (Nori); sorted source_key ASC
    NOTE: summary.raw not indexed; name_en uses Nori match approximation.
    Exact ILIKE requires mapping extension (add summary.raw keyword subfield
    + reindex).
  - q: BM25 multi_match on title^5/aliases^4/search_text; sorted _score DESC

Deep pagination (PATCH-06 / PATCH-003F): offset + limit > _DEEP_PAGINATION_LIMIT
(9,900) uses PIT + search_after instead of raising.
MsdsPaginationDepthExceededError is raised only when PIT creation fails.

track_total_hits=true gives accurate pagination totals.
"""
from __future__ import annotations

import logging
import os
import threading

from typing import Optional

from services.shared_search.opensearch_client import CURRENT_ALIAS, get_client

logger = logging.getLogger(__name__)

_CHEM_BASE_FILTER: list[dict] = [
    {"term": {"object_type": "CHEM"}},
    {"term": {"source_id": "KOSHA_MSDS"}},
    {"term": {"publication_status": "PUBLISHED"}},
    {"term": {"visibility_scopes": "PUBLIC"}},
]

_DEEP_PAGINATION_LIMIT = 9_900
_SNAPSHOT_CACHE_TTL = 300        # 5 minutes (legacy count-based cache, kept for helpers)
_SNAPSHOT_COUNT_TOLERANCE = 50   # allow ±50 docs during re-index window (legacy)
_CAS_INDEX_ENV_VAR = "KOSHA_MSDS_CAS_INDEX_READY"
_QUERY_OS_CALL_BUDGET = 200      # total network requests per q query (CLOSURE-A)
# CLOSURE-A: total = 1 create_pit + ≤198 client.search + 1 delete_pit ≤ 200.
# budget_ref is initialised to (_QUERY_OS_CALL_BUDGET - 2) to reserve the create+delete slots.
# Each _collect_all_os_pit batch decrements budget_ref by 1.
# For 20,568 hits: 21 batches/term × 2 fields = 42 search calls per term — well within 198.


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
    """PIT creation failed during deep pagination (offset + limit > 9,900)."""


class MsdsHydrationIntegrityError(MsdsOsError):
    """OS result IDs not fully found in DB scope — membership drift detected.

    Raised when len(hydrated_rows) < len(os_chem_ids): at least one OS
    result is absent from the scoped DB view. Signals OS/DB out-of-sync
    rather than silently returning a short page (PATCH-02E).
    """


class MsdsCandidateEnumerationIncompleteError(MsdsOsError):
    """_collect_all_os() exhausted its page budget with results still remaining.

    Raised when collected < os_total after _CANDIDATE_MAX_PAGES pages. Prevents
    returning a partial candidate set as if it were complete (P0-03).
    """


class MsdsCandidateEnumerationIntegrityError(MsdsOsError):
    """_collect_all_os() collected more IDs than OS reported, or the OS total
    changed between pages (index generation swap during candidate scan).

    Raised on COLLECTED > TOTAL or cross-page total inconsistency (CLOSURE-02).
    """


# ---------------------------------------------------------------------------
# Snapshot gate (PATCH-02 → PATCH-003B proof-registry gate)
# ---------------------------------------------------------------------------

_snapshot_cache_lock = threading.Lock()
_snapshot_cache: dict = {}

# CLOSURE-01: state cache removed — the 60 s TTL could miss snapshot or
# physical-index generation changes between proof registration and gate check.
# All state lookups are now live (uncached) on every gate invocation.


def _cas_index_ready() -> bool:
    val = os.environ.get(_CAS_INDEX_ENV_VAR, "").strip().lower()
    return val in ("1", "true", "yes")


def _get_db_chem_count(sb=None) -> Optional[int]:
    """Legacy count helper — kept for os_chem_available()."""
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
    """Legacy count helper — kept for os_chem_available()."""
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


def _get_current_gate_state(client, sb, scope: str) -> tuple[str, str, int]:
    """Return (snapshot_id, physical_index, outbox_wm) for the given scope.

    Used to match against a registered SnapshotProof. Returns ('', '', 0)
    when any sub-lookup fails (fail-closed: caller raises MsdsSnapshotGateError).
    CLOSURE-01: scope-specific snapshot lookup prevents SEO_PREVIEW proof
    from passing a FULL scope gate check.
    """
    from services.kosha_msds.snapshot_proof import (
        _get_current_snapshot,
        _get_outbox_watermark,
        _get_physical_index,
    )

    try:
        snapshot_id, _ = _get_current_snapshot(sb, scope)
        physical_index = _get_physical_index(client)
        outbox_wm = _get_outbox_watermark(sb)
        return (snapshot_id, physical_index, outbox_wm)
    except Exception as exc:
        logger.warning("MSDS gate state lookup failed: %s", exc)
        return ("", "", 0)


def check_snapshot_gate(*, scope: str, client=None, sb=None) -> None:
    """Verify a registered SnapshotProof covers the current system state.

    scope must match the publication scope being served (SEO_PREVIEW or FULL).
    Raises MsdsSnapshotGateError when:
    - Current state lookup fails (fail-closed)
    - No proof is registered for the given scope
    - Registered proof does not match the current state triple
      (snapshot_id, physical_index, outbox_wm)
    - verify_proof(proof) returns False
    - Uncommitted PENDING CHEM events exist (uncached check every invocation)

    CLOSURE-01: state lookups are live (uncached) on every call — the 60 s
    TTL previously cached the state triple and could miss snapshot or
    physical-index generation changes between proof registration and gate check.
    """
    from services.kosha_msds.snapshot_proof import get_registered_proof, verify_proof

    if client is None:
        client = get_client()
    if sb is None:
        from db.supabase_client import get_supabase
        sb = get_supabase()

    # Live state lookup — no cache (CLOSURE-01)
    current_state = _get_current_gate_state(client, sb, scope)

    if not current_state or current_state == ("", "", 0):
        raise MsdsSnapshotGateError(
            "Snapshot gate state lookup failed (fail-closed)"
        )

    proof = get_registered_proof(scope)

    if proof is None:
        raise MsdsSnapshotGateError(
            f"No snapshot proof registered for scope {scope!r}; "
            "gate is closed until a valid proof is loaded"
        )

    # Check that proof covers current state
    proof_state = (proof.snapshot_id, proof.physical_index, proof.chem_outbox_high_watermark)
    if proof_state != current_state:
        raise MsdsSnapshotGateError(
            f"Registered proof state mismatch: proof={proof_state} current={current_state}"
        )

    if not verify_proof(proof):
        raise MsdsSnapshotGateError(
            f"Registered proof failed verification: status={proof.verification_status} "
            f"error={proof.error_message!r}"
        )

    # Uncached PENDING check: detect new uncommitted events since proof was generated (P0-01).
    try:
        from services.kosha_msds.snapshot_proof import _get_outbox_pending_count
        pending_count = _get_outbox_pending_count(sb)
    except Exception as exc:
        raise MsdsSnapshotGateError(
            f"Pending event count check failed at gate: {exc}"
        ) from exc
    if pending_count > 0:
        raise MsdsSnapshotGateError(
            f"Uncommitted CHEM events at gate check time: pending_count={pending_count}"
        )


def _clear_snapshot_cache() -> None:
    """Reset legacy count-based snapshot cache. For tests only."""
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
# Wildcard escape helper (PATCH-003D)
# ---------------------------------------------------------------------------


def _wildcard_escape(term: str) -> str:
    """Escape OpenSearch wildcard special chars: *, ?, \\"""
    return term.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def _name_must_clauses(
    name_ko: Optional[str],
    name_en: Optional[str],
) -> list[dict]:
    """Build must-clauses for name_ko / name_en name searches (CLOSURE-B).

    Single source of truth used by both search_os() (structured filter path)
    and _build_chem_term_query() (PIT candidate path) so the two paths are
    always identical.
    """
    clauses: list[dict] = []
    if name_ko:
        escaped = _wildcard_escape(name_ko)
        clauses.append({
            "wildcard": {
                "title.raw": {
                    "value": f"*{escaped}*",
                    "case_insensitive": True,
                }
            }
        })
    if name_en:
        clauses.append({
            "match": {
                "summary": {"query": name_en, "analyzer": "tai_nori_search"}
            }
        })
    return clauses


def _build_chem_term_query(
    *,
    name_ko: Optional[str] = None,
    name_en: Optional[str] = None,
) -> tuple[dict, list]:
    """Build (query_body, sort) for a CHEM name/term search.

    IMP-010A / CLOSURE-B: delegates must-clause construction to
    _name_must_clauses() so the PIT candidate path and search_os() share
    an identical query shape for name_ko / name_en matching.
    """
    filters: list[dict] = list(_CHEM_BASE_FILTER)
    must_clauses = _name_must_clauses(name_ko, name_en)

    if must_clauses:
        query_body = {"bool": {"filter": filters, "must": must_clauses}}
    else:
        query_body = {"bool": {"filter": filters}}

    return query_body, [{"source_key": "asc"}]


# ---------------------------------------------------------------------------
# PIT deep-page helper (PATCH-003F)
# ---------------------------------------------------------------------------

_PIT_BATCH = 1_000
_PIT_KEEP_ALIVE = "2m"


def _search_os_deep_page(
    *,
    query_body: dict,
    sort: list[dict],
    offset: int,
    limit: int,
    client,
) -> tuple[list[str], int]:
    """PIT + search_after based pagination for offset+limit > 9,900.

    Creates a PIT, scans in batches of 1,000 until offset+limit results
    are accumulated, then slices and cleans up PIT.

    Raises MsdsPaginationDepthExceededError if PIT creation fails
    (e.g., OS version does not support PIT).
    """
    try:
        pit_resp = client.create_pit(
            index=CURRENT_ALIAS,
            params={"keep_alive": _PIT_KEEP_ALIVE},
        )
        pit_id = pit_resp.get("pit_id") or ""
    except Exception as exc:
        raise MsdsPaginationDepthExceededError(
            f"PIT creation failed (OS may not support PIT): {exc}"
        ) from exc

    if not pit_id:
        raise MsdsPaginationDepthExceededError("PIT creation returned empty pit_id")

    try:
        collected: list[str] = []
        search_after = None
        total = 0
        needed = offset + limit

        while len(collected) < needed:
            body: dict = {
                **query_body,
                "sort": sort,
                "size": _PIT_BATCH,
                "track_total_hits": True,
                "pit": {"id": pit_id, "keep_alive": _PIT_KEEP_ALIVE},
                "_source": ["source_key"],
            }
            if search_after:
                body["search_after"] = search_after
            resp = client.search(body=body)  # no index needed with PIT
            hits_obj = resp.get("hits") or {}
            total_raw = hits_obj.get("total") or {}
            total = (
                total_raw.get("value", 0)
                if isinstance(total_raw, dict)
                else int(total_raw or 0)
            )
            hits = hits_obj.get("hits") or []
            if not hits:
                break
            for h in hits:
                sk = (h.get("_source") or {}).get("source_key", "")
                if sk:
                    collected.append(sk)
            search_after = hits[-1].get("sort")
            if len(hits) < _PIT_BATCH:
                break

        return collected[offset: offset + limit], total
    finally:
        try:
            client.delete_pit(body={"pit_id": pit_id})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Search (PATCH-03..06 + PATCH-003C/D/F)
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

    PATCH-003C/D:
      name_ko → wildcard on title.raw (case_insensitive=True) for ILIKE semantics;
      name_en → match on summary (Nori approximation; summary.raw not indexed).

    PATCH-003F: offset + limit > 9,900 → PIT + search_after (deep page).
    MsdsPaginationDepthExceededError raised only on PIT failure.

    track_total_hits=true ensures accurate totals beyond 10,000 hits.
    """
    if client is None:
        client = get_client()

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

    # PATCH-003C/D / CLOSURE-B: name must-clauses via shared helper
    text_q = (q or "").strip()
    must_clauses: list[dict] = _name_must_clauses(name_ko, name_en)
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

    # PATCH-003F: deep pagination routing — use PIT when offset+limit > threshold
    if offset + limit > _DEEP_PAGINATION_LIMIT:
        return _search_os_deep_page(
            query_body={"query": query_body},
            sort=sort,
            offset=offset,
            limit=limit,
            client=client,
        )

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


# ---------------------------------------------------------------------------
# OS-backed adapter (PATCH-02C: moved from search_adapter to eliminate
# search-engine dependency from the CHEM-09 plan module)
# ---------------------------------------------------------------------------


_CANDIDATE_PAGE_SIZE = 1_000   # per-term page size for full candidate enumeration
_CANDIDATE_MAX_PAGES = 50     # budget: max 50,000 results per (term, field) pair


def _collect_all_os(*, client, budget_ref: Optional[list] = None, **kwargs) -> list[str]:
    """Collect ALL matching chem_ids for a term, paginating until exhausted.

    Uses _CANDIDATE_PAGE_SIZE per page, up to _CANDIDATE_MAX_PAGES pages.
    For results > _DEEP_PAGINATION_LIMIT, search_os routes to PIT internally.

    budget_ref: mutable [remaining_calls] counter shared across all terms in
    one search_by_q_os call (CLOSURE-04). When exhausted, raises INCOMPLETE.

    CLOSURE-02 integrity checks:
    - Raises MsdsCandidateEnumerationIncompleteError when collected < os_total
      (budget exhausted, short page with total mismatch, or query-level budget).
    - Raises MsdsCandidateEnumerationIntegrityError when collected > os_total
      or when os_total changes between pages (index swap during candidate scan)
      or when duplicate chem_ids appear across pages.
    """
    all_ids: list[str] = []
    page_off = 0
    first_total: Optional[int] = None
    last_total: Optional[int] = None

    for _ in range(_CANDIDATE_MAX_PAGES):
        # Query-level budget guard (CLOSURE-04)
        if budget_ref is not None:
            if budget_ref[0] <= 0:
                # FIX-01/K01/K03: budget 0 before any OS call for this term →
                # we have NOT searched it at all; returning [] would falsely
                # report 0 results for unchecked candidates (K03).
                if last_total is None:
                    raise MsdsCandidateEnumerationIncompleteError(
                        "Query-level OS call budget exhausted before first page "
                        "for this term (unchecked candidates may have results — "
                        "falsely reporting 0 is forbidden)"
                    )
                if isinstance(last_total, int) and len(all_ids) < last_total:
                    raise MsdsCandidateEnumerationIncompleteError(
                        f"Query-level OS call budget exhausted: "
                        f"collected={len(all_ids)} os_total={last_total}"
                    )
                break
            budget_ref[0] -= 1

        ids, total = search_os(
            limit=_CANDIDATE_PAGE_SIZE, offset=page_off, client=client, **kwargs
        )

        # Detect OS total changing between pages (index generation swap mid-scan) — J05/J06
        if first_total is None:
            first_total = total
        if isinstance(total, int) and isinstance(first_total, int) and total != first_total:
            raise MsdsCandidateEnumerationIntegrityError(
                f"OS total changed between pages: page_0_total={first_total} "
                f"current_total={total} at page_off={page_off} "
                f"(index swap or concurrent reindex during candidate scan)"
            )

        last_total = total
        all_ids.extend(ids)

        if len(ids) < _CANDIDATE_PAGE_SIZE:
            break
        page_off += _CANDIDATE_PAGE_SIZE
        if isinstance(total, int) and page_off >= total:
            break
    else:
        # Loop ran all _CANDIDATE_MAX_PAGES iterations without break → budget exhausted
        if isinstance(last_total, int) and len(all_ids) < last_total:
            raise MsdsCandidateEnumerationIncompleteError(
                f"Candidate enumeration budget exhausted: "
                f"collected={len(all_ids)} os_total={last_total} "
                f"(budget={_CANDIDATE_MAX_PAGES} pages × {_CANDIDATE_PAGE_SIZE})"
            )

    # Short-page incomplete: break fired before all pages were consumed (J05)
    if isinstance(last_total, int) and last_total > 0 and len(all_ids) < last_total:
        raise MsdsCandidateEnumerationIncompleteError(
            f"Candidate enumeration incomplete: "
            f"collected={len(all_ids)} os_total={last_total} "
            f"(short page before full enumeration)"
        )

    # Post-loop integrity: over-collection or duplicate pages
    if isinstance(last_total, int) and last_total > 0 and len(all_ids) > last_total:
        raise MsdsCandidateEnumerationIntegrityError(
            f"Collected more IDs than OS total: collected={len(all_ids)} "
            f"os_total={last_total} (duplicate page in OS response)"
        )
    if len(all_ids) != len(set(all_ids)):
        dup_count = len(all_ids) - len(set(all_ids))
        raise MsdsCandidateEnumerationIntegrityError(
            f"Duplicate chem_ids in candidate set: {dup_count} duplicates "
            f"(OS returned same document in multiple pages)"
        )
    return all_ids


def _collect_all_os_pit(
    *,
    client,
    pit_id_ref: list,
    budget_ref: Optional[list] = None,
    name_ko: Optional[str] = None,
    name_en: Optional[str] = None,
) -> list[str]:
    """Collect ALL matching chem_ids via PIT + search_after (O(n) per term).

    IMP-010B/C: Uses the caller-supplied PIT ID (pit_id_ref[0]) so all terms
    in one search_by_q_os call share a single PIT (created once, deleted once
    in the caller's finally block).

    budget_ref: mutable [remaining_calls] counter; each actual client.search
    call decrements it by 1 AFTER the call (IMP-010D). PIT create/delete are
    NOT counted. Raises MsdsCandidateEnumerationIncompleteError when budget is
    exhausted before collection is complete.

    pit_id_ref: mutable [pit_id]; updated from resp.get("pit_id") on each
    response to handle OpenSearch PIT-ID renewal.

    CLOSURE-02 integrity checks identical to _collect_all_os:
    - MsdsCandidateEnumerationIncompleteError: budget=0 before first page,
      budget exhausted mid-collection, short page with total mismatch.
    - MsdsCandidateEnumerationIntegrityError: total changed between pages,
      over-collection, duplicate chem_ids in result set.
    """
    query_body, sort = _build_chem_term_query(name_ko=name_ko, name_en=name_en)

    all_ids: list[str] = []
    first_total: Optional[int] = None
    last_total: Optional[int] = None
    search_after = None

    for _ in range(_CANDIDATE_MAX_PAGES):
        # Budget guard (before search call)
        if budget_ref is not None:
            if budget_ref[0] <= 0:
                if last_total is None:
                    raise MsdsCandidateEnumerationIncompleteError(
                        "Query-level OS call budget exhausted before first page "
                        "for this term (unchecked candidates may have results — "
                        "falsely reporting 0 is forbidden)"
                    )
                if isinstance(last_total, int) and len(all_ids) < last_total:
                    raise MsdsCandidateEnumerationIncompleteError(
                        f"Query-level OS call budget exhausted: "
                        f"collected={len(all_ids)} os_total={last_total}"
                    )
                break

        body: dict = {
            "query": query_body,
            "sort": sort,
            "size": _CANDIDATE_PAGE_SIZE,
            "track_total_hits": True,
            "pit": {"id": pit_id_ref[0], "keep_alive": _PIT_KEEP_ALIVE},
            "_source": ["source_key"],
        }
        if search_after is not None:
            body["search_after"] = search_after

        resp = client.search(body=body)

        # PIT ID renewal (OpenSearch may return updated pit_id)
        new_pit_id = resp.get("pit_id")
        if new_pit_id:
            pit_id_ref[0] = new_pit_id

        # Budget decrement after each actual client.search call (IMP-010D)
        if budget_ref is not None:
            budget_ref[0] -= 1

        hits_obj = resp.get("hits") or {}
        total_raw = hits_obj.get("total") or {}
        total = (
            total_raw.get("value", 0)
            if isinstance(total_raw, dict)
            else int(total_raw or 0)
        )
        hits = hits_obj.get("hits") or []

        # Cross-page total consistency (CLOSURE-02)
        if first_total is None:
            first_total = total
        if isinstance(total, int) and isinstance(first_total, int) and total != first_total:
            raise MsdsCandidateEnumerationIntegrityError(
                f"OS total changed between pages: page_0_total={first_total} "
                f"current_total={total} at len_collected={len(all_ids)} "
                f"(index swap or concurrent reindex during candidate scan)"
            )

        last_total = total

        for h in hits:
            sk = (h.get("_source") or {}).get("source_key", "")
            if sk:
                all_ids.append(sk)

        if len(hits) < _CANDIDATE_PAGE_SIZE:
            break

        if hits:
            search_after = hits[-1].get("sort")

        if isinstance(total, int) and total > 0 and len(all_ids) >= total:
            break
    else:
        # Loop ran all _CANDIDATE_MAX_PAGES iterations without break
        if isinstance(last_total, int) and len(all_ids) < last_total:
            raise MsdsCandidateEnumerationIncompleteError(
                f"Candidate enumeration budget exhausted: "
                f"collected={len(all_ids)} os_total={last_total} "
                f"(budget={_CANDIDATE_MAX_PAGES} pages × {_CANDIDATE_PAGE_SIZE})"
            )

    # Short-page incomplete (CLOSURE-02 J05 equivalent)
    if isinstance(last_total, int) and last_total > 0 and len(all_ids) < last_total:
        raise MsdsCandidateEnumerationIncompleteError(
            f"Candidate enumeration incomplete: "
            f"collected={len(all_ids)} os_total={last_total} "
            f"(short page before full enumeration)"
        )

    # Over-collection
    if isinstance(last_total, int) and last_total > 0 and len(all_ids) > last_total:
        raise MsdsCandidateEnumerationIntegrityError(
            f"Collected more IDs than OS total: collected={len(all_ids)} "
            f"os_total={last_total} (duplicate page in OS response)"
        )

    # Duplicate chem_ids
    if len(all_ids) != len(set(all_ids)):
        dup_count = len(all_ids) - len(set(all_ids))
        raise MsdsCandidateEnumerationIntegrityError(
            f"Duplicate chem_ids in candidate set: {dup_count} duplicates "
            f"(OS returned same document in multiple pages)"
        )

    return all_ids


def search_by_q_os(
    *,
    q: str,
    limit: int = 20,
    offset: int = 0,
    dictionary_lookup=None,
    client=None,
) -> tuple[list[str], int, dict]:
    """OS-backed free-text search for MSDS.

    Returns (chem_ids_page, total, match_metadata). Uses identifier
    detection for exact queries; for free text follows CHEM-09 priority:
      NORMALIZED_EXACT → DICTIONARY_EXPANSION → KIWI_TOKEN
    Each term is searched against name_ko AND name_en, with full
    pagination per (term, field) pair (PATCH-004).

    P0: Identifier exact → single direct OS call (IDENTIFIER_EXACT).
    P1: Free-text priority collection:
      1. normalized_query: name_ko + name_en (NORMALIZED_EXACT)
      2. Each expanded_term: name_ko + name_en (DICTIONARY_EXPANSION)
      3. Each token: name_ko + name_en (KIWI_TOKEN)
    Dedup by chem_id preserving first-seen order. Total = len(deduped).
    Page = deduped[off:off+lim].

    Moved from services.kosha_msds.search_adapter (PATCH-02C).
    """
    from services.kosha_msds.search_adapter import (
        MATCH_BM25_NORI,
        MATCH_IDENTIFIER_EXACT,
        _clamp_pagination,
        build_search_plan,
    )

    lim, off = _clamp_pagination(limit, offset)
    plan = build_search_plan(q, dictionary_lookup=dictionary_lookup)
    match_meta: dict = {
        "normalized_query": plan.normalized_query,
        "compact_query": plan.compact_query,
        "identifier_kind": plan.identifier_kind,
        "tokens": list(plan.tokens),
        "expanded_terms": list(plan.expanded_terms),
        "match_type": None,
    }

    if plan.is_empty:
        return [], 0, match_meta

    # P0: Identifier exact — single direct OS call
    if plan.identifier_kind is not None:
        kwargs: dict = {plan.identifier_kind: plan.identifier_value}
        chem_ids, total = search_os(limit=lim, offset=off, client=client, **kwargs)
        match_meta["match_type"] = MATCH_IDENTIFIER_EXACT
        return chem_ids, total, match_meta

    # P1: Free-text — CHEM-09 priority: NORMALIZED → DICTIONARY → KIWI_TOKEN
    # IMP-010B: Resolve client here so create_pit can be called directly.
    if client is None:
        client = get_client()

    from services.kosha_msds.search_adapter import (
        MATCH_DICTIONARY,
        MATCH_KIWI_TOKEN,
        MATCH_NORMALIZED_EXACT,
    )

    seen: set[str] = set()
    all_deduped: list[str] = []
    item_meta: dict[str, dict] = {}  # chem_id → {match_type, matched_term} (first-seen wins)
    # CLOSURE-A: reserve 2 slots for create_pit+delete_pit; search budget = total-2
    budget = [_QUERY_OS_CALL_BUDGET - 2]

    def _collect_with_meta(ids: list[str], mt: str, term: str) -> None:
        for cid in ids:
            if cid not in seen:
                seen.add(cid)
                all_deduped.append(cid)
                item_meta[cid] = {"match_type": mt, "matched_term": term}

    # IMP-010B: Create 1 PIT for all terms (O(n) vs O(n²) offset re-scan)
    try:
        pit_resp = client.create_pit(
            index=CURRENT_ALIAS,
            params={"keep_alive": _PIT_KEEP_ALIVE},
        )
        pit_id = pit_resp.get("pit_id") or ""
    except Exception as exc:
        raise MsdsPaginationDepthExceededError(
            f"PIT creation failed for free-text search: {exc}"
        ) from exc

    if not pit_id:
        raise MsdsPaginationDepthExceededError(
            "PIT creation returned empty pit_id for free-text search"
        )

    pit_id_ref = [pit_id]

    try:
        def _run_term(term: str, mt: str) -> None:
            if not term:
                return
            _collect_with_meta(
                _collect_all_os_pit(
                    name_ko=term, client=client,
                    pit_id_ref=pit_id_ref, budget_ref=budget,
                ),
                mt, term,
            )
            _collect_with_meta(
                _collect_all_os_pit(
                    name_en=term, client=client,
                    pit_id_ref=pit_id_ref, budget_ref=budget,
                ),
                mt, term,
            )

        # Priority: normalized → dictionary expansions → kiwi tokens
        _run_term(plan.normalized_query, MATCH_NORMALIZED_EXACT)
        for term in plan.expanded_terms:
            _run_term(term, MATCH_DICTIONARY)
        for token in plan.tokens:
            _run_term(token, MATCH_KIWI_TOKEN)

    finally:
        try:
            client.delete_pit(body={"pit_id": pit_id_ref[0]})
        except Exception as _del_exc:
            logger.warning(
                "PIT delete failed for free-text search (pit_id=%s): %s",
                pit_id_ref[0], _del_exc,
            )

    total = len(all_deduped)
    page = all_deduped[off: off + lim]
    match_meta["match_type"] = "CHEM_09"  # actual search path: NORMALIZED→DICTIONARY→KIWI (not BM25)
    match_meta["per_item_metadata"] = {  # page-sized only (P0-02: response proportional to page size)
        cid: item_meta[cid] for cid in page if cid in item_meta
    }
    return page, total, match_meta
