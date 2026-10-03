"""leg-prod msds_ref.identity_projection read client — WO-MSDS-04A."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from supabase import create_client


def _get_leg_client():
    url = os.environ.get("LEG_SUPABASE_URL", "")
    key = os.environ.get("LEG_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("LEG_SUPABASE_URL and LEG_SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def find_reference_candidates(
    snapshot_id: str,
    cas_list: List[str],
    product_name_normalized: Optional[str],
    substance_name_normalized: Optional[str],
    alias_normalized: Optional[str],
) -> List[Dict[str, Any]]:
    """Query identity_projection for matching reference candidates.

    Returns list of dicts with: content_id, chem_id, match_reason, rank_no, evidence_json.
    No numeric confidence. Deterministic only.
    """
    sb = _get_leg_client()
    candidates: List[Dict[str, Any]] = []
    seen_content_ids: set = set()

    def _add(row: Dict, reason: str, rank: int, evidence: Dict):
        cid = row["content_id"]
        if cid not in seen_content_ids:
            seen_content_ids.add(cid)
            candidates.append({
                "reference_content_id": cid,
                "reference_chem_id": row["chem_id"],
                "reference_snapshot_id": snapshot_id,
                "cas_no": row.get("cas_no"),
                "match_reason": reason,
                "rank_no": rank,
                "evidence_json": evidence,
            })

    # Rank 1: EXACT_CAS
    for cas in cas_list:
        res = (
            sb.table("identity_projection")
            .select("content_id,chem_id,cas_no,product_name")
            .eq("snapshot_id", snapshot_id)
            .eq("cas_no", cas.strip())
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_CAS", 1, {"cas": cas})

    # Rank 2: EXACT_REFERENCE_PRODUCT_NAME
    if product_name_normalized:
        res = (
            sb.table("identity_projection")
            .select("content_id,chem_id,cas_no,product_name_normalized")
            .eq("snapshot_id", snapshot_id)
            .eq("product_name_normalized", product_name_normalized)
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_REFERENCE_PRODUCT_NAME", 2, {"product_name_normalized": product_name_normalized})

    # Rank 3: EXACT_SUBSTANCE_NAME
    if substance_name_normalized:
        res = (
            sb.table("identity_projection")
            .select("content_id,chem_id,cas_no,substance_name_normalized")
            .eq("snapshot_id", snapshot_id)
            .eq("substance_name_normalized", substance_name_normalized)
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_SUBSTANCE_NAME", 3, {"substance_name_normalized": substance_name_normalized})

    # Rank 4: EXACT_ALIAS
    if alias_normalized:
        res = (
            sb.table("identity_projection")
            .select("content_id,chem_id,cas_no,alias_normalized")
            .eq("snapshot_id", snapshot_id)
            .eq("alias_normalized", alias_normalized)
            .execute()
        )
        for row in (res.data or []):
            _add(row, "EXACT_ALIAS", 4, {"alias_normalized": alias_normalized})

    return candidates


def verify_reference_exists(snapshot_id: str, content_id: str) -> bool:
    """Fail-closed check that a reference_content_id exists in the snapshot."""
    try:
        sb = _get_leg_client()
        res = (
            sb.table("identity_projection")
            .select("content_id")
            .eq("snapshot_id", snapshot_id)
            .eq("content_id", content_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False  # fail-closed for existence check
