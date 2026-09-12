"""Parse selectAtchList metadata → asset rows — WP-1C-2.

source_file_url 추측 생성 금지. PK는 DB IDENTITY → checksum에 논리키를 저장.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .normalizer import content_type_from_filename

MIME = {
    "PDF": "application/pdf",
    "IMAGE": "image/*",
    "VIDEO": "video/*",
    "HTML": "text/html",
    "EBOOK": "application/epub+zip",
}


def logical_checksum(material_id: str, atcfl_no: Any, seq: Any, file_name: Any = "") -> str:
    """Source may repeat contsAtcflNo+Seq across files (R6/pilot 30576). file_name disambiguates."""
    raw = f"{material_id}|{atcfl_no}|{seq}|{file_name or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _asset_type(filename: str | None) -> str:
    ct = content_type_from_filename(filename)
    if ct:
        return ct
    return "ATTACHMENT"


def parse_attachments(
    raw: dict[str, Any] | None,
    *,
    material_id: str,
    source_url: str,
    video_storage_false: bool,
    http_status: int | None = 200,
) -> dict:
    if http_status is not None and http_status != 200:
        return {"ok": False, "failure_reason": "ATTACHMENT_PARSE_ERROR", "assets": []}
    if not isinstance(raw, dict):
        return {"ok": True, "failure_reason": None, "assets": []}
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    lst = payload.get("list") if isinstance(payload, dict) else []
    if not isinstance(lst, list):
        return {"ok": False, "failure_reason": "ATTACHMENT_PARSE_ERROR", "assets": []}
    assets = []
    for i, item in enumerate(lst):
        if not isinstance(item, dict):
            continue
        name = item.get("orgnlAtchFileNm")
        atype = _asset_type(name if isinstance(name, str) else None)
        seq = item.get("contsAtcflSeq") if item.get("contsAtcflSeq") is not None else i
        no = item.get("contsAtcflNo") or ""
        size = item.get("atcflSz")
        try:
            size_i = int(size) if size is not None else None
        except (TypeError, ValueError):
            size_i = None
        storage = False
        if atype == "VIDEO" or video_storage_false:
            storage = False
        assets.append({
            "material_id": material_id,
            "asset_type": atype,
            "file_name": name,
            "source_file_url": None,
            "external_url": source_url,
            "embed_url": None,
            "mime_type": MIME.get(atype),
            "file_size": size_i,
            "local_storage_url": None,
            "checksum": logical_checksum(material_id, no, seq, name),
            "display_order": i,
            "storage_allowed": storage,
            "is_original": True,
            "contsAtcflNo": no,
            "contsAtcflSeq": seq,
        })
    return {"ok": True, "failure_reason": None, "assets": assets}
