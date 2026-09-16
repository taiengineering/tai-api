"""Common Work → Canonical Fact Projector.

One registry-driven projector. Family if/else files are forbidden.
SOURCE DATA != LEG CANONICAL FACT. missing != false (omit, do not emit false).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional


def _attrs(row: Mapping[str, Any]) -> Dict[str, Any]:
    raw = row.get("attributes") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _truthy(val: Any) -> bool:
    return val is True


def _active(row: Mapping[str, Any]) -> bool:
    return row.get("active") is True


def project_work_row(row: Mapping[str, Any]) -> Dict[str, bool]:
    """Project one structured work row to exact approved canonical facts.

    Inactive rows emit nothing. Partial painting conditions emit nothing
    (missing, not false). One family never expands into another.
    """
    if not _active(row):
        return {}
    work_type = row.get("work_type")
    if not isinstance(work_type, str) or not work_type:
        return {}
    subtype = row.get("work_subtype")
    attrs = _attrs(row)

    if work_type == "FORKLIFT":
        return {"uses_forklift": True}

    if work_type == "HIGH_PLACE":
        out: Dict[str, bool] = {}
        if _truthy(attrs.get("fall_risk")):
            out["performs_work_with_fall_risk"] = True
        roof = subtype == "ROOF" or _truthy(attrs.get("roof"))
        if roof:
            out["performs_work_on_roof"] = True
        # generic HIGH_PLACE does not produce has_high_place_work (MEWP).
        return out

    if work_type == "PAINTING":
        if (
            _truthy(attrs.get("spray"))
            and _truthy(attrs.get("flammable_liquid"))
            and _truthy(attrs.get("enclosed_space"))
        ):
            return {
                "performs_spray_work_with_flammable_liquid_in_enclosed_space": True
            }
        return {}

    if work_type == "MAINTENANCE":
        powered = subtype == "POWERED_MACHINERY" or _truthy(
            attrs.get("powered_machinery")
        )
        if powered:
            return {"performs_powered_machinery_maintenance_or_servicing": True}
        return {}

    if work_type == "ELECTRICAL":
        if subtype == "DEENERGIZED":
            return {"performs_deenergized_circuit_electrical_work": True}
        if subtype == "NEAR_DEENERGIZED":
            return {"performs_electrical_work_near_deenergized_circuit": True}
        if subtype == "ENERGIZED":
            return {"performs_energized_circuit_electrical_work": True}
        if subtype in (None, ""):
            return {"performs_electrical_work": True}
        return {}

    return {}


def project_work_rows(rows: Optional[Iterable[Mapping[str, Any]]]) -> Dict[str, bool]:
    """Union of projected facts. True stays True. Missing stays absent."""
    out: Dict[str, bool] = {}
    for row in rows or ():
        for key, val in project_work_row(row).items():
            if val is True:
                out[key] = True
    return out
