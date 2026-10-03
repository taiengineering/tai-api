"""GPT Vision fallback provider — WO-MSDS-04B-PATCH-001.

Called only when CLOVA returns insufficient facts.
Structured Outputs — model never selects Product/Reference candidates.

Required env vars:
  OPENAI_API_KEY
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

_ENV_KEY = "OPENAI_API_KEY"
_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You are an MSDS (Material Safety Data Sheet) text extractor. "
    "Extract ONLY the following fields from the provided MSDS image. "
    "Do NOT identify, select, or recommend any product or regulatory reference. "
    "Return JSON matching the provided schema exactly. "
    "If a field is not found, use null."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": ["string", "null"]},
        "manufacturer_name": {"type": ["string", "null"]},
        "supplier_name": {"type": ["string", "null"]},
        "product_code": {"type": ["string", "null"]},
        "cas_numbers": {"type": "array", "items": {"type": "string"}},
        "insufficient": {"type": "boolean"},
    },
    "required": [
        "product_name", "manufacturer_name", "supplier_name",
        "product_code", "cas_numbers", "insufficient",
    ],
    "additionalProperties": False,
}

_INPUT_COST_PER_M = 0.15
_OUTPUT_COST_PER_M = 0.60
_KRW_PER_USD = 1350


@dataclass
class VisionResult:
    full_text: str = ""
    insufficient: bool = False
    latency_ms: float = 0.0
    cost_krw: float = 0.0
    error: Optional[str] = None


class VisionCredentialError(Exception):
    pass


def vision_available() -> bool:
    return bool(os.environ.get(_ENV_KEY))


def run_vision_ocr(image_path: str) -> VisionResult:
    """Run GPT Vision extraction on a JPEG image file.

    Raises VisionCredentialError if credentials absent.
    """
    if not vision_available():
        raise VisionCredentialError("OpenAI credentials absent")

    try:
        from openai import OpenAI
    except ImportError:
        return VisionResult(error="openai package not installed")

    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except OSError as e:
        return VisionResult(error=f"image read failed: {e}")

    client = OpenAI(api_key=os.environ[_ENV_KEY])
    t0 = time.perf_counter()

    try:
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}",
                                "detail": "auto",
                            },
                        },
                        {"type": "text", "text": "Extract MSDS fields from this image."},
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "msds_extraction",
                    "schema": _SCHEMA,
                    "strict": True,
                },
            },
            max_tokens=512,
        )
    except Exception as e:
        return VisionResult(error=str(e)[:500])

    latency_ms = (time.perf_counter() - t0) * 1000
    content = response.choices[0].message.content
    data = json.loads(content)

    in_tokens = response.usage.prompt_tokens
    out_tokens = response.usage.completion_tokens
    cost_usd = (
        in_tokens * _INPUT_COST_PER_M + out_tokens * _OUTPUT_COST_PER_M
    ) / 1_000_000
    cost_krw = cost_usd * _KRW_PER_USD

    return VisionResult(
        full_text=_result_to_text(data),
        insufficient=data.get("insufficient", False),
        latency_ms=latency_ms,
        cost_krw=cost_krw,
    )


def rasterize_pdf_page(pdf_bytes: bytes, page_no: int = 1, dpi: int = 150) -> Optional[str]:
    """Rasterize a single PDF page to a temp JPEG using pypdfium2.

    page_no is 1-indexed. Returns temp file path or None on failure.
    Caller must delete the returned file when done.
    """
    tmp_jpg_path: Optional[str] = None
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf_bytes)
        page_index = page_no - 1
        if page_index < 0 or page_index >= len(doc):
            return None

        page = doc[page_index]
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_jpg:
            tmp_jpg_path = tmp_jpg.name

        pil_image.save(tmp_jpg_path, "JPEG", quality=85)
        return tmp_jpg_path
    except Exception:
        if tmp_jpg_path is not None:
            try:
                os.unlink(tmp_jpg_path)
            except OSError:
                pass
        return None


def _result_to_text(data: dict) -> str:
    lines = []
    if data.get("product_name"):
        lines.append(f"제품명: {data['product_name']}")
    if data.get("manufacturer_name"):
        lines.append(f"제조사: {data['manufacturer_name']}")
    if data.get("supplier_name"):
        lines.append(f"공급자: {data['supplier_name']}")
    if data.get("product_code"):
        lines.append(f"제품코드: {data['product_code']}")
    for cas in data.get("cas_numbers", []):
        lines.append(f"CAS 번호: {cas}")
    return "\n".join(lines)
