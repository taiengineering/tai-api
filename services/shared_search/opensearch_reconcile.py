"""OpenSearch ↔ Domain SoT reconcile — WO-TAI-SHARED-SEARCH-INCREMENTAL-001 §35-§37.

Read-only diagnostic pass:
  1. For each adapter, stream iter_expected_hashes() (SoT declaration)
  2. Scan the live OpenSearch alias for the same object_type
  3. Report MISSING / EXTRA / STALE_HASH / MATCH per domain

Does NOT write to OpenSearch.  Enqueues PENDING SYNC_OBJECT events for
any MISSING or STALE_HASH canonical_ids so the incremental worker will
fix them on the next cycle.

Called by:
    direct://shared_search_reconcile  (§22, §23 scheduler)
    tools/shared_search/opensearch_verify.py  (optional manual trigger)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from opensearchpy import OpenSearch

from services.shared_search.opensearch_client import CURRENT_ALIAS, get_client
from services.shared_search.opensearch_projection import (
    AliasNotReady,
    resolve_alias_target,
)
from services.shared_search.production_bindings import build_production_adapters

logger = logging.getLogger(__name__)

# OpenSearch scroll window for full-index scan
_SCROLL_SIZE = 500
_SCROLL_TTL  = "2m"


@dataclass
class OpenSearchReconcileReport:
    domain_name:     str
    object_type:     str
    expected_count:  int = 0
    current_count:   int = 0
    match:           int = 0
    missing:         list = field(default_factory=list)
    extra:           list = field(default_factory=list)
    stale_by_hash:   list = field(default_factory=list)
    enqueued:        int = 0
    ok:              bool = False

    def to_dict(self) -> dict:
        return {
            "domain_name":    self.domain_name,
            "object_type":    self.object_type,
            "expected_count": self.expected_count,
            "current_count":  self.current_count,
            "match":          self.match,
            "missing":        self.missing[:50],   # cap for log safety
            "extra":          self.extra[:50],
            "stale_by_hash":  self.stale_by_hash[:50],
            "enqueued":       self.enqueued,
            "ok":             self.ok,
        }


# ---------------------------------------------------------------------------
# OpenSearch full scan helpers
# ---------------------------------------------------------------------------

def _scan_alias_for_type(
    client: OpenSearch,
    alias: str,
    object_type: str,
) -> dict[str, str]:
    """Return {canonical_id: content_hash} for all docs of *object_type*
    in the current alias, using scroll API."""
    index: dict[str, str] = {}
    query = {
        "query": {"term": {"object_type": object_type}},
        "_source": ["canonical_id", "content_hash"],
        "size": _SCROLL_SIZE,
    }
    try:
        resp = client.search(
            index=alias,
            body=query,
            scroll=_SCROLL_TTL,
        )
    except Exception as exc:
        logger.warning("scan_alias failed for %s/%s: %s", alias, object_type, exc)
        return index

    scroll_id = resp.get("_scroll_id")
    hits      = resp["hits"]["hits"]

    while hits:
        for hit in hits:
            src = hit.get("_source", {})
            cid  = src.get("canonical_id")
            chash = src.get("content_hash")
            if cid:
                index[str(cid)] = chash or ""
        if not scroll_id:
            break
        try:
            resp  = client.scroll(scroll_id=scroll_id, scroll=_SCROLL_TTL)
            hits  = resp["hits"]["hits"]
            scroll_id = resp.get("_scroll_id", scroll_id)
        except Exception as exc:
            logger.warning("scroll failed: %s", exc)
            break

    if scroll_id:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

    return index


# ---------------------------------------------------------------------------
# Per-domain reconcile
# ---------------------------------------------------------------------------

def _reconcile_domain(
    adapter,
    client: OpenSearch,
    alias: str,
    supabase_client,
) -> OpenSearchReconcileReport:
    report = OpenSearchReconcileReport(
        domain_name=adapter.domain_name,
        object_type=adapter.object_type,
    )

    # 1. SoT declared hashes
    sot: dict[str, str] = {}
    for row in adapter.iter_expected_hashes():
        cid  = str(row.get("canonical_id", ""))
        chash = str(row.get("content_hash", ""))
        if cid:
            sot[cid] = chash
    report.expected_count = len(sot)

    # 2. Current OpenSearch projection
    current = _scan_alias_for_type(client, alias, adapter.object_type)
    report.current_count = len(current)

    # 3. Diff
    sot_ids     = set(sot)
    current_ids = set(current)

    report.missing      = sorted(sot_ids - current_ids)
    report.extra        = sorted(current_ids - sot_ids)
    report.stale_by_hash = sorted(
        cid for cid in sot_ids & current_ids
        if sot[cid] != current[cid]
    )
    report.match = len(sot_ids & current_ids) - len(report.stale_by_hash)
    report.ok    = (not report.missing and not report.extra
                    and not report.stale_by_hash)

    # 4. Enqueue MISSING + STALE for incremental repair
    to_repair = report.missing + report.stale_by_hash
    for cid in to_repair:
        try:
            supabase_client.rpc("enqueue_search_index_sync", {
                "p_domain_name":  adapter.domain_name,
                "p_object_type":  adapter.object_type,
                "p_canonical_id": cid,
                "p_reason":       "reconcile",
            }).execute()
            report.enqueued += 1
        except Exception as exc:
            logger.warning(
                "reconcile enqueue failed %s/%s: %s",
                adapter.domain_name, cid, exc,
            )

    return report


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_reconcile(
    *,
    supabase_client=None,
    os_client: Optional[OpenSearch] = None,
) -> dict:
    """Run a full reconcile pass across all production domains.

    Returns observability dict:
        alias          — physical index name used
        domains        — list of per-domain OpenSearchReconcileReport.to_dict()
        total_missing  — sum of missing across all domains
        total_extra    — sum of extra
        total_stale    — sum of stale_by_hash
        total_enqueued — sum of enqueued repair events
        ok             — True if all domains are clean
    """
    if supabase_client is None:
        raise ValueError("run_reconcile requires supabase_client")

    c = os_client or get_client()

    try:
        alias_target = resolve_alias_target(c)
    except AliasNotReady as exc:
        logger.error("reconcile aborted — alias not ready: %s", exc)
        return {"error": str(exc), "ok": False}

    adapters = build_production_adapters(supabase_client)
    reports  = []

    for adapter in adapters:
        logger.info(
            "reconcile %s/%s …", adapter.domain_name, adapter.object_type
        )
        rpt = _reconcile_domain(adapter, c, CURRENT_ALIAS, supabase_client)
        reports.append(rpt.to_dict())
        logger.info(
            "  %s: expected=%d current=%d match=%d missing=%d extra=%d stale=%d enqueued=%d ok=%s",
            rpt.domain_name, rpt.expected_count, rpt.current_count,
            rpt.match, len(rpt.missing), len(rpt.extra),
            len(rpt.stale_by_hash), rpt.enqueued, rpt.ok,
        )

    total_missing  = sum(len(r["missing"])      for r in reports)
    total_extra    = sum(len(r["extra"])         for r in reports)
    total_stale    = sum(len(r["stale_by_hash"]) for r in reports)
    total_enqueued = sum(r["enqueued"]           for r in reports)
    all_ok         = all(r["ok"]                 for r in reports)

    return {
        "alias":          alias_target,
        "domains":        reports,
        "total_missing":  total_missing,
        "total_extra":    total_extra,
        "total_stale":    total_stale,
        "total_enqueued": total_enqueued,
        "ok":             all_ok,
    }
