"""CLOVA General OCR V2 provider — WO-MSDS-04B-IMPLEMENTATION-001.

Pass1: pages 1-5. Pass2: pages 6-10 (only if doc has >5 pages).
One multipart POST per pass; KRW 3/call.

Required env vars:
  CLOVA_OCR_INVOKE_URL  — HTTPS endpoint from CLOVA console
  CLOVA_OCR_SECRET      — APIGW-Signature secret
"""
from __future__ import annotations

import io
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

_ENV_URL = "CLOVA_OCR_INVOKE_URL"
_ENV_SECRET = "CLOVA_OCR_SECRET"
_KRW_PER_CALL = 3


@dataclass
class OcrResult:
    provider: str
    full_text: str = ""
    pages_processed: int = 0
    latency_ms: float = 0.0
    cost_krw: float = 0.0
    call_count: int = 0
    error: Optional[str] = None


class OcrCredentialError(Exception):
    pass


class OcrProviderError(Exception):
    pass


def clova_available() -> bool:
    return bool(os.environ.get(_ENV_URL) and os.environ.get(_ENV_SECRET))


def _slice_pdf(pdf_bytes: bytes, start_page: int, end_page: int) -> Optional[bytes]:
    """Return PDF bytes for pages [start_page, end_page) (0-indexed). Returns None on failure."""
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


def _call_clova(pdf_bytes: bytes) -> OcrResult:
    """Single CLOVA multipart POST. Returns OcrResult with raw text lines joined."""
    try:
        import requests
    except ImportError:
        return OcrResult(provider="CLOVA", error="requests package not installed")

    url = os.environ[_ENV_URL]
    secret = os.environ[_ENV_SECRET]

    request_body = json.dumps({
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": "auto",
        "images": [{"format": "pdf", "name": "msds"}],
    })

    t0 = time.perf_counter()
    try:
        resp = requests.post(
            url,
            headers={"X-OCR-SECRET": secret},
            data={"message": request_body},
            files={"file": ("msds.pdf", pdf_bytes, "application/pdf")},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return OcrResult(provider="CLOVA", error=str(e)[:500])

    latency_ms = (time.perf_counter() - t0) * 1000

    lines = []
    pages = 0
    for img in data.get("images", []):
        pages += 1
        for field in img.get("fields", []):
            text = field.get("inferText", "")
            if text:
                lines.append(text)

    return OcrResult(
        provider="CLOVA",
        full_text=" ".join(lines),
        pages_processed=pages,
        latency_ms=latency_ms,
        cost_krw=_KRW_PER_CALL,
        call_count=1,
    )


def run_clova_ocr(pdf_bytes: bytes) -> OcrResult:
    """Run two-pass CLOVA OCR: pass1=pages 1-5, pass2=pages 6-10.

    Raises OcrCredentialError if credentials absent.
    Raises OcrProviderError if pass1 fails.
    Pass2 failure is non-fatal (partial results returned).
    """
    if not clova_available():
        raise OcrCredentialError("CLOVA credentials absent")

    total_pages = _pdf_page_count(pdf_bytes)

    # Pass 1: pages 1-5
    pass1_bytes = _slice_pdf(pdf_bytes, 0, 5) or pdf_bytes
    r1 = _call_clova(pass1_bytes)
    if r1.error:
        raise OcrProviderError(f"CLOVA pass1: {r1.error}")

    full_text = r1.full_text
    pages_processed = r1.pages_processed
    calls = 1
    cost = r1.cost_krw
    latency = r1.latency_ms

    # Pass 2: pages 6-10 (only when document has more than 5 pages)
    if total_pages > 5:
        pass2_bytes = _slice_pdf(pdf_bytes, 5, 10)
        if pass2_bytes:
            r2 = _call_clova(pass2_bytes)
            if not r2.error:
                full_text = full_text + "\n" + r2.full_text
                pages_processed += r2.pages_processed
                calls += 1
                cost += r2.cost_krw
                latency += r2.latency_ms

    return OcrResult(
        provider="CLOVA",
        full_text=full_text,
        pages_processed=pages_processed,
        latency_ms=latency,
        cost_krw=cost,
        call_count=calls,
    )
