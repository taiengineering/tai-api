"""DB 조회 · 결과 반환 함수 — legal_engine_svc.py에서 분리.

run_get_legal_result, run_get_legal_summary, run_create_inspection_sets_from_legal 등
순수 DB 조회 + 응답 포매팅 함수를 모아둔 모듈.
"""
from __future__ import annotations

from typing import Any, Dict, List


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
