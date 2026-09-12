"""Read-only R2 GET presign — WP-2. PUT/DELETE/public URL 금지."""
from __future__ import annotations

from .r2_store import ALLOWED_BUCKET, assert_bucket

SIGNED_TTL_SECONDS = 600


def _safe_filename(name: str) -> str:
    raw = (name or "file").replace('"', "").replace("\\", "").replace("\n", "")
    return raw[:180] or "file"


class R2GetSigner:
    """generate_presigned_url(get_object) only. Never PUT/DELETE/GET body."""

    def __init__(self, client, *, ttl: int = SIGNED_TTL_SECONDS):
        self.client = client
        self.ttl = int(ttl)
        self.puts = 0
        self.deletes = 0
        self.presigns = 0

    def sign(self, bucket: str, key: str, *, mime: str | None = None, filename: str | None = None) -> str:
        assert_bucket(bucket)
        if bucket != ALLOWED_BUCKET:
            raise ValueError("UNEXPECTED_BUCKET")
        if not (key or "").strip():
            raise ValueError("STORAGE_KEY_REQUIRED")
        params = {"Bucket": bucket, "Key": key}
        if mime:
            params["ResponseContentType"] = mime
        if filename:
            params["ResponseContentDisposition"] = f'inline; filename="{_safe_filename(filename)}"'
        self.presigns += 1
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=self.ttl,
        )
