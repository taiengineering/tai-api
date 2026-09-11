"""Private R2 (S3-compatible) client — WP-1C-5A.

CLI object-store helpers 금지. public URL / r2.dev 금지. DELETE 금지.
ETag 는 content SHA 가 아니다.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from typing import Any, Optional

ALLOWED_BUCKET = "tai-kosha-originals"
FORBIDDEN_BUCKETS = frozenset({"45cm-backup"})
PRIVATE_ENDPOINT_SUFFIX = ".r2.cloudflarestorage.com"
META_SHA = "tai-content-sha256"
META_SOURCE_KEY = "tai-source-asset-key"
META_MATERIAL_ID = "tai-material-id"


class R2Error(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def assert_bucket(bucket: str) -> None:
    if bucket in FORBIDDEN_BUCKETS:
        raise R2Error("FORBIDDEN_BUCKET", bucket)
    if bucket != ALLOWED_BUCKET:
        raise R2Error("UNEXPECTED_BUCKET", bucket)


def credentials_from_env(env: Optional[dict] = None) -> dict:
    src = env if env is not None else os.environ
    names = (
        "CLOUDFLARE_R2_ACCOUNT_ID",
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_BUCKET",
    )
    missing = [n for n in names if not (src.get(n) or "").strip()]
    if missing:
        raise R2Error("R2_INTEGRATION_BLOCKED", ",".join(missing))
    bucket = src["CLOUDFLARE_R2_BUCKET"].strip()
    assert_bucket(bucket)
    account = src["CLOUDFLARE_R2_ACCOUNT_ID"].strip()
    endpoint = f"https://{account}{PRIVATE_ENDPOINT_SUFFIX}"
    if "r2.dev" in endpoint or "pages.dev" in endpoint:
        raise R2Error("PUBLIC_ENDPOINT_FORBIDDEN", endpoint)
    return {
        "account_id": account,
        "access_key_id": src["CLOUDFLARE_R2_ACCESS_KEY_ID"].strip(),
        "secret_access_key": src["CLOUDFLARE_R2_SECRET_ACCESS_KEY"].strip(),
        "bucket": bucket,
        "endpoint": endpoint,
    }


def make_s3_client(creds: dict, *, boto3_mod=None):
    boto3_mod = boto3_mod or __import__("boto3")
    from botocore.config import Config
    return boto3_mod.client(
        "s3",
        endpoint_url=creds["endpoint"],
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _code_of(exc: Exception) -> str:
    resp = getattr(exc, "response", None) or {}
    err = resp.get("Error") or {}
    return str(err.get("Code") or getattr(exc, "code", "") or "")


def _http_status(exc: Exception) -> int | None:
    resp = getattr(exc, "response", None) or {}
    meta = resp.get("ResponseMetadata") or {}
    st = meta.get("HTTPStatusCode")
    try:
        return int(st) if st is not None else None
    except (TypeError, ValueError):
        return None


def classify_client_error(exc: Exception) -> str:
    code = _code_of(exc)
    st = _http_status(exc)
    if code in ("404", "NoSuchKey", "NotFound", "404 Not Found") or st == 404:
        return "MISSING"
    if code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch") or st in (401, 403):
        return "AUTH"
    if (st is not None and st >= 500) or code in ("500", "503", "SlowDown", "InternalError"):
        return "TRANSIENT"
    return "HEAD_ERROR"


class R2Store:
    def __init__(self, client, bucket: str = ALLOWED_BUCKET):
        assert_bucket(bucket)
        self.client = client
        self.bucket = bucket
        self.puts = 0
        self.heads = 0
        self.gets = 0
        self.deletes = 0

    def head(self, key: str) -> dict:
        self.heads += 1
        try:
            r = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            kind = classify_client_error(e)
            if kind == "MISSING":
                return {"exists": False, "key": key}
            if kind == "AUTH":
                raise R2Error("R2_HEAD_AUTH", kind) from e
            if kind == "TRANSIENT":
                raise R2Error("R2_HEAD_TRANSIENT", kind) from e
            raise R2Error("R2_HEAD_ERROR", kind) from e
        meta = {str(k).lower(): str(v) for k, v in (r.get("Metadata") or {}).items()}
        etag = r.get("ETag")
        return {
            "exists": True,
            "key": key,
            "content_length": r.get("ContentLength"),
            "content_type": r.get("ContentType"),
            "metadata": meta,
            "etag": etag,
            "sha256_metadata": meta.get(META_SHA) or meta.get("tai-content-sha256"),
        }

    def get_bytes(self, key: str, max_bytes: int = 20 * 1024 * 1024) -> bytes:
        """Private R2 read-back only. Not a KOSHA source GET."""
        self.gets += 1
        r = self.client.get_object(Bucket=self.bucket, Key=key)
        body = r["Body"]
        data = body.read(max_bytes + 1) if hasattr(body, "read") else body
        if len(data) > max_bytes:
            raise R2Error("RESPONSE_TOO_LARGE")
        return data

    def verify_existing(self, key: str, expected_sha: str) -> str:
        """HEAD then optional legacy GET. PUT/DELETE 없음. ETag ≠ SHA."""
        h = self.head(key)
        if not h["exists"]:
            raise R2Error("VERSION_OBJECT_MISSING", key)
        meta_sha = h.get("sha256_metadata")
        etag = (h.get("etag") or "").strip('"')
        if meta_sha:
            if meta_sha == expected_sha:
                if etag and etag == expected_sha:
                    pass  # coincidence only; SHA SoT is metadata
                return "OBJECT_EXISTS_VERIFIED"
            raise R2Error("R2_OBJECT_CONFLICT", key)
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(prefix="kosha_r2_legacy_")
            os.close(fd)
            data = self.get_bytes(key)
            with open(tmp, "wb") as f:
                f.write(data)
            calc = hashlib.sha256(data).hexdigest()
            if calc != expected_sha:
                raise R2Error("R2_OBJECT_CONFLICT", key)
            return "LEGACY_OBJECT"
        finally:
            if tmp and os.path.isfile(tmp):
                os.remove(tmp)

    def put_new(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        source_asset_key: str,
        material_id: str,
        content_sha256: str,
    ) -> str:
        h = self.head(key)
        if h["exists"]:
            status = self.verify_existing(key, content_sha256)
            if status in ("OBJECT_EXISTS_VERIFIED", "LEGACY_OBJECT"):
                return "OBJECT_EXISTS_VERIFIED"
            raise R2Error("R2_OBJECT_CONFLICT", key)
        meta = {
            META_SHA: content_sha256,
            META_SOURCE_KEY: source_asset_key,
            META_MATERIAL_ID: material_id,
        }
        self.puts += 1
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
            Metadata=meta,
        )
        return "PUT"

    def readback_verify(self, key: str, expected_sha: str) -> None:
        data = self.get_bytes(key)
        calc = hashlib.sha256(data).hexdigest()
        if calc != expected_sha:
            raise R2Error("READBACK_MISMATCH", key)

    def delete(self, key: str) -> None:
        raise R2Error("R2_DELETE_FORBIDDEN", key)
