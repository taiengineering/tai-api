"""MSDS PDF native text extraction — WO-MSDS-04A-IMPLEMENTATION-001."""
from __future__ import annotations

import re
import hashlib
from typing import Any, Dict, List, Optional

try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
except ImportError:
    PdfReader = None  # type: ignore
    PdfReadError = Exception  # type: ignore


_CAS_PATTERN = re.compile(r'\b(\d{2,7}-\d{2}-\d)\b')

# Korean/common MSDS section markers for CAS extraction context
_CAS_CONTEXT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'구성\s*성분', r'composition', r'section\s*3', r'CAS\s*번호', r'CAS\s*No',
        r'cas\s*number', r'화학물질명',
    ]
]

_PRODUCT_NAME_MARKERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'제품명\s*[:\s]+(.+)', r'product\s*name\s*[:\s]+(.+)',
        r'상품명\s*[:\s]+(.+)', r'물질명\s*[:\s]+(.+)',
    ]
]

_MANUFACTURER_MARKERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'제조\s*사\s*[:\s]+(.+)', r'제조\s*업체\s*[:\s]+(.+)',
        r'manufacturer\s*[:\s]+(.+)', r'회사명\s*[:\s]+(.+)',
    ]
]


def _normalize(text: str) -> str:
    """Trim + casefold + collapse whitespace."""
    return " ".join(text.strip().casefold().split())


class ExtractionResult:
    def __init__(self, page_count: int, facts: List[Dict[str, Any]], ocr_required: bool = False, error: Optional[str] = None):
        self.page_count = page_count
        self.facts = facts
        self.ocr_required = ocr_required
        self.error = error


def extract_facts(file_bytes: bytes) -> ExtractionResult:
    """Extract Identity Facts from PDF bytes using native text layer.

    Returns ExtractionResult. ocr_required=True if no usable facts found.
    """
    if PdfReader is None:
        return ExtractionResult(0, [], error="pypdf not installed")

    try:
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
    except PdfReadError as e:
        return ExtractionResult(0, [], error=f"PDF parse error: {e}")
    except Exception as e:
        return ExtractionResult(0, [], error=f"Unexpected error: {e}")

    page_count = len(reader.pages)
    pages_text: List[tuple] = []

    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages_text.append((i + 1, text))

    if not pages_text:
        return ExtractionResult(page_count, [], ocr_required=True)

    full_text = "\n".join(t for _, t in pages_text)
    facts: List[Dict[str, Any]] = []

    # --- Product name extraction ---
    for marker in _PRODUCT_NAME_MARKERS:
        for page_no, page_text in pages_text:
            for m in marker.finditer(page_text):
                val = m.group(1).strip().split("\n")[0].strip()
                if val and len(val) > 1:
                    facts.append({
                        "fact_type": "PRODUCT_NAME",
                        "raw_value": val,
                        "normalized_value": _normalize(val),
                        "source_page": page_no,
                        "evidence_json": {"pattern": marker.pattern, "match": val[:200]},
                    })
                    break  # first match per marker
            else:
                continue
            break

    # --- Manufacturer extraction ---
    for marker in _MANUFACTURER_MARKERS:
        for page_no, page_text in pages_text:
            for m in marker.finditer(page_text):
                val = m.group(1).strip().split("\n")[0].strip()
                if val and len(val) > 1:
                    facts.append({
                        "fact_type": "MANUFACTURER_NAME",
                        "raw_value": val,
                        "normalized_value": _normalize(val),
                        "source_page": page_no,
                        "evidence_json": {"pattern": marker.pattern, "match": val[:200]},
                    })
                    break
            else:
                continue
            break

    # --- CAS extraction: prefer context-aware section ---
    cas_found: set = set()
    # First pass: near CAS context markers
    for ctx_pat in _CAS_CONTEXT_PATTERNS:
        for page_no, page_text in pages_text:
            for ctx_match in ctx_pat.finditer(page_text):
                # look in surrounding 500 chars
                start = max(0, ctx_match.start() - 50)
                end = min(len(page_text), ctx_match.end() + 500)
                region = page_text[start:end]
                for cas_m in _CAS_PATTERN.finditer(region):
                    cas = cas_m.group(1)
                    if cas not in cas_found:
                        cas_found.add(cas)
                        facts.append({
                            "fact_type": "CAS",
                            "raw_value": cas,
                            "normalized_value": cas,
                            "source_page": page_no,
                            "evidence_json": {"context": ctx_pat.pattern, "cas": cas},
                        })

    # Second pass: anywhere in document if no CAS found yet
    if not cas_found:
        for page_no, page_text in pages_text:
            for cas_m in _CAS_PATTERN.finditer(page_text):
                cas = cas_m.group(1)
                if cas not in cas_found:
                    cas_found.add(cas)
                    facts.append({
                        "fact_type": "CAS",
                        "raw_value": cas,
                        "normalized_value": cas,
                        "source_page": page_no,
                        "evidence_json": {"cas": cas},
                    })

    if not facts:
        return ExtractionResult(page_count, [], ocr_required=True)

    return ExtractionResult(page_count, facts)
