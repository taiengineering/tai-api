"""
Nexas / anonymous diagnosis — Runtime Compiler step1 실행.

legal_engine_svc.run_diagnose_step1(legacy) 대신
runtime_metadata_resolution → v1 projection → build_step1_result_data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, FrozenSet

from schemas.legal_engine import DiagnoseStep1Body
from services.legal_context import _input_to_facility_context
from services.legal_engine_svc import evaluate_facility_conditions_db
from services.legal_rules import get_construction_summary
from services.legal_format import _classify_rules_db, format_rule_result_db
from services.legal_helpers import get_sector_groups
from services.legal_rules import normalize_sector_db, risk_level
from services.legal_runtime_fetch import fetch_runtime_rules_as_v1
from services.legal_step1_builder import build_step1_result_data

RUNTIME_ENGINE_VERSION = "v3.0-runtime-compiler"


def run_diagnose_step1_runtime(
    supabase,
    body: DiagnoseStep1Body,
    allowed_sectors: FrozenSet[str],
) -> Dict[str, Any]:
    """Runtime compiler 기반 step1 — legacy master_building_legal_rules 미사용."""
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError(
            "sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다."
        )

    sector_db = normalize_sector_db(sector_raw)
    sector_groups = get_sector_groups(sector_db)

    all_rules = fetch_runtime_rules_as_v1(
        supabase,
        sector_db=sector_db,
        factory_id=(body.factory_id or "").strip() or None,
        diagnosis_stage=1,
    )

    inp = dict(body.input or {})
    flat_fields = {
        "building_use_type": body.building_use_type,
        "employee_count": body.employee_count,
        "floor_area": body.floor_area,
        "worker_count": body.worker_count,
        "total_floor_area": body.total_floor_area,
        "electric_capacity": body.electric_capacity,
        "floor_count": body.floor_count,
        "contract_amount_eok": body.contract_amount_eok,
        "ksic_major": body.ksic_major,
        "facility_type": body.facility_type,
        "elevator_count": body.elevator_count,
        "gas_capacity_kg": body.gas_capacity_kg,
        "gas_capacity_m3": body.gas_capacity_m3,
        "boiler_capacity_kw": body.boiler_capacity_kw,
        "annual_energy_toe": body.annual_energy_toe,
        "has_high_pressure_gas": body.has_high_pressure_gas,
        "has_boiler": body.has_boiler,
        "has_hazardous_material": body.has_hazardous_material,
        "has_chemical_substance": body.has_chemical_substance,
        "construction_type": body.construction_type,
        "direct_workers": body.direct_workers,
        "subcon_workers": body.subcon_workers,
        "electrical_capacity_kw": body.electrical_capacity_kw,
        "has_tunnel_bridge": body.has_tunnel_bridge,
        "has_blasting": body.has_blasting,
        "has_crane": body.has_crane,
        "has_high_work": body.has_high_work,
    }
    for k, v in flat_fields.items():
        if v is not None and k not in inp:
            inp[k] = v

    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()
    applicable, not_applicable = evaluate_facility_conditions_db(
        facility_ctx, all_rules, sector_raw
    )

    result_data = build_step1_result_data(
        sector_raw,
        sector_groups,
        RUNTIME_ENGINE_VERSION,
        evaluated_at,
        facility_ctx,
        applicable,
        not_applicable,
        _classify_rules_db,
        format_rule_result_db,
        risk_level,
        get_construction_summary,
        supabase=supabase,
    )
    result_data["rule_version"] = "runtime_metadata_resolution:v1"
    return result_data
