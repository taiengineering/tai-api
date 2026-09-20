"""Shared Search — incremental indexing pipeline (durable outbox drain).

Pulls events from ``search_index_outbox`` via the
``claim_search_index_events`` RPC, processes them through the appropriate
Domain adapter, and writes/deletes in the live OpenSearch alias.

Fence semantics (fail-closed):
  - ``_rebuild_active(sb)`` reads ``search_index_fence.rebuild_active``.
    On any DB error it returns ``True`` (fail-closed — refuse to write
    while fence state is unknown).
  - ``process_queue()`` checks the fence BEFORE claiming any events.
    If the fence is active, the function returns immediately with
    ``{"claimed": 0, "fence_active": True}``.

Object-type safety:
  - ``sync_object()`` verifies that the event's ``object_type`` matches
    the adapter's ``object_type`` before processing.  Mismatch raises
    ``ValueError`` immediately (fail-closed).

Canonical preparation:
  - After ``adapter.object_reindex_payload()`` returns a non-None payload,
    the payload is normalized via ``prepare_search_document()`` before any
    OpenSearch write.  A ``SearchContractError`` during normalization raises
    ``ProjectionWriteError`` (fail-closed — event is not silently skipped).

Completion RPC:
  - ``complete_search_index_event`` returns a boolean.  A ``False`` response
    (fence triggered at completion time) is logged but does not increment
    the ``completed`` counter.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from services.shared_search.contract import (
    PUBLICATION_STATUS_PUBLISHED,
    SearchContractError,
)
from services.shared_search.opensearch_client import CURRENT_ALIAS
from services.shared_search.opensearch_projection import (
    delete_document,
    upsert_document,
)
from services.shared_search.opensearch_store import document_id
from services.shared_search.writer import prepare_search_document

logger = logging.getLogger(__name__)


class ProjectionWriteError(Exception):
    """Raised when an incremental projection write fails fatally."""


# ---------------------------------------------------------------------------
# Fence helpers
# ---------------------------------------------------------------------------

_FENCE_TABLE = "search_index_fence"


def _rebuild_active(supabase: Any) -> bool:
    """Read ``search_index_fence.rebuild_active``.

    Returns ``True`` (fail-closed) on any DB error so we never write
    while rebuild state is unknown.
    """
    try:
        r = (supabase.table(_FENCE_TABLE)
                     .select("rebuild_active")
                     .eq("id", 1)
                     .limit(1)
                     .execute())
        rows = list(getattr(r, "data", None) or [])
        if rows:
            return bool(rows[0].get("rebuild_active", False))
        return False
    except Exception as exc:
        logger.warning("rebuild fence read failed (fail-closed): %s", exc)
        return True  # FAIL-CLOSED: treat as active to prevent writes


# ---------------------------------------------------------------------------
# Requeue / fail helpers
# ---------------------------------------------------------------------------

def _fail_event(supabase: Any, event_id: int, reason: str,
                worker_id: str, attempt_no: int) -> None:
    """Mark an event as permanently failed."""
    try:
        supabase.rpc("fail_search_index_event", {
            "p_event_id":   event_id,
            "p_reason":     reason,
            "p_worker_id":  worker_id,
            "p_attempt_no": attempt_no,
        }).execute()
    except Exception as exc:
        logger.warning("fail_event failed for event %s: %s", event_id, exc)


# ---------------------------------------------------------------------------
# Core: single-object sync
# ---------------------------------------------------------------------------

def sync_object(
    *,
    domain_name: str,
    object_type: str,
    canonical_id: str,
    supabase_client: Any,
    os_client: Any,
    adapter_map: Optional[dict] = None,
) -> dict:
    """Sync a single canonical object to OpenSearch.

    Checks the rebuild fence first.  Returns a result dict with an
    ``"outcome"`` key.

    Possible outcomes:
      ``"SKIP_FENCE"``   — fence is active; write refused.
      ``"SKIP_NO_ADAPTER"`` — no adapter registered for domain_name.
      ``"UPSERT"`` / ``"NOOP"`` — document written or skipped (hash match).
      ``"DELETE"`` / ``"DELETE_NOOP"`` — tombstone applied.

    Raises:
      ``ValueError``            — object_type mismatch between event and adapter.
      ``ProjectionWriteError``  — normalization failure.
    """
    result: dict = {
        "domain_name": domain_name,
        "object_type": object_type,
        "canonical_id": canonical_id,
        "outcome": None,
    }

    # Fence check
    if _rebuild_active(supabase_client):
        result["outcome"] = "SKIP_FENCE"
        return result

    # Adapter lookup
    if adapter_map is None:
        from services.shared_search.production_bindings import build_production_adapters
        adapters = build_production_adapters(supabase_client)
        adapter_map = {a.domain_name: a for a in adapters}

    adapter = adapter_map.get(domain_name)
    if adapter is None:
        logger.warning("No adapter for domain %s", domain_name)
        result["outcome"] = "SKIP_NO_ADAPTER"
        return result

    # BLOCKER 4: object_type mismatch guard
    if adapter.object_type != object_type:
        raise ValueError(
            f"object_type mismatch: event object_type={object_type!r} "
            f"but {domain_name} adapter expects {adapter.object_type!r}"
        )

    # Resolve OpenSearch index (via alias) — must resolve to exactly 1 index
    try:
        alias_resp = os_client.indices.get_alias(name=CURRENT_ALIAS)
        indices = list(alias_resp.keys())
        if len(indices) != 1:
            raise ProjectionWriteError(
                f"alias {CURRENT_ALIAS} must resolve to exactly 1 index; "
                f"found {len(indices)}: {indices}"
            )
        physical_index = indices[0]
    except ProjectionWriteError:
        raise
    except Exception as exc:
        raise ProjectionWriteError(
            f"alias lookup failed for {CURRENT_ALIAS}: {exc}"
        ) from exc

    doc_id = document_id(object_type, canonical_id)

    # Fetch payload from SoT
    try:
        payload = adapter.object_reindex_payload(canonical_id)
    except Exception as exc:
        raise ProjectionWriteError(
            f"adapter.object_reindex_payload failed for {canonical_id}: {exc}"
        ) from exc

    if payload is None:
        # Tombstone
        outcome = delete_document(os_client, physical_index, doc_id)
        result["outcome"] = outcome
        return result

    # BLOCKER 1 (revisited): canonical preparation
    try:
        doc, wire = prepare_search_document(payload)
    except SearchContractError as exc:
        raise ProjectionWriteError(
            f"normalization failed for {canonical_id}: {exc}"
        ) from exc

    if doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
        # Adapter returned payload but it's not published → tombstone
        outcome = delete_document(os_client, physical_index, doc_id)
        result["outcome"] = outcome
        return result

    # NOOP check + write via canonical wire
    outcome = upsert_document(os_client, physical_index, doc_id, wire)
    result["outcome"] = outcome
    return result


# ---------------------------------------------------------------------------
# Queue processor
# ---------------------------------------------------------------------------

def process_queue(
    *,
    supabase_client: Any,
    os_client: Any = None,
    worker_id: Optional[str] = None,
    batch_size: int = 50,
) -> dict:
    """Drain one batch of events from the outbox.

    BLOCKER 9: fence is checked BEFORE claiming any events.

    Returns an ``obs`` dict with metrics:
      ``fence_active`` — True if fence blocked processing.
      ``claimed``      — number of events claimed.
      ``completed``    — number successfully completed.
      ``failed``       — number marked failed.
      ``noop``         — number NOOP (hash matched, no write).
    """
    obs: dict = {
        "fence_active": False,
        "claimed": 0,
        "completed": 0,
        "failed": 0,
        "noop": 0,
    }

    sb = supabase_client

    # BLOCKER 9: check fence BEFORE claiming
    if _rebuild_active(sb):
        obs["fence_active"] = True
        return obs  # claimed=0, no attempt consumption

    if worker_id is None:
        worker_id = str(uuid.uuid4())

    if os_client is None:
        from services.shared_search.opensearch_client import get_client
        os_client = get_client()

    # Claim a batch of events
    try:
        claim_resp = sb.rpc("claim_search_index_events", {
            "p_worker_id": worker_id,
            "p_batch_size": batch_size,
        }).execute()
        events = list(getattr(claim_resp, "data", None) or [])
    except Exception as exc:
        logger.error("claim_search_index_events failed: %s", exc)
        return obs

    obs["claimed"] = len(events)
    if not events:
        return obs

    # Build adapter map once per batch
    try:
        from services.shared_search import production_bindings as _pb
        adapters = _pb.build_production_adapters(sb)
        adapter_map = {a.domain_name: a for a in adapters}
    except Exception as exc:
        logger.error("build_production_adapters failed: %s", exc)
        return obs

    for event in events:
        event_id = event.get("id")
        domain_name = event.get("domain_name", "")
        object_type = event.get("object_type", "")
        canonical_id = event.get("canonical_id", "")
        attempt_no  = event.get("attempt_no", 1)

        try:
            result = sync_object(
                domain_name=domain_name,
                object_type=object_type,
                canonical_id=canonical_id,
                supabase_client=sb,
                os_client=os_client,
                adapter_map=adapter_map,
            )
        except Exception as exc:
            logger.error(
                "sync_object failed for event %s (%s/%s/%s): %s",
                event_id, domain_name, object_type, canonical_id, exc,
            )
            _fail_event(sb, event_id, str(exc)[:500], worker_id, attempt_no)
            obs["failed"] += 1
            continue

        outcome = result.get("outcome", "")

        if outcome == "SKIP_FENCE":
            # Fence became active mid-batch — requeue, don't complete
            try:
                sb.rpc("requeue_search_index_event", {
                    "p_event_id":   event_id,
                    "p_worker_id":  worker_id,
                    "p_attempt_no": attempt_no,
                    "p_reason": "fence_active_mid_batch",
                }).execute()
            except Exception as exc:
                logger.warning("requeue failed for event %s: %s", event_id, exc)
            continue  # don't complete

        if outcome == "SKIP_NO_ADAPTER":
            _fail_event(sb, event_id, f"no adapter for domain {domain_name}", worker_id, attempt_no)
            obs["failed"] += 1
            continue  # don't complete

        if outcome == "NOOP":
            obs["noop"] += 1
        # UPSERT / DELETE / DELETE_NOOP all fall through to complete

        # Complete the event
        try:
            ok_resp = sb.rpc("complete_search_index_event", {
                "p_event_id": event_id,
                "p_worker_id": worker_id,
            }).execute()
            completed_ok = ok_resp.data if isinstance(ok_resp.data, bool) else bool(ok_resp.data if ok_resp.data else False)
            if completed_ok:
                obs["completed"] += 1
            else:
                logger.warning("completion fenced for event %s", event_id)
                # Don't increment completed
        except Exception as exc:
            logger.warning(
                "complete_search_index_event failed for event %s: %s",
                event_id, exc,
            )

    return obs
