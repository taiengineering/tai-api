"""CAS number checksum validation and OCR character correction — WO-MSDS-04B-PATCH-001."""
from __future__ import annotations

import re
from typing import Optional, Tuple

_CAS_PATTERN = re.compile(r'^(\d{2,7})-(\d{2})-(\d)$')
# O→0, I→1, S→5, B→8
_OCR_TABLE = str.maketrans("OISB", "0158")


def _checksum(body: str, check: int) -> bool:
    digits = list(reversed(body))
    total = sum((i + 1) * int(d) for i, d in enumerate(digits))
    return (total % 10) == check


def validate_cas(cas: str) -> Tuple[bool, bool]:
    """Return (format_valid, checksum_valid)."""
    m = _CAS_PATTERN.fullmatch(cas.strip())
    if not m:
        return False, False
    body = m.group(1) + m.group(2)
    check = int(m.group(3))
    return True, _checksum(body, check)


def try_correct_cas(raw: str) -> Optional[str]:
    """Apply OCR substitutions (O→0, I→1, S→5, B→8); return corrected CAS if valid, else None.

    Only returns a value if the original was invalid and the correction is both
    format-valid and checksum-valid.
    """
    corrected = raw.strip().upper().translate(_OCR_TABLE)
    if corrected == raw.strip():
        return None
    fmt, chk = validate_cas(corrected)
    return corrected if (fmt and chk) else None


def extract_valid_cas(raw: str) -> Optional[str]:
    """Validate raw CAS string; apply OCR correction if needed. Returns canonical form or None."""
    fmt, chk = validate_cas(raw)
    if fmt and chk:
        return raw.strip()
    return try_correct_cas(raw)
