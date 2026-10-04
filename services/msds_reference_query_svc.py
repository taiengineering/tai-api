"""MSDS Reference candidate query service.

Queries msds_ref_identity_projection_v for reference enrichment.
Owner: LEG / Reference Domain.
Caller: POST /internal/reference/msds/candidates

Match semantics (deterministic, no fuzzy/LLM):
  rank 1 = EXACT_CAS
  rank 2 = EXACT_REFERENCE_PRODUCT_NAME
  rank 3 = EXACT_SUBSTANCE_NAME
  rank 4 = EXACT_ALIAS

Deduplication: content_id.
Write operations: 0 (read-only).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_VIEW = "msds_ref_identity_projection_v"
_SNAPSHOTS_TABLE = "snapshots"
_SNAPSHOTS_SCHEMA = "msds_ref"


class ReferenceQueryError(Exception):
    pass


class SnapshotNotReadyError(ReferenceQueryError):
    pass


def _get_client():
    url = os.environ.get("LEG_SUPABASE_URL", "").strip()
    key = os.environ.get("LEG_SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise ReferenceQueryError(
            "REFERENCE_NOT_CONFIGURED: LEG_SUPABASE_URL and LEG_SUPABASE_SERVICE_ROLE_KEY must be set"
        )
    from supabase import create_client
    return create_client(url, key)


def validate_snapshot(snapshot_id: str) -> None:
    """Raise SnapshotNotReadyError if snapshot is absent or not COMPLETED."""
    sb = _get_client()
    res = (
        sb.schema(_SNAPSHOTS_SCHEMA)
        .table(_SNAPSHOTS_TABLE)
        .select("id,status")
        .eq("id", snapshot_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise SnapshotNotReadyError(f"REFERENCE_SNAPSHOT_NOT_READY: {snapshot_id} not found")
    if rows[0].get("status") != "COMPLETED":
        raise SnapshotNotReadyError(
            f"REFERENCE_SNAPSHOT_NOT_READY: {snapshot_id} status={rows[0].get('status')}"
        )


def find_candidates(
    snapshot_id: str,
    cas_list: List[str],
    product_name_normalized: Optional[str],
) -> List[Dict[str, Any]]:
    """Query reference view for enrichment candidates.

    Returns list of:
      reference_content_id, reference_chem_id, reference_snapshot_id,
      match_reason, rank_no, evidence_json
    """
    sb = _get_client()
    candidates: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(row: Dict, reason: str, rank: int, evidence: Dict) -> None:
        cid = row["content_id"]
        if cid not in seen:
            seen.add(cid)
            candidates.append({
                "reference_content_id": cid,
                "reference_chem_id": row.get("chem_id"),
                "reference_snapshot_id": snapshot_id,
                "match_reason": reason,
                "rank_no": rank,
                "evidence_json": evidence,
            })

    # Rank 1: EXACT_CAS
    for cas in cas_list:
        res = (
            sb.table(_VIEW)
            .select("content_id,chem_id,cas_no")
            .eq("snapshot_id", snapshot_id)
            .eq("cas_no", cas.strip())
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_CAS", 1, {"cas": cas})

    # Rank 2: EXACT_REFERENCE_PRODUCT_NAME
    if product_name_normalized:
        res = (
            sb.table(_VIEW)
            .select("content_id,chem_id,product_name_normalized")
            .eq("snapshot_id", snapshot_id)
            .eq("product_name_normalized", product_name_normalized)
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_REFERENCE_PRODUCT_NAME", 2, {"product_name_normalized": product_name_normalized})

        # Rank 3: EXACT_SUBSTANCE_NAME
        res = (
            sb.table(_VIEW)
            .select("content_id,chem_id,substance_name_normalized")
            .eq("snapshot_id", snapshot_id)
            .eq("substance_name_normalized", product_name_normalized)
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_SUBSTANCE_NAME", 3, {"substance_name_normalized": product_name_normalized})

        # Rank 4: EXACT_ALIAS
        res = (
            sb.table(_VIEW)
            .select("content_id,chem_id,alias_normalized")
            .eq("snapshot_id", snapshot_id)
            .eq("alias_normalized", product_name_normalized)
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_ALIAS", 4, {"alias_normalized": product_name_normalized})

    return candidates
