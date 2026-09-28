"""Equipment type code identity normalization.

Canonical form: 3-digit zero-padded numeric string (001–040).
Authority: equipment_type_inspection_map table.

Known legacy uppercase aliases are mapped to their canonical numeric identity.
Unknown / lowercase / free-text strings are NOT inferred — they pass through
unchanged and will be rejected by downstream authority validation.
"""
from __future__ import annotations

from typing import Optional

# Legacy uppercase alias → canonical numeric identity.
# Based on equipment_type_inspection_map authority.
_ALIAS_TO_NUMERIC: dict[str, str] = {
    "CRANE":            "021",
    "CONVEYOR":         "024",
    "PRESS":            "023",
    "PRESSURE_VESSEL":  "038",
}


def normalize_equipment_type_code(value: Optional[str]) -> Optional[str]:
    """Return canonical numeric form of an equipment_type_code.

    Rules:
      - None           → None
      - Strip whitespace first.
      - Known uppercase alias → numeric (PRESS→023, CONVEYOR→024, CRANE→021, PRESSURE_VESSEL→038).
      - Numeric / unknown string → returned as-is after strip.
      - Lowercase free-text is NOT inferred (pass-through; downstream will reject).
    """
    if value is None:
        return None
    stripped = value.strip()
    return _ALIAS_TO_NUMERIC.get(stripped, stripped)
