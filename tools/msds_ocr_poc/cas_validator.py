"""CAS number regex + checksum validator for OBJ-MSDS-04B PoC.

CAS checksum:
  Digits from right (excluding check digit), positions 1..N.
  sum(pos_i * digit_i) % 10 == check_digit
"""
import re
from typing import Optional

_CAS_PATTERN = re.compile(r'\b(\d{1,7})-(\d{2})-(\d)\b')
_CAS_FIND = re.compile(r'\b\d{1,7}-\d{2}-\d\b')


def _checksum(body: str, check: int) -> bool:
    digits = body.replace("-", "")
    total = sum((i + 1) * int(d) for i, d in enumerate(reversed(digits)))
    return (total % 10) == check


def validate_cas(cas: str) -> tuple[bool, bool]:
    """Return (format_valid, checksum_valid)."""
    cas = cas.strip()
    m = _CAS_PATTERN.fullmatch(cas)
    if not m:
        return False, False
    body = m.group(1) + m.group(2)
    check = int(m.group(3))
    return True, _checksum(body, check)


def extract_cas_candidates(text: str) -> list[str]:
    """Extract all CAS-format strings from text."""
    return _CAS_FIND.findall(text)


def extract_valid_cas(text: str) -> list[str]:
    """Extract CAS strings that pass format + checksum."""
    return [c for c in extract_cas_candidates(text) if validate_cas(c) == (True, True)]


# ---------------------------------------------------------------------------
# OCR confusion correction helpers
# ---------------------------------------------------------------------------

_OCR_CORRECTIONS = [
    (re.compile(r'[Oo]'), '0'),
    (re.compile(r'[Il|]'), '1'),
    (re.compile(r'[Ss]'), '5'),
    (re.compile(r'[Bb]'), '8'),
    (re.compile(r'[Zz]'), '2'),
]


def try_correct_cas(raw: str) -> Optional[str]:
    """Try to recover a valid CAS from an OCR-corrupted string.

    Only applies corrections to strings that match the hyphen position pattern
    but fail checksum. Returns corrected CAS or None.
    Does NOT guess or permute — single-pass left-to-right substitution only.
    """
    # Must look like a CAS structurally (hyphens in right positions)
    if not re.match(r'^[^\-]{1,7}-[^\-]{2}-[^\-]$', raw.strip()):
        return None
    corrected = raw.strip()
    for pattern, replacement in _OCR_CORRECTIONS:
        # Only replace in digit positions — not in hyphens
        parts = corrected.split('-')
        parts = [pattern.sub(replacement, p) for p in parts]
        corrected = '-'.join(parts)
    fmt_ok, chk_ok = validate_cas(corrected)
    if fmt_ok and chk_ok and corrected != raw.strip():
        return corrected
    return None
