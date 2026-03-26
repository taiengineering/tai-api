"""
법령 판정 엔진 라우터 — v3.1.0
변경사항:
  v3.1.0
    - apply-quote: 판정 결과를 quotes.legal_result_json 에 저장 (누락 수정)
    - apply-quote: GET /legal-engine/quote-result/{quote_id} 조회 엔드포인트 추가
    - legal_applications upsert: except pass → 에러 로깅으로 개선 (silent fail 제거)
  v3.0.0
    - apply/{factory_id}: mode 파라미터 (facility/process/equipment/all)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Any, Dict
from datetime import datetime, timezone
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "3.1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_survey_data(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def _survey_data_to_factory_fields(survey_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    견적 survey_data(JSON) → 시설 조건 법령 엔진용 필드.
    factories 테이블과 동일한 키(worker_count, total_floor_area, …)를 맞춤.
    """
    snap = survey_data.get("survey_snapshot")
    if not isinstance(snap, dict):
        snap = {}

    def _to_float(*vals) -> float:
        for v in vals:
            if v is None or v == "":
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return 0.0

    def _to_int(*vals) -> int:
        for v in vals:
            if v is None or v == "":
                continue
            try:
                return int(float(v))
            except (TypeError, ValueError):
                continue
        return 0

    workers = _to_int(
        survey_data.get("employee_count"),
        snap.get("workers"),
    )
    area = _to_float(
        survey_data.get("floor_area"),
        snap.get("area"),
    )
    power = _to_float(
        survey_data.get("electrical_kw"),
        snap.get("elecKw"),
    )
    building_use = (
        str(snap.get("bldgUse") or "").strip()
        or str(survey_data.get("building_type") or "").strip()
        or str(snap.get("btype") or "").strip()
        or str(snap.get("btypeCustom") or "").strip()
    )
    ksic = str(survey_data.get("ksic_code") or snap.get("ksic_code") or "").strip()

    return {
        "worker_count": workers,
        "total_floor_area": area,
        "electric_capacity": power,
        "building_use_code": building_use,
        "ksic_code": ksic,
    }


def format_rule_result(rule: dict, source_label: str = "") -> dict:
    """룰 결과 포맷 통일"""
    return {
        "rule_id": rule.get("rule_id", ""),
        "rule_type": rule.get("rule_type", ""),
        "law_name": rule.get("law_name", ""),
        "law_article": rule.get("law_article", ""),
        "description": rule.get("description", ""),
        "appointment_target": rule.get("appointment_target", ""),
        "qualification_required": rule.get("qualification_required", ""),
        "inspection_cycle": rule.get("inspection_cycle", ""),
        "penalty_amount": rule.get("penalty_amount", ""),
        "source_label": source_label,
    }


# ──────────────────────────────────────────────
# POST /legal-engine/apply/{factory_id}
# 법령 판정 실행 — mode 파라미터로 4가지 모드 지원
# ──────────────────────────────────────────────
@router.post("/apply/{factory_id}")
async def apply_legal_engine(
    factory_id: str,
    body: Optional[dict] = None,
    mode: str = Query("all", description="판정 모드: facility/process/equipment/all"),
):
    """
    법령 판정 실행
    - facility:  시설 조건만으로 판정 (빠른 기본 진단)
    - process:   등록 공정 기반 판정
    - equipment: 등록 설비 기반 판정
    - all:       종합가동 (facility + process + equipment 통합, 기본값)
    """
    supabase = get_supabase()

    # body에서도 mode 받기 (프론트 편의)
    if body and body.get("mode"):
        mode = body["mode"]

    if mode not in ("facility", "process", "equipment", "all"):
        raise HTTPException(status_code=400, detail="mode는 facility/process/equipment/all 중 하나여야 합니다.")

    # 1. 시설 정보 조회
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).single().execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    factory = fac_res.data

    # 2. 법령 룰 전체 조회
    rules_res = supabase.table("master_building_legal_rules").select("*").eq(
        "is_active", True
    ).execute()
    all_rules = rules_res.data or []

    evaluated_at = _now_iso()
    triggered = {
        "appointment": [],
        "inspection": [],
        "action": [],
        "report": [],
        "not_applicable": [],
    }
    triggered_by_source = {
        "factory_condition": 0,
        "registered_equipment": 0,
        "process_recommended": 0,
    }

    # ── MODE: facility (시설 조건만) ──
    if mode == "facility":
        applicable, not_applicable = _evaluate_facility_conditions(factory, all_rules)
        triggered_by_source["factory_condition"] = len(applicable)
        _classify_rules(applicable, triggered)
        for r in not_applicable:
            triggered["not_applicable"].append(format_rule_result(r))

    # ── MODE: process (등록 공정 기반) ──
    elif mode == "process":
        process_rules, not_applicable = await _evaluate_process_conditions(
            factory_id, factory, all_rules, supabase
        )
        triggered_by_source["process_recommended"] = len(process_rules)
        _classify_rules(process_rules, triggered)
        for r in not_applicable:
            triggered["not_applicable"].append(format_rule_result(r))

    # ── MODE: equipment (등록 설비 기반) ──
    elif mode == "equipment":
        equip_rules, not_applicable = await _evaluate_equipment_conditions(
            factory_id, factory, all_rules, supabase
        )
        triggered_by_source["registered_equipment"] = len(equip_rules)
        _classify_rules(equip_rules, triggered)
        for r in not_applicable:
            triggered["not_applicable"].append(format_rule_result(r))

    # ── MODE: all (종합가동) ──
    else:
        fac_applicable, _ = _evaluate_facility_conditions(factory, all_rules)
        triggered_by_source["factory_condition"] = len(fac_applicable)

        equip_applicable, _ = await _evaluate_equipment_conditions(
            factory_id, factory, all_rules, supabase
        )
        triggered_by_source["registered_equipment"] = len(equip_applicable)

        proc_applicable, _ = await _evaluate_process_conditions(
            factory_id, factory, all_rules, supabase
        )
        triggered_by_source["process_recommended"] = len(proc_applicable)

        rule_map = {}
        for r in fac_applicable:
            rule_map[r["rule_id"]] = (r, "🏢 시설조건")
        for r in equip_applicable:
            if r["rule_id"] not in rule_map:
                rule_map[r["rule_id"]] = (r, "⚙️ 등록설비")
        for r in proc_applicable:
            if r["rule_id"] not in rule_map:
                rule_map[r["rule_id"]] = (r, "🔄 공정추천")

        applicable_combined = list(rule_map.values())
        applicable_only = [r for r, _ in applicable_combined]

        applicable_ids = set(r["rule_id"] for r in applicable_only)
        not_applicable = [r for r in all_rules if r["rule_id"] not in applicable_ids]

        _classify_rules_with_source(applicable_combined, triggered)
        for r in not_applicable:
            triggered["not_applicable"].append(format_rule_result(r))

    # 3. 결과 구성
    total_applicable = (
        len(triggered["appointment"]) +
        len(triggered["inspection"]) +
        len(triggered["action"]) +
        len(triggered["report"])
    )

    result_data = {
        "factory_id": factory_id,
        "engine_version": ENGINE_VERSION,
        "mode": mode,
        "evaluated_at": evaluated_at,
        "total_rules_checked": len(all_rules),
        "applicable_count": total_applicable,
        "triggered_by_source": triggered_by_source,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"],
        "not_applicable": triggered["not_applicable"],
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
        }
    }

    # 4. legal_applications 저장 — upsert (unique: factory_id+mode)
    try:
        supabase.table("legal_applications").upsert({
            "factory_id": factory_id,
            "engine_version": ENGINE_VERSION,
            "mode": mode,
            "result_json": result_data,
            "evaluated_at": evaluated_at,
        }, on_conflict="factory_id,mode").execute()
    except Exception as e:
        # silent fail 제거 → 로그 출력 (응답은 정상 반환)
        print(f"[LEGAL ENGINE] legal_applications 저장 실패: {e}")

    return {"status": "success", "data": result_data}


# ──────────────────────────────────────────────
# POST /legal-engine/apply-quote/{quote_id}
# 견적 survey_data 기반 시설 조건 법령 판정
# v3.1.0: 판정 결과를 quotes 테이블에 저장 (누락 수정)
# ──────────────────────────────────────────────
@router.post("/apply-quote/{quote_id}")
async def apply_legal_engine_from_quote(quote_id: str):
    supabase = get_supabase()

    qres = (
        supabase.table("quotes")
        .select("id, quote_no, survey_data")
        .eq("id", quote_id)
        .single()
        .execute()
    )
    if not qres.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")

    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd:
        raise HTTPException(
            status_code=400,
            detail="survey_data가 없습니다. 법적진단 설문 접수 건만 실행할 수 있습니다.",
        )

    factory_like = _survey_data_to_factory_fields(sd)
    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    all_rules = rules_res.data or []
    evaluated_at = _now_iso()

    applicable, not_applicable = _evaluate_facility_conditions(factory_like, all_rules)
    triggered = {
        "appointment": [],
        "inspection": [],
        "action": [],
        "report": [],
        "not_applicable": [],
    }
    _classify_rules(applicable, triggered)
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result(r))

    total_applicable = (
        len(triggered["appointment"])
        + len(triggered["inspection"])
        + len(triggered["action"])
        + len(triggered["report"])
    )

    na_list = triggered["not_applicable"]
    na_cap = 100
    na_trimmed = len(na_list) > na_cap

    result_data = {
        "quote_id": quote_id,
        "quote_no": qres.data.get("quote_no"),
        "source": "quote_survey",
        "engine_version": ENGINE_VERSION,
        "mode": "facility",
        "evaluated_at": evaluated_at,
        "facility_context": factory_like,
        "note": "견적 설문 기반으로 시설(facility) 조건만 적용했습니다. 등록 설비·공정 기반 판정은 사업장 등록 후 법령엔진을 실행하세요.",
        "total_rules_checked": len(all_rules),
        "applicable_count": total_applicable,
        "triggered_by_source": {"factory_condition": len(applicable)},
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"],
        "not_applicable": na_list[:na_cap],
        "not_applicable_total": len(na_list),
        "not_applicable_truncated": na_trimmed,
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
        },
    }

    # ✅ v3.1.0 수정: quotes 테이블에 판정 결과 저장 (이전 버전에서 누락됨)
    try:
        supabase.table("quotes").update({
            "legal_result_json":      result_data,
            "legal_evaluated_at":     evaluated_at,
            "legal_applicable_count": total_applicable,
            "updated_at":             evaluated_at,
        }).eq("id", quote_id).execute()
        print(f"[LEGAL ENGINE] quotes 판정 결과 저장 완료: {quote_id} ({total_applicable}건)")
    except Exception as e:
        print(f"[LEGAL ENGINE] quotes 저장 실패: {e}")

    return {"status": "success", "data": result_data}


# ──────────────────────────────────────────────
# GET /legal-engine/quote-result/{quote_id}
# 견적 판정 결과 조회 (재판정 없이) — v3.1.0 신규
# ──────────────────────────────────────────────
@router.get("/quote-result/{quote_id}")
async def get_legal_result_from_quote(quote_id: str):
    """
    저장된 견적 법령판정 결과 조회.
    apply-quote 를 먼저 실행해야 데이터가 있습니다.
    """
    supabase = get_supabase()

    res = (
        supabase.table("quotes")
        .select("id, quote_no, legal_result_json, legal_evaluated_at, legal_applicable_count")
        .eq("id", quote_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")

    if not res.data.get("legal_result_json"):
        raise HTTPException(
            status_code=404,
            detail="법령판정 결과가 없습니다. POST /legal-engine/apply-quote/{quote_id} 를 먼저 실행하세요."
        )

    return {
        "status": "success",
        "data": {
            "quote_id":             quote_id,
            "quote_no":             res.data.get("quote_no"),
            "legal_evaluated_at":   res.data.get("legal_evaluated_at"),
            "legal_applicable_count": res.data.get("legal_applicable_count"),
            "result":               res.data.get("legal_result_json"),
        }
    }


# ──────────────────────────────────────────────
# GET /legal-engine/result/{factory_id}
# 기존 판정 결과 조회 (재판정 없이)
# ──────────────────────────────────────────────
@router.get("/result/{factory_id}")
async def get_legal_result(
    factory_id: str,
    mode: str = Query("all", description="조회할 모드: facility/process/equipment/all"),
):
    supabase = get_supabase()

    try:
        res = supabase.table("legal_applications").select("*").eq(
            "factory_id", factory_id
        ).eq("mode", mode).order("evaluated_at", desc=True).limit(1).execute()
    except Exception:
        raise HTTPException(status_code=404, detail="판정 결과가 없습니다. 먼저 판정을 실행하세요.")

    if not res.data:
        raise HTTPException(status_code=404, detail="판정 결과가 없습니다. 먼저 판정을 실행하세요.")

    return {"status": "success", "data": res.data[0].get("result_json", {})}


# ──────────────────────────────────────────────
# GET /legal-engine/summary/{factory_id}
# 판정 결과 요약
# ──────────────────────────────────────────────
@router.get("/summary/{factory_id}")
async def get_legal_summary(factory_id: str):
    supabase = get_supabase()

    try:
        res = supabase.table("legal_applications").select(
            "mode, evaluated_at, result_json"
        ).eq("factory_id", factory_id).order("evaluated_at", desc=True).limit(4).execute()
    except Exception:
        return {"status": "success", "data": {"factory_id": factory_id, "results": []}}

    results = []
    for row in (res.data or []):
        rj = row.get("result_json", {})
        results.append({
            "mode": row.get("mode", "all"),
            "evaluated_at": row.get("evaluated_at"),
            "summary": rj.get("summary", {}),
            "engine_version": rj.get("engine_version", ""),
        })

    return {"status": "success", "data": {"factory_id": factory_id, "results": results}}


# ──────────────────────────────────────────────
# 내부 헬퍼 함수들
# ──────────────────────────────────────────────

def _evaluate_facility_conditions(factory: dict, rules: list) -> tuple:
    """시설 조건 기반 법령 판정"""
    applicable = []
    not_applicable = []

    workers = factory.get("worker_count") or 0
    area = factory.get("total_floor_area") or 0
    power = factory.get("electric_capacity") or 0
    building_use = factory.get("building_use_code", "")
    ksic = factory.get("ksic_code", "")

    for rule in rules:
        matched = _check_rule_conditions(rule, {
            "worker_count": workers,
            "total_floor_area": area,
            "electric_capacity": power,
            "building_use_code": building_use,
            "ksic_code": ksic,
        })
        if matched:
            applicable.append(rule)
        else:
            not_applicable.append(rule)

    return applicable, not_applicable


async def _evaluate_equipment_conditions(
    factory_id: str, factory: dict, rules: list, supabase
) -> tuple:
    """등록 설비 기반 법령 판정"""
    eq_res = supabase.table("equipment_assets").select(
        "equipment_std, equipment_type_code, count, capacity"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    registered_equip = eq_res.data or []
    equip_std_set  = set(e.get("equipment_std", "")       for e in registered_equip)
    equip_type_set = set(e.get("equipment_type_code", "") for e in registered_equip)

    applicable = []
    not_applicable = []

    for rule in rules:
        target_equip = rule.get("target_equipment_std", "")
        target_type  = rule.get("target_equipment_type", "")

        matched = False
        if target_equip and target_equip in equip_std_set:
            matched = True
        elif target_type and target_type in equip_type_set:
            matched = True
        elif not target_equip and not target_type:
            workers = factory.get("worker_count") or 0
            area    = factory.get("total_floor_area") or 0
            matched = _check_rule_conditions(rule, {
                "worker_count": workers,
                "total_floor_area": area,
            })

        if matched:
            applicable.append(rule)
        else:
            not_applicable.append(rule)

    return applicable, not_applicable


async def _evaluate_process_conditions(
    factory_id: str, factory: dict, rules: list, supabase
) -> tuple:
    """등록 공정 기반 법령 판정 (공정 → 설비 추론 → 법령 적용)"""
    proc_res = supabase.table("factory_process").select(
        "process_id, source"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    process_ids = [
        r["process_id"] for r in (proc_res.data or [])
        if r.get("source") != "MANUAL"
    ]

    if not process_ids:
        return [], rules

    eq_res = supabase.table("v_equipment_unified").select(
        "facility_name_std, match_band"
    ).in_("process_id", process_ids).in_("match_band", ["MUST", "CORE"]).execute()

    inferred_equip = set(r["facility_name_std"] for r in (eq_res.data or []))

    applicable = []
    not_applicable = []

    for rule in rules:
        target_equip = rule.get("target_equipment_std", "")

        if target_equip and target_equip in inferred_equip:
            applicable.append(rule)
        elif not target_equip:
            workers = factory.get("worker_count") or 0
            area    = factory.get("total_floor_area") or 0
            if _check_rule_conditions(rule, {"worker_count": workers, "total_floor_area": area}):
                applicable.append(rule)
            else:
                not_applicable.append(rule)
        else:
            not_applicable.append(rule)

    return applicable, not_applicable


def _check_rule_conditions(rule: dict, context: dict) -> bool:
    """룰 조건 체크"""
    conditions = rule.get("conditions", [])
    if not conditions:
        return False

    for cond in conditions:
        field    = cond.get("field", "")
        operator = cond.get("operator", "gte")
        value    = cond.get("value")

        if value is None:
            continue

        actual = context.get(field)
        if actual is None:
            continue

        try:
            actual_num = float(actual)
            value_num  = float(value)
            if operator in ("gte", ">=") and actual_num >= value_num:
                return True
            elif operator in ("lte", "<=") and actual_num <= value_num:
                return True
            elif operator in ("gt", ">")  and actual_num >  value_num:
                return True
            elif operator in ("lt", "<")  and actual_num <  value_num:
                return True
            elif operator in ("eq", "=", "==") and actual_num == value_num:
                return True
        except (TypeError, ValueError):
            if operator in ("eq", "=", "==") and str(actual) == str(value):
                return True
            elif operator in ("in", "contains") and str(actual) in str(value):
                return True

    return False


def _classify_rules(rules: list, triggered: dict):
    """룰을 타입별로 분류"""
    for rule in rules:
        rule_type = rule.get("rule_type", "").lower()
        formatted = format_rule_result(rule)
        if "appointment" in rule_type or "선임" in rule_type:
            triggered["appointment"].append(formatted)
        elif "inspection" in rule_type or "점검" in rule_type:
            triggered["inspection"].append(formatted)
        elif "action" in rule_type or "조치" in rule_type:
            triggered["action"].append(formatted)
        elif "report" in rule_type or "신고" in rule_type:
            triggered["report"].append(formatted)
        else:
            triggered["action"].append(formatted)


def _classify_rules_with_source(rule_source_pairs: list, triggered: dict):
    """소스 레이블 포함하여 룰 분류"""
    for rule, source_label in rule_source_pairs:
        rule_type = rule.get("rule_type", "").lower()
        formatted = format_rule_result(rule, source_label)
        if "appointment" in rule_type or "선임" in rule_type:
            triggered["appointment"].append(formatted)
        elif "inspection" in rule_type or "점검" in rule_type:
            triggered["inspection"].append(formatted)
        elif "action" in rule_type or "조치" in rule_type:
            triggered["action"].append(formatted)
        elif "report" in rule_type or "신고" in rule_type:
            triggered["report"].append(formatted)
        else:
            triggered["action"].append(formatted)
