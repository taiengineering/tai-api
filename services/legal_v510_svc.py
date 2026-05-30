from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from schemas.legal_engine import DiagnoseStep1Body
from schemas.legal_engine_v510 import DiagnoseStep2Body
from services.legal_format import _classify_rules_db, format_rule_result_db
from services.legal_v510_helpers import (
    _evaluate_facility_conditions_db_v510,
    _get_construction_summary,
    _input_to_facility_context_v510,
)
from services.legal_rules import (
    _evaluate_condition,
    _resolve_obligation_type,
    _risk_level,
    normalize_sector_db as _normalize_sector_db,
)
from services.leg_output_adapter import adapt, _group_by_type, _group_by_law
from services.legal_diagnosis_rules import fetch_diagnosis_rules
from services.legal_runtime import _create_report_events_from_rules, _save_diagnosis_result
from services.leg_obligation_enrichment import enrich


def run_diagnose_step1_v510(
    supabase,
    body: DiagnoseStep1Body,
    allowed_sectors,
    engine_version: str,
) -> Dict[str, Any]:
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError("sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.")

    factory_id = (body.factory_id or "").strip()
    if factory_id:
        fac_check = supabase.table("factories").select("id").eq("id", factory_id).limit(1).execute()
        if not fac_check.data:
            raise LookupError("시설을 찾을 수 없습니다.")

    sector_db = _normalize_sector_db(sector_raw)
    all_rules = fetch_diagnosis_rules(
        supabase,
        sector_db=sector_db,
        diagnosis_stage=1,
        factory_id=factory_id or None,
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
    }
    for k, v in flat_fields.items():
        if v is not None and k not in inp:
            inp[k] = v

    facility_ctx = _input_to_facility_context_v510(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()

    applicable, not_applicable = _evaluate_facility_conditions_db_v510(facility_ctx, all_rules, sector_raw)

    triggered: Dict[str, List] = {
        "appointment": [],
        "inspection": [],
        "notify": [],
        "report": [],
        "action": [],
        "not_applicable": [],
    }
    _classify_rules_db(applicable, triggered)
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result_db(r))

    total_applicable = (
        len(triggered["appointment"])
        + len(triggered["inspection"])
        + len(triggered["notify"])
        + len(triggered["report"])
        + len(triggered["action"])
    )

    law_names = sorted({x.get("law_name") for x in applicable if x.get("law_name")})
    appointment_n = len(triggered["appointment"])
    risk = _risk_level(total_applicable, appointment_n)

    obligations: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        if triggered[key]:
            obligations.append({"category": key, "label": label, "items": triggered[key]})
    if triggered["report"]:
        obligations.append({"category": "report", "label": "신고", "items": triggered["report"]})
    if triggered["notify"]:
        obligations.append({"category": "notify", "label": "보고", "items": triggered["notify"]})

    rules_table: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        for row in triggered[key]:
            rules_table.append({"category": label, **row})
    for row in triggered["report"]:
        rules_table.append({"category": "신고", **row})
    for row in triggered["notify"]:
        rules_table.append({"category": "보고", **row})

    law_cats: List[str] = []
    seen: set = set()
    for x in applicable:
        c = (x.get("law_category_code") or x.get("law_name") or "").strip()
        if c and c not in seen:
            seen.add(c)
            law_cats.append(c)

    key_obligations: List[str] = []
    for x in applicable[:20]:
        t = (x.get("remarks") or x.get("obligation_summary") or "").strip()
        if t and t not in key_obligations:
            key_obligations.append(t)

    rules_out: List[Dict[str, Any]] = []
    for x in applicable:
        rules_out.append(
            {
                "rule_id": x.get("rule_id"),
                "law_name": x.get("law_name") or "",
                "law_article": x.get("law_article") or "",
                "obligation": (x.get("obligation_summary") or x.get("remarks") or "").strip(),
                "remarks": (x.get("remarks") or "").strip(),
                "obligation_summary": (x.get("obligation_summary") or "").strip(),
            }
        )

    result_data = {
        "factory_id": factory_id or None,
        "sector": sector_raw,
        "step": 1,
        "engine_version": engine_version,
        "evaluated_at": evaluated_at,
        "facility_context": facility_ctx,
        "risk_level": risk,
        "applicable_law_categories": law_cats,
        "appointment_required_flag": appointment_n > 0,
        "key_obligations": key_obligations,
        "rules": rules_out,
        "law_badges": law_names,
        "obligations": obligations,
        "rules_table": rules_table,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "not_applicable": triggered["not_applicable"][:100],
        "not_applicable_total": len(not_applicable),
        "total_rules_checked": len(all_rules),
        "applicable_count": total_applicable,
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
            "notify": len(triggered["notify"]),
            "form_linked": sum(1 for r in applicable if (r.get("form_code") or "").strip()),
        },
    }
    if sector_raw == "CONSTRUCTION":
        result_data["construction_summary"] = _get_construction_summary(facility_ctx)

    obligation_contract = adapt(result_data, mode=sector_raw)

    # Enrichment Guard: 조건 없는 rule을 applicable에서 분리
    enrichment_result = enrich(
        obligation_contract.get("obligations", []),
        supabase,
    )
    obligation_contract["obligations"] = enrichment_result["applicable"]
    obligation_contract["enrichment_stats"] = enrichment_result["enrichment_stats"]

    # review_required는 API 응답에서 제외 — 운영자 검토용 백로그
    review_list = enrichment_result["review_required"]
    obligation_contract["review_required_count"] = len(review_list)
    obligation_contract["review_sample"] = [
        {
            "obligation_id": r.get("obligation_id", ""),
            "law_name": r.get("law_name", ""),
            "law_article": r.get("law_article", ""),
            "title": r.get("title", ""),
            "missing_fields": (r.get("enrichment") or {}).get("missing_fields", []),
        }
        for r in review_list[:10]
    ]

    # grouped_by_type/law를 applicable 기준으로 재생성
    obligation_contract["grouped_by_type"] = _group_by_type(enrichment_result["applicable"])
    obligation_contract["grouped_by_law"] = _group_by_law(enrichment_result["applicable"])
    obligation_contract["evidence_refs"] = [
        {"law_name": g["law_name"], "count": g["count"]}
        for g in obligation_contract["grouped_by_law"]
    ]

    # summary 업데이트
    obligation_contract["summary"]["applicable_after_enrichment"] = len(enrichment_result["applicable"])
    obligation_contract["summary"]["review_required"] = len(enrichment_result["review_required"])

    obligation_contract["sector"] = sector_raw
    obligation_contract["step"] = 1
    if sector_raw == "CONSTRUCTION" and result_data.get("construction_summary"):
        obligation_contract["construction_summary"] = result_data["construction_summary"]
    result_data["obligation_contract"] = obligation_contract

    diagnosis_id = None
    if factory_id:
        try:
            (
                supabase.table("factory_diagnosis_results")
                .update({"is_latest": False})
                .eq("factory_id", factory_id)
                .eq("sector", sector_raw)
                .eq("is_latest", True)
                .execute()
            )
        except Exception:
            pass
        try:
            save_res = (
                supabase.table("factory_diagnosis_results")
                .insert(
                    {
                        "factory_id": factory_id,
                        "sector": sector_raw,
                        "diagnosis_stage": 1,
                        "input_data": inp,
                        "result_data": result_data,
                        "rule_count": total_applicable,
                        "is_latest": True,
                    }
                )
                .execute()
            )
            if save_res.data:
                diagnosis_id = save_res.data[0].get("id")
        except Exception:
            pass

        if diagnosis_id and applicable:
            try:
                rule_rows = []
                for rule in applicable:
                    rule_rows.append(
                        {
                            "diagnosis_id": diagnosis_id,
                            "rule_code": rule.get("rule_id") or rule.get("rule_code") or "",
                            "rule_name": (rule.get("obligation_summary") or rule.get("remarks") or "").strip(),
                            "law_name": rule.get("law_name") or "",
                            "law_article": rule.get("law_article") or "",
                            "obligation": (rule.get("obligation_summary") or "").strip(),
                            "obligation_type": _resolve_obligation_type(rule),
                            "due_date": None,
                            "status": "PENDING",
                            "form_code": rule.get("form_code") or None,
                        }
                    )
                for i in range(0, len(rule_rows), 50):
                    supabase.table("diagnosis_rule_results").insert(rule_rows[i : i + 50]).execute()
            except Exception:
                pass

    result_data["diagnosis_id"] = diagnosis_id
    obligation_contract["diagnosis_id"] = diagnosis_id
    obligation_contract["factory_id"] = factory_id or None
    return {"status": "success", "data": obligation_contract}


def run_diagnose_step2_v510(supabase, body: DiagnoseStep2Body, engine_version: str) -> Dict[str, Any]:
    factory_id = body.factory_id
    diagnosis_id = body.diagnosis_id
    processes = body.processes
    construction_types = body.construction_types
    work_types: List[str] = body.construction_work_types or []
    if not factory_id:
        raise ValueError("factory_id 필수")

    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table("factory_diagnosis_results").select("*").eq("id", diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass

    sector = (prev or {}).get("sector", "MANUFACTURING")
    input_data = dict((prev or {}).get("input_data") or {})
    input_data["processes"] = processes
    input_data["construction_types"] = construction_types
    input_data["sector"] = sector

    sector_db = _normalize_sector_db(sector)
    rules = fetch_diagnosis_rules(
        supabase,
        sector_db=sector_db,
        diagnosis_stage_lte=2,
        work_types=work_types if work_types else None,
        factory_id=factory_id,
    )
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
    _create_report_events_from_rules(supabase, factory_id, matched)

    prev_codes = set()
    if prev:
        prev_rules = (prev.get("result_data") or {}).get("rules", [])
        prev_codes = {r.get("rule_code") for r in prev_rules}
    added = [r for r in matched if (r.get("rule_code") or r.get("rule_id")) not in prev_codes]

    result = diagnosis.get("result_data", {})
    work_type_summary: Dict[str, int] = {}
    if work_types:
        for r in matched:
            wt = r.get("construction_work_type") or "COMMON"
            work_type_summary[wt] = work_type_summary.get(wt, 0) + 1

    return {
        "status": "success",
        "diagnosis_id": diagnosis.get("id"),
        "stage": 2,
        "engine_version": engine_version,
        "sector": sector,
        "rule_count": len(matched),
        "added_rule_count": len(added),
        "filtered_by_work_types": work_types if work_types else None,
        "work_type_summary": work_type_summary if work_types else None,
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
                "rule_name": r.get("rule_name") or r.get("remarks", ""),
                "law_article": r.get("law_article", ""),
                "work_type": r.get("construction_work_type"),
                "work_type_label": r.get("construction_work_type_label"),
            }
            for r in added
        ],
    }
