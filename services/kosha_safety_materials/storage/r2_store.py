"""Private R2 (S3-compatible) client — WP-1C-5A / PATCH-5B-R2-READBACK.

CLI object-store helpers 금지. public URL / r2.dev 금지. DELETE 금지.
ETag 는 content SHA 가 아니다.
GET Body.read(amt) 는 at most amt — EOF까지 chunk loop 로만 완전 소비한다.
"""
from __future__ import annotations

import hashlib
import http.client
import os
import socket
import ssl
import time
from typing import Any, Optional

from .limits import MAX_BINARY_BYTES

ALLOWED_BUCKET = "tai-kosha-originals"
FORBIDDEN_BUCKETS = frozenset({"45cm-backup"})
PRIVATE_ENDPOINT_SUFFIX = ".r2.cloudflarestorage.com"
META_SHA = "tai-content-sha256"
META_SOURCE_KEY = "tai-source-asset-key"
META_MATERIAL_ID = "tai-material-id"
MAX_BYTES = MAX_BINARY_BYTES
READ_CHUNK = 64 * 1024
GET_ATTEMPTS = 3
GET_TRANSIENT_BACKOFF = (1.0, 3.0)
_TRANSIENT_NET = (
    ConnectionResetError,
    TimeoutError,
    BrokenPipeError,
    socket.timeout,
    ssl.SSLError,
    http.client.IncompleteRead,
)


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
    if isinstance(exc, _TRANSIENT_NET):
        return "TRANSIENT"
    code = _code_of(exc)
    st = _http_status(exc)
    if code in ("404", "NoSuchKey", "NotFound", "404 Not Found") or st == 404:
        return "MISSING"
    if code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch") or st in (401, 403):
        return "AUTH"
    if (st is not None and st >= 500) or code in ("500", "503", "SlowDown", "InternalError"):
        return "TRANSIENT"
    return "HEAD_ERROR"


def is_get_transient(exc: Exception) -> bool:
    if isinstance(exc, R2Error) and exc.code in ("R2_READ_INCOMPLETE", "R2_TRANSIENT", "R2_HEAD_TRANSIENT"):
        return True
    return classify_client_error(exc) == "TRANSIENT"


def consume_streaming_body(
    body,
    *,
    declared_length: int | None = None,
    max_bytes: int = MAX_BYTES,
    chunk: int = READ_CHUNK,
    collect: bool = False,
) -> dict:
    """Read until EOF. body.read(n) is at most n bytes — loop until empty."""
    digest = hashlib.sha256()
    total = 0
    parts: list[bytes] = []
    raw = body
    if not hasattr(body, "read"):
        if not isinstance(body, (bytes, bytearray)):
            raise R2Error("R2_READ_INCOMPLETE", type(body).__name__)
        raw_b = bytes(body)
        total = len(raw_b)
        if total > max_bytes:
            raise R2Error("RESPONSE_TOO_LARGE")
        if declared_length is not None and int(declared_length) != total:
            raise R2Error("R2_READ_INCOMPLETE", f"declared={declared_length} actual={total}")
        digest.update(raw_b)
        return {
            "sha256": digest.hexdigest(),
            "byte_count": total,
            "declared_length": declared_length,
            "data": raw_b if collect else None,
        }
    try:
        while True:
            try:
                piece = raw.read(chunk)
            except _TRANSIENT_NET as e:
                raise R2Error("R2_READ_INCOMPLETE", type(e).__name__) from e
            if piece is None:
                break
            if not isinstance(piece, (bytes, bytearray)):
                raise R2Error("R2_READ_INCOMPLETE", type(piece).__name__)
            if len(piece) == 0:
                break
            total += len(piece)
            if total > max_bytes:
                raise R2Error("RESPONSE_TOO_LARGE")
            digest.update(piece)
            if collect:
                parts.append(bytes(piece))
    finally:
        closer = getattr(raw, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
    if declared_length is not None and int(declared_length) != total:
        raise R2Error("R2_READ_INCOMPLETE", f"declared={declared_length} actual={total}")
    return {
        "sha256": digest.hexdigest(),
        "byte_count": total,
        "declared_length": declared_length,
        "data": b"".join(parts) if collect else None,
    }


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

    def _get_once(self, key: str, *, max_bytes: int, collect: bool) -> dict:
        try:
            r = self.client.get_object(Bucket=self.bucket, Key=key)
        except R2Error:
            raise
        except Exception as e:
            kind = classify_client_error(e)
            if kind == "MISSING":
                raise R2Error("VERSION_OBJECT_MISSING", key) from e
            if kind == "AUTH":
                raise R2Error("R2_ACCESS_BLOCKED", kind) from e
            if kind == "TRANSIENT":
                raise R2Error("R2_TRANSIENT", kind) from e
            raise R2Error("R2_GET_ERROR", kind) from e
        declared = r.get("ContentLength")
        if declared is None:
            meta = r.get("ResponseMetadata") or {}
            headers = meta.get("HTTPHeaders") or {}
            declared = headers.get("content-length")
        if declared is not None:
            try:
                declared = int(declared)
            except (TypeError, ValueError):
                declared = None
        return consume_streaming_body(
            r.get("Body"),
            declared_length=declared,
            max_bytes=max_bytes,
            collect=collect,
        )

    def stream_get(
        self,
        key: str,
        *,
        max_bytes: int = MAX_BYTES,
        collect: bool = False,
        sleeper=time.sleep,
    ) -> dict:
        """Private R2 GET until EOF. Short/reset reads retry; complete SHA mismatch is not retried here."""
        last: R2Error | None = None
        for attempt in range(GET_ATTEMPTS):
            self.gets += 1
            try:
                return self._get_once(key, max_bytes=max_bytes, collect=collect)
            except R2Error as e:
                if e.code in ("READBACK_MISMATCH", "RESPONSE_TOO_LARGE", "R2_ACCESS_BLOCKED",
                              "VERSION_OBJECT_MISSING", "R2_OBJECT_CONFLICT"):
                    raise
                if e.code not in ("R2_READ_INCOMPLETE", "R2_TRANSIENT"):
                    raise
                last = e
            except Exception as e:
                if not is_get_transient(e):
                    raise R2Error("R2_GET_ERROR", type(e).__name__) from e
                last = R2Error("R2_TRANSIENT", type(e).__name__)
            if attempt >= GET_ATTEMPTS - 1:
                raise R2Error("R2_TRANSIENT", str(last) if last else "exhausted")
            sleeper(GET_TRANSIENT_BACKOFF[attempt])
        raise R2Error("R2_TRANSIENT")

    def get_bytes(self, key: str, max_bytes: int = MAX_BYTES, *, sleeper=time.sleep) -> bytes:
        """Private R2 read-back only. Not a KOSHA source GET. Streams to EOF."""
        got = self.stream_get(key, max_bytes=max_bytes, collect=True, sleeper=sleeper)
        return got["data"] or b""

    def verify_existing(self, key: str, expected_sha: str, *, sleeper=time.sleep) -> str:
        """HEAD then full-byte GET. PUT/DELETE 없음. ETag ≠ SHA. metadata SHA is not sufficient."""
        h = self.head(key)
        if not h["exists"]:
            raise R2Error("VERSION_OBJECT_MISSING", key)
        got = self.stream_get(key, collect=False, sleeper=sleeper)
        if got["sha256"] != expected_sha:
            raise R2Error("R2_OBJECT_CONFLICT", key)
        if h.get("sha256_metadata"):
            return "OBJECT_EXISTS_VERIFIED"
        return "LEGACY_OBJECT"

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
            return "OBJECT_EXISTS_VERIFIED"
        meta = {
            META_SHA: content_sha256,
            META_SOURCE_KEY: source_asset_key,
            META_MATERIAL_ID: material_id,
        }
        self.puts += 1
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
                Metadata=meta,
            )
        except Exception as e:
            self.puts -= 1
            kind = classify_client_error(e)
            if kind == "AUTH":
                raise R2Error("R2_ACCESS_BLOCKED", kind) from e
            if kind == "TRANSIENT":
                raise R2Error("R2_TRANSIENT", kind) from e
            raise R2Error("R2_PUT_ERROR", kind) from e
        return "PUT"

    def readback_verify(self, key: str, expected_sha: str, *, sleeper=time.sleep) -> dict:
        got = self.stream_get(key, collect=False, sleeper=sleeper)
        if got["sha256"] != expected_sha:
            raise R2Error("READBACK_MISMATCH", key)
        return got

    def delete(self, key: str) -> None:
        raise R2Error("R2_DELETE_FORBIDDEN", key)
