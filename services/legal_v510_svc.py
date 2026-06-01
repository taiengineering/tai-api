from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from schemas.legal_engine import DiagnoseStep1Body
from schemas.legal_engine_v510 import DiagnoseStep2Body
from services.legal_format import _classify_rules_db, format_rule_result_db
from services.legal_v510_helpers import (
    _get_construction_summary,
    _input_to_facility_context_v510,
)
from services.legal_rules import (
    _evaluate_condition,
    _evaluate_conditions,
    _resolve_obligation_type,
    _risk_level,
    normalize_sector_db as _normalize_sector_db,
)
from services.input_normalizer import normalize_input
from services.leg_candidate_adapter import to_candidate_contract
from services.legal_diagnosis_rules import fetch_diagnosis_rules
from services.legal_runtime import _create_report_events_from_rules, _save_diagnosis_result


def run_diagnose_step1_v510(supabase, body: DiagnoseStep1Body, allowed_sectors, engine_version: str) -> Dict[str, Any]:
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError("sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.")

    factory_id = (body.factory_id or "").strip()
    if factory_id:
        fac_check = supabase.table("factories").select("id").eq("id", factory_id).limit(1).execute()
        if not fac_check.data:
            raise LookupError("시설을 찾을 수 없습니다.")

    sector_db = _normalize_sector_db(sector_raw)
    all_rules = fetch_diagnosis_rules(supabase, sector_db=sector_db, diagnosis_stage=1, factory_id=factory_id or None)

    inp = dict(body.input or {})
    for k, v in {
        "building_use_type": body.building_use_type, "employee_count": body.employee_count,
        "floor_area": body.floor_area, "worker_count": body.worker_count,
        "total_floor_area": body.total_floor_area, "electric_capacity": body.electric_capacity,
        "floor_count": body.floor_count, "contract_amount_eok": body.contract_amount_eok,
        "ksic_major": body.ksic_major, "facility_type": body.facility_type,
    }.items():
        if v is not None and k not in inp:
            inp[k] = v

    facility_ctx = _input_to_facility_context_v510(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()

    # normalize_input을 통해 condition_code alias 완전 보장
    # (floor_area→building_area, electric_capacity→electrical_capacity_kw+electric_capacity 등)
    eval_ctx = normalize_input(inp)
    eval_ctx["sector"] = sector_raw
    applicable, not_applicable = _evaluate_conditions(eval_ctx, all_rules)

    triggered: Dict[str, List] = {"appointment":[],"inspection":[],"notify":[],"report":[],"action":[],"not_applicable":[]}
    _classify_rules_db(applicable, triggered)
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result_db(r))

    total_applicable = sum(len(triggered[k]) for k in ("appointment","inspection","notify","report","action"))
    appointment_n = len(triggered["appointment"])

    raw_leg = {
        "engine_version": engine_version, "mode": sector_raw, "evaluated_at": evaluated_at,
        "total_rules_checked": len(all_rules), "not_applicable_count": len(not_applicable),
        "applicable_count": total_applicable,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "summary": {
            "total": total_applicable, "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]), "action": len(triggered["action"]),
            "report": len(triggered["report"]), "notify": len(triggered["notify"]),
        },
    }
    if sector_raw == "CONSTRUCTION":
        raw_leg["construction_summary"] = _get_construction_summary(facility_ctx)

    candidate_contract = to_candidate_contract(raw_leg)
    candidate_contract["sector"] = sector_raw
    candidate_contract["step"] = 1
    candidate_contract["factory_id"] = factory_id or None
    if sector_raw == "CONSTRUCTION" and raw_leg.get("construction_summary"):
        candidate_contract["construction_summary"] = raw_leg["construction_summary"]

    result_data = {
        "factory_id": factory_id or None, "sector": sector_raw, "step": 1,
        "engine_version": engine_version, "evaluated_at": evaluated_at,
        "facility_context": facility_ctx, "candidate_contract": candidate_contract,
        "total_rules_checked": len(all_rules), "applicable_count": total_applicable,
    }

    diagnosis_id = None
    if factory_id:
        try:
            supabase.table("factory_diagnosis_results").update({"is_latest": False}).eq("factory_id", factory_id).eq("sector", sector_raw).eq("is_latest", True).execute()
        except Exception:
            pass
        try:
            save_res = supabase.table("factory_diagnosis_results").insert({
                "factory_id": factory_id, "sector": sector_raw, "diagnosis_stage": 1,
                "input_data": inp, "result_data": result_data, "rule_count": total_applicable, "is_latest": True,
            }).execute()
            if save_res.data:
                diagnosis_id = save_res.data[0].get("id")
        except Exception:
            pass
        if diagnosis_id and applicable:
            try:
                rule_rows = [{"diagnosis_id": diagnosis_id, "rule_code": r.get("rule_id") or r.get("rule_code") or "",
                    "rule_name": (r.get("obligation_summary") or r.get("remarks") or "").strip(),
                    "law_name": r.get("law_name") or "", "law_article": r.get("law_article") or "",
                    "obligation": (r.get("obligation_summary") or "").strip(),
                    "obligation_type": _resolve_obligation_type(r), "due_date": None,
                    "status": "PENDING", "form_code": r.get("form_code") or None} for r in applicable]
                for i in range(0, len(rule_rows), 50):
                    supabase.table("diagnosis_rule_results").insert(rule_rows[i:i+50]).execute()
            except Exception:
                pass

    candidate_contract["diagnosis_id"] = diagnosis_id
    return {"status": "success", "data": candidate_contract}


def run_diagnose_step2_v510(supabase, body: DiagnoseStep2Body, engine_version: str) -> Dict[str, Any]:
    factory_id = body.factory_id
    diagnosis_id = body.diagnosis_id
    work_types: List[str] = body.construction_work_types or []
    if not factory_id:
        raise ValueError("factory_id 필수")

    prev = None
    if diagnosis_id:
        try:
            prev = supabase.table("factory_diagnosis_results").select("*").eq("id", diagnosis_id).single().execute().data
        except Exception:
            pass

    sector = (prev or {}).get("sector", "MANUFACTURING")
    input_data = dict((prev or {}).get("input_data") or {})
    input_data["processes"] = body.processes
    input_data["construction_types"] = body.construction_types
    input_data["sector"] = sector

    sector_db = _normalize_sector_db(sector)
    rules = fetch_diagnosis_rules(supabase, sector_db=sector_db, diagnosis_stage_lte=2, work_types=work_types if work_types else None, factory_id=factory_id)
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
    _create_report_events_from_rules(supabase, factory_id, matched)

    prev_codes = {r.get("rule_code") for r in ((prev or {}).get("result_data") or {}).get("rules", [])}
    added = [r for r in matched if (r.get("rule_code") or r.get("rule_id")) not in prev_codes]
    result = diagnosis.get("result_data", {})
    work_type_summary = {}
    if work_types:
        for r in matched:
            wt = r.get("construction_work_type") or "COMMON"
            work_type_summary[wt] = work_type_summary.get(wt, 0) + 1

    return {
        "status": "success", "diagnosis_id": diagnosis.get("id"), "stage": 2,
        "engine_version": engine_version, "sector": sector,
        "rule_count": len(matched), "added_rule_count": len(added),
        "filtered_by_work_types": work_types if work_types else None,
        "work_type_summary": work_type_summary if work_types else None,
        "summary": {"applicable_law_categories": result.get("applicable_law_categories",[]),
            "appointment_required": result.get("appointment_required", False),
            "key_obligations": result.get("key_obligations",[]), "risk_level": result.get("risk_level","LOW")},
        "rules": result.get("rules", []),
        "added_rules": [{"rule_code": r.get("rule_code") or r.get("rule_id"),
            "rule_name": r.get("rule_name") or r.get("remarks",""), "law_article": r.get("law_article",""),
            "work_type": r.get("construction_work_type"), "work_type_label": r.get("construction_work_type_label")} for r in added],
    }
