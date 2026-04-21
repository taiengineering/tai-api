from __future__ import annotations

from typing import Any, Dict

from services.legal_helpers import (
    _to_float,
    _to_int,
    get_construction_amount_threshold,
    get_effective_worker_count,
)


def _truthy(v: Any) -> bool:
    if v is True:
        return True
    if v in (False, None, "", 0):
        return False
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _survey_data_to_context(survey_data: Dict[str, Any]) -> Dict[str, Any]:
    snap = survey_data.get("survey_snapshot")
    if not isinstance(snap, dict):
        snap = {}
    equip_list = snap.get("equip") or []
    workers = _to_int(survey_data.get("employee_count"), snap.get("workers"))
    area = _to_float(survey_data.get("floor_area"), snap.get("area"))
    power_kw = _to_float(survey_data.get("electrical_kw"), snap.get("elecKw"))
    floors = _to_int(snap.get("floors"), survey_data.get("floors_above"))
    gas_kg = _to_float(snap.get("gasKg"), survey_data.get("gas_kg"))
    boiler_th = _to_float(snap.get("boilerTh"), survey_data.get("boiler_th"))
    outsource = _to_int(snap.get("outsource"), survey_data.get("outsource_count"))
    has_chem = "chem" in equip_list or bool(survey_data.get("equip_chemical"))
    has_elev = "elev" in equip_list or bool(survey_data.get("equip_elevator"))
    has_gas = "gas" in equip_list or gas_kg > 0
    has_boiler = "boiler" in equip_list or boiler_th > 0
    btype = str(snap.get("btype") or snap.get("bldgUse") or survey_data.get("building_type") or "").strip()
    ksic = str(survey_data.get("ksic_code") or snap.get("ksic_code") or "").strip()
    is_factory = 1 if (btype.startswith("공장") or btype.startswith("제조") or ksic.upper().startswith("C")) else 0
    cons_eok = _to_float(snap.get("constructionAmt"), survey_data.get("construction_amt"))
    return {
        "employee_count": workers,
        "building_area": area,
        "electrical_capacity_kw": power_kw,
        "floor_count": floors,
        "contractor_count": outsource,
        "transformer_capacity_kva": power_kw,
        "construction_amount": cons_eok * 100_000_000 if cons_eok > 0 else 0,
        "gas_capacity_kg": gas_kg if gas_kg > 0 else (1 if has_gas else 0),
        "gas_capacity_m3": 1 if has_gas else 0,
        "boiler_capacity_kw": boiler_th * 700 if boiler_th > 0 else (1 if has_boiler else 0),
        "boiler_capacity_th": boiler_th,
        "is_hazardous_material": 1 if has_chem else 0,
        "elevator_count": 1 if has_elev else 0,
        "is_factory_registered": is_factory,
        "is_multi_use": 0,
        "annual_energy_toe": 0,
        "building_use_code": btype,
        "ksic_code": ksic,
    }


def _factory_to_context(factory: dict) -> Dict[str, Any]:
    ctx = {
        "employee_count": _to_int(factory.get("employee_count")),
        "building_area": _to_float(factory.get("building_area")),
        "electrical_capacity_kw": _to_float(factory.get("electrical_capacity_kw")),
        "floor_count": _to_int(factory.get("floor_count")),
        "contractor_count": _to_int(factory.get("contractor_count")),
        "transformer_capacity_kva": _to_float(factory.get("transformer_capacity_kva")),
        "gas_capacity_kg": _to_float(factory.get("gas_capacity_kg")),
        "gas_capacity_m3": _to_float(factory.get("gas_capacity_m3")),
        "boiler_capacity_kw": _to_float(factory.get("boiler_capacity_kw")),
        "boiler_capacity_th": _to_float(factory.get("boiler_capacity_th")),
        "elevator_count": _to_int(factory.get("elevator_count")),
        "is_hazardous_material": 1 if factory.get("is_hazardous_material") else 0,
        "is_factory_registered": 1 if factory.get("is_factory_registered") else 0,
        "is_multi_use": 1 if factory.get("is_multi_use") else 0,
        "annual_energy_toe": _to_float(factory.get("annual_energy_toe")),
        "construction_amount": _to_float(factory.get("construction_amount")),
        "building_use_code": str(factory.get("main_purpose_name") or factory.get("building_use_code") or ""),
        "ksic_code": str(factory.get("ksic_code") or ""),
    }
    sec = str(factory.get("sector") or factory.get("site_type") or "").upper()
    if sec == "CONSTRUCTION":
        effective = get_effective_worker_count(factory)
        threshold = get_construction_amount_threshold(factory)
        ctx["worker_count"] = effective
        ctx["subcontractor_worker_count"] = int(factory.get("subcontractor_worker_count") or 0)
        ctx["construction_type"] = factory.get("construction_type") or "건축"
        ctx["safety_manager_threshold"] = threshold
    else:
        ctx["worker_count"] = ctx["employee_count"]
    return ctx


def _input_to_facility_context(sector: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    sec = sector.strip().upper()
    ctx: Dict[str, Any] = {
        "worker_count": 0,
        "total_floor_area": 0.0,
        "electric_capacity": 0.0,
        "building_use_code": "",
        "ksic_code": "",
        "floor_count": 0,
        "construction_amount": 0.0,
        "contract_amount": 0.0,
        "is_hazardous_material": 0,
        "is_multi_use": 0,
        "is_factory_registered": 0,
        "has_high_pressure_gas": 0,
        "has_hazardous_material": 0,
        "has_chemical_substance": 0,
        "has_boiler": 0,
        "has_tunnel_bridge": 0,
        "hospital_beds": 0,
        "student_count": 0,
        "gas_capacity_kg": 0,
        "gas_capacity_m3": 0,
        "boiler_capacity_kw": 0,
        "elevator_count": 0,
        "annual_energy_toe": 0,
    }
    if sec == "BUILDING":
        ctx["building_use_code"] = str(inp.get("building_use") or inp.get("building_use_type") or inp.get("building_use_code") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["building_area"] = ctx["total_floor_area"]
        ctx["floor_count"] = int(inp.get("floor_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["electrical_capacity_kw"] = ctx["electric_capacity"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["gas_capacity_kg"] = float(inp.get("gas_capacity_kg") or 0) or ctx["has_high_pressure_gas"]
        ctx["gas_capacity_m3"] = float(inp.get("gas_capacity_m3") or 0)
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["elevator_count"] = int(inp.get("elevator_count") or 0) or (1 if _truthy(inp.get("has_elevator")) else 0)
        ctx["annual_energy_toe"] = float(inp.get("annual_energy_toe") or 0)
        ctx["has_boiler"] = 1 if _truthy(inp.get("has_boiler")) else 0
        ctx["boiler_capacity_kw"] = float(inp.get("boiler_capacity_kw") or 0) or ctx["has_boiler"]
    elif sec == "MANUFACTURING":
        ctx["ksic_code"] = str(inp.get("ksic_major") or inp.get("ksic_code") or "")
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["electrical_capacity_kw"] = ctx["electric_capacity"]
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["gas_capacity_kg"] = float(inp.get("gas_capacity_kg") or 0) or ctx["has_high_pressure_gas"]
        ctx["gas_capacity_m3"] = float(inp.get("gas_capacity_m3") or 0) or (1 if _truthy(inp.get("has_city_gas")) else 0)
        ctx["has_boiler"] = 1 if _truthy(inp.get("has_boiler")) else 0
        ctx["boiler_capacity_kw"] = float(inp.get("boiler_capacity_kw") or 0) or ctx["has_boiler"]
        ctx["has_chemical_substance"] = 1 if _truthy(inp.get("has_chemical_substance")) else 0
        ctx["elevator_count"] = int(inp.get("elevator_count") or 0) or (1 if _truthy(inp.get("has_elevator")) else 0)
        ctx["annual_energy_toe"] = float(inp.get("annual_energy_toe") or 0)
        ctx["building_area"] = float(inp.get("building_area") or inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["total_floor_area"] = ctx["building_area"]
        ksic = ctx["ksic_code"].upper()
        ctx["is_factory_registered"] = 1 if (_truthy(inp.get("is_factory_registered")) or ksic.startswith("C")) else 0
    elif sec == "CONSTRUCTION":
        eok = float(inp.get("contract_amount_eok") or 0)
        amount = eok * 100_000_000.0
        ctx["construction_amount"] = amount
        ctx["contract_amount"] = amount
        raw_site = str(inp.get("construction_type") or inp.get("site_type") or "건축")
        site_ko = {"BUILDING": "건축", "CIVIL": "토목", "SPECIALTY": "공통"}
        site_type = site_ko.get(raw_site.upper(), raw_site)
        ctx["construction_type"] = site_type
        ctx["building_use_code"] = site_type
        ctx["is_building"] = 1 if site_type in ("건축", "BUILDING") else 0
        ctx["is_civil"] = 1 if site_type in ("토목", "CIVIL") else 0
        direct = int(inp.get("direct_workers") or inp.get("worker_count") or inp.get("employee_count") or 0)
        subcon = int(inp.get("subcon_workers") or inp.get("subcontractor_worker_count") or 0)
        ctx["worker_count"] = direct + subcon
        ctx["employee_count"] = direct + subcon
        ctx["direct_workers"] = direct
        ctx["subcon_workers"] = subcon
        ctx["subcontractor_worker_count"] = subcon
        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0
        ctx["has_blasting"] = 1 if _truthy(inp.get("has_blasting")) else 0
        ctx["has_crane"] = 1 if _truthy(inp.get("has_crane")) else 0
        ctx["has_high_work"] = 1 if _truthy(inp.get("has_high_work")) else 0
        elec_kw = float(inp.get("electrical_capacity_kw") or inp.get("electric_capacity") or 0)
        ctx["electric_capacity"] = elec_kw
        ctx["electrical_capacity_kw"] = elec_kw
        ctx["transformer_capacity_kva"] = elec_kw
        ctx["safety_manager_threshold"] = get_construction_amount_threshold({"construction_type": site_type})
    elif sec in ("SPECIAL_FACILITY", "SPECIAL"):
        ctx["building_use_code"] = str(inp.get("facility_type") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["hospital_beds"] = int(inp.get("hospital_beds") or 0)
        ctx["student_count"] = int(inp.get("student_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["building_area"] = ctx["total_floor_area"]
    return ctx
