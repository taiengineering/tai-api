"""Gated Type1/3 attachment binary GET — WP-1C-5A (PATCH-4).

detail_client 에 download 함수를 넣지 않는다. live KOSHA GET 은 이번 WP에서 호출하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional
from urllib.parse import urlparse

from ..hosts import ALLOWED_HOSTS, DEFAULT_UA
from .. import license_policy

DOWNLOAD_URL = "https://portal.kosha.or.kr/api/portal24/bizA/p/files/downloadAtchFile"
FILE_LIST_URL = "https://portal.kosha.or.kr/api/portal24/bizA/p/files/getFileList"
TIMEOUT = 30
MAX_BYTES = 20 * 1024 * 1024
CHUNK = 64 * 1024
PDF_MAGIC = b"%PDF"
ALLOWED_HTTPS_HOSTS = frozenset(ALLOWED_HOSTS)
BLOCKED_CONTENT_TYPES = frozenset({
    "text/html",
    "application/json",
    "text/plain",
    "application/javascript",
    "text/xml",
    "application/xml",
    "application/xhtml+xml",
})


class BinaryFetchError(Exception):
    def __init__(self, code: str, message: str = "", status: int | None = None,
                 body_bytes_read: int = 0):
        super().__init__(message or code)
        self.code = code
        self.status = status
        self.body_bytes_read = body_bytes_read


def assert_binary_allowed(kogl_type: str | None, content_type: str | None) -> None:
    d = license_policy.decide(kogl_type, content_type, official_embed_confirmed=False)
    ct = (content_type or "").strip().upper()
    if ct == "VIDEO":
        raise BinaryFetchError("VIDEO_BINARY_FORBIDDEN")
    if not d.binary_storage_allowed:
        raise BinaryFetchError("LICENSE_STORAGE_FORBIDDEN", d.kogl_type)


def assert_https_allowed(url: str, *, redirect: bool = False) -> None:
    p = urlparse(url)
    if p.scheme != "https":
        raise BinaryFetchError("SCHEME_NOT_ALLOWED", p.scheme or "")
    host = (p.hostname or "").lower()
    if host not in ALLOWED_HTTPS_HOSTS:
        raise BinaryFetchError(
            "REDIRECT_HOST_BLOCKED" if redirect else "HOST_NOT_ALLOWED",
            host,
        )


def _content_type(headers) -> str:
    raw = headers.get("Content-Type") if headers else ""
    return (raw or "").split(";")[0].strip().lower()


def classify_non_binary(ctype: str, head: bytes) -> Optional[str]:
    base = (ctype or "").split(";")[0].strip().lower()
    if base == "text/html" or base == "application/xhtml+xml":
        return "HTML_NOT_BINARY"
    if base == "application/json":
        return "JSON_NOT_BINARY"
    if base == "text/plain":
        return "TEXT_NOT_BINARY"
    if base in BLOCKED_CONTENT_TYPES:
        return "HTML_NOT_BINARY"
    hl = (head or b"").lstrip().lower()
    if hl.startswith(b"<!doctype") or hl.startswith(b"<html") or hl.startswith(b"<head"):
        return "HTML_NOT_BINARY"
    if hl.startswith(b"{") or hl.startswith(b"["):
        return "JSON_NOT_BINARY"
    return None


def assert_pdf_payload(ctype: str, head: bytes) -> None:
    blocked = classify_non_binary(ctype, head)
    if blocked:
        raise BinaryFetchError(blocked)
    if not (head or b"").startswith(PDF_MAGIC):
        raise BinaryFetchError("PDF_MAGIC_MISMATCH")


class GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Inspect Location before the next request. Disallowed host body is never read."""

    def __init__(self, chain: Optional[list] = None):
        super().__init__()
        self.chain = chain if chain is not None else []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_https_allowed(newurl, redirect=True)
        self.chain.append({"from": req.full_url, "to": newurl, "status": code})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_guarded_opener(chain: Optional[list] = None, extra_handlers=()):
    rh = GuardedRedirectHandler(chain if chain is not None else [])
    handlers = [rh, *extra_handlers]
    if not extra_handlers:
        handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    return urllib.request.build_opener(*handlers), rh


def fetch_https_binary(
    url: str,
    dest_path: str,
    *,
    headers: Optional[dict] = None,
    opener=None,
    expect_pdf: bool = False,
    max_bytes: int = MAX_BYTES,
) -> dict:
    assert_https_allowed(url, redirect=False)
    chain: list = []
    rh = None
    if opener is None:
        opener, rh = build_guarded_opener(chain)
    else:
        for h in getattr(opener, "handlers", []):
            if isinstance(h, GuardedRedirectHandler):
                rh = h
                if h.chain is not None:
                    chain = h.chain
                break
    req = urllib.request.Request(
        url,
        method="GET",
        headers=headers or {"User-Agent": DEFAULT_UA, "Accept": "*/*"},
    )
    body_bytes_read = 0
    try:
        resp = opener.open(req, timeout=TIMEOUT)
    except BinaryFetchError:
        raise
    except urllib.error.HTTPError as e:
        raise BinaryFetchError("DOWNLOAD_HTTP_ERROR", f"http {e.code}", status=e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise BinaryFetchError("DOWNLOAD_HTTP_ERROR", type(e).__name__) from e

    try:
        final = getattr(resp, "geturl", lambda: url)()
        assert_https_allowed(final, redirect=True if final != url else False)
        cl_raw = resp.headers.get("Content-Length") if resp.headers else None
        if cl_raw not in (None, ""):
            try:
                cl_i = int(cl_raw)
            except (TypeError, ValueError):
                cl_i = None
            if cl_i is not None and cl_i > max_bytes:
                raise BinaryFetchError("RESPONSE_TOO_LARGE", status=getattr(resp, "status", None),
                                       body_bytes_read=0)
        ctype = _content_type(resp.headers)
        pre = classify_non_binary(ctype, b"")
        if pre:
            raise BinaryFetchError(pre, status=getattr(resp, "status", None), body_bytes_read=0)

        hasher = hashlib.sha256()
        parent = os.path.dirname(dest_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        first = b""
        with open(dest_path, "wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                body_bytes_read += len(chunk)
                if body_bytes_read > max_bytes:
                    raise BinaryFetchError("RESPONSE_TOO_LARGE", status=getattr(resp, "status", None),
                                           body_bytes_read=body_bytes_read)
                if not first:
                    first = chunk[:16]
                    if expect_pdf:
                        assert_pdf_payload(ctype, first)
                    else:
                        blocked = classify_non_binary(ctype, first)
                        if blocked:
                            raise BinaryFetchError(blocked, status=getattr(resp, "status", None),
                                                   body_bytes_read=body_bytes_read)
                hasher.update(chunk)
                out.write(chunk)

        if body_bytes_read <= 0:
            raise BinaryFetchError("EMPTY_BODY", status=getattr(resp, "status", None), body_bytes_read=0)
        if expect_pdf:
            assert_pdf_payload(ctype, first)

        status = getattr(resp, "status", None)
        if status is None:
            status = getattr(resp, "code", 200)
        if not (200 <= int(status) < 300):
            raise BinaryFetchError("DOWNLOAD_HTTP_ERROR", f"http {status}", status=status,
                                   body_bytes_read=body_bytes_read)
        used_chain = rh.chain if rh is not None else chain
        return {
            "ok": True,
            "status": int(status),
            "content_type": ctype,
            "content_disposition": resp.headers.get("Content-Disposition") if resp.headers else None,
            "declared_content_length": cl_raw,
            "content_length": body_bytes_read,
            "final_url": final,
            "redirect_chain": list(used_chain),
            "sha256": hasher.hexdigest(),
            "dest_path": dest_path,
            "body_bytes_read": body_bytes_read,
        }
    finally:
        try:
            resp.close()
        except Exception:
            pass


def fetch_file_list(atcfl_no: str) -> list[dict]:
    """POST getFileList metadata. Not a binary download. 5A live call = 0."""
    assert_https_allowed(FILE_LIST_URL, redirect=False)
    body = {
        "fileId": str(atcfl_no),
        "fileUploadType": "02",
        "atcflTaskColNm": "lastFile",
        "atcflSeTaskComCdNm": "Y",
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        FILE_LIST_URL,
        data=data,
        method="POST",
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "chnlId": "portal24",
        },
    )
    opener, _rh = build_guarded_opener()
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES)
            ctype = _content_type(resp.headers)
            if ctype and "json" not in ctype:
                raise BinaryFetchError("FILE_LIST_NOT_JSON", ctype, status=getattr(resp, "status", None))
            obj = json.loads(raw.decode("utf-8"))
    except BinaryFetchError:
        raise
    except urllib.error.HTTPError as e:
        raise BinaryFetchError("FILE_LIST_HTTP_ERROR", f"http {e.code}", status=e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise BinaryFetchError("FILE_LIST_HTTP_ERROR", type(e).__name__) from e
    payload = obj.get("payload") if isinstance(obj, dict) else None
    if not isinstance(payload, list):
        raise BinaryFetchError("FILE_LIST_PARSE_ERROR")
    return [x for x in payload if isinstance(x, dict)]


def pick_first_pdf(file_list: list[dict]) -> dict | None:
    pdfs = []
    for it in file_list:
        name = str(it.get("orgnlAtchFileNm") or "")
        ext = str(it.get("atcflExtnNm") or "").lower()
        if name.lower().endswith(".pdf") or ext == "pdf":
            pdfs.append(it)
    if not pdfs:
        return None

    def sort_key(it):
        try:
            seq_i = int(it.get("atcflSeq"))
        except (TypeError, ValueError):
            seq_i = 10**9
        return (seq_i, str(it.get("orgnlAtchFileNm") or ""))

    pdfs.sort(key=sort_key)
    return pdfs[0]


def fetch_attachment_binary(
    kogl_type: str,
    content_type: str,
    atcfl_no: str,
    atcfl_seq: Any,
    file_name: str | None = None,
    mime_type: str | None = None,
    dest_path: str | None = None,
    opener=None,
    expect_pdf: bool = False,
) -> dict:
    assert_binary_allowed(kogl_type, content_type)
    q: dict[str, str] = {
        "atcflNo": str(atcfl_no),
        "atcflSeq": str(atcfl_seq),
    }
    if file_name:
        q["fileName"] = file_name
    if mime_type:
        q["mimeType"] = mime_type
    url = DOWNLOAD_URL + "?" + urllib.parse.urlencode(q)
    assert_https_allowed(url, redirect=False)
    tmp_owned = False
    path = dest_path
    if not path:
        fd, path = tempfile.mkstemp(prefix="kosha_bin_", dir=None)
        os.close(fd)
        tmp_owned = True
    headers = {"User-Agent": DEFAULT_UA, "Accept": "*/*", "chnlId": "portal24"}
    try:
        return fetch_https_binary(
            url, path, headers=headers, opener=opener, expect_pdf=expect_pdf,
        )
    except Exception:
        if tmp_owned and path and os.path.isfile(path):
            os.remove(path)
        raise
