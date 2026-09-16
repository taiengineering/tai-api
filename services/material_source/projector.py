"""Common Material Source projector.

One projector. Family-specific chemical projectors are forbidden.
Output is source classification contract only. No LEG booleans.
missing != false (omit, do not emit false).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from services.material_source.store import catalog_index


WORK_FAMILY_FACTS = (
    "uses_forklift",
    "performs_work_with_fall_risk",
    "performs_work_on_roof",
    "performs_spray_work_with_flammable_liquid_in_enclosed_space",
    "performs_powered_machinery_maintenance_or_servicing",
    "performs_electrical_work",
    "performs_deenergized_circuit_electrical_work",
    "performs_electrical_work_near_deenergized_circuit",
    "performs_energized_circuit_electrical_work",
    "has_welding",
    "uses_gases_for_welding_cutting_heating",
    "has_confined_space",
    "performs_confined_space_work",
)


def _active(row: Mapping[str, Any]) -> bool:
    return row.get("is_active") is True


def project_material_row(
    row: Mapping[str, Any],
    *,
    classifications_by_key: Optional[Mapping[str, List[Mapping[str, Any]]]] = None,
    authority_dir=None,
) -> List[Dict[str, str]]:
    """Project one factory_materials row to source classifications.

    Inactive rows emit nothing. Free-text without material_master_key emits
    nothing (ABSENT, not false). Unknown keys emit nothing.
    """
    if not _active(row):
        return []
    key = row.get("material_master_key")
    if not isinstance(key, str) or not key.strip():
        return []
    if classifications_by_key is None:
        classifications_by_key = catalog_index(authority_dir)["classifications_by_key"]
    hits = classifications_by_key.get(key) or []
    out: List[Dict[str, str]] = []
    for item in hits:
        if item.get("active") is False:
            continue
        out.append(
            {
                "material_key": key,
                "classification_code": item["classification_code"],
                "source_ref": item["source_ref"],
            }
        )
    out.sort(key=lambda r: (r["material_key"], r["classification_code"]))
    return out


def project_factory_material_rows(
    rows: Optional[Iterable[Mapping[str, Any]]],
    *,
    authority_dir=None,
) -> Dict[str, Any]:
    """Union of source classifications. Does not emit LEG booleans or false."""
    idx = catalog_index(authority_dir)
    items: List[Dict[str, str]] = []
    seen = set()
    for row in rows or ():
        for item in project_material_row(
            row, classifications_by_key=idx["classifications_by_key"]
        ):
            marker = (item["material_key"], item["classification_code"])
            if marker in seen:
                continue
            seen.add(marker)
            items.append(item)
    items.sort(key=lambda r: (r["material_key"], r["classification_code"]))
    return {"material_classifications": items}
