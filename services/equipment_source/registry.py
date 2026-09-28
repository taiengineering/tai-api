"""Equipment source registry — equipment_type_code → canonical boolean facts.

Authority: equipment_assets.equipment_type_code (numeric codes 001–040).
Only codes with confirmed canonical boolean targets are listed here.
Unknown codes are silently skipped by the projector (missing != false).

Mapping authority note (code_condition_resolver discrepancies):
  "010" (비상발전기): code_condition_resolver maps "010"→has_generator
      (name differs from has_emergency_gen used here). Canonical LEG fact name
      is has_emergency_gen per equipment_assets practice.
  "038" (압력용기): absent from code_condition_resolver; mapping authority is
      equipment_type_inspection_map / equipment_assets data only.
  "014", "023", "024": code_condition_resolver alignment not independently confirmed.

EQUIPMENT_CODE_AUTHORITY_BLOCKED codes (no exact code in existing authority):
  has_construction_machine — 건설기계: no numeric code in equipment_type_code system
  has_high_speed_rotor     — 고속회전체: no numeric code in equipment_type_code system
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet

EQUIPMENT_CODE_MAP: Dict[str, Dict[str, Any]] = {
    "010": {"label": "비상발전기", "boolean_facts": ["has_emergency_gen"]},
    "014": {"label": "보일러",    "boolean_facts": ["has_boiler"]},
    "023": {"label": "프레스",    "boolean_facts": ["has_press"]},
    "024": {"label": "컨베이어",  "boolean_facts": ["has_conveyor"]},
    "038": {"label": "압력용기",  "boolean_facts": ["has_pressure_vessel"]},
}

KNOWN_CODES: FrozenSet[str] = frozenset(EQUIPMENT_CODE_MAP)
