"""Immutable KOSHA asset addressing — WP-1C-3A / 5A.

source_asset_key (논리 identity) 와 content_checksum (binary SHA-256) 을 분리한다.
현재 DB assets.checksum 은 논리키이며 의미를 바꾸지 않는다.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


def source_asset_key(material_id: str, atcfl_no: Any, seq: Any, file_name: Any = "") -> str:
    """Same formula as assets.checksum (logical). Not a binary SHA."""
    raw = f"{material_id}|{atcfl_no}|{seq}|{file_name or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def content_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(name: str | None) -> str:
    raw = (name or "file").strip().replace("\\", "/")
    base = raw.split("/")[-1]
    if not base or base in (".", ".."):
        base = "file"
    if "." in base and not base.startswith("."):
        stem, ext = base.rsplit(".", 1)
        ext = re.sub(r"[^A-Za-z0-9]+", "", ext)[:16]
    else:
        stem, ext = base, ""
    stem_s = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "file"
    stem_s = stem_s[:160]
    return f"{stem_s}.{ext}" if ext else stem_s


def object_key(material_id: str, asset_key: str, sha256_hex: str, filename: str | None) -> str:
    mid = re.sub(r"[^A-Za-z0-9_-]", "_", str(material_id))
    ak = re.sub(r"[^a-fA-F0-9]", "", asset_key).lower() or "unknown"
    hx = re.sub(r"[^a-fA-F0-9]", "", sha256_hex).lower()
    if len(hx) != 64:
        raise ValueError("content_checksum must be sha256 hex")
    return f"kosha/{mid}/{ak}/{hx}/{sanitize_filename(filename)}"


def version_action(existing_content_sha: str | None, new_content_sha: str) -> str:
    if existing_content_sha and existing_content_sha == new_content_sha:
        return "NO_CHANGE"
    return "NEW_VERSION"
