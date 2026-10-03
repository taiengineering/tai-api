"""GPT-5.4-mini Vision fallback provider — PoC only.

Called only when primary OCR (CLOVA) returns insufficient facts.
Uses Structured Outputs — model never decides Product/Reference candidates.

Required env vars:
  OPENAI_API_KEY

Cost reference (2026-10-03):
  Input:  $0.75 / 1M tokens
  Output: $4.50 / 1M tokens
  ~1920x1080 image = ~765 input tokens (detail=auto)
"""
import base64
import json
import os
import time
from typing import Optional

from .base import BlockedCredentials, OcrPage, OcrProvider, OcrResult

_ENV_KEY = "OPENAI_API_KEY"
_MODEL = "gpt-4.5-mini"  # use 4.5-mini as 5.4-mini alias pending

_INPUT_COST_PER_M = 0.75
_OUTPUT_COST_PER_M = 4.50

_SYSTEM_PROMPT = """You are an MSDS (Material Safety Data Sheet) text extractor.
Extract ONLY the following fields from the provided MSDS image.
Do NOT identify, select, or recommend any product or regulatory reference.
Return JSON matching the provided schema exactly.
If a field is not found, use null.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": ["string", "null"]},
        "manufacturer_name": {"type": ["string", "null"]},
        "supplier_name": {"type": ["string", "null"]},
        "product_code": {"type": ["string", "null"]},
        "cas_numbers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "CAS numbers found in the document in format NNNNNN-NN-N"
        },
        "insufficient": {
            "type": "boolean",
            "description": "true if product_name and cas_numbers are both absent/unreadable"
        },
    },
    "required": ["product_name", "manufacturer_name", "supplier_name",
                 "product_code", "cas_numbers", "insufficient"],
    "additionalProperties": False,
}


class VisionProvider(OcrProvider):
    name = "GPT_VISION_FALLBACK"

    def _check_availability(self) -> None:
        if not os.environ.get(_ENV_KEY):
            raise BlockedCredentials(
                f"OpenAI credentials absent: {_ENV_KEY} not set"
            )

    def ocr_pdf(self, pdf_path: str, max_pages: Optional[int] = None) -> OcrResult:
        # Vision works on images; PDF must be rasterized first
        # For PoC, rasterize page 1 only as a proxy
        try:
            from pdf2image import convert_from_path
        except ImportError:
            return OcrResult(
                provider=self.name,
                error="pdf2image not installed; cannot rasterize PDF for Vision",
            )
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=150)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            images[0].save(tmp.name, "JPEG", quality=85)
            return self.ocr_image(tmp.name)

    def ocr_image(self, image_path: str) -> OcrResult:
        self._check_availability()
        from openai import OpenAI

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        client = OpenAI(api_key=os.environ[_ENV_KEY])

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{img_b64}",
                                       "detail": "auto"}},
                        {"type": "text", "text": "Extract MSDS fields from this image."},
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "msds_extraction", "schema": _SCHEMA, "strict": True},
            },
            max_tokens=512,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        content = response.choices[0].message.content
        data = json.loads(content)

        in_tokens = response.usage.prompt_tokens
        out_tokens = response.usage.completion_tokens
        cost_usd = (in_tokens * _INPUT_COST_PER_M + out_tokens * _OUTPUT_COST_PER_M) / 1_000_000

        text = _vision_result_to_text(data)
        return OcrResult(
            provider=self.name,
            pages=[OcrPage(page_no=1, text=text, latency_ms=latency_ms)],
            total_latency_ms=latency_ms,
            call_count=1,
            estimated_cost_krw=cost_usd * 1350,  # approx KRW
        )


def _vision_result_to_text(data: dict) -> str:
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
