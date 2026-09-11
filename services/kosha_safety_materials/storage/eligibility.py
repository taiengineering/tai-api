"""Current Type1/3 non-video storage eligibility — WP-1C-5B.

Does not use assets.storage_allowed. Historical snapshot members excluded.
"""
from __future__ import annotations

from typing import Iterable

ALLOWED_KOGL = frozenset({"1", "3"})


def is_eligible_detail(detail: dict, membership_ids: set[str]) -> bool:
    if not detail or detail.get("material_id") not in membership_ids:
        return False
    if detail.get("enrichment_status") != "OK":
        return False
    if detail.get("kogl_type") not in ALLOWED_KOGL:
        return False
    if (detail.get("content_type") or "").upper() == "VIDEO":
        return False
    return True


def is_eligible_asset(asset: dict, detail: dict, membership_ids: set[str]) -> bool:
    if not is_eligible_detail(detail, membership_ids):
        return False
    if asset.get("material_id") != detail.get("material_id"):
        return False
    if (asset.get("asset_type") or "").upper() == "VIDEO":
        return False
    if not asset.get("checksum"):
        return False
    return True


def live_kogl_ok(db_kogl: str, live_kogl: str) -> str | None:
    """Return None if ok, else LICENSE_CHANGED_REVIEW_REQUIRED."""
    db, live = str(db_kogl), str(live_kogl)
    if db == "1" and live == "1":
        return None
    if db == "3" and live == "3":
        return None
    return "LICENSE_CHANGED_REVIEW_REQUIRED"


def sort_pending_key(item: dict) -> tuple:
    kogl = str(item.get("kogl_type") or "9")
    atype = str(item.get("asset_type") or "")
    pdf = 0 if atype == "PDF" else 1
    size = item.get("file_size")
    size_i = int(size) if isinstance(size, int) or (isinstance(size, str) and str(size).isdigit()) else 10**18
    return (0 if kogl == "1" else 1, pdf, size_i, str(item.get("material_id") or ""), int(item.get("asset_id") or 0))


def pending_without_version(eligible: list[dict], versioned_keys: set[str]) -> list[dict]:
    out = [e for e in eligible if e.get("source_asset_key") not in versioned_keys]
    out.sort(key=sort_pending_key)
    return out
