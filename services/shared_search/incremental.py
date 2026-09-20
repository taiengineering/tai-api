"""Incremental indexer — WO-TAI-SHARED-SEARCH-INCREMENTAL-001 §18.

Entry points:
    sync_object(...)     — index a single canonical_id from any Domain
    process_queue(...)   — claim + drain outbox events (§12)

Design rules:
    - Adapters: reuse DomainAdapter.object_reindex_payload() (§16)
    - Alias guard: resolve_alias_target() before every write (§17)
    - content_hash NOOP: skip write if hash unchanged (§19)
    - DELETE: adapter returns None → delete document (§20)
    - Rebuild fence: halt if search_index_runtime_state.rebuild_active (§39)
    - production_bindings: build adapters once per process_queue call

No activation.  This module may be imported without side-effects.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from opensearchpy import OpenSearch

from services.shared_search.opensearch_client import (
    CURRENT_ALIAS,
    OpenSearchUnavailable,
    get_client,
)
from services.shared_search.opensearch_projection import (
    AliasNotReady,
    ProjectionWriteError,
    delete_document,
    resolve_alias_target,
    upsert_document,
)
from services.shared_search.opensearch_store import document_id
from services.shared_search.production_bindings import build_production_adapters

logger = logging.getLogger(__name__)

# Claim batch size for process_queue
_DEFAULT_CLAIM_LIMIT = int(os.environ.get("TAI_INCREMENTAL_CLAIM_LIMIT", "50"))

# Lease seconds (must exceed longest adapter fetch)
_DEFAULT_LEASE_SECONDS = int(
    os.environ.get("TAI_INCREMENTAL_LEASE_SECONDS", "180")
)


# ---------------------------------------------------------------------------
# Rebuild fence (§39-§45)
# ---------------------------------------------------------------------------

def _rebuild_active(supabase_client) -> bool:
    """Return True if a full rebuild is in progress (fence = on)."""
    try:
        r = (supabase_client
             .table("search_index_runtime_state")
             .select("rebuild_active")
             .eq("id", 1)
             .limit(1)
             .execute())
        rows = list(getattr(r, "data", None) or [])
        return bool(rows[0].get("rebuild_active")) if rows else False
    except Exception as exc:
        # Fail-open on DB error: proceed with incremental (fence unavailable)
        logger.warning("rebuild fence read failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Adapter registry helpers
# ---------------------------------------------------------------------------

def _build_adapter_map(supabase_client) -> dict[str, Any]:
    """Return {domain_name: adapter} from production_bindings."""
    adapters = build_production_adapters(supabase_client)
    return {a.domain_name: a for a in adapters}


# ---------------------------------------------------------------------------
# sync_object — single-document incremental index (§18)
# ---------------------------------------------------------------------------

def sync_object(
    *,
    domain_name: str,
    object_type: str,
    canonical_id: str,
    supabase_client,
    os_client: Optional[OpenSearch] = None,
    adapter_map: Optional[dict] = None,
) -> dict:
    """Index or tombstone one canonical object.

    Returns an observability dict:
        outcome     — "UPSERT" | "NOOP" | "DELETE" | "NOT_FOUND" | "SKIP_FENCE"
        domain_name — echoed
        object_type — echoed
        canonical_id — echoed
        doc_id      — OpenSearch _id used
        error       — present only on failure (raise still propagates)
    """
    result: dict[str, Any] = {
        "domain_name": domain_name,
        "object_type": object_type,
        "canonical_id": canonical_id,
    }

    # Rebuild fence (§39): if rebuild is active, skip incremental writes
    if _rebuild_active(supabase_client):
        logger.info(
            "incremental SKIP_FENCE %s/%s/%s — rebuild in progress",
            domain_name, object_type, canonical_id,
        )
        result["outcome"] = "SKIP_FENCE"
        return result

    # Resolve alias before any write (§17)
    c = os_client or get_client()
    physical_index = resolve_alias_target(c)

    # Adapter lookup
    if adapter_map is None:
        adapter_map = _build_adapter_map(supabase_client)

    adapter = adapter_map.get(domain_name)
    if adapter is None:
        raise ValueError(f"No adapter registered for domain_name={domain_name!r}")

    doc_id = document_id(object_type, canonical_id)
    result["doc_id"] = doc_id

    # Fetch payload (§20: None → DELETE)
    payload = adapter.object_reindex_payload(canonical_id)

    if payload is None:
        outcome = delete_document(c, physical_index, doc_id)
        result["outcome"] = outcome
        logger.info(
            "incremental %s %s/%s/%s",
            outcome, domain_name, object_type, canonical_id,
        )
        return result

    # UPSERT (with content_hash NOOP, §19)
    outcome = upsert_document(c, physical_index, doc_id, payload)
    result["outcome"] = outcome
    logger.info(
        "incremental %s %s/%s/%s",
        outcome, domain_name, object_type, canonical_id,
    )
    return result


# ---------------------------------------------------------------------------
# process_queue — drain outbox events (§12, §47)
# ---------------------------------------------------------------------------

def process_queue(
    *,
    limit: int = _DEFAULT_CLAIM_LIMIT,
    supabase_client=None,
    os_client: Optional[OpenSearch] = None,
    worker_id: Optional[str] = None,
    lease_seconds: int = _DEFAULT_LEASE_SECONDS,
) -> dict:
    """Claim and process up to *limit* PENDING outbox events.

    Returns observability dict (§47):
        worker_id       — worker identifier used
        claimed         — events claimed from outbox
        completed       — events marked DONE
        noop            — content-hash unchanged (skipped writes)
        deleted         — DELETE outcomes
        failed          — events that failed (marked retry or DEAD)
        fence_skipped   — events skipped due to rebuild fence
        errors          — list of {event_id, error} for failed events
    """
    if supabase_client is None:
        raise ValueError(
            "process_queue requires a supabase_client — "
            "pass the process-level client from the scheduler handler."
        )

    sb = supabase_client
    c  = os_client or get_client()
    wid = worker_id or f"incremental-{uuid.uuid4().hex[:8]}"

    obs: dict[str, Any] = {
        "worker_id":     wid,
        "claimed":       0,
        "completed":     0,
        "noop":          0,
        "deleted":       0,
        "failed":        0,
        "fence_skipped": 0,
        "errors":        [],
    }

    # Claim events atomically (§12 FOR UPDATE SKIP LOCKED)
    try:
        resp = sb.rpc("claim_search_index_events", {
            "p_limit":          limit,
            "p_worker_id":      wid,
            "p_lease_seconds":  lease_seconds,
        }).execute()
    except Exception as exc:
        logger.error("claim_search_index_events failed: %s", exc)
        raise

    events = list(getattr(resp, "data", None) or [])
    obs["claimed"] = len(events)
    if not events:
        return obs

    # Build adapter map once for the entire batch
    adapter_map = _build_adapter_map(sb)

    # Resolve alias once; if alias is not ready, fail all claimed events back
    try:
        physical_index = resolve_alias_target(c)
    except AliasNotReady as exc:
        logger.error("alias not ready — returning all claimed events: %s", exc)
        for ev in events:
            _fail_event(sb, ev, str(exc), attempt_ok=False)
            obs["failed"] += 1
        return obs

    for ev in events:
        event_id   = ev["id"]
        attempt_no = ev["attempt_no"]
        domain     = ev["domain_name"]
        obj_type   = ev["object_type"]
        cid        = ev["canonical_id"]

        try:
            result = sync_object(
                domain_name=domain,
                object_type=obj_type,
                canonical_id=cid,
                supabase_client=sb,
                os_client=c,
                adapter_map=adapter_map,
            )
            outcome = result.get("outcome", "UNKNOWN")

            if outcome == "SKIP_FENCE":
                obs["fence_skipped"] += 1
                # Return to PENDING immediately (don't count as attempt)
                _requeue_fenced(sb, ev)
                continue

            if outcome == "NOOP":
                obs["noop"] += 1
            elif outcome in ("DELETE", "NOT_FOUND"):
                obs["deleted"] += 1

            # Mark DONE (§13 fenced completion)
            ok = sb.rpc("complete_search_index_event", {
                "p_event_id":  event_id,
                "p_worker_id": wid,
                "p_attempt":   attempt_no,
            }).execute()
            obs["completed"] += 1

        except (AliasNotReady, ProjectionWriteError, OpenSearchUnavailable) as exc:
            logger.warning(
                "incremental fail %s/%s/%s attempt=%s: %s",
                domain, obj_type, cid, attempt_no, exc,
            )
            _fail_event(sb, ev, str(exc))
            obs["failed"] += 1
            obs["errors"].append({"event_id": event_id, "error": str(exc)})

        except Exception as exc:
            logger.exception(
                "incremental unexpected error %s/%s/%s attempt=%s",
                domain, obj_type, cid, attempt_no,
            )
            _fail_event(sb, ev, str(exc))
            obs["failed"] += 1
            obs["errors"].append({"event_id": event_id, "error": str(exc)})

    return obs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fail_event(sb, ev: dict, error: str, *, attempt_ok: bool = True) -> None:
    """Call fail_search_index_event RPC to mark retry or DEAD."""
    try:
        sb.rpc("fail_search_index_event", {
            "p_event_id":  ev["id"],
            "p_worker_id": ev["worker_id"],
            "p_attempt":   ev["attempt_no"],
            "p_error":     error[:1000],
        }).execute()
    except Exception as exc:
        logger.error("fail_search_index_event RPC error: %s", exc)


def _requeue_fenced(sb, ev: dict) -> None:
    """Return a fence-skipped event to PENDING without consuming an attempt."""
    try:
        sb.rpc("fail_search_index_event", {
            "p_event_id":    ev["id"],
            "p_worker_id":   ev["worker_id"],
            "p_attempt":     ev["attempt_no"],
            "p_error":       "rebuild_fence_active",
            "p_backoff_secs": 30,
        }).execute()
    except Exception as exc:
        logger.error("requeue_fenced RPC error: %s", exc)
