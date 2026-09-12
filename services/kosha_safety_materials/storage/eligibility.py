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


def _file_size_int(item: dict) -> int | None:
    size = item.get("file_size")
    if isinstance(size, bool):
        return None
    if isinstance(size, int):
        return size
    if isinstance(size, str) and size.isdigit():
        return int(size)
    return None


def sort_pending_key(item: dict) -> tuple:
    """Type1 → PDF → positive known size (small first) → size 0/NULL last.

    Does not drop size 0/NULL from eligibility; those remain pending, just later.
    """
    kogl = str(item.get("kogl_type") or "9")
    atype = str(item.get("asset_type") or "")
    pdf = 0 if atype == "PDF" else 1
    size_i = _file_size_int(item)
    unknown = 0 if (size_i is not None and size_i > 0) else 1
    size_rank = size_i if (size_i is not None and size_i > 0) else 0
    return (
        0 if kogl == "1" else 1,
        pdf,
        unknown,
        size_rank,
        str(item.get("material_id") or ""),
        int(item.get("asset_id") or 0),
    )


class EligibilityError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def require_asset_id(item: dict):
    aid = item.get("asset_id")
    if aid is None or aid == "" or aid == "pending":
        raise EligibilityError("ASSET_ID_REQUIRED")
    return aid


def pending_without_version(
    eligible: list[dict],
    versioned_asset_ids: set,
    held_asset_ids: set | None = None,
) -> list[dict]:
    """Actionable pending = eligible minus current versions minus OPEN holds.

    Holds are not storage completion. checksum is not the checkpoint.
    """
    out = []
    versioned = set(versioned_asset_ids)
    held = set(held_asset_ids or ())
    for e in eligible:
        aid = require_asset_id(e)
        if aid in versioned or aid in held:
            continue
        out.append(e)
    out.sort(key=sort_pending_key)
    return out
