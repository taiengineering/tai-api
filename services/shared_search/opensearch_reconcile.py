"""OpenSearch reconciliation — SoT ↔ OpenSearch index parity check.

Reconciliation reads the Domain adapter's expected hashes
(``adapter.iter_expected_hashes()``) and compares them against what is
actually indexed in OpenSearch.  Discrepancies are enqueued into the
durable outbox for the incremental indexer to repair.

Report categories:
  missing         — expected by SoT but absent from OpenSearch
  stale_by_hash   — present in OpenSearch but hash differs from SoT
  extra           — present in OpenSearch but absent from SoT
                    (adapter will return None → tombstone on replay)

All three categories are enqueued (BLOCKER 5A: extra → enqueue with
``p_reason="reconcile_extra"`` so the incremental worker tombstones them).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class ReconcileReport:
    domain_name: str
    object_type: str
    expected: int = 0
    indexed: int = 0
    missing: list = field(default_factory=list)
    stale_by_hash: list = field(default_factory=list)
    extra: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            not self.missing
            and not self.stale_by_hash
            and not self.extra
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_os_domain(client, index: str, object_type: str, *, page_size: int = 500) -> dict[str, str]:
    """Scan OpenSearch for all docs of object_type using search_after (no 10k cap).

    Returns ``{doc_id: content_hash}`` for the domain.
    """
    result: dict[str, str] = {}
    search_after = None
    while True:
        body: dict = {
            "query": {"term": {"object_type": object_type}},
            "_source": ["content_hash", "canonical_id"],
            "size": page_size,
            "sort": [{"_id": "asc"}],
        }
        if search_after:
            body["search_after"] = search_after
        resp = client.search(index=index, body=body)
        hits = (resp.get("hits") or {}).get("hits") or []
        if not hits:
            break
        for hit in hits:
            doc_id = hit.get("_id", "")
            src = hit.get("_source") or {}
            result[doc_id] = src.get("content_hash") or ""
        search_after = hits[-1].get("sort")
        if len(hits) < page_size:
            break
    return result


def _domain_id(object_type: str, canonical_id: str) -> str:
    return f"{object_type}::{canonical_id}"


# ---------------------------------------------------------------------------
# Per-domain reconciliation
# ---------------------------------------------------------------------------

def _reconcile_domain(
    adapter,
    client,
    index: str,
    supabase: Any,
) -> ReconcileReport:
    """Reconcile one domain adapter against the live OpenSearch index."""
    domain_name = adapter.domain_name
    object_type = adapter.object_type

    report = ReconcileReport(domain_name=domain_name, object_type=object_type)

    # --- SoT side ---
    sot: dict[str, str] = {}   # {doc_id: content_hash}
    for row in adapter.iter_expected_hashes():
        cid = str(row.get("canonical_id") or "")
        h = row.get("content_hash") or ""
        if cid:
            sot[_domain_id(object_type, cid)] = h
    report.expected = len(sot)

    # --- OpenSearch side ---
    try:
        os_map = _scan_os_domain(client, index, object_type)
    except Exception as exc:
        logger.warning("reconcile OS scan failed for %s: %s", domain_name, exc)
        os_map = {}
    report.indexed = len(os_map)

    # --- Classify ---
    sot_set = set(sot)
    os_set = set(os_map)

    missing = []
    stale_by_hash = []
    extra = []

    for doc_id in sot_set - os_set:
        # Extract canonical_id from doc_id (format: object_type::canonical_id)
        cid = doc_id.split("::", 1)[1] if "::" in doc_id else doc_id
        missing.append({"doc_id": doc_id, "canonical_id": cid})

    for doc_id in sot_set & os_set:
        if sot[doc_id] != os_map[doc_id]:
            cid = doc_id.split("::", 1)[1] if "::" in doc_id else doc_id
            stale_by_hash.append({
                "doc_id": doc_id,
                "canonical_id": cid,
                "sot_hash": sot[doc_id],
                "os_hash": os_map[doc_id],
            })

    for doc_id in os_set - sot_set:
        cid = doc_id.split("::", 1)[1] if "::" in doc_id else doc_id
        extra.append({"doc_id": doc_id, "canonical_id": cid})

    report.missing = missing
    report.stale_by_hash = stale_by_hash
    report.extra = extra

    # --- Enqueue repairs (BLOCKER 5A: missing + stale + extra) ---
    to_repair = report.missing + report.stale_by_hash + report.extra

    for item in to_repair:
        cid = item["canonical_id"]
        if item in report.extra:
            reason = "reconcile_extra"
        else:
            reason = "reconcile"
        try:
            supabase.rpc("enqueue_search_index_sync", {
                "p_domain_name": domain_name,
                "p_object_type": object_type,
                "p_canonical_id": cid,
                "p_event_key": f"reconcile:{domain_name}:{cid}",
                "p_reason": reason,
            }).execute()
        except Exception as exc:
            logger.warning("enqueue reconcile failed for %s/%s: %s", domain_name, cid, exc)

    return report


# ---------------------------------------------------------------------------
# Full reconciliation run
# ---------------------------------------------------------------------------

def run_reconcile(
    adapters: list,
    client,
    index: str,
    supabase: Any,
) -> dict:
    """Reconcile all adapters. Returns a summary dict."""
    reports = []
    total_missing = 0
    total_stale = 0
    total_extra = 0
    total_enqueued = 0
    all_ok = True

    for adapter in adapters:
        try:
            report = _reconcile_domain(adapter, client, index, supabase)
            reports.append(report)
            total_missing += len(report.missing)
            total_stale += len(report.stale_by_hash)
            total_extra += len(report.extra)
            total_enqueued += len(report.missing) + len(report.stale_by_hash) + len(report.extra)
            if not report.ok:
                logger.warning(
                    "Reconcile %s: missing=%d stale=%d extra=%d",
                    report.domain_name,
                    len(report.missing),
                    len(report.stale_by_hash),
                    len(report.extra),
                )
            else:
                logger.info("Reconcile %s: OK (expected=%d)", report.domain_name, report.expected)
        except Exception as exc:
            logger.error("Reconcile domain %s failed: %s", adapter.domain_name, exc)
            all_ok = False  # domain failure makes whole run not-ok

    return {
        "domains": len(reports),
        "total_missing": total_missing,
        "total_stale": total_stale,
        "total_extra": total_extra,
        "total_enqueued": total_enqueued,
        "all_ok": all_ok and total_missing == 0 and total_stale == 0 and total_extra == 0,
    }
