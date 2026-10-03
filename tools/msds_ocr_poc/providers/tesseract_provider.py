"""Tesseract OCR provider — local baseline for PoC comparison.

Requires:
  - tesseract binary (brew install tesseract tesseract-lang)
  - pytesseract Python package
  - Korean language data: tesseract-lang or kor.traineddata

This is a LOCAL BASELINE only — not a Production candidate.
"""
import os
import time
from typing import Optional

from .base import OcrPage, OcrProvider, OcrResult, ProviderNotInstalled

_COST_PER_CALL_KRW = 0.0  # local, no API cost


class TesseractProvider(OcrProvider):
    name = "TESSERACT_ENG_KOR"

    def _check_availability(self) -> None:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
        except ImportError:
            raise ProviderNotInstalled("pytesseract not installed: pip install pytesseract")
        except Exception as e:
            raise ProviderNotInstalled(f"tesseract binary not found or not working: {e}")

    def ocr_pdf(self, pdf_path: str, max_pages: Optional[int] = None) -> OcrResult:
        self._check_availability()
        import pytesseract
        from PIL import Image
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        if max_pages is not None:
            page_count = min(page_count, max_pages)

        pages = []
        total_latency = 0.0
        call_count = 0

        for i in range(page_count):
            # Rasterize PDF page to image via pypdf
            # Note: pypdf cannot rasterize natively — use pdf2image if available
            # Fallback: extract native text and test OCR on JPEG only
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(pdf_path, first_page=i + 1, last_page=i + 1,
                                           dpi=200)
                img = images[0]
            except ImportError:
                # Cannot rasterize — record as limitation
                pages.append(OcrPage(page_no=i + 1, text="",
                                     provider_request_id="PDF2IMAGE_ABSENT"))
                continue

            t0 = time.perf_counter()
            text = pytesseract.image_to_string(img, lang="kor+eng")
            latency_ms = (time.perf_counter() - t0) * 1000
            total_latency += latency_ms
            call_count += 1
            pages.append(OcrPage(page_no=i + 1, text=text, latency_ms=latency_ms))

        return OcrResult(
            provider=self.name,
            pages=pages,
            total_latency_ms=total_latency,
            call_count=call_count,
            estimated_cost_krw=_COST_PER_CALL_KRW,
        )

    def ocr_image(self, image_path: str) -> OcrResult:
        self._check_availability()
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        t0 = time.perf_counter()
        text = pytesseract.image_to_string(img, lang="kor+eng")
        latency_ms = (time.perf_counter() - t0) * 1000

        return OcrResult(
            provider=self.name,
            pages=[OcrPage(page_no=1, text=text, latency_ms=latency_ms)],
            total_latency_ms=latency_ms,
            call_count=1,
            estimated_cost_krw=_COST_PER_CALL_KRW,
        )
