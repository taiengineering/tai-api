"""Validate canonical detail+assets before WRITE — WP-1C-2."""
from __future__ import annotations

from .hosts import is_allowed_host
from .license_policy import KOGL_VALID, RENDER_VALID

CONTENT_VALID = ("PDF", "IMAGE", "VIDEO", "HTML", "EBOOK", "OTHER")
STATUS_VALID = ("PENDING", "OK", "PARTIAL", "FAILED")
ASSET_TYPE_VALID = ("PDF", "IMAGE", "VIDEO", "HTML", "EBOOK", "ATTACHMENT", "OTHER")


def valid_medseq(seq) -> bool:
    """non-empty, digits only, positive integer. leading zeros allowed if int(seq)>0."""
    s = str(seq or "").strip()
    if not s or not s.isdigit():
        return False
    return int(s) > 0


def validate(detail: dict, assets: list[dict], *, catalog_exists: bool, requested_med_seq: str) -> list[str]:
    errs: list[str] = []
    if not catalog_exists or not detail.get("material_id"):
        errs.append("material_id missing from catalog")
        return errs
    if not is_allowed_host(detail.get("source_url")):
        errs.append("source_url host not allowed")
    title = (detail.get("source_title") or "").strip()
    if not title:
        errs.append("source_title empty")
    seq = str(detail.get("source_med_seq") or "").strip()
    req = str(requested_med_seq or "").strip()
    if not valid_medseq(seq):
        errs.append("source_med_seq invalid")
    if not valid_medseq(req):
        errs.append("requested_med_seq invalid")
    if seq != req:
        errs.append("source_med_seq mismatch")
    if detail.get("kogl_type") not in KOGL_VALID:
        errs.append("kogl_type invalid")
    if detail.get("render_policy") not in RENDER_VALID:
        errs.append("render_policy invalid")
    if detail.get("content_type") not in CONTENT_VALID:
        errs.append("content_type invalid")
    if detail.get("enrichment_status") not in STATUS_VALID:
        errs.append("enrichment_status invalid")
    if detail.get("kogl_type") == "UNKNOWN" and detail.get("render_policy") != "LINK_ONLY":
        errs.append("UNKNOWN must be LINK_ONLY")
    if detail.get("content_type") == "VIDEO":
        if detail.get("license_storage_allowed") is not False:
            errs.append("VIDEO storage_allowed must be false")
        for a in assets:
            if a.get("storage_allowed") is not False:
                errs.append("VIDEO asset storage_allowed must be false")
                break
            if a.get("local_storage_url"):
                errs.append("VIDEO local_storage_url must be null")
                break
    if detail.get("render_policy") == "OFFICIAL_EMBED" and not detail.get("official_embed_confirmed"):
        errs.append("OFFICIAL_EMBED without confirmation")
    for a in assets:
        if a.get("asset_type") not in ASSET_TYPE_VALID:
            errs.append("asset_type invalid")
            break
        if a.get("material_id") != detail.get("material_id"):
            errs.append("asset material_id mismatch")
            break
    return errs
