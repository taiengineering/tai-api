"""OpenSearch bootstrap tool — WO-TAI-SHARED-SEARCH-F3 §45.

READ-ONLY verification + mapping setup helper.
Production execute = OWNER GO前 FORBIDDEN.

Usage (dry-run only — no production writes):
    python3 tools/shared_search/opensearch_bootstrap.py --check

    # Creates candidate index (local/test only):
    python3 tools/shared_search/opensearch_bootstrap.py \\
        --create-candidate --run-id <uuid>

Env vars required:
    TAI_OPENSEARCH_URL   (e.g. http://localhost:9200)
"""
from __future__ import annotations

import argparse
import json
import sys

# Allow running from repo root
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from services.shared_search.opensearch_client import (
    CURRENT_ALIAS,
    ENV_URL,
    OpenSearchUnavailable,
    check_health,
    get_client,
)
from services.shared_search.opensearch_mapping import (
    INDEX_BODY,
    candidate_index_name,
    mapping_sha256,
)

# ---------------------------------------------------------------------------

REQUIRED_PLUGINS = ["analysis-nori"]

GOLDEN_TERMS = [
    "지게차", "밀폐공간", "밀폐공간작업", "산업안전보건법",
    "안전보건관리책임자", "물질안전보건자료", "이동식크레인",
    "작업발판", "안전난간", "MSDS",
]


def cmd_check(args) -> int:
    """Verify cluster health, Nori plugin, current alias target."""
    client = get_client()

    # 1. Health
    health = check_health(client)
    status = health.get("status", "unknown")
    print(f"[health] status={status}  nodes={health.get('number_of_nodes')}")
    if status == "red":
        print("ERROR: cluster status is RED")
        return 1

    # 2. Plugins
    cat = client.cat.plugins(format="json")
    loaded = {p.get("component", "") for p in (cat or [])}
    for plugin in REQUIRED_PLUGINS:
        ok = any(plugin in comp for comp in loaded)
        mark = "✓" if ok else "✗ MISSING"
        print(f"[plugin] {plugin}: {mark}")
        if not ok:
            print(f"ERROR: required plugin '{plugin}' not found in cluster.")
            return 1

    # 3. Current alias
    alias_ok = client.indices.exists_alias(name=CURRENT_ALIAS)
    print(f"[alias] {CURRENT_ALIAS}: {'EXISTS' if alias_ok else 'NOT YET CREATED'}")
    if alias_ok:
        alias_info = client.indices.get_alias(name=CURRENT_ALIAS)
        for idx in alias_info:
            print(f"  → physical index: {idx}")

    # 4. Mapping hash
    print(f"[mapping] expected SHA-256: {mapping_sha256()[:16]}…")

    print("\nBootstrap check PASS")
    return 0


def cmd_nori_analyze(args) -> int:
    """Run _analyze on Golden terms and print token output (§14, §49)."""
    client = get_client()
    results = {}
    for term in GOLDEN_TERMS:
        resp = client.indices.analyze(body={
            "analyzer": "nori",  # built-in shorthand
            "text": term,
        })
        tokens = [t["token"] for t in resp.get("tokens", [])]
        results[term] = tokens
        print(f"  {term!r:30s} → {tokens}")

    # Save evidence artifact
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "docs", "search", "evidence")
    os.makedirs(out_dir, exist_ok=True)
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(out_dir, f"f3_opensearch_nori_analyze_{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"analyzer": "nori", "results": results}, fh,
                  ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {out_path}")
    return 0


def cmd_create_candidate(args) -> int:
    """Create a candidate index for a given run_id (local/test only)."""
    client = get_client()
    run_id = args.run_id
    from services.shared_search.opensearch_store import OpenSearchSearchStore
    store = OpenSearchSearchStore(client)
    idx = store.create_candidate_index(run_id)
    print(f"Created candidate index: {idx}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="OpenSearch bootstrap helper")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("check", help="Verify cluster, plugins, alias")
    sub.add_parser("nori-analyze", help="Run _analyze on Golden terms")
    cc = sub.add_parser("create-candidate", help="Create candidate index (test)")
    cc.add_argument("--run-id", required=True)
    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)
    cmd_map = {
        "check":            cmd_check,
        "nori-analyze":     cmd_nori_analyze,
        "create-candidate": cmd_create_candidate,
    }
    sys.exit(cmd_map[args.cmd](args))


if __name__ == "__main__":
    main()
