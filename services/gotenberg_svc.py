"""Gotenberg Chromium HTML→PDF 렌더러 — 도메인 무관 공통. (STEP 2B)

HTML → POST {GOTENBERG_URL}/forms/chromium/convert/html → PDF bytes.
GOTENBERG_URL 은 env 에서만 읽는다(하드코딩 금지). 운영값(hostname·포트 전부)은 Railway env 로만
바인딩 — 이 파일 어디에도 URL/포트 리터럴은 존재하지 않는다(테스트 PORT-1/2 grep 어서션).

오류 계약(라우터가 HTTP 로 번역) :
  PDF_RENDER_CONFIG_MISSING (503) — GOTENBERG_URL env 미설정 (localhost/public fallback 금지)
  PDF_RENDER_UNAVAILABLE    (503) — network/timeout/5xx 등 렌더 서버 접속·처리 실패
  PDF_RENDER_INVALID        (502) — 4xx (503 아님) 또는 응답이 유효 PDF 아님 (content-type 또는 %PDF- 미검증)
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

_CONVERT_PATH = "/forms/chromium/convert/html"


class PdfRenderError(Exception):
    def __init__(self, code: str, message: str, http_status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _base_url() -> str:
    url = (os.getenv("GOTENBERG_URL") or "").strip().rstrip("/")
    if not url:
        # 임의 localhost/public fallback 금지 (REV-2 §13). env 미설정은 config 오류.
        raise PdfRenderError(
            "PDF_RENDER_CONFIG_MISSING",
            "PDF 렌더 서버(GOTENBERG_URL) 설정이 없습니다.",
            503,
        )
    return url


def render_html_pdf(html_content: str, *, trace_id: Optional[str] = None, timeout: float = 30.0) -> bytes:
    """self-contained HTML(str) → PDF bytes. 실패는 controlled PdfRenderError. raw 응답 미노출."""
    url = _base_url() + _CONVERT_PATH
    files = {"files": ("index.html", html_content.encode("utf-8"), "text/html")}
    data = {"preferCssPageSize": "true", "printBackground": "true"}
    try:
        resp = httpx.post(url, files=files, data=data, timeout=timeout)
    except Exception as e:                        # network / timeout / transport
        raise PdfRenderError(
            "PDF_RENDER_UNAVAILABLE",
            "PDF 렌더 서버에 연결할 수 없습니다.",
            503,
        ) from e
    if resp.status_code >= 500:
        raise PdfRenderError(
            "PDF_RENDER_UNAVAILABLE",
            "PDF 렌더 서버 오류.",
            503,
        )
    if resp.status_code != 200:
        raise PdfRenderError(
            "PDF_RENDER_INVALID",
            "PDF 렌더 응답이 올바르지 않습니다.",
            502,
        )
    ctype = (resp.headers.get("content-type") or "").lower()
    body = resp.content or b""
    if "application/pdf" not in ctype or not body.startswith(b"%PDF-"):
        raise PdfRenderError(
            "PDF_RENDER_INVALID",
            "PDF 렌더 결과가 유효한 PDF가 아닙니다.",
            502,
        )
    return body
