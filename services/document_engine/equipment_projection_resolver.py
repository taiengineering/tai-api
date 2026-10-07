"""AUTO-SRC-02B: Equipment type code → EQUIP doc_detail resolver (GAP-02C).

Resolves canonical numeric equipment_type_code to AUTO EQUIP projection_detail.
Source of truth: document_equipment_projection_map (DB); static fallback for tests.
Uses canonicalizer to normalize aliases before lookup (CRANE→021, etc.).
"""
from __future__ import annotations

from typing import Optional

from services.equipment_source.canonicalizer import normalize_equipment_type_code

# Static fallback map identical to the 40-row seed in the migration.
# Used in tests and when DB is unavailable.
# Keys = normalized numeric codes (zero-padded strings).
_STATIC_MAP: dict[str, Optional[str]] = {
    "001": "ELEC",
    "002": "ELEC",
    "003": "ELEC",
    "004": "ELEC",
    "005": "ELEC",
    "006": "ELEC",
    "007": "ELEC",
    "008": "ELEC",
    "009": "ELEC",
    "010": "ELEC",
    "011": "MACHINE",
    "012": "MACHINE",
    "013": "MACHINE",
    "014": "BOILER",
    "015": None,
    "016": "MACHINE",
    "017": "MACHINE",
    "018": "MACHINE",
    "019": "REFRIG",
    "020": "REFRIG",
    "021": "CRANE",
    "022": "CRANE",
    "023": "MACHINE",
    "024": "MACHINE",
    "025": "ELEV",
    "026": "ELEV",
    "027": "GAS",
    "028": "GAS",
    "029": "HAZMAT",
    "030": "HAZMAT",
    "031": "FIRE",
    "032": "FIRE",
    "033": "FIRE",
    "034": "FIRE",
    "035": None,
    "036": None,
    "037": None,
    "038": "MACHINE",
    "039": "REFRIG",
    "040": None,
}


def resolve_equipment_detail(
    equipment_type_code: Optional[str],
    *,
    _override_map: Optional[dict[str, Optional[str]]] = None,
) -> Optional[str]:
    """Return EQUIP projection_detail for the given equipment_type_code.

    Returns None for UNRESOLVED codes (015/035/036/037/040) and unknown codes.
    Normalizes aliases (CRANE→021) before lookup.
    """
    if equipment_type_code is None:
        return None
    normalized = normalize_equipment_type_code(equipment_type_code)
    if normalized is None:
        return None
    lookup = _override_map if _override_map is not None else _STATIC_MAP
    return lookup.get(normalized)
