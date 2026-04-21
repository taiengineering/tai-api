from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.legal_format import _classify_rules_db, build_result, format_rule_result_db
from services.legal_context import _input_to_facility_context
from services.legal_helpers import get_sector_groups
from services.legal_runtime import (
    _create_report_events_from_rules,
    _evaluate_equipment_conditions,
    _evaluate_process_conditions,
    _save_diagnosis_result,
    run_apply_engine_runtime,
    run_apply_quote_runtime,
)
from services.legal_step1_builder import build_step1_result_data
from services.legal_rules import (
    _determine_risk_level,
    _evaluate_condition,
    _evaluate_conditions,
    finalize_step1_storage,
    evaluate_facility_conditions_db,
    get_construction_summary,
    normalize_sector_db,
    risk_level,
)

ENGINE_VERSION = "5.7.0"
ALLOWED_DIAGNOSE_SECTORS = frozenset({"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"})


def run_diagnose_step2(supabase, body, engine_version: str) -> Dict[str, Any]:
    factory_id = body.factory_id
    diagnosis_id = body.diagnosis_id
    work_types: List[str] = list(body.construction_work_types or [])
    work_type_codes_direct: List[str] = body.work_type_codes or []
    kcsc_process_ids: List[str] = body.kcsc_process_ids or []
    prev: Optional[Dict[str, Any]] = None
    if diagnosis_id:
        try:
            prev_res = supabase.table("factory_diagnosis_results").select("*").eq("id", diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass
    sector = (prev or {}).get("sector", body.sector or "CONSTRUCTION")
    input_data = dict((prev or {}).get("input_data") or {})
    input_data.update({"processes": body.processes or [], "construction_types": body.construction_types or [], "sector": sector})
    kcsc_processes: List[Dict[str, Any]] = []
    kcsc_process_summary: List[Dict[str, Any]] = []
    if kcsc_process_ids:
        try:
            kcsc_res = (
                supabase.table("kcsc_process_master")
                .select("id, process_name, work_type_code, work_type_label, risk_level")
                .in_("id", kcsc_process_ids)
                .eq("is_active", True)
                .execute()
            )
            kcsc_processes = kcsc_res.data or []
        except Exception as e:
            print(f"[STEP2] kcsc_process_master 조회 실패: {e}")
        work_types = list(set(work_types + [p["work_type_code"] for p in kcsc_processes if p.get("work_type_code")]))
        input_data["kcsc_process_ids"] = kcsc_process_ids
        for p in kcsc_processes:
            kcsc_process_summary.append(
                {
                    "process_id": p["id"],
                    "process_name": p.get("process_name", ""),
                    "work_type_code": p.get("work_type_code"),
                    "work_type_label": p.get("work_type_label"),
                    "risk_level": p.get("risk_level", "MEDIUM"),
                    "has_legal_rules": p.get("work_type_code") is not None,
                }
            )
    if work_type_codes_direct:
        work_types = list(set(work_types + work_type_codes_direct))
    sector_groups = get_sector_groups(sector)
    q = supabase.table("master_building_legal_rules").select("*").in_("sector", sector_groups).lte("diagnosis_stage", 2).eq("is_active", True)
    if sector == "CONSTRUCTION" and work_types:
        q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({','.join(work_types)})")
    rules = q.execute().data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    diagnosis = {}
    if factory_id:
        diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
        _create_report_events_from_rules(supabase, factory_id, matched)
    prev_codes = {r.get("rule_code") for r in (prev or {}).get("result_data", {}).get("rules", []) if prev} if prev else set()
    added = [r for r in matched if (r.get("rule_code") or r.get("rule_id")) not in prev_codes]
    result = diagnosis.get("result_data", {})
    return {
        "status": "success",
        "diagnosis_id": diagnosis.get("id"),
        "stage": 2,
        "engine_version": engine_version,
        "sector": sector,
        "sector_groups": sector_groups,
        "rule_count": len(matched),
        "added_rule_count": len(added),
        "kcsc_process_summary": kcsc_process_summary,
        "summary": {
            "applicable_law_categories": result.get("applicable_law_categories", []),
            "appointment_required": result.get("appointment_required", False),
            "key_obligations": result.get("key_obligations", []),
            "risk_level": result.get("risk_level", "LOW"),
        },
        "rules": result.get("rules", []),
        "added_rules": [
            {
                "rule_code": r.get("rule_code") or r.get("rule_id"),
                "rule_name": r.get("remarks") or r.get("rule_name") or r.get("obligation_summary", ""),
                "law_article": r.get("law_article", ""),
            }
            for r in added
        ],
    }


def run_diagnose_step3(supabase, body, engine_version: str) -> Dict[str, Any]:
    factory_id = body.factory_id
    diagnosis_id = body.diagnosis_id
    equipments: List[Dict[str, Any]] = list(body.equipments or [])
    kcsc_work_ids: List[str] = list(body.kcsc_work_ids or [])
    prev: Optional[Dict[str, Any]] = None
    if diagnosis_id:
        try:
            prev_res = supabase.table("factory_diagnosis_results").select("*").eq("id", diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass
    sector = (prev or {}).get("sector", "MANUFACTURING")
    input_data = dict((prev or {}).get("input_data") or {})
    input_data["sector"] = sector
    extra_equipment_codes: List[str] = []
    kcsc_work_summary: List[Dict[str, Any]] = []
    if kcsc_work_ids:
        try:
            rows = (
                supabase.table("kcsc_work_master")
                .select("id, title, is_hazardous, hazard_type, equipment_type_codes, work_type_code")
                .in_("id", kcsc_work_ids)
                .execute()
                .data
                or []
            )
            for w in rows:
                eq_codes = w.get("equipment_type_codes") or []
                extra_equipment_codes.extend(eq_codes)
                kcsc_work_summary.append(
                    {
                        "work_id": w["id"],
                        "title": w.get("title", ""),
                        "is_hazardous": w.get("is_hazardous", False),
                        "equipment_codes": eq_codes,
                    }
                )
            extra_equipment_codes = list(set(extra_equipment_codes))
        except Exception as e:
            print(f"[STEP3] kcsc_work_master 조회 실패: {e}")
    for code in extra_equipment_codes:
        if not any(e.get("equipment_code") == code for e in equipments):
            equipments.append({"equipment_code": code})
    input_data["equipments"] = equipments
    sector_groups_s3 = get_sector_groups(sector)
    q = supabase.table("master_building_legal_rules").select("*").in_("sector", sector_groups_s3).eq("diagnosis_stage", 3).eq("is_active", True)
    if sector == "CONSTRUCTION" and extra_equipment_codes:
        q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({','.join(extra_equipment_codes)})")
    rules = q.execute().data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 3, input_data, matched)
    return {
        "status": "success",
        "diagnosis_id": diagnosis.get("id"),
        "stage": 3,
        "sector": sector,
        "engine_version": engine_version,
        "rule_count": len(matched),
        "kcsc_work_summary": kcsc_work_summary,
    }


def run_diagnose_step1(
    supabase,
    body,
    engine_version: str,
    allowed_sectors,
    normalize_sector_fn,
    input_to_context_fn,
    evaluate_facility_fn,
    classify_rules_db_fn,
    format_rule_result_db_fn,
    risk_level_fn,
    construction_summary_fn,
):
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError("sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.")
    factory_id = (body.factory_id or "").strip()
    fac_company_id = None
    if factory_id:
        fac_check = supabase.table("factories").select("id, company_id").eq("id", factory_id).limit(1).execute()
        if not fac_check.data:
            raise LookupError("시설을 찾을 수 없습니다.")
        fac_company_id = fac_check.data[0].get("company_id")

    sector_groups = get_sector_groups(normalize_sector_fn(sector_raw))
    all_rules = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .in_("sector", sector_groups)
        .eq("diagnosis_stage", 1)
        .execute()
        .data
        or []
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

    from datetime import datetime

    facility_ctx = input_to_context_fn(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()
    applicable, not_applicable = evaluate_facility_fn(facility_ctx, all_rules, sector_raw)

    result_data = build_step1_result_data(
        sector_raw,
        sector_groups,
        engine_version,
        evaluated_at,
        facility_ctx,
        applicable,
        not_applicable,
        classify_rules_db_fn,
        format_rule_result_db_fn,
        risk_level_fn,
        construction_summary_fn,
    )
    result_data["factory_id"] = factory_id or None
    return {"result_data": result_data, "factory_id": factory_id, "sector_raw": sector_raw, "inp": inp, "applicable": applicable, "fac_company_id": fac_company_id}


def finalize_diagnose_step1(supabase, diag: Dict[str, Any]):
    return finalize_step1_storage(supabase, diag)


async def run_apply_engine(
    supabase,
    factory_id: str,
    mode: str,
    engine_version: str,
    now_iso_fn,
    factory_to_context_fn,
    get_effective_worker_count_fn,
    get_construction_amount_threshold_fn,
):
    return await run_apply_engine_runtime(
        supabase,
        factory_id,
        mode,
        engine_version,
        now_iso_fn,
        factory_to_context_fn,
        get_effective_worker_count_fn,
        get_construction_amount_threshold_fn,
    )


def run_apply_quote(supabase, quote_id: str, engine_version: str, parse_survey_data_fn, survey_to_context_fn, now_iso_fn):
    return run_apply_quote_runtime(supabase, quote_id, engine_version, parse_survey_data_fn, survey_to_context_fn, now_iso_fn)


def _evaluate_facility_conditions_db(facility_ctx: Dict[str, Any], rules: List[Dict[str, Any]], sector: str = "") -> tuple:
    return evaluate_facility_conditions_db(facility_ctx, rules, sector)


def run_get_legal_result_from_quote(supabase, quote_id: str) -> Dict[str, Any]:
    res = supabase.table("quotes").select("id, quote_no, legal_result_json, legal_evaluated_at, legal_applicable_count").eq("id", quote_id).single().execute()
    if not res.data:
        raise LookupError("견적을 찾을 수 없습니다.")
    if not res.data.get("legal_result_json"):
        raise LookupError("판정 결과 없음.")
    return {
        "status": "success",
        "data": {
            "quote_id": quote_id,
            "quote_no": res.data.get("quote_no"),
            "legal_evaluated_at": res.data.get("legal_evaluated_at"),
            "legal_applicable_count": res.data.get("legal_applicable_count"),
            "result": res.data.get("legal_result_json"),
        },
    }


def run_get_legal_result(supabase, factory_id: str, mode: str = "all") -> Dict[str, Any]:
    try:
        fac = supabase.table("factories").select("legal_result_json, last_diagnosis_at, legal_applicable_count, diagnosis_status").eq("id", factory_id).single().execute()
        if fac.data and fac.data.get("legal_result_json"):
            rj = fac.data["legal_result_json"]
            rj.pop("not_applicable", None)
            return {
                "status": "success",
                "data": {
                    **rj,
                    "last_diagnosis_at": fac.data.get("last_diagnosis_at"),
                    "legal_applicable_count": fac.data.get("legal_applicable_count"),
                    "diagnosis_status": fac.data.get("diagnosis_status"),
                },
            }
    except Exception:
        pass
    try:
        res = supabase.table("legal_applications").select("*").eq("factory_id", factory_id).eq("mode", mode).order("evaluated_at", desc=True).limit(1).execute()
        if res.data:
            rj = res.data[0].get("result_json", {})
            rj.pop("not_applicable", None)
            return {"status": "success", "data": rj}
    except Exception:
        pass
    raise LookupError("판정 결과 없음.")


def run_get_legal_summary(supabase, factory_id: str) -> Dict[str, Any]:
    try:
        res = supabase.table("legal_applications").select("mode, evaluated_at, result_json").eq("factory_id", factory_id).order("evaluated_at", desc=True).limit(4).execute()
    except Exception:
        return {"status": "success", "data": {"factory_id": factory_id, "results": []}}
    results = [
        {
            "mode": row.get("mode", "all"),
            "evaluated_at": row.get("evaluated_at"),
            "summary": row.get("result_json", {}).get("summary", {}),
            "engine_version": row.get("result_json", {}).get("engine_version", ""),
        }
        for row in (res.data or [])
    ]
    return {"status": "success", "data": {"factory_id": factory_id, "results": results}}


def run_create_inspection_sets_from_legal(supabase, factory_id: str, cycle_code_map: Dict[str, Any]) -> Dict[str, Any]:
    fac = supabase.table("factories").select("id, company_id, legal_result_json").eq("id", factory_id).single().execute()
    if not fac.data:
        raise LookupError("시설을 찾을 수 없습니다.")
    company_id = fac.data.get("company_id")
    result_json = fac.data.get("legal_result_json")
    inspection_rules: List[Dict[str, Any]] = result_json.get("inspection_required", []) if result_json else []
    if not inspection_rules:
        return {"status": "success", "message": "생성할 점검 항목이 없습니다.", "data": {"created": 0}}
    existing_res = supabase.table("inspection_sets").select("legal_rule_id").eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").eq("is_active", True).execute()
    existing_rule_ids = {r["legal_rule_id"] for r in (existing_res.data or []) if r.get("legal_rule_id")}
    insert_rows = []
    for rule in inspection_rules:
        rule_id = rule.get("rule_id", "")
        if rule_id in existing_rule_ids:
            continue
        law_name = rule.get("law_name", "")
        cycle_code = rule.get("inspection_cycle_code") or ""
        cycle_unit, cycle_value = cycle_code_map.get(cycle_code, ("year", 1))
        schedule_type = rule.get("schedule_type") or "PERIODIC"
        unit_label = "년" if cycle_unit == "year" else "개월"
        insert_rows.append(
            {
                "company_id": company_id,
                "factory_id": factory_id,
                "inspection_set_name": f"{law_name} 점검",
                "inspection_set_code": rule_id,
                "legal_rule_id": rule_id,
                "law_name": law_name,
                "law_article": rule.get("law_article", ""),
                "cycle_unit": cycle_unit,
                "cycle_value": cycle_value,
                "cycle_base_type": "LAST_INSPECTION",
                "cycle_base_guide": (f"마지막 점검일로부터 {cycle_value}{unit_label}마다" if schedule_type == "PERIODIC" else f"작업({rule.get('construction_work_type','')}) 시작 전 실시"),
                "description": rule.get("description", ""),
                "source": "LEGAL_ENGINE",
                "is_active": True,
                "anchor_confirmed": False,
                "status_code": "PENDING_ANCHOR",
            }
        )
    if not insert_rows:
        return {"status": "success", "message": f"모두 기존 유지 ({len(existing_rule_ids)}개)", "data": {"created": 0}}
    created = 0
    for i in range(0, len(insert_rows), 20):
        res = supabase.table("inspection_sets").insert(insert_rows[i : i + 20]).execute()
        created += len(res.data or [])
    return {"status": "success", "message": f"{created}개 생성", "data": {"created": created}}


def run_debug_quote_context(supabase, quote_id: str, parse_survey_data_fn, survey_to_context_fn) -> Dict[str, Any]:
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data:
        raise LookupError("견적을 찾을 수 없습니다.")
    sd = parse_survey_data_fn(qres.data.get("survey_data"))
    if not sd:
        raise ValueError("survey_data 없음")
    return {"status": "success", "quote_no": qres.data.get("quote_no"), "context": survey_to_context_fn(sd)}


def run_get_latest_diagnosis(supabase, factory_id: str) -> Dict[str, Any]:
    res = supabase.table("factory_diagnosis_results").select("*").eq("factory_id", factory_id).eq("is_latest", True).order("created_at", desc=True).limit(1).execute()
    if not res.data:
        raise LookupError("진단 결과 없음")
    return {"status": "success", "data": res.data[0]}


def run_get_diagnosis_history(supabase, factory_id: str, page: int, page_size: int) -> Dict[str, Any]:
    offset = (page - 1) * page_size
    res = (
        supabase.table("factory_diagnosis_results")
        .select("id, sector, diagnosis_stage, rule_count, is_latest, created_at", count="exact")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or [], "total": res.count or 0, "page": page, "page_size": page_size}}


def run_diagnose_step1_endpoint(supabase, body) -> Dict[str, Any]:
    diag = run_diagnose_step1(
        supabase,
        body,
        ENGINE_VERSION,
        ALLOWED_DIAGNOSE_SECTORS,
        normalize_sector_db,
        _input_to_facility_context,
        evaluate_facility_conditions_db,
        _classify_rules_db,
        format_rule_result_db,
        risk_level,
        get_construction_summary,
    )
    final = finalize_diagnose_step1(supabase, diag)
    result_data = final["result_data"]
    factory_id = final["factory_id"]
    sector_raw = final["sector_raw"]
    diagnosis_id = final["diagnosis_id"]
    fac_company_id = final["fac_company_id"]
    applicable = final["applicable"]
    if factory_id and sector_raw == "CONSTRUCTION" and diagnosis_id:
        try:
            from routers.legal_engine_patch import generate_schedules_from_diagnosis

            generate_schedules_from_diagnosis(factory_id)
        except Exception as e:
            print(f"[AUTO_SCHEDULE] 건설현장 일정 자동생성 실패: {e}")
    if factory_id and diagnosis_id and applicable:
        try:
            from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis

            auto_create_inspection_sets_from_diagnosis(supabase, factory_id, fac_company_id, applicable)
        except Exception as e:
            print(f"[AUTO_INSPECT_SETS] inspection_sets 자동생성 실패: {e}")
    return {"status": "success", "data": result_data}
