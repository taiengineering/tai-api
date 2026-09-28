"""Equipment Source → canonical boolean facts projector.

Shared by persistent (equipment_assets) and transient (equipment_list) paths.
SOURCE DATA != CANONICAL FACT. missing != false (omit, do not emit false).

is_operating explicitly False → skip row.
is_operating absent or True → proceed.
equipment_type_code absent or unknown → missing (not false).
Numeric attributes in row are captured for replay only; no numeric projection (HOLD).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from services.equipment_source.canonicalizer import normalize_equipment_type_code
from services.equipment_source.registry import EQUIPMENT_CODE_MAP


def project_equipment_row(row: Mapping[str, Any]) -> Dict[str, bool]:
    """Project one equipment row to canonical boolean facts.

    Skips rows where is_operating is explicitly False.
    Returns {} for unknown or absent equipment_type_code (missing, not false).
    Uppercase aliases are normalized to numeric before registry lookup.
    """
    if row.get("is_operating") is False:
        return {}
    code = row.get("equipment_type_code")
    if not isinstance(code, str) or not code.strip():
        return {}
    code = normalize_equipment_type_code(code)
    spec = EQUIPMENT_CODE_MAP.get(code)
    if spec is None:
        return {}
    return {fact: True for fact in spec.get("boolean_facts", [])}


def project_equipment_rows(rows: Optional[Iterable[Mapping[str, Any]]]) -> Dict[str, bool]:
    """Union of projected facts across all rows. True stays True. Missing stays absent."""
    out: Dict[str, bool] = {}
    for row in rows or ():
        for k, v in project_equipment_row(row).items():
            if v is True:
                out[k] = True
    return out
