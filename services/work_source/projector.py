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
        if _truthy(attrs.get("edge_or_opening_fall_risk")):
            out["has_work_platform_or_path_edge_or_opening_fall_risk"] = True
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
        out: Dict[str, bool] = {}
        powered = subtype == "POWERED_MACHINERY" or _truthy(attrs.get("powered_machinery"))
        if powered:
            out["performs_powered_machinery_maintenance_or_servicing"] = True
        equipment_type = attrs.get("equipment_type")
        # PR-W1-D FC-018: 공기정화설비 청소·개보수.
        if equipment_type == "AIR_PURIFICATION":
            out["performs_air_purification_equipment_maintenance_or_cleaning"] = True
        # PR-W1-D FC-019C: 열차 정기적 점검·정비. periodic 누락/false → 미방출(fail-closed).
        if equipment_type == "TRAIN" and _truthy(attrs.get("periodic")):
            out["performs_periodic_train_maintenance_or_inspection"] = True
        # PR-W1-D FC-019D: 원심기·분쇄기 정비·청소·검사.
        if equipment_type in ("CENTRIFUGE", "CRUSHER"):
            out["performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection"] = True
        return out

    if work_type == "EXCAVATION":
        if _truthy(attrs.get("uses_machinery")):
            return {"excavation_machinery_in_use": True}
        return {}

    if work_type == "ASBESTOS_WASTE_DUST_PROCESSING":
        return {"has_asbestos_waste_dust_processing_work": True}

    if work_type == "ELECTRICAL":
        if subtype == "DEENERGIZED":
            return {"performs_deenergized_circuit_electrical_work": True}
        if subtype == "NEAR_DEENERGIZED":
            return {"performs_electrical_work_near_deenergized_circuit": True}
        if subtype == "NEAR_ENERGIZED":
            return {"performs_electrical_work_near_energized_circuit": True}
        if subtype == "ENERGIZED":
            return {"performs_energized_circuit_electrical_work": True}
        if subtype in (None, ""):
            return {"performs_electrical_work": True}
        return {}

    if work_type == "SCAFFOLD":
        # WO-E2E-OBJ01-SEM002-ART57A-CONSUMER-INPUT-WIRING-001 (Art.57 첫 문장) +
        # WO-E2E-OBJ01-SEM002-ART57B-FASTLANE-IMPLEMENT-001    (Art.57 제2항) +
        # WO-E2E-OBJ03-L3-55-SEMANTIC-INPUT-INTEGRATION-001 PATCH-1 Phase 3
        #   (DEEPEN G002/G004/G011: FC-015A scaffold_kind exact subtype facts).
        # Each row = one scaffold + one activity; per-row evaluation preserves
        # same-entity binding. missing != false — omit absent keys.
        kind = attrs.get("scaffold_kind")
        out: Dict[str, bool] = {}

        # --- Per-kind structural facts (independent of activity subtype) ---
        # WO-E2E-OBJ03-L3-55-SEMANTIC-INPUT-INTEGRATION-001 PATCH-1 Phase 3:
        # DEEPEN FC-015A exact subtype facts. Only emitted for NEW DEEPEN codes;
        # legacy STEEL_PIPE / LOG / OTHER preserve prior behavior (no new fact).
        # WO-E2E-OBJ04-L3-COVERAGE-ACTIVATION-WAVE1-DESIGN-001 PR-W1-A:
        # Remaining 7 DEEPEN subtypes added. missing != false — omit absent keys.
        if kind == "STEEL_PIPE_SCAFFOLD":
            out["scaffold_kind_is_steel_pipe_scaffold"] = True
        elif kind == "STEEL_FRAME_SCAFFOLD":
            out["scaffold_kind_is_steel_frame_scaffold"] = True
        elif kind == "SUSPENDED_GONDOLA_SCAFFOLD":
            out["scaffold_kind_is_suspended_gondola_scaffold"] = True
        elif kind == "HANGING_SCAFFOLD":
            out["scaffold_kind_is_hanging_scaffold"] = True
        elif kind == "HORSE_TRESTLE_SCAFFOLD":
            out["scaffold_kind_is_horse_trestle_scaffold"] = True
        elif kind == "MOBILE_SCAFFOLD":
            out["scaffold_kind_is_mobile_scaffold"] = True
        elif kind == "SYSTEM_SCAFFOLD":
            out["scaffold_kind_is_system_scaffold"] = True
        elif kind == "LEANING_SCAFFOLD":
            out["scaffold_kind_is_leaning_scaffold"] = True
        elif kind == "HOOK_SCAFFOLD":
            out["scaffold_kind_is_hook_scaffold"] = True
        elif kind == "WORK_CHAIR_SUSPENDED_SCAFFOLD":
            out["scaffold_kind_is_work_chair_suspended_scaffold"] = True

        # --- Activity-dependent facts ---
        _activity_subtypes = ("ASSEMBLY", "DISMANTLE", "MODIFICATION", "USE_WITH_WORKERS", "INSTALLATION")
        if subtype not in _activity_subtypes:
            return out  # return any per-kind facts; no activity facts

        # --- Art.57 첫 문장 (Art.57-A): ASSEMBLY/DISMANTLE/MODIFICATION only ---
        if subtype in ("ASSEMBLY", "DISMANTLE", "MODIFICATION"):
            is_dalbi = _truthy(attrs.get("is_dalbi"))
            raw_h = attrs.get("height_m")
            # numeric fail-closed: bool excluded, negative/None invalid.
            height_ge5 = (
                isinstance(raw_h, (int, float))
                and not isinstance(raw_h, bool)
                and raw_h >= 5
            )
            if is_dalbi or height_ge5:
                out["performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold"] = True

        # --- Art.57 제2항 (Art.57-B): ASSEMBLY only ---
        # Legacy STEEL_PIPE + LOG + new STEEL_PIPE_SCAFFOLD all qualify.
        if subtype == "ASSEMBLY":
            if kind in ("STEEL_PIPE", "STEEL_PIPE_SCAFFOLD", "LOG"):
                out["performs_steel_pipe_or_log_scaffold_assembly"] = True

        # --- Same-row composite facts (PR-W1-A CORRECTION-1 + SEMANTIC CORRECTION-2) ---
        # INSTALLATION composites (FC-015B=INSTALLATION: Art.63 달비계, Art.66의2 걸침비계).
        if subtype == "INSTALLATION":
            if kind == "SUSPENDED_GONDOLA_SCAFFOLD":
                out["performs_suspended_gondola_scaffold_installation"] = True
            elif kind == "WORK_CHAIR_SUSPENDED_SCAFFOLD":
                out["performs_work_chair_suspended_scaffold_installation"] = True
            elif kind == "HOOK_SCAFFOLD":
                out["performs_hook_scaffold_installation"] = True

        # ASSEMBLY-only composites (Art.59/62/69/70 DEEPEN FC-015A+FC-015B expressions).
        if subtype == "ASSEMBLY":
            if kind == "SYSTEM_SCAFFOLD":
                out["performs_system_scaffold_assembly"] = True
            elif kind == "STEEL_PIPE_SCAFFOLD":
                out["performs_steel_pipe_scaffold_assembly"] = True

        # ASSEMBLY or USE_WITH_WORKERS composites.
        if subtype in ("ASSEMBLY", "USE_WITH_WORKERS"):
            if kind == "HANGING_SCAFFOLD":
                out["performs_hanging_scaffold_assembly_or_use_with_workers"] = True
            elif kind == "STEEL_FRAME_SCAFFOLD":
                out["performs_steel_frame_scaffold_assembly_or_use_with_workers"] = True
            elif kind == "MOBILE_SCAFFOLD":
                out["performs_mobile_scaffold_assembly_or_use_with_workers"] = True
            elif kind == "HORSE_TRESTLE_SCAFFOLD":
                out["performs_horse_trestle_scaffold_assembly_or_use_with_workers"] = True

        return out

    return {}


def project_work_rows(rows: Optional[Iterable[Mapping[str, Any]]]) -> Dict[str, bool]:
    """Union of projected facts. True stays True. Missing stays absent."""
    out: Dict[str, bool] = {}
    for row in rows or ():
        for key, val in project_work_row(row).items():
            if val is True:
                out[key] = True
    return out
