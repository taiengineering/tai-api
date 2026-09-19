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
         → duplicate guard (§11)
         → stage_documents() bulk
  6. per-domain expected/indexed comparison (§10)
  7. failed_bulk_items == 0 check (§8)
  8. refresh + validate_run (HARD: actual == expected, §9)
  9. check_duplicates()
  10. promote() — VALIDATED guard (§12-§14)

Hard-fail: any partial bulk failure or count mismatch → FAILED, alias unchanged.

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

from services.shared_search.contract import PUBLICATION_STATUS_PUBLISHED
from services.shared_search.production_bindings import build_production_adapters
from services.shared_search.writer import prepare_search_document
from services.shared_search.contract import SearchContractError
from services.shared_search.opensearch_client import get_client
from services.shared_search.opensearch_store import (
    OpenSearchSearchStore,
    RebuildRejected,
    RUN_STATUS_FAILED,
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
# Dry-run (no OpenSearch writes, uses real adapter API)
# ---------------------------------------------------------------------------

def dry_run() -> None:
    """Dry-run census using real F2 adapter API (§17 F3-G1).

    Reports per-domain: eligible, prepared PUBLISHED, HOLD, duplicate,
    normalization failure — without writing to OpenSearch.
    """
    from services.shared_search.indexer import Indexer
    from services.shared_search.writer import MemoryStore

    supabase = _build_supabase_client()
    adapters = build_production_adapters(supabase)
    store = MemoryStore()
    indexer = Indexer(store)

    print("=== DRY RUN CENSUS ===")
    grand_total_eligible = 0
    grand_total_published = 0

    for adapter in adapters:
        census = indexer.dry_run(adapter)
        published = census.published_count
        eligible  = census.eligible_count
        grand_total_eligible  += eligible
        grand_total_published += published
        print(
            f"  {adapter.domain_name:20s} "
            f"eligible={eligible:6d}  "
            f"published={published:6d}  "
            f"hold={census.hold_count:4d}  "
            f"dup={census.duplicate_count:4d}  "
            f"norm_fail={census.normalization_failures:4d}"
        )

    print(f"  {'TOTAL':20s} eligible={grand_total_eligible:6d}  published={grand_total_published:6d}")


# ---------------------------------------------------------------------------
# Full rebuild
# ---------------------------------------------------------------------------

def full_rebuild() -> None:
    """Production full rebuild (§16 F3-G1).

    Hard-fails on any bulk error or count mismatch.
    Promotion blocked unless all guards pass.
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

        total_prepared   = 0
        per_domain_expected: dict[str, int] = {}

        for adapter in adapters:
            domain = adapter.domain_name
            prepared_docs: list[dict] = []
            prepared_count = 0
            seen_ids: set[str] = set()
            dups_this_domain = 0

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

                # §11: duplicate guard
                identity = f"{doc.object_type}::{doc.canonical_id}"
                if identity in seen_ids:
                    dups_this_domain += 1
                    logger.warning("Duplicate identity in %s: %s", domain, identity)
                    continue
                seen_ids.add(identity)

                prepared_docs.append(wire)
                prepared_count += 1

            if dups_this_domain > 0:
                reason = (
                    f"Domain {domain} has {dups_this_domain} duplicate "
                    "canonical identities. Rebuild aborted."
                )
                store.fail_run(run_id, reason)
                raise RebuildRejected(reason)

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

        # §11: Duplicate check across full index
        store.check_duplicates(run_id)

        # §9-§10: Hard validation (actual == expected, per-domain parity)
        store.validate_run(
            run_id,
            expected_count=total_prepared,
            per_domain_expected=per_domain_expected,
        )

        # §12-§14: Promote with VALIDATED guard
        new_idx = store.promote(run_id)
        logger.info("REBUILD COMPLETE → %s", new_idx)

    except RebuildRejected as exc:
        logger.error("REBUILD FAILED (safety blocked): %s", exc)
        sys.exit(1)
    except Exception as exc:
        store.fail_run(run_id, str(exc))
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
