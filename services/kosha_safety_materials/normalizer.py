"""Normalize KOSHA parsed fields → DB canonical detail row — WP-1C-2."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from . import license_policy
from .hosts import is_allowed_host, join_kosha_url

KST = ZoneInfo("Asia/Seoul")

# R6 실측 제작형태명 + R5A ctgr01 코드 (명시적만)
SHP_NAME_TO_CONTENT = {
    "동영상": "VIDEO",
    "책자": "PDF",
    "리플릿": "IMAGE",
    "리플렛": "IMAGE",
    "스티커": "IMAGE",
    "포스터": "IMAGE",
    "OPS": "PDF",
    "교안(PPT)": "OTHER",
    "교안": "OTHER",
    "VR": "OTHER",
    "AR": "OTHER",
}
SHP_CODE_TO_CONTENT = {
    "1": "PDF",      # 책자
    "2": "VIDEO",    # 동영상
    "6": "IMAGE",    # 리플릿
    "7": "OTHER",    # 교안
    "9": "IMAGE",    # 포스터
    "12": "PDF",     # OPS
    "13": "IMAGE",   # 스티커
    "18": "OTHER",   # VR
    "19": "OTHER",   # AR
}

EXT_MAP = {
    ".pdf": "PDF",
    ".jpg": "IMAGE", ".jpeg": "IMAGE", ".png": "IMAGE", ".gif": "IMAGE", ".webp": "IMAGE",
    ".mp4": "VIDEO", ".webm": "VIDEO", ".avi": "VIDEO",
    ".epub": "EBOOK",
    ".html": "HTML", ".htm": "HTML",
}

HASH_DETAIL_KEYS = (
    "material_id", "source_provider", "source_med_seq", "source_url",
    "source_title", "source_description", "source_published_at", "source_updated_at",
    "kogl_type", "license_name", "license_source_url",
    "commercial_allowed", "modification_allowed", "render_policy",
    "content_type", "thumbnail_url", "enrichment_status", "failure_reason",
)
HASH_ASSET_KEYS = (
    "checksum", "asset_type", "file_name", "mime_type", "file_size",
    "display_order", "storage_allowed", "is_original",
    "source_file_url", "external_url", "embed_url",
)


def parse_published(conts_reg_ymd: Any, frst_reg_dt: Any) -> str | None:
    """Return ISO timestamptz string or None. 추정 금지 — 파싱 가능한 값만."""
    if conts_reg_ymd:
        s = str(conts_reg_ymd).strip()
        if len(s) == 8 and s.isdigit():
            dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=KST)
            return dt.isoformat()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            y, m, d = (int(x) for x in s.split("-"))
            return datetime(y, m, d, tzinfo=KST).isoformat()
    if frst_reg_dt:
        s = str(frst_reg_dt).strip()
        try:
            if s.endswith("Z"):
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt.isoformat()
        except ValueError:
            return None
    return None


def content_type_from_filename(name: str | None) -> str | None:
    if not name or "." not in name:
        return None
    ext = "." + name.rsplit(".", 1)[-1].lower()
    return EXT_MAP.get(ext)


def content_type_from_shp(cd: Any, nm: Any) -> str | None:
    if nm is not None:
        mapped = SHP_NAME_TO_CONTENT.get(str(nm).strip())
        if mapped:
            return mapped
    if cd is not None:
        mapped = SHP_CODE_TO_CONTENT.get(str(cd).strip())
        if mapped:
            return mapped
    return None


def resolve_content_type(fields: dict, assets: list[dict]) -> str:
    for a in assets:
        ct = content_type_from_filename(a.get("file_name"))
        if ct:
            return ct
    shp = content_type_from_shp(fields.get("contsFbctnShpCd"), fields.get("contsFbctnShpNm"))
    if shp:
        return shp
    return "OTHER"


def thumbnail_url(fields: dict) -> str | None:
    for key in ("medThumbnailPath", "thumbPath"):
        u = join_kosha_url(fields.get(key) if isinstance(fields.get(key), str) else None)
        if u:
            return u
    return None


def canonical_hash(detail: dict, assets: list[dict]) -> str:
    payload = {k: detail.get(k) for k in HASH_DETAIL_KEYS}
    ast = []
    for a in assets:
        ast.append({k: a.get(k) for k in HASH_ASSET_KEYS})
    ast.sort(key=lambda x: (x.get("checksum") or "", x.get("display_order") or 0, x.get("file_name") or ""))
    payload["assets"] = ast
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def normalize_detail(
    *,
    material_id: str,
    catalog_url: str,
    catalog_title: str | None,
    fields: dict,
    assets: list[dict],
    official_embed_confirmed: bool = False,
    enrichment_status: str = "OK",
    failure_reason: str | None = None,
) -> dict:
    title = (fields.get("medName") or catalog_title or "").strip()
    desc = fields.get("medNote")
    if isinstance(desc, str):
        desc = desc.strip() or None
    else:
        desc = None
    kogl_raw = fields.get("medGonggongnuri")
    kogl = license_policy.normalize_kogl_type(None if kogl_raw is None else str(kogl_raw))
    kogl_nm = fields.get("medGonggongnuriNm")
    if kogl in ("1", "2", "3", "4"):
        license_name = str(kogl_nm).strip() if kogl_nm else None
        license_source_url = catalog_url if is_allowed_host(catalog_url) else None
    else:
        license_name = None
        license_source_url = None
    ct = resolve_content_type(fields, assets)
    decision = license_policy.decide(kogl, ct, official_embed_confirmed=official_embed_confirmed)
    pub = parse_published(fields.get("contsRegYmd"), fields.get("frstRegDt"))
    row = {
        "material_id": material_id,
        "source_provider": "KOSHA",
        "source_med_seq": str(fields.get("medSeq") or ""),
        "source_url": catalog_url,
        "source_title": title,
        "source_description": desc,
        "source_published_at": pub,
        "source_updated_at": None,
        "kogl_type": decision.kogl_type,
        "license_name": license_name,
        "license_source_url": license_source_url,
        "commercial_allowed": decision.commercial_allowed,
        "modification_allowed": decision.modification_allowed,
        "render_policy": decision.render_policy,
        "content_type": ct,
        "thumbnail_url": thumbnail_url(fields),
        "enrichment_status": enrichment_status,
        "failure_reason": failure_reason,
        "official_embed_confirmed": bool(official_embed_confirmed),
        "license_storage_allowed": decision.storage_allowed,
    }
    row["source_content_hash"] = canonical_hash(row, assets)
    return row
