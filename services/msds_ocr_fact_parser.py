"""OCR / Vision text → MSDS Fact contract — WO-MSDS-04B-PATCH-001."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.cas_validator import extract_valid_cas, try_correct_cas

# Broad pattern capturing CAS-like strings with possible OCR character substitutions
_CAS_PATTERN = re.compile(r'\b([0-9A-Z]{2,7}-[0-9A-Z]{2}-[0-9A-Z])\b')

_PRODUCT_NAME_MARKERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'제품명\s*[:\s]+(.+)',
        r'product\s*name\s*[:\s]+(.+)',
        r'상품명\s*[:\s]+(.+)',
        r'물질명\s*[:\s]+(.+)',
    ]
]

_MANUFACTURER_MARKERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'제조\s*사\s*[:\s]+(.+)',
        r'제조\s*업체\s*[:\s]+(.+)',
        r'manufacturer\s*[:\s]+(.+)',
        r'회사명\s*[:\s]+(.+)',
    ]
]

_SUPPLIER_MARKERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'공급\s*자\s*[:\s]+(.+)',
        r'supplier\s*[:\s]+(.+)',
    ]
]

_PRODUCT_CODE_MARKERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'제품\s*코드\s*[:\s]+(.+)',
        r'product\s*code\s*[:\s]+(.+)',
    ]
]

_CAS_CONTEXT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'구성\s*성분', r'composition', r'section\s*3', r'CAS\s*번호',
        r'CAS\s*No', r'cas\s*number', r'화학물질명',
    ]
]


def _normalize(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _extract_first(markers: list, text: str) -> Optional[str]:
    for marker in markers:
        m = marker.search(text)
        if m:
            val = m.group(1).strip().split("\n")[0].strip()
            if val and len(val) > 1:
                return val
    return None


def _cas_evidence(raw: str, valid: str, method: str, context: Optional[str] = None) -> Dict:
    correction_applied = valid != raw.strip()
    ev: Dict[str, Any] = {
        "cas": valid,
        "correction_applied": correction_applied,
    }
    if correction_applied:
        ev["corrected_value"] = valid
    if context:
        ev["context"] = context
    return ev


def parse_ocr_facts(text: str, extraction_method: str = "OCR") -> List[Dict[str, Any]]:
    """Parse OCR or Vision text into MSDS fact dicts ready for msds_intake_facts insertion.

    extraction_method: 'OCR' | 'VISION'
    CAS numbers validated and OCR-corrected via cas_validator.
    Corrected CAS carries correction_applied=true in evidence_json.
    """
    facts: List[Dict[str, Any]] = []

    product_name = _extract_first(_PRODUCT_NAME_MARKERS, text)
    if product_name:
        facts.append({
            "fact_type": "PRODUCT_NAME",
            "raw_value": product_name,
            "normalized_value": _normalize(product_name),
            "extraction_method": extraction_method,
            "evidence_json": {"match": product_name[:200]},
        })

    mfr = _extract_first(_MANUFACTURER_MARKERS, text)
    if mfr:
        facts.append({
            "fact_type": "MANUFACTURER_NAME",
            "raw_value": mfr,
            "normalized_value": _normalize(mfr),
            "extraction_method": extraction_method,
            "evidence_json": {"match": mfr[:200]},
        })

    supplier = _extract_first(_SUPPLIER_MARKERS, text)
    if supplier:
        facts.append({
            "fact_type": "SUPPLIER_NAME",
            "raw_value": supplier,
            "normalized_value": _normalize(supplier),
            "extraction_method": extraction_method,
            "evidence_json": {"match": supplier[:200]},
        })

    code = _extract_first(_PRODUCT_CODE_MARKERS, text)
    if code:
        facts.append({
            "fact_type": "PRODUCT_CODE",
            "raw_value": code,
            "normalized_value": _normalize(code),
            "extraction_method": extraction_method,
            "evidence_json": {"match": code[:200]},
        })

    # CAS: context-aware pass first, full-text fallback if none found
    cas_found: set[str] = set()
    for ctx_pat in _CAS_CONTEXT_PATTERNS:
        for ctx_m in ctx_pat.finditer(text):
            start = max(0, ctx_m.start() - 50)
            end = min(len(text), ctx_m.end() + 500)
            region = text[start:end]
            for raw_m in _CAS_PATTERN.finditer(region):
                raw_cas = raw_m.group(1)
                valid = extract_valid_cas(raw_cas)
                if valid and valid not in cas_found:
                    cas_found.add(valid)
                    facts.append({
                        "fact_type": "CAS",
                        "raw_value": raw_cas,
                        "normalized_value": valid,
                        "extraction_method": extraction_method,
                        "evidence_json": _cas_evidence(raw_cas, valid, extraction_method,
                                                       ctx_pat.pattern),
                    })

    if not cas_found:
        for raw_m in _CAS_PATTERN.finditer(text):
            raw_cas = raw_m.group(1)
            valid = extract_valid_cas(raw_cas)
            if valid and valid not in cas_found:
                cas_found.add(valid)
                facts.append({
                    "fact_type": "CAS",
                    "raw_value": raw_cas,
                    "normalized_value": valid,
                    "extraction_method": extraction_method,
                    "evidence_json": _cas_evidence(raw_cas, valid, extraction_method),
                })

    return facts


def is_sufficient(facts: List[Dict[str, Any]]) -> bool:
    """True only when facts contain both PRODUCT_NAME and at least one checksum-valid CAS."""
    types = {f["fact_type"] for f in facts}
    return "PRODUCT_NAME" in types and "CAS" in types
