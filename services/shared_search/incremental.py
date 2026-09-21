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
    bulk_upsert_documents,
    delete_document,
    get_document_content_hashes,
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
# Bulk domain activation path
# ---------------------------------------------------------------------------

def bulk_sync_published_domain(
    *,
    domain_name: str,
    object_type: str,
    os_client: Any,
    supabase_client: Any,
    adapter_map: Optional[dict] = None,
    db_canonical_ids: Optional[set] = None,
    mget_batch_size: int = 500,
    chunk_size: int = 500,
) -> dict:
    """Bulk-activate all PUBLISHED documents for a domain.

    Safer and faster than calling sync_object() per canonical ID:
      - Domain adapter scanned once (iter_expected_hashes / iter_documents)
      - Hash comparison via batched _mget (no per-document GET)
      - Only changed documents sent to bulk INDEX
      - Fence + alias re-checked once per chunk (not per document)
      - No Supabase writes — READ ONLY against DB

    Args:
        db_canonical_ids: frozen set of canonical IDs currently
            eligible in the DB.  Must equal the adapter expected set
            (set-parity gate).  Pass None to skip parity check.

    Returns a result dict with keys:
        domain_name, object_type, physical_index,
        expected, noop, upsert, failed, batches,
        fence_blocked, alias_drift.

    Raises ProjectionWriteError on any safety gate failure before the
    first write.  Partial writes (fence/alias mid-run) stop cleanly and
    set the corresponding flag.
    """
    result: dict = {
        "domain_name": domain_name,
        "object_type": object_type,
        "physical_index": None,
        "expected": 0,
        "noop": 0,
        "upsert": 0,
        "failed": 0,
        "batches": 0,
        "fence_blocked": False,
        "alias_drift": False,
    }

    # --- initial fence ---
    if _rebuild_active(supabase_client):
        result["fence_blocked"] = True
        return result

    # --- alias freeze ---
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

    result["physical_index"] = physical_index

    # --- adapter lookup ---
    if adapter_map is None:
        from services.shared_search.production_bindings import build_production_adapters
        adapter_map = {a.domain_name: a for a in build_production_adapters(supabase_client)}

    adapter = adapter_map.get(domain_name)
    if adapter is None:
        raise ProjectionWriteError(f"No adapter for domain {domain_name}")

    if adapter.object_type != object_type:
        raise ValueError(
            f"object_type mismatch: adapter.object_type={adapter.object_type!r} "
            f"but requested object_type={object_type!r}"
        )

    # --- PASS 1: collect expected {canonical_id → content_hash} ---
    expected_hashes: dict[str, str] = {}
    duplicates: list[str] = []
    for item in adapter.iter_expected_hashes():
        cid = item["canonical_id"]
        if cid in expected_hashes:
            duplicates.append(cid)
        expected_hashes[cid] = item["content_hash"]

    if duplicates:
        raise ProjectionWriteError(
            f"Duplicate canonical IDs in expected set: {duplicates[:5]} "
            f"(total {len(duplicates)})"
        )

    result["expected"] = len(expected_hashes)

    # --- set parity gate ---
    if db_canonical_ids is not None:
        db_only = db_canonical_ids - set(expected_hashes)
        adapter_only = set(expected_hashes) - db_canonical_ids
        if db_only or adapter_only:
            raise ProjectionWriteError(
                f"Set parity failed for {domain_name}: "
                f"DB-only={len(db_only)}, adapter-only={len(adapter_only)}"
            )

    # --- MGET hash comparison ---
    doc_ids_list = [document_id(object_type, cid) for cid in expected_hashes]
    stored_hashes: dict[str, Optional[str]] = {}
    for i in range(0, len(doc_ids_list), mget_batch_size):
        batch_ids = doc_ids_list[i:i + mget_batch_size]
        stored_hashes.update(
            get_document_content_hashes(os_client, physical_index, batch_ids)
        )

    # --- hash classification ---
    noop_set: set[str] = set()
    upsert_set: set[str] = set()
    for cid, expected_hash in expected_hashes.items():
        stored = stored_hashes.get(document_id(object_type, cid))
        if stored is not None and stored == expected_hash:
            noop_set.add(cid)
        else:
            upsert_set.add(cid)

    result["noop"] = len(noop_set)

    if not upsert_set:
        return result  # all NOOP, nothing to write

    # --- PASS 2: build UPSERT payloads ---
    upsert_items: list[tuple[str, dict]] = []

    for payload in adapter.iter_documents():
        cid = payload.get("canonical_id")
        if cid not in upsert_set:
            continue

        # non-PUBLISHED guard (PUBLISHED-UPSERT-ONLY path)
        pub_status = payload.get("publication_status")
        if pub_status != PUBLICATION_STATUS_PUBLISHED:
            raise ProjectionWriteError(
                f"Non-PUBLISHED payload for {cid}: {pub_status!r} — "
                f"use outbox path for HOLD/DELETE"
            )

        try:
            _doc, wire = prepare_search_document(payload)
        except SearchContractError as exc:
            raise ProjectionWriteError(
                f"normalization failed for {cid}: {exc}"
            ) from exc

        if _doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
            raise ProjectionWriteError(
                f"Non-PUBLISHED after prepare for {cid}: {_doc.publication_status!r}"
            )

        # PASS 1 / PASS 2 hash guard
        pass2_hash = wire.get("content_hash")
        pass1_hash = expected_hashes[cid]
        if pass2_hash != pass1_hash:
            raise ProjectionWriteError(
                f"PASS1/PASS2 hash mismatch for {cid}: "
                f"expected {pass1_hash!r}, got {pass2_hash!r} "
                f"(source changed during activation)"
            )

        upsert_items.append((document_id(object_type, cid), wire))

    # --- missing payload guard ---
    found_ids = {item[0] for item in upsert_items}
    missing = {document_id(object_type, cid) for cid in upsert_set} - found_ids
    if missing:
        raise ProjectionWriteError(
            f"Missing payloads for {len(missing)} UPSERT candidates: "
            f"{list(missing)[:5]}"
        )

    # --- bulk write with per-chunk safety guards ---
    for i in range(0, len(upsert_items), chunk_size):
        chunk = upsert_items[i:i + chunk_size]

        if _rebuild_active(supabase_client):
            result["fence_blocked"] = True
            break

        try:
            current_alias = os_client.indices.get_alias(name=CURRENT_ALIAS)
            current_indices = list(current_alias.keys())
            if len(current_indices) != 1 or current_indices[0] != physical_index:
                result["alias_drift"] = True
                break
        except Exception as exc:
            raise ProjectionWriteError(
                f"alias re-check failed before chunk {i // chunk_size}: {exc}"
            ) from exc

        success, failed = bulk_upsert_documents(
            os_client, physical_index, chunk, chunk_size=len(chunk)
        )
        result["batches"] += 1
        result["upsert"] += success
        result["failed"] += failed

        if failed > 0:
            logger.error(
                "bulk_sync_published_domain: %d failures in batch %d — stopping",
                failed, result["batches"],
            )
            break

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
