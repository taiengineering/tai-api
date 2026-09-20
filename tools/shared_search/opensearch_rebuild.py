"""OpenSearch full rebuild tool — WO-TAI-SHARED-SEARCH-F3 §46 + F3-G1 §2-§17.

Rebuild flow (§16 F3-G1):
  1. Supabase client 생성
  2. build_production_adapters(supabase_client)    ← real F2 API (§3)
  3. begin_run
  4. create_candidate_index
  5. for each adapter:
       adapter.iter_documents()                     ← real F2 API
         → prepare_search_document()               ← F1 canonical (§4-§5)
         → PUBLISHED only (§6)
         → global identity duplicate guard (§7-§9)
         → bulk stage
  6. per-domain expected/indexed comparison (§10)
  7. failed_bulk_items == 0 check (§8)
  8. refresh + validate_run (HARD: actual == expected, per-domain, §9-§10)
  9. promote() — VALIDATED guard (§12-§14)
 10. rebuild fence OFF (§39-§44 INCREMENTAL-001)

Hard-fail: any partial bulk failure, count mismatch, or duplicate → FAILED,
alias unchanged.  Rebuild fence is reset OFF on any exit path.

OpenSearch _id aggregation is NOT used for duplicate detection (§6 BLOCKER B):
OpenSearch _id field is not aggregatable. Duplicate detection is done in TAI
canonical preparation (global_seen identity tracking), before any write.

Usage:
    DRY RUN (no OpenSearch writes):
        python3 tools/shared_search/opensearch_rebuild.py --dry-run

    FULL REBUILD (requires Owner GO — production OpenSearch):
        python3 tools/shared_search/opensearch_rebuild.py --full

Env vars:
    TAI_OPENSEARCH_URL
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY  (or SUPABASE_KEY)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from services.shared_search.contract import (
    PUBLICATION_STATUS_PUBLISHED,
    SearchContractError,
)
from services.shared_search.production_bindings import build_production_adapters
from services.shared_search.writer import prepare_search_document
from services.shared_search.census import run_census
from services.shared_search.opensearch_client import get_client
from services.shared_search.opensearch_projection import doc_to_os_body
from services.shared_search.opensearch_store import (
    OpenSearchSearchStore,
    RebuildRejected,
    RUN_STATUS_FAILED,
    document_id,
)


# ---------------------------------------------------------------------------
# Supabase client factory (same pattern as tools/shared_search/f2_census.py)
# ---------------------------------------------------------------------------

def _build_supabase_client():
    """Import supabase-py lazily so CLI stays importable in tests."""
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Rebuild fence helpers (§39-§44 INCREMENTAL-001)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


def _fence_on(supabase, candidate_index: str) -> int:
    """Set rebuild_active=True; return start_event_id watermark.

    start_event_id = max(id) from search_index_outbox at this moment.
    Incremental workers skip writes for events that arrive while the
    fence is active — they return to PENDING and will be processed
    after fence drops.  Events with id > start_event_id that arrive
    during the rebuild are replayed into the candidate before promotion.
    """
    # Watermark: highest outbox id at fence-set time
    r = (supabase.table("search_index_outbox")
                 .select("id")
                 .order("id", desc=True)
                 .limit(1)
                 .execute())
    rows = list(getattr(r, "data", None) or [])
    start_event_id = rows[0]["id"] if rows else 0

    supabase.table("search_index_runtime_state").update({
        "rebuild_active":     True,
        "candidate_index":    candidate_index,
        "rebuild_started_at": _now_iso(),
        "start_event_id":     start_event_id,
        "updated_at":         _now_iso(),
    }).eq("id", 1).execute()

    logger.info(
        "Rebuild fence ON — candidate=%s start_event_id=%s",
        candidate_index, start_event_id,
    )
    return start_event_id


def _fence_off(supabase) -> None:
    """Clear rebuild fence.  Called on both promote-success and any failure."""
    try:
        supabase.table("search_index_runtime_state").update({
            "rebuild_active":  False,
            "candidate_index": None,
            "updated_at":      _now_iso(),
        }).eq("id", 1).execute()
        logger.info("Rebuild fence OFF")
    except Exception as exc:
        logger.error("fence_off failed (non-fatal): %s", exc)


def _replay_outbox_into_candidate(
    supabase,
    adapters: list,
    client,
    candidate_index: str,
    start_event_id: int,
) -> dict:
    """Replay outbox events id > start_event_id into the candidate physical index.

    Called after validate_run() (base parity confirmed), before promote().
    Ensures events that arrived during the rebuild are applied to the
    candidate so promotion does not expose stale data to any consumer.

    Replay target = candidate physical index (NOT the current alias).
    """
    adapter_map = {a.domain_name: a for a in adapters}
    seen: set[tuple[str, str, str]] = set()
    replayed = deleted = errors = 0

    batch_start = 0
    while True:
        r = (supabase.table("search_index_outbox")
                     .select("domain_name,object_type,canonical_id")
                     .gt("id", start_event_id)
                     .order("id")
                     .range(batch_start, batch_start + 999)
                     .execute())
        rows = list(getattr(r, "data", None) or [])
        if not rows:
            break

        for row in rows:
            identity = (row["domain_name"], row["object_type"], row["canonical_id"])
            if identity in seen:
                continue  # only replay latest state per identity
            seen.add(identity)

            adapter = adapter_map.get(row["domain_name"])
            if adapter is None:
                continue

            doc_id_val = document_id(row["object_type"], row["canonical_id"])

            try:
                payload = adapter.object_reindex_payload(row["canonical_id"])
                if payload is None:
                    # Tombstone: remove from candidate (ignore 404)
                    try:
                        client.delete(index=candidate_index, id=doc_id_val, refresh=False)
                    except Exception:
                        pass
                    deleted += 1
                else:
                    try:
                        doc, wire = prepare_search_document(payload)
                    except SearchContractError as exc:
                        logger.warning("replay norm error %s: %s", doc_id_val, exc)
                        errors += 1
                        continue
                    if doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
                        continue
                    body = doc_to_os_body(wire)
                    client.index(
                        index=candidate_index, id=doc_id_val, body=body, refresh=False
                    )
                    replayed += 1
            except Exception as exc:
                logger.warning("replay error %s: %s", doc_id_val, exc)
                errors += 1

        if len(rows) < 1000:
            break
        batch_start += 1000

    logger.info(
        "Candidate replay: replayed=%d deleted=%d errors=%d (id>%s)",
        replayed, deleted, errors, start_event_id,
    )
    return {"replayed": replayed, "deleted": deleted, "errors": errors}


# ---------------------------------------------------------------------------
# Dry-run (no OpenSearch writes, uses real F2 adapter API + census.py)
# §3 F3-G1: Use adapter.iter_documents() → prepare_search_document() via
#            run_census(). Never duplicate census logic inside this script.
# ---------------------------------------------------------------------------

def dry_run() -> None:
    """Dry-run census using real F2 adapter API (§17 F3-G1).

    Reports per-domain: yielded, published, hold, removed, duplicates,
    normalization_failure — without writing to OpenSearch.

    Uses run_census() from services/shared_search/census.py as the
    single census authority. No domain census logic is duplicated here.

    Also performs global cross-adapter duplicate identity check
    (object_type, canonical_id) in informational mode only.
    """
    supabase = _build_supabase_client()
    adapters = build_production_adapters(supabase)

    print("=== DRY RUN CENSUS ===")
    print(f"  {'Domain':20s} {'yielded':>8s} {'published':>10s} {'hold':>6s} "
          f"{'removed':>8s} {'dup':>5s} {'norm_fail':>10s}")

    grand_total_yielded    = 0
    grand_total_published  = 0
    grand_total_hold       = 0
    grand_total_removed    = 0
    grand_total_dup        = 0
    grand_total_norm_fail  = 0

    # Global cross-adapter identity tracking
    global_seen: set[tuple[str, str]] = set()
    cross_adapter_dups: list[str] = []

    for adapter in adapters:
        # run_census() is READ-only and uses normalize_document internally.
        # It tracks published / hold / removed / duplicate_canonical_ids.
        census = run_census(adapter)

        grand_total_yielded   += census.yielded_count
        grand_total_published += census.published
        grand_total_hold      += census.hold
        grand_total_removed   += census.removed
        grand_total_dup       += census.duplicate_canonical_ids
        grand_total_norm_fail += (
            census.normalization_failures
            + census.identity_failures
            + census.title_failures
            + census.timestamp_failures
        )

        print(
            f"  {adapter.domain_name:20s} "
            f"{census.yielded_count:8d} "
            f"{census.published:10d} "
            f"{census.hold:6d} "
            f"{census.removed:8d} "
            f"{census.duplicate_canonical_ids:5d} "
            f"{census.normalization_failures:10d}"
        )

        # Cross-adapter global duplicate detection (informational)
        # Re-iterate adapter to check cross-domain identity conflicts
        for payload in adapter.iter_documents():
            try:
                doc, _ = prepare_search_document(payload)
            except SearchContractError:
                continue
            if doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
                continue
            identity = (doc.object_type, doc.canonical_id)
            if identity in global_seen:
                cross_adapter_dups.append(
                    f"{adapter.domain_name}:{doc.canonical_id}"
                )
            else:
                global_seen.add(identity)

    print(f"  {'TOTAL':20s} "
          f"{grand_total_yielded:8d} "
          f"{grand_total_published:10d} "
          f"{grand_total_hold:6d} "
          f"{grand_total_removed:8d} "
          f"{grand_total_dup:5d} "
          f"{grand_total_norm_fail:10d}")

    if cross_adapter_dups:
        print(f"\n  WARN: {len(cross_adapter_dups)} cross-adapter duplicates detected:")
        for dup in cross_adapter_dups[:10]:
            print(f"    {dup}")
    else:
        print("\n  Cross-adapter duplicate check: CLEAN")

    print()
    print(f"  OpenSearch write = 0, DB write = 0")


# ---------------------------------------------------------------------------
# Full rebuild
# ---------------------------------------------------------------------------

def full_rebuild() -> None:
    """Production full rebuild (§16 F3-G1 + §39-§44 INCREMENTAL-001).

    Duplicate detection via global_seen (§7-§9 F3-G1):
    OpenSearch _id field is NOT aggregatable — no _id cardinality check.
    Duplicates are detected in TAI canonical preparation stage,
    before any OpenSearch write.

    Rebuild fence (§39-§44):
    Sets search_index_runtime_state.rebuild_active=True during the run so
    incremental workers skip writes until the rebuild is complete.
    Fence is cleared on both success and failure paths.
    """
    supabase = _build_supabase_client()
    adapters = build_production_adapters(supabase)
    client   = get_client()
    store    = OpenSearchSearchStore(client)

    expected_domains = [a.domain_name for a in adapters]
    run_id = store.begin_run(expected_domains)
    logger.info("Run ID: %s", run_id)

    try:
        idx = store.create_candidate_index(run_id)
        logger.info("Candidate index: %s", idx)

        # Fence ON — incremental workers halt writes during rebuild (§39-§42)
        start_event_id = _fence_on(supabase, idx)

        total_prepared   = 0
        per_domain_expected: dict[str, int] = {}

        # §7-§9 F3-G1: Global identity guard — duplicate detection before write
        # OpenSearch _id aggregation on _id is NOT supported (not aggregatable).
        # TAI is the single authority for duplicate detection.
        global_seen: set[tuple[str, str]] = set()

        for adapter in adapters:
            domain = adapter.domain_name
            prepared_docs: list[dict] = []
            prepared_count = 0

            for raw_payload in adapter.iter_documents():
                # §4-§5: canonical prepare (normalize + content_hash)
                try:
                    doc, wire = prepare_search_document(raw_payload)
                except SearchContractError as exc:
                    logger.warning("Normalization failure %s: %s", domain, exc)
                    continue

                # §6: PUBLISHED only
                if doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
                    continue

                # §7-§9: Global identity duplicate guard
                identity = (doc.object_type, doc.canonical_id)
                if identity in global_seen:
                    reason = (
                        f"Duplicate canonical identity "
                        f"({doc.object_type}, {doc.canonical_id}) "
                        f"in domain={domain}. Rebuild aborted."
                    )
                    store.fail_run(run_id, reason)
                    raise RebuildRejected(reason)
                global_seen.add(identity)

                prepared_docs.append(wire)
                prepared_count += 1

            per_domain_expected[domain] = prepared_count
            total_prepared += prepared_count

            # Bulk stage (raises RebuildRejected on any failure §8)
            indexed, failed = store.stage_documents(
                run_id,
                iter(prepared_docs),
                domain_name=domain,
                prepared_count=prepared_count,
            )
            logger.info(
                "  %s: prepared=%d, indexed=%d, failed=%d",
                domain, prepared_count, indexed, failed,
            )

        logger.info(
            "Total: prepared=%d, domains=%d", total_prepared, len(adapters)
        )

        # §9-§10: Hard validation on base build (actual == expected, per-domain parity)
        store.validate_run(
            run_id,
            expected_count=total_prepared,
            per_domain_expected=per_domain_expected,
        )

        # §43-§44: Replay events that arrived after fence-on into candidate
        # before promotion so the promoted index is never stale.
        replay = _replay_outbox_into_candidate(
            supabase, adapters, client, idx, start_event_id
        )
        logger.info(
            "Replay complete: replayed=%d deleted=%d errors=%d",
            replay["replayed"], replay["deleted"], replay["errors"],
        )

        # §12-§14: Promote with VALIDATED guard
        new_idx = store.promote(run_id)

        # Fence OFF — incremental workers resume (§43-§44)
        _fence_off(supabase)
        logger.info("REBUILD COMPLETE → %s  (start_event_id=%s)", new_idx, start_event_id)

    except RebuildRejected as exc:
        _fence_off(supabase)
        logger.error("REBUILD FAILED (safety blocked): %s", exc)
        sys.exit(1)
    except Exception as exc:
        store.fail_run(run_id, str(exc))
        _fence_off(supabase)
        logger.error("REBUILD FAILED (unexpected): %s", exc)
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Census without OpenSearch writes")
    g.add_argument("--full", action="store_true",
                   help="REQUIRES Owner GO — production write")
    args = p.parse_args()

    if args.dry_run:
        dry_run()
    else:
        full_rebuild()


if __name__ == "__main__":
    main()
