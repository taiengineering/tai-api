"""Deterministic MSDS fact parser.

Extracts PRODUCT_NAME, MANUFACTURER_NAME, SUPPLIER_NAME, PRODUCT_CODE, CAS
from raw text (OCR output or native PDF text).

Contract: never fabricates fields. Returns only what the regex finds.
Caller decides whether partial results are sufficient.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from .cas_validator import extract_valid_cas, try_correct_cas, extract_cas_candidates


@dataclass
class ParsedFacts:
    product_name: Optional[str] = None
    manufacturer_name: Optional[str] = None
    supplier_name: Optional[str] = None
    product_code: Optional[str] = None
    cas_numbers: list[str] = field(default_factory=list)
    cas_invalid_rejected: list[str] = field(default_factory=list)
    cas_corrected: list[str] = field(default_factory=list)
    insufficient: bool = False


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PRODUCT_NAME_PATTERNS = [
    re.compile(r'제품명[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Product Name[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'화학물질명[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'명칭[^:：]*[：:]\s*(.+)', re.IGNORECASE),
]

_MANUFACTURER_PATTERNS = [
    re.compile(r'제조사[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'제조업체[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Manufacturer[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Company[^:：]*[：:]\s*(.+)', re.IGNORECASE),
]

_SUPPLIER_PATTERNS = [
    re.compile(r'공급자[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'공급업체[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Supplier[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Distributor[^:：]*[：:]\s*(.+)', re.IGNORECASE),
]

_PRODUCT_CODE_PATTERNS = [
    re.compile(r'제품코드[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Product Code[^:：]*[：:]\s*(.+)', re.IGNORECASE),
    re.compile(r'Article[^:：\s]*[：:\s]\s*([A-Z0-9\-]{3,20})\b', re.IGNORECASE),
    re.compile(r'Cat\.?\s*No\.?[^:：]*[：:]\s*(.+)', re.IGNORECASE),
]


def _first_match(text: str, patterns: list[re.Pattern]) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            val = m.group(1).strip()
            # Cut at line boundary
            val = val.split('\n')[0].strip()
            if val:
                return val
    return None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_facts(text: str, auto_correct_cas: bool = False) -> ParsedFacts:
    """Parse MSDS text into structured facts.

    auto_correct_cas: if True, attempt single-pass OCR error correction
                      (O→0, I→1, S→5, B→8) on invalid CAS candidates.
                      Correction is RECORDED separately, never silently promoted.
    """
    facts = ParsedFacts()

    facts.product_name = _first_match(text, _PRODUCT_NAME_PATTERNS)
    facts.manufacturer_name = _first_match(text, _MANUFACTURER_PATTERNS)
    facts.supplier_name = _first_match(text, _SUPPLIER_PATTERNS)
    facts.product_code = _first_match(text, _PRODUCT_CODE_PATTERNS)

    valid_cas = extract_valid_cas(text)
    all_candidates = extract_cas_candidates(text)
    invalid = [c for c in all_candidates if c not in valid_cas]

    facts.cas_numbers = valid_cas

    if auto_correct_cas:
        for raw in invalid:
            corrected = try_correct_cas(raw)
            if corrected and corrected not in facts.cas_numbers:
                facts.cas_corrected.append(corrected)
                # Corrected values are returned separately — caller decides
        facts.cas_invalid_rejected = [c for c in invalid
                                       if c not in facts.cas_corrected]
    else:
        facts.cas_invalid_rejected = invalid

    facts.insufficient = (
        facts.product_name is None
        and not facts.cas_numbers
    )

    return facts


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def compare_facts(extracted: ParsedFacts, ground_truth: dict) -> dict:
    """Return per-field match results for benchmarking."""
    gt_cas = set(ground_truth.get("cas_numbers", []))
    ex_cas = set(extracted.cas_numbers)

    def match(extracted_val: Optional[str], gt_val: Optional[str]) -> str:
        if gt_val is None:
            return "N/A"
        if extracted_val is None:
            return "MISS"
        # Normalize whitespace and case for comparison
        norm = lambda s: re.sub(r'\s+', ' ', s).strip()
        return "EXACT" if norm(extracted_val) == norm(gt_val) else "PARTIAL"

    cas_recall = len(ex_cas & gt_cas) / len(gt_cas) if gt_cas else 1.0
    false_positives = len(ex_cas - gt_cas)

    return {
        "product_name": match(extracted.product_name, ground_truth.get("product_name")),
        "manufacturer_name": match(extracted.manufacturer_name, ground_truth.get("manufacturer_name")),
        "supplier_name": match(extracted.supplier_name, ground_truth.get("supplier_name")),
        "product_code": match(extracted.product_code, ground_truth.get("product_code")),
        "cas_recall": cas_recall,
        "cas_false_positive": false_positives,
        "cas_extracted": sorted(ex_cas),
        "cas_expected": sorted(gt_cas),
        "cas_invalid_rejected": extracted.cas_invalid_rejected,
    }
