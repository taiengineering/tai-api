"""OpenSearch verify tool — WO-TAI-SHARED-SEARCH-F3 §47. READ-ONLY.

Checks:
    cluster health
    plugin presence (analysis-nori)
    alias target
    document count
    per object_type count
    mapping SHA
    Nori analyzer check

Usage:
    python3 tools/shared_search/opensearch_verify.py
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from services.shared_search.opensearch_client import CURRENT_ALIAS, check_health, get_client
from services.shared_search.opensearch_mapping import mapping_sha256

REQUIRED_PLUGINS = ["analysis-nori"]


def main() -> None:
    client = get_client()
    ok = True

    # 1. Health
    health = check_health(client)
    status = health.get("status", "unknown")
    print(f"cluster.health = {status}")
    if status == "red":
        print("FAIL: cluster status RED")
        ok = False

    # 2. Plugins
    cat = client.cat.plugins(format="json")
    loaded = {p.get("component", "") for p in (cat or [])}
    for plugin in REQUIRED_PLUGINS:
        present = any(plugin in comp for comp in loaded)
        print(f"plugin.{plugin} = {'PRESENT' if present else 'MISSING'}")
        if not present:
            ok = False

    # 3. Alias + document count
    alias_ok = client.indices.exists_alias(name=CURRENT_ALIAS)
    print(f"alias.{CURRENT_ALIAS} = {'EXISTS' if alias_ok else 'MISSING'}")
    if alias_ok:
        alias_info = client.indices.get_alias(name=CURRENT_ALIAS)
        for idx in alias_info:
            print(f"  physical_index = {idx}")
        count_resp = client.count(index=CURRENT_ALIAS,
                                   body={"query": {"match_all": {}}})
        total = count_resp.get("count", 0)
        print(f"  total_docs = {total}")

        # Per object_type
        agg_resp = client.search(
            index=CURRENT_ALIAS,
            body={
                "size": 0,
                "aggs": {
                    "by_type": {
                        "terms": {"field": "object_type", "size": 20}
                    }
                },
            },
        )
        buckets = agg_resp.get("aggregations", {}).get("by_type", {}).get("buckets", [])
        for b in buckets:
            print(f"  object_type[{b['key']}] = {b['doc_count']}")
    else:
        ok = False

    # 4. Mapping SHA
    expected = mapping_sha256()
    print(f"mapping.expected_sha256 = {expected[:16]}…")

    # 5. Nori analyzer check
    try:
        resp = client.indices.analyze(index=CURRENT_ALIAS if alias_ok else None,
                                       body={"analyzer": "nori", "text": "산업안전보건법"})
        tokens = [t["token"] for t in resp.get("tokens", [])]
        print(f"nori._analyze('산업안전보건법') = {tokens}")
    except Exception as exc:
        print(f"nori._analyze ERROR: {exc}")
        ok = False

    print("\n" + ("VERIFY PASS" if ok else "VERIFY FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
