"""AUTO-SRC-02B: Deterministic projection selector for AUTO_SOURCE channel.

Determines which projection_type(s) an inspection_set maps to.
Three rules, evaluated in priority order:

  RULE 1 (explicit binding): inspection_set_projection_binding rows
          → returned as-is; can produce multiple projections per source
  RULE 2 (asset-derived EQUIP): inspection has asset_id AND equipment_type_code
          resolves to a RESOLVED detail → yields EQUIP projection
  RULE 3 (generic INSP fallback): any completed inspection with no specialized
          binding and no EQUIP resolution → yields INSP projection

Fail-closed: if RULE 1 = empty AND RULE 2 = UNRESOLVED AND no fallback applies,
returns an empty list (inspection stays invisible in AUTO document library).

ASBESTOS/GUARD/SCAFFOLD: explicit workflow binding only (RULE 1); never
derived from numeric code auto-resolution (not reachable via RULE 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from services.document_engine.equipment_projection_resolver import (
    resolve_equipment_detail,
)


@dataclass(frozen=True)
class ProjectionDecision:
    projection_type: str
    projection_detail: Optional[str]
    rule: str  # "RULE_1_EXPLICIT", "RULE_2_ASSET_EQUIP", "RULE_3_INSP_FALLBACK"


def select_projections(
    *,
    explicit_bindings: List[dict],
    asset_id: Optional[str],
    equipment_type_code: Optional[str],
    is_completed: bool,
) -> List[ProjectionDecision]:
    """Return the ordered list of projection decisions for one inspection_set.

    Parameters
    ----------
    explicit_bindings:
        Rows from inspection_set_projection_binding (dicts with keys
        projection_type, projection_detail).
    asset_id:
        safety_inspections.asset_id (may be None for non-equipment inspections).
    equipment_type_code:
        equipment_assets.equipment_type_code for the linked asset (None if no asset).
    is_completed:
        True if the inspection record has status_code = 'COMPLETED'.
    """
    results: List[ProjectionDecision] = []

    # RULE 1: explicit binding rows win and are returned verbatim
    for row in explicit_bindings:
        results.append(
            ProjectionDecision(
                projection_type=row["projection_type"],
                projection_detail=row.get("projection_detail"),
                rule="RULE_1_EXPLICIT",
            )
        )

    if results:
        return results

    # RULE 2: asset-derived EQUIP (only when asset_id is populated)
    if asset_id is not None:
        detail = resolve_equipment_detail(equipment_type_code)
        if detail is not None:
            return [
                ProjectionDecision(
                    projection_type="EQUIP",
                    projection_detail=detail,
                    rule="RULE_2_ASSET_EQUIP",
                )
            ]
        # UNRESOLVED equipment code (015/035/036/037/040 or unknown) — fail-closed
        return []

    # RULE 3: generic INSP fallback (completed inspections with no asset link)
    if is_completed:
        return [
            ProjectionDecision(
                projection_type="INSP",
                projection_detail=None,
                rule="RULE_3_INSP_FALLBACK",
            )
        ]

    return []
