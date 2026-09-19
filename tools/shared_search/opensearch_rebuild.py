"""OpenSearch full rebuild tool — WO-TAI-SHARED-SEARCH-F3 §46.

Reuses existing:
    build_production_adapters()   F2 Domain adapter wiring
    Indexer                       F2 common indexer
    OpenSearchSearchStore         F3 bulk writer

Rebuild flow (§33):
    begin_run → create_candidate_index → stage_documents (bulk)
    → validate_run → promote (atomic alias) → rollback if needed

Usage:
    DRY RUN (local):
    python3 tools/shared_search/opensearch_rebuild.py --dry-run

    FULL REBUILD (production — requires Owner GO):
    python3 tools/shared_search/opensearch_rebuild.py --full

Env vars:
    TAI_OPENSEARCH_URL
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from services.shared_search.production_bindings import build_production_adapters
from services.shared_search.indexer import Indexer
from services.shared_search.opensearch_client import get_client
from services.shared_search.opensearch_store import OpenSearchSearchStore


def dry_run() -> None:
    """Index all domains in-memory (no OpenSearch write). Reports counts."""
    adapters = build_production_adapters()
    indexer  = Indexer(adapters=adapters)
    census   = indexer.dry_run_census()
    print("=== DRY RUN CENSUS ===")
    for domain, stats in census.items():
        print(f"  {domain}: {stats}")
    print(f"  TOTAL: {sum(s.get('yielded', 0) for s in census.values())}")


def full_rebuild() -> None:
    """Production full rebuild — requires TAI_OPENSEARCH_URL."""
    client  = get_client()
    store   = OpenSearchSearchStore(client)
    adapters = build_production_adapters()
    indexer  = Indexer(adapters=adapters)

    expected_domains = [a.domain for a in adapters]
    run_id = store.begin_run(expected_domains)
    print(f"Run ID: {run_id}")

    try:
        idx = store.create_candidate_index(run_id)
        print(f"Candidate index: {idx}")

        total_indexed = 0
        total_failed  = 0
        for adapter in adapters:
            docs = list(indexer.build_domain(adapter.domain))
            ok, fail = store.stage_documents(run_id, docs)
            total_indexed += ok
            total_failed  += fail
            print(f"  {adapter.domain}: indexed={ok}, failed={fail}")

        print(f"Total indexed={total_indexed}, failed={total_failed}")
        ok = store.validate_run(run_id, expected_count=total_indexed)
        if not ok:
            print("Validation FAILED — run aborted")
            sys.exit(1)

        new_idx = store.promote(run_id)
        print(f"Promoted → {new_idx}")
        print("REBUILD COMPLETE")
    except Exception as exc:
        store.fail_run(run_id, str(exc))
        print(f"REBUILD FAILED: {exc}")
        raise


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--full",    action="store_true",
                   help="REQUIRES Owner GO — production write")
    args = p.parse_args()
    if args.dry_run:
        dry_run()
    else:
        full_rebuild()


if __name__ == "__main__":
    main()
