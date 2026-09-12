"""Read-only R2 GET presign — WP-2 / WP-DL+A1. PUT/DELETE/public URL 금지."""
from __future__ import annotations

from urllib.parse import quote

from .r2_store import ALLOWED_BUCKET, assert_bucket

SIGNED_TTL_SECONDS = 600
ALLOWED_DISPOSITIONS = frozenset({"inline", "attachment"})


def _safe_filename(name: str) -> str:
    raw = (name or "file").replace('"', "").replace("\\", "").replace("\n", "").replace("\r", "")
    return raw[:180] or "file"


def _ascii_filename(name: str) -> str:
    safe = _safe_filename(name)
    out = []
    for ch in safe:
        o = ord(ch)
        out.append(ch if 32 <= o < 127 else "_")
    collapsed = "".join(out).strip("._") or "file"
    return collapsed[:180]


def content_disposition_header(disposition: str, filename: str | None) -> str:
    """Reuse _safe_filename. ASCII filename= plus RFC 5987 filename*."""
    raw = _safe_filename(filename or "file")
    ascii_name = _ascii_filename(raw)
    starred = quote(raw.encode("utf-8"), safe="")
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{starred}'


class R2GetSigner:
    """generate_presigned_url(get_object) only. Never PUT/DELETE/GET body."""

    def __init__(self, client, *, ttl: int = SIGNED_TTL_SECONDS):
        self.client = client
        self.ttl = int(ttl)
        self.puts = 0
        self.deletes = 0
        self.presigns = 0

    def sign(
        self,
        bucket: str,
        key: str,
        *,
        mime: str | None = None,
        filename: str | None = None,
        disposition: str = "inline",
    ) -> str:
        assert_bucket(bucket)
        if bucket != ALLOWED_BUCKET:
            raise ValueError("UNEXPECTED_BUCKET")
        if not (key or "").strip():
            raise ValueError("STORAGE_KEY_REQUIRED")
        disp = (disposition or "inline").strip().lower()
        if disp not in ALLOWED_DISPOSITIONS:
            raise ValueError("INVALID_CONTENT_DISPOSITION")
        params = {"Bucket": bucket, "Key": key}
        if mime:
            params["ResponseContentType"] = mime
        if filename or disp == "attachment":
            params["ResponseContentDisposition"] = content_disposition_header(disp, filename)
        self.presigns += 1
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=self.ttl,
        )
