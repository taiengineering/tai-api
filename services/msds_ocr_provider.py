"""CLOVA General OCR V2 provider — WO-MSDS-04B-PATCH-001.

Exposes run_clova_ocr_range() for a single page-range call.
Service orchestration (pass1/pass2 logic) lives in msds_intake_svc.

Required env vars:
  CLOVA_OCR_INVOKE_URL  — HTTPS endpoint from CLOVA console
  CLOVA_OCR_SECRET      — APIGW-Signature secret

Cost: ~KRW 3 / API call.
"""
from __future__ import annotations

import io
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import tenacity

_ENV_URL = "CLOVA_OCR_INVOKE_URL"
_ENV_SECRET = "CLOVA_OCR_SECRET"
_KRW_PER_CALL = 3
_MAX_ATTEMPTS = 3


@dataclass
class OcrResult:
    provider: str
    full_text: str = ""
    pages_processed: int = 0
    latency_ms: float = 0.0
    cost_krw: float = 0.0
    call_count: int = 0
    request_id: str = ""
    error: Optional[str] = None


class OcrCredentialError(Exception):
    pass


class OcrProviderError(Exception):
    pass


class OcrRateLimitError(OcrProviderError):
    pass


class OcrRequestFailedError(OcrProviderError):
    pass


class OcrUnsupportedFormatError(OcrProviderError):
    pass


def clova_available() -> bool:
    return bool(os.environ.get(_ENV_URL) and os.environ.get(_ENV_SECRET))


def _slice_pdf(pdf_bytes: bytes, start_page: int, end_page: int) -> Optional[bytes]:
    """Return PDF containing pages [start_page, end_page) (0-indexed). None on failure."""
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if i < start_page:
                continue
            if i >= end_page:
                break
            writer.add_page(page)
        if len(writer.pages) == 0:
            return None
        out = io.BytesIO()
        writer.write(out)
        sliced = out.getvalue()
        return sliced if sliced else None
    except Exception:
        return None


def _pdf_page_count(pdf_bytes: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return 0


def _is_retryable(exc: Exception) -> bool:
    """True for network errors, 429, and 5xx status codes."""
    import requests
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return status == 429 or status >= 500
    return False


def _call_clova(pdf_bytes: bytes) -> OcrResult:
    """Single CLOVA multipart POST with retry. Raises OcrProviderError sub-types on failure."""
    try:
        import requests
    except ImportError:
        raise OcrProviderError("requests package not installed")

    url = os.environ[_ENV_URL]
    secret = os.environ[_ENV_SECRET]
    request_id = str(uuid.uuid4())

    request_body = json.dumps({
        "version": "V2",
        "requestId": request_id,
        "timestamp": int(time.time() * 1000),
        "lang": "auto",
        "images": [{"format": "pdf", "name": "msds"}],
    })

    @tenacity.retry(
        retry=tenacity.retry_if_exception(_is_retryable),
        stop=tenacity.stop_after_attempt(_MAX_ATTEMPTS),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _do_post() -> "requests.Response":
        return requests.post(
            url,
            headers={"X-OCR-SECRET": secret},
            data={"message": request_body},
            files={"file": ("msds.pdf", pdf_bytes, "application/pdf")},
            timeout=60,
        )

    t0 = time.perf_counter()
    try:
        resp = _do_post()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if status == 429:
            raise OcrRateLimitError(f"CLOVA rate limited (429)") from e
        if status == 415 or status == 400:
            raise OcrUnsupportedFormatError(f"CLOVA format error ({status})") from e
        raise OcrRequestFailedError(f"CLOVA HTTP {status}") from e
    except Exception as e:
        raise OcrRequestFailedError(f"CLOVA request failed: {str(e)[:200]}") from e

    try:
        resp.raise_for_status()
    except Exception as e:
        status = resp.status_code
        if status == 429:
            raise OcrRateLimitError(f"CLOVA rate limited (429)") from e
        raise OcrRequestFailedError(f"CLOVA HTTP {status}") from e

    latency_ms = (time.perf_counter() - t0) * 1000

    try:
        data = resp.json()
    except Exception as e:
        raise OcrRequestFailedError(f"CLOVA invalid JSON response: {e}") from e

    lines = []
    pages = 0
    for img in data.get("images", []):
        pages += 1
        for f in img.get("fields", []):
            text = f.get("inferText", "")
            if text:
                lines.append(text)

    return OcrResult(
        provider="CLOVA",
        full_text=" ".join(lines),
        pages_processed=pages,
        latency_ms=latency_ms,
        cost_krw=_KRW_PER_CALL,
        call_count=1,
        request_id=request_id,
    )


def run_clova_ocr_range(
    pdf_bytes: bytes,
    start_page: int = 0,
    end_page: int = 5,
) -> OcrResult:
    """Run CLOVA OCR on pages [start_page, end_page) of a PDF.

    Raises OcrCredentialError if credentials absent.
    Raises OcrProviderError sub-types on API failure.
    """
    if not clova_available():
        raise OcrCredentialError("CLOVA credentials absent: "
                                 f"{_ENV_URL} and {_ENV_SECRET} required")

    sliced = _slice_pdf(pdf_bytes, start_page, end_page)
    if sliced is None:
        raise OcrRequestFailedError(
            f"Failed to slice PDF pages {start_page}-{end_page}"
        )
    return _call_clova(sliced)
