"""NAVER CLOVA General OCR V2 adapter — PoC only.

Production use: add to tools/msds_ocr_poc/providers/ only.
Required env vars:
  CLOVA_OCR_INVOKE_URL   — e.g. https://ocr.apigw.ntruss.com/custom/v1/.../general
  CLOVA_OCR_SECRET       — secret key from CLOVA OCR console

Cost reference (2026-10-03):
  KRW 3 / call (General OCR, VAT excl.)
  First 100 calls/month free
"""
import json
import os
import time
import uuid
from typing import Optional

from .base import BlockedCredentials, OcrPage, OcrProvider, OcrResult

_URL_ENV = "CLOVA_OCR_INVOKE_URL"
_SECRET_ENV = "CLOVA_OCR_SECRET"
_COST_PER_CALL_KRW = 3.0


class ClovaOcrProvider(OcrProvider):
    name = "NAVER_CLOVA_GENERAL_V2"

    def _check_availability(self) -> None:
        if not os.environ.get(_URL_ENV) or not os.environ.get(_SECRET_ENV):
            raise BlockedCredentials(
                f"CLOVA credentials absent: {_URL_ENV} and {_SECRET_ENV} not set"
            )

    def ocr_pdf(self, pdf_path: str, max_pages: Optional[int] = None) -> OcrResult:
        self._check_availability()
        import requests

        url = os.environ[_URL_ENV]
        secret = os.environ[_SECRET_ENV]

        with open(pdf_path, "rb") as f:
            file_bytes = f.read()

        payload = {
            "images": [{
                "format": "pdf",
                "name": os.path.basename(pdf_path),
                "data": None,
            }],
            "requestId": str(uuid.uuid4()),
            "version": "V2",
            "timestamp": int(time.time() * 1000),
            "lang": "ko",
        }

        headers = {
            "X-OCR-SECRET": secret,
            "Content-Type": "application/json",
        }

        # CLOVA General OCR accepts PDF as multipart
        t0 = time.perf_counter()
        resp = requests.post(
            url,
            headers={"X-OCR-SECRET": secret},
            files={"file": (os.path.basename(pdf_path), file_bytes, "application/pdf")},
            data={"message": json.dumps(payload)},
            timeout=60,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        body = resp.json()

        pages = _parse_clova_response(body)
        if max_pages is not None:
            pages = pages[:max_pages]

        return OcrResult(
            provider=self.name,
            pages=pages,
            total_latency_ms=latency_ms,
            call_count=1,
            estimated_cost_krw=_COST_PER_CALL_KRW,
        )

    def ocr_image(self, image_path: str) -> OcrResult:
        self._check_availability()
        import requests

        url = os.environ[_URL_ENV]
        secret = os.environ[_SECRET_ENV]

        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        fmt = "jpeg" if ext in ("jpg", "jpeg") else ext

        with open(image_path, "rb") as f:
            file_bytes = f.read()

        payload = {
            "images": [{"format": fmt, "name": os.path.basename(image_path)}],
            "requestId": str(uuid.uuid4()),
            "version": "V2",
            "timestamp": int(time.time() * 1000),
            "lang": "ko",
        }

        t0 = time.perf_counter()
        resp = requests.post(
            url,
            headers={"X-OCR-SECRET": secret},
            files={"file": (os.path.basename(image_path), file_bytes, f"image/{fmt}")},
            data={"message": json.dumps(payload)},
            timeout=60,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        body = resp.json()

        pages = _parse_clova_response(body)
        return OcrResult(
            provider=self.name,
            pages=pages,
            total_latency_ms=latency_ms,
            call_count=1,
            estimated_cost_krw=_COST_PER_CALL_KRW,
        )


def _parse_clova_response(body: dict) -> list[OcrPage]:
    """Extract text from CLOVA General OCR V2 response."""
    pages = []
    images = body.get("images", [])
    for i, img in enumerate(images):
        fields = img.get("fields", [])
        texts = [f.get("inferText", "") for f in fields]
        text = " ".join(t for t in texts if t)
        pages.append(OcrPage(
            page_no=i + 1,
            text=text,
            provider_request_id=body.get("requestId"),
        ))
    return pages
