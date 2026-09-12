"""KOSHA portal detail/attachment metadata client — WP-1C-4B.

metadata POST only. binary download 경로 금지.
429/401/403: retry 0, StopRun.
5xx/timeout: 최대 2회 재시도 (1s, 3s) 후 TRANSIENT_UPSTREAM_FAILURE.
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .hosts import DEFAULT_UA, DETAIL_HOST, is_allowed_host

DETAIL_BASE = f"https://{DETAIL_HOST}/api/portal24/bizV/p/VCPDG01007"
TIMEOUT = 20
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_PATHS = frozenset({"selectMediaList", "selectAtchList"})
FORBIDDEN_FRAGMENTS = (
    "downloadAtchFile",
    "files/download",
    "getFileList",
    "mediaStream",
    "getVideoStreamUrl",
    "viewThumbnail",
)
TRANSIENT_BACKOFF = (1.0, 3.0)


class StopRun(Exception):
    def __init__(self, reason: str, http_status: int | None = None, endpoint: str | None = None,
                 evidence: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status
        self.endpoint = endpoint
        self.evidence = dict(evidence or {})


class MaterialFetchError(Exception):
    def __init__(self, code: str, status: int | None = None, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.status = status


def _ctx():
    return ssl.create_default_context()


def classify_http_status(status: int) -> str | None:
    """Return StopRun reason, material failure code, or None if caller continues."""
    if status == 429:
        return "QUOTA_BLOCKED"
    if status in (401, 403):
        return "ACCESS_BLOCKED"
    if status == 404:
        return "DETAIL_HTTP_404"
    if status >= 500:
        return "TRANSIENT_UPSTREAM"
    return None


def post_json(path: str, body: dict[str, Any], *, timeout: int = TIMEOUT, sleeper=time.sleep) -> dict[str, Any]:
    if path not in ALLOWED_PATHS or any(x in path for x in FORBIDDEN_FRAGMENTS):
        raise MaterialFetchError("FORBIDDEN_PATH", message=path)
    url = f"{DETAIL_BASE}/{path}"
    if not is_allowed_host(url):
        raise MaterialFetchError("HOST_NOT_ALLOWED", message=urlparse(url).hostname or "")
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    attempts = 0
    last_exc: Exception | None = None
    while attempts < 3:
        attempts += 1
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": f"https://{DETAIL_HOST}",
                "chnlId": "portal24",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
                raw = resp.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise MaterialFetchError("PARSER_FAILED", status=resp.status)
                final = resp.geturl()
                if not is_allowed_host(final):
                    raise MaterialFetchError("HOST_NOT_ALLOWED", message=urlparse(final).hostname or "")
                try:
                    data = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    raise MaterialFetchError("PARSER_FAILED", status=resp.status)
                return {
                    "ok": 200 <= resp.status < 300,
                    "status": resp.status,
                    "json": data,
                    "final_url": final,
                    "endpoint": path,
                }
        except MaterialFetchError:
            raise
        except urllib.error.HTTPError as e:
            kind = classify_http_status(e.code)
            if kind in ("QUOTA_BLOCKED", "ACCESS_BLOCKED"):
                raise StopRun(kind, http_status=e.code, endpoint=path) from e
            if kind == "DETAIL_HTTP_404":
                code = "ATTACHMENT_PARSE_ERROR" if path == "selectAtchList" else "DETAIL_HTTP_404"
                raise MaterialFetchError(code, status=404) from e
            if kind == "TRANSIENT_UPSTREAM":
                last_exc = e
                if attempts <= 2:
                    sleeper(TRANSIENT_BACKOFF[attempts - 1])
                    continue
                raise StopRun("TRANSIENT_UPSTREAM_FAILURE", http_status=e.code, endpoint=path) from e
            raise MaterialFetchError("DETAIL_HTTP_ERROR", status=e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempts <= 2:
                sleeper(TRANSIENT_BACKOFF[attempts - 1])
                continue
            raise StopRun("TRANSIENT_UPSTREAM_FAILURE", http_status=None, endpoint=path) from e
    raise StopRun("TRANSIENT_UPSTREAM_FAILURE", endpoint=path) from last_exc


def fetch_detail(med_seq: int | str, *, post=post_json) -> dict[str, Any]:
    return post("selectMediaList", {"medSeq": int(med_seq)})


def fetch_attachments(med_seq: int | str, *, post=post_json) -> dict[str, Any]:
    return post("selectAtchList", {"medSeq": int(med_seq)})
