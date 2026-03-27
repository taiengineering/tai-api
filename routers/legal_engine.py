"""
법령 판정 엔진 라우터 — v4.1.2
=================================
v4.1.2:
  - /apply 응답에서 not_applicable 제거 → 응답 경량화
  - DB(factories) 저장은 not_applicable 포함 전체 저장 유지
  - /apply 응답: summary + applicable 항목만 반환
  - /result 조회 시에도 not_applicable 제외 (프론트 불필요)

v4.1.1: equipment_assets is_active 컬럼 없음 → 필터 제거
v4.1.0: 파이프라인 전체 연결 (컬럼명 수정 / 반기 코드 / factories 저장 / inspection_sets 생성)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Any, Dict
from datetime import datetime, timezone
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "4.1.2"


# ──────────────────────────────────────────────
# 코드 → 한글명 매핑 테이블
# ──────────────────────────────────────────────

APPOINTMENT_TARGET_MAP = {
    "safety_manager":             "안전관리자",
    "health_manager":             "보건관리자",
    "safety_health_director":     "안전보건관리책임자",
    "safety_health_manager":      "안전보건관리담당자",
    "fire_safety_manager":        "소방안전관리자",
    "electric_safety_manager":    "전기안전관리자",
    "gas_safety_manager":         "가스안전관리자",
    "elevator_safety_manager":    "승강기안전관리자",
    "energy_manager":             "에너지관리자",
    "building_manager":           "건축물관리자(유지관리자)",
    "hazardous_material_manager": "위험물안전관리자",
    "city_gas_manager":           "도시가스안전관리자",
}

INSPECTION_CYCLE_UNIT_MAP = {
    "001": "일 1회",
    "002": "주 1회",
    "003": "월 1회",
    "004": "분기 1회",
    "005": "반기 1회",
    "006": "연 1회",
    "007": "2년마다",
    "008": "5년마다",
    "009": "4년마다",
    "010": "3년마다",
    "011": "3년마다",
    "012": "10년마다",
    "013": "5년마다(시설)",
}

RULE_TYPE_MAP = {
    "001": "appointment",
    "002": "inspection",
    "003": "report",
    "004": "action",
    "005": "action",
    "007": "action",
    "008": "action",
}


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


# ──────────────────────────────────────────────
# context 변환
# ──────────────────────────────────────────────

def _survey_data_to_context(survey_data: Dict[str, Any]) -> Dict[str, Any]:
    snap = survey_data.get("survey_snapshot")
    if not isinstance(snap, dict):
        snap = {}
    equip_list = snap.get("equip") or []
    workers    = _to_int(survey_data.get("employee_count"), snap.get("workers"))
    area       = _to_float(survey_data.get("floor_area"), snap.get("area"))
    power_kw   = _to_float(survey_data.get("electrical_kw"), snap.get("elecKw"))
    floors     = _to_int(snap.get("floors"), survey_data.get("floors_above"))
    gas_kg     = _to_float(snap.get("gasKg"), survey_data.get("gas_kg"))
    boiler_th  = _to_float(snap.get("boilerTh"), survey_data.get("boiler_th"))
    outsource  = _to_int(snap.get("outsource"), survey_data.get("outsource_count"))
    has_chem   = "chem"   in equip_list or bool(survey_data.get("equip_chemical"))
    has_elev   = "elev"   in equip_list or bool(survey_data.get("equip_elevator"))
    has_gas    = "gas"    in equip_list or gas_kg > 0
    has_boiler = "boiler" in equip_list or boiler_th > 0
    btype = str(snap.get("btype") or snap.get("bldgUse") or survey_data.get("building_type") or "").strip()
    ksic  = str(survey_data.get("ksic_code") or snap.get("ksic_code") or "").strip()
    is_factory = 1 if (btype.startswith("공장") or btype.startswith("제조") or ksic.upper().startswith("C")) else 0
    cons_eok = _to_float(snap.get("constructionAmt"), survey_data.get("construction_amt"))
    return {
        "employee_count":          workers,
        "building_area":           area,
        "electrical_capacity_kw":  power_kw,
        "floor_count":             floors,
        "contractor_count":        outsource,
        "transformer_capacity_kva": power_kw,
        "construction_amount":     cons_eok * 100_000_000 if cons_eok > 0 else 0,
        "gas_capacity_kg":         gas_kg if gas_kg > 0 else (1 if has_gas else 0),
        "gas_capacity_m3":         1 if has_gas else 0,
        "boiler_capacity_kw":      boiler_th * 700 if boiler_th > 0 else (1 if has_boiler else 0),
        "boiler_capacity_th":      boiler_th,
        "is_hazardous_material":   1 if has_chem else 0,
        "elevator_count":          1 if has_elev else 0,
        "is_factory_registered":   is_factory,
        "is_multi_use":            0,
        "annual_energy_toe":       0,
        "building_use_code":       btype,
        "ksic_code":               ksic,
    }


def _factory_to_context(factory: dict) -> Dict[str, Any]:
    """v4.1.0: 실제 DB 컬럼명으로 전면 수정"""
    return {
        "employee_count":           _to_int(factory.get("employee_count")),
        "building_area":            _to_float(factory.get("building_area")),
        "electrical_capacity_kw":   _to_float(factory.get("electrical_capacity_kw")),
        "floor_count":              _to_int(factory.get("floor_count")),
        "contractor_count":         _to_int(factory.get("contractor_count")),
        "transformer_capacity_kva": _to_float(factory.get("transformer_capacity_kva")),
        "gas_capacity_kg":          _to_float(factory.get("gas_capacity_kg")),
        "gas_capacity_m3":          _to_float(factory.get("gas_capacity_m3")),
        "boiler_capacity_kw":       _to_float(factory.get("boiler_capacity_kw")),
        "boiler_capacity_th":       _to_float(factory.get("boiler_capacity_th")),
        "elevator_count":           _to_int(factory.get("elevator_count")),
        "is_hazardous_material":    1 if factory.get("is_hazardous_material") else 0,
        "is_factory_registered":    1 if factory.get("is_factory_registered") else 0,
        "is_multi_use":             1 if factory.get("is_multi_use") else 0,
        "annual_energy_toe":        _to_float(factory.get("annual_energy_toe")),
        "construction_amount":      _to_float(factory.get("construction_amount")),
        "building_use_code":        str(factory.get("main_purpose_name") or factory.get("building_use_code") or ""),
        "ksic_code":                str(factory.get("ksic_code") or ""),
    }


# ──────────────────────────────────────────────
# 조건 체크
# ──────────────────────────────────────────────

def _check_rule_conditions(rule: dict, context: dict) -> bool:
    condition_code = rule.get("condition_code", "")
    operator       = rule.get("condition_operator_code", "gte")
    value_str      = rule.get("condition_value")
    if not condition_code:
        return True
    actual = context.get(condition_code)
    if actual is None:
        return False
    if condition_code.startswith("is_") and actual == 0:
        return False
    if value_str is None:
        try:
            return float(actual) > 0
        except (TypeError, ValueError):
            return bool(actual)
    try:
        actual_num = float(actual)
        value_num  = float(value_str)
        if operator in ("gte", ">="): return actual_num >= value_num
        elif operator in ("lte", "<="): return actual_num <= value_num
        elif operator in ("gt", ">"): return actual_num > value_num
        elif operator in ("lt", "<"): return actual_num < value_num
        elif operator in ("eq", "=", "=="): return actual_num == value_num
        elif operator in ("neq", "!=", "<>"): return actual_num != value_num
        else: return actual_num >= value_num
    except (TypeError, ValueError):
        if operator in ("eq", "=", "=="): return str(actual).strip() == str(value_str).strip()
        elif operator in ("in", "contains"): return str(value_str) in str(actual)
        return False


# ──────────────────────────────────────────────
# 결과 포맷
# ──────────────────────────────────────────────

def _get_inspection_cycle_label(rule: dict) -> str:
    val  = rule.get("inspection_cycle_value")
    unit = rule.get("inspection_cycle_unit_code", "")
    if not val and not unit:
        return ""
    unit_label = INSPECTION_CYCLE_UNIT_MAP.get(str(unit), f"코드({unit})")
    if val and str(val) != "1":
        return f"연 {val}회" if unit_label == "연 1회" else f"{val}{unit_label}"
    return unit_label


def _get_appointment_target_label(rule: dict) -> str:
    return APPOINTMENT_TARGET_MAP.get(rule.get("appointment_target_code", ""), rule.get("appointment_target_code", ""))


def format_rule_result(rule: dict, source_label: str = "") -> dict:
    pen_val  = rule.get("penalty_value")
    pen_unit = rule.get("penalty_unit_code", "")
    return {
        "rule_id":               rule.get("rule_id", ""),
        "rule_type":             str(rule.get("rule_type_code", "")),
        "law_name":              rule.get("law_name", ""),
        "law_article":           rule.get("law_article", ""),
        "description":           rule.get("remarks", ""),
        "appointment_target":    _get_appointment_target_label(rule),
        "qualification_required": rule.get("appointment_qualification_code", ""),
        "inspection_cycle":      _get_inspection_cycle_label(rule),
        "penalty_amount":        f"{pen_val} {pen_unit}" if pen_val and pen_unit else (str(pen_val) if pen_val else ""),
        "source_label":          source_label,
        "appointment_required":  rule.get("appointment_required", False),
        "inspection_required":   rule.get("inspection_required", False),
        "action_required":       rule.get("action_required", False),
        "report_required":       rule.get("report_required", False),
        "condition_code":        rule.get("condition_code", ""),
        "condition_value":       rule.get("condition_value"),
    }


# ──────────────────────────────────────────────
# 분류 함수
# ──────────────────────────────────────────────

def _classify_rules(rules: list, triggered: dict):
    for rule in rules:
        _classify_one(rule, format_rule_result(rule), triggered)


def _classify_rules_with_source(rule_source_pairs: list, triggered: dict):
    for rule, source_label in rule_source_pairs:
        _classify_one(rule, format_rule_result(rule, source_label), triggered)


def _classify_one(rule: dict, formatted: dict, triggered: dict):
    category = RULE_TYPE_MAP.get(str(rule.get("rule_type_code", "")), "action")
    if rule.get("appointment_required"):
        triggered["appointment"].append(formatted)
    elif rule.get("inspection_required"):
        triggered["inspection"].append(formatted)
    elif rule.get("report_required"):
        triggered["report"].append(formatted)
    elif rule.get("action_required"):
        triggered["action"].append(formatted)
    else:
        triggered.get(category, triggered["action"]).append(formatted)


# ──────────────────────────────────────────────
# 조건 평가
# ──────────────────────────────────────────────

def _evaluate_conditions(context: dict, rules: list) -> tuple:
    applicable, not_applicable = [], []
    for rule in rules:
        (applicable if _check_rule_conditions(rule, context) else not_applicable).append(rule)
    return applicable, not_applicable


async def _evaluate_equipment_conditions(factory_id, factory_context, rules, supabase):
    # v4.1.1: is_active 컬럼 없음 → 필터 제거
    eq_res = supabase.table("equipment_assets").select(
        "equipment_type_code, quantity, capacity_value"
    ).eq("factory_id", factory_id).execute()
    extra = dict(factory_context)
    for eq in (eq_res.data or []):
        tc = eq.get("equipment_type_code", "")
        if tc in ("elevator", "elev"): extra["elevator_count"] = max(extra.get("elevator_count", 0), 1)
        elif tc == "boiler": extra["boiler_capacity_kw"] = max(extra.get("boiler_capacity_kw", 0), _to_float(eq.get("capacity_value")) or 1)
        elif tc in ("gas", "gas_tank"): extra["gas_capacity_kg"] = max(extra.get("gas_capacity_kg", 0), 1)
        elif tc in ("hazmat", "chemical"): extra["is_hazardous_material"] = 1
        elif tc in ("electric", "transformer"):
            cap = _to_float(eq.get("capacity_value"))
            if cap:
                extra["electrical_capacity_kw"] = max(extra.get("electrical_capacity_kw", 0), cap)
                extra["transformer_capacity_kva"] = max(extra.get("transformer_capacity_kva", 0), cap)
    return _evaluate_conditions(extra, rules)


async def _evaluate_process_conditions(factory_id, factory_context, rules, supabase):
    proc_res = supabase.table("factory_process").select("process_id, source").eq("factory_id", factory_id).eq("is_active", True).execute()
    process_ids = [r["process_id"] for r in (proc_res.data or []) if r.get("source") != "MANUAL"]
    if not process_ids:
        return [], rules
    eq_res = supabase.table("v_equipment_unified").select("facility_name_std, match_band").in_("process_id", process_ids).in_("match_band", ["MUST", "CORE"]).execute()
    inferred = set(r["facility_name_std"] for r in (eq_res.data or []))
    extra = dict(factory_context)
    for name in inferred:
        nl = name.lower()
        if "승강기" in nl or "엘리베이터" in nl: extra["elevator_count"] = max(extra.get("elevator_count", 0), 1)
        if "보일러" in nl: extra["boiler_capacity_kw"] = max(extra.get("boiler_capacity_kw", 0), 1)
        if "가스" in nl: extra["gas_capacity_kg"] = max(extra.get("gas_capacity_kg", 0), 1)
        if "위험물" in nl or "화학" in nl: extra["is_hazardous_material"] = 1
    return _evaluate_conditions(extra, rules)


# ──────────────────────────────────────────────
# 결과 구성 — v4.1.2: not_applicable 별도 처리
# ──────────────────────────────────────────────

def _build_result(applicable, not_applicable, all_rules, mode, evaluated_at,
                  source_pairs=None, include_not_applicable=True, **extra_fields):
    triggered = {"appointment": [], "inspection": [], "action": [], "report": []}
    if source_pairs is not None:
        _classify_rules_with_source(source_pairs, triggered)
    else:
        _classify_rules(applicable, triggered)

    total = sum(len(triggered[k]) for k in triggered)

    result = {
        "engine_version":        ENGINE_VERSION,
        "mode":                  mode,
        "evaluated_at":          evaluated_at,
        "total_rules_checked":   len(all_rules),
        "not_applicable_count":  len(not_applicable),   # 건수만 포함
        "applicable_count":      total,
        "appointment_required":  triggered["appointment"],
        "inspection_required":   triggered["inspection"],
        "action_required":       triggered["action"],
        "report_required":       triggered["report"],
        "summary": {
            "total":       total,
            "appointment": len(triggered["appointment"]),
            "inspection":  len(triggered["inspection"]),
            "action":      len(triggered["action"]),
            "report":      len(triggered["report"]),
        },
        **extra_fields,
    }

    # DB 저장용에만 not_applicable 포함 (include_not_applicable=True)
    if include_not_applicable:
        result["not_applicable"] = [format_rule_result(r) for r in not_applicable]

    return result


# ══════════════════════════════════════════════
# API 엔드포인트
# ══════════════════════════════════════════════

@router.post("/apply/{factory_id}")
async def apply_legal_engine(
    factory_id: str,
    body: Optional[dict] = None,
    mode: str = Query("all"),
):
    """
    시설 등록 기반 법령 판정 (v4.1.2)
    - 응답: summary + applicable 항목만 (not_applicable 제외)
    - DB 저장: not_applicable 포함 전체 저장
    """
    supabase = get_supabase()

    if body and body.get("mode"):
        mode = body["mode"]
    if mode not in ("facility", "process", "equipment", "all"):
        raise HTTPException(status_code=400, detail="mode는 facility/process/equipment/all 중 하나여야 합니다.")

    fac_res = supabase.table("factories").select("*").eq("id", factory_id).single().execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    factory = fac_res.data

    rules_res = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).execute()
    all_rules = rules_res.data or []

    evaluated_at = _now_iso()
    context = _factory_to_context(factory)
    triggered_by_source = {"factory_condition": 0, "registered_equipment": 0, "process_recommended": 0}

    if mode == "facility":
        applicable, not_applicable = _evaluate_conditions(context, all_rules)
        triggered_by_source["factory_condition"] = len(applicable)
        source_pairs = None
    elif mode == "process":
        applicable, not_applicable = await _evaluate_process_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["process_recommended"] = len(applicable)
        source_pairs = None
    elif mode == "equipment":
        applicable, not_applicable = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["registered_equipment"] = len(applicable)
        source_pairs = None
    else:  # all
        fac_app, _  = _evaluate_conditions(context, all_rules)
        triggered_by_source["factory_condition"] = len(fac_app)
        eq_app, _   = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["registered_equipment"] = len(eq_app)
        proc_app, _ = await _evaluate_process_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["process_recommended"] = len(proc_app)

        rule_map = {}
        for r in fac_app:  rule_map[r["rule_id"]] = (r, "🏢 시설조건")
        for r in eq_app:   rule_map.setdefault(r["rule_id"], (r, "⚙️ 등록설비"))
        for r in proc_app: rule_map.setdefault(r["rule_id"], (r, "🔄 공정추천"))

        source_pairs   = list(rule_map.values())
        applicable_ids = {r["rule_id"] for r, _ in source_pairs}
        not_applicable = [r for r in all_rules if r["rule_id"] not in applicable_ids]
        applicable     = []

    # DB 저장용 (not_applicable 포함)
    result_for_db = _build_result(
        applicable, not_applicable, all_rules, mode, evaluated_at,
        source_pairs=source_pairs, include_not_applicable=True,
        factory_id=factory_id, triggered_by_source=triggered_by_source,
    )

    # 응답용 (not_applicable 제외 — 경량)
    result_for_response = _build_result(
        applicable, not_applicable, all_rules, mode, evaluated_at,
        source_pairs=source_pairs, include_not_applicable=False,
        factory_id=factory_id, triggered_by_source=triggered_by_source,
    )

    # factories 테이블 저장 (전체 결과)
    try:
        supabase.table("factories").update({
            "legal_result_json":      result_for_db,
            "last_diagnosis_at":      evaluated_at,
            "diagnosis_status":       "DONE",
            "legal_applicable_count": result_for_db.get("applicable_count", 0),
            "updated_at":             evaluated_at,
        }).eq("id", factory_id).execute()
        print(f"[LEGAL ENGINE v4.1.2] factories 저장 완료: {factory_id} ({result_for_db.get('applicable_count', 0)}건)")
    except Exception as e:
        print(f"[LEGAL ENGINE v4.1.2] factories 저장 실패: {e}")

    # legal_applications 보조 저장
    try:
        supabase.table("legal_applications").upsert({
            "factory_id":     factory_id,
            "engine_version": ENGINE_VERSION,
            "mode":           mode,
            "result_json":    result_for_db,
            "evaluated_at":   evaluated_at,
        }, on_conflict="factory_id,mode").execute()
    except Exception as e:
        print(f"[LEGAL ENGINE v4.1.2] legal_applications 저장 실패 (무시): {e}")

    return {"status": "success", "data": result_for_response}


@router.post("/apply-quote/{quote_id}")
async def apply_legal_engine_from_quote(quote_id: str):
    """견적 survey_data 기반 법령 판정"""
    supabase = get_supabase()
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd:
        raise HTTPException(status_code=400, detail="survey_data가 없습니다.")
    context   = _survey_data_to_context(sd)
    rules_res = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).execute()
    all_rules = rules_res.data or []
    evaluated_at = _now_iso()
    applicable, not_applicable = _evaluate_conditions(context, all_rules)
    result_data = _build_result(
        applicable, not_applicable, all_rules, "facility", evaluated_at,
        include_not_applicable=False,
        quote_id=quote_id, quote_no=qres.data.get("quote_no"),
        source="quote_survey",
        not_applicable_total=len(not_applicable),
        triggered_by_source={"factory_condition": len(applicable)},
    )
    try:
        supabase.table("quotes").update({
            "legal_result_json":      result_data,
            "legal_evaluated_at":     evaluated_at,
            "legal_applicable_count": result_data["applicable_count"],
            "updated_at":             evaluated_at,
        }).eq("id", quote_id).execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] quotes 저장 실패: {e}")
    return {"status": "success", "data": result_data}


@router.get("/quote-result/{quote_id}")
async def get_legal_result_from_quote(quote_id: str):
    """저장된 견적 법령판정 결과 조회"""
    supabase = get_supabase()
    res = supabase.table("quotes").select(
        "id, quote_no, legal_result_json, legal_evaluated_at, legal_applicable_count"
    ).eq("id", quote_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    if not res.data.get("legal_result_json"):
        raise HTTPException(status_code=404, detail="판정 결과 없음.")
    return {"status": "success", "data": {
        "quote_id": quote_id,
        "quote_no": res.data.get("quote_no"),
        "legal_evaluated_at": res.data.get("legal_evaluated_at"),
        "legal_applicable_count": res.data.get("legal_applicable_count"),
        "result": res.data.get("legal_result_json"),
    }}


@router.get("/result/{factory_id}")
async def get_legal_result(factory_id: str, mode: str = Query("all")):
    """
    v4.1.2: factories 우선 조회 — not_applicable 제외하고 반환
    """
    supabase = get_supabase()
    try:
        fac = supabase.table("factories").select(
            "legal_result_json, last_diagnosis_at, legal_applicable_count, diagnosis_status"
        ).eq("id", factory_id).single().execute()
        if fac.data and fac.data.get("legal_result_json"):
            rj = fac.data["legal_result_json"]
            # not_applicable 제거해서 반환
            rj.pop("not_applicable", None)
            return {
                "status": "success",
                "data": {
                    **rj,
                    "last_diagnosis_at":      fac.data.get("last_diagnosis_at"),
                    "legal_applicable_count": fac.data.get("legal_applicable_count"),
                    "diagnosis_status":       fac.data.get("diagnosis_status"),
                }
            }
    except Exception:
        pass
    # fallback
    try:
        res = supabase.table("legal_applications").select("*").eq(
            "factory_id", factory_id
        ).eq("mode", mode).order("evaluated_at", desc=True).limit(1).execute()
        if res.data:
            rj = res.data[0].get("result_json", {})
            rj.pop("not_applicable", None)
            return {"status": "success", "data": rj}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="판정 결과 없음. POST /legal-engine/apply/{factory_id} 먼저 실행하세요.")


@router.get("/summary/{factory_id}")
async def get_legal_summary(factory_id: str):
    """판정 결과 요약"""
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
            "mode":           row.get("mode", "all"),
            "evaluated_at":   row.get("evaluated_at"),
            "summary":        rj.get("summary", {}),
            "engine_version": rj.get("engine_version", ""),
        })
    return {"status": "success", "data": {"factory_id": factory_id, "results": results}}


# ──────────────────────────────────────────────
# 법령결과 → inspection_sets 자동 생성
# ──────────────────────────────────────────────

@router.post("/create-inspection-sets/{factory_id}")
async def create_inspection_sets_from_legal(factory_id: str):
    """
    factories.legal_result_json의 inspection_required →
    inspection_sets 자동 생성 (멱등성 보장). v4.1.0 신규
    """
    supabase = get_supabase()
    fac = supabase.table("factories").select(
        "id, company_id, legal_result_json"
    ).eq("id", factory_id).single().execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    result_json = fac.data.get("legal_result_json")
    if not result_json:
        raise HTTPException(status_code=400, detail="법령판정 결과가 없습니다. 먼저 POST /legal-engine/apply/{factory_id} 실행하세요.")

    company_id       = fac.data.get("company_id")
    inspection_rules = result_json.get("inspection_required", [])
    if not inspection_rules:
        return {"status": "success", "message": "생성할 점검 항목이 없습니다.", "data": {"created": 0}}

    supabase.table("inspection_sets").delete().eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").execute()

    insert_rows = []
    for rule in inspection_rules:
        cycle_label = rule.get("inspection_cycle", "")
        law_name    = rule.get("law_name", "")
        rule_id     = rule.get("rule_id", "")
        cycle_unit, cycle_value = "year", 1
        if "월 1회" in cycle_label or "매월" in cycle_label: cycle_unit, cycle_value = "month", 1
        elif "반기" in cycle_label: cycle_unit, cycle_value = "month", 6
        elif "분기" in cycle_label: cycle_unit, cycle_value = "month", 3
        elif "2년" in cycle_label:  cycle_unit, cycle_value = "year",  2
        elif "3년" in cycle_label:  cycle_unit, cycle_value = "year",  3
        elif "4년" in cycle_label:  cycle_unit, cycle_value = "year",  4
        elif "5년" in cycle_label:  cycle_unit, cycle_value = "year",  5
        elif "10년" in cycle_label: cycle_unit, cycle_value = "year", 10
        elif "연 2회" in cycle_label: cycle_unit, cycle_value = "month", 6
        insert_rows.append({
            "company_id":          company_id,
            "factory_id":          factory_id,
            "inspection_set_name": f"{law_name} 점검",
            "inspection_set_code": rule_id,
            "legal_rule_id":       rule_id,
            "law_name":            law_name,
            "law_article":         rule.get("law_article", ""),
            "cycle_unit":          cycle_unit,
            "cycle_value":         cycle_value,
            "description":         rule.get("description", ""),
            "source":              "LEGAL_ENGINE",
            "is_active":           True,
        })
    if not insert_rows:
        return {"status": "success", "message": "변환할 항목 없음", "data": {"created": 0}}

    created = 0
    for i in range(0, len(insert_rows), 50):
        res = supabase.table("inspection_sets").insert(insert_rows[i:i+50]).execute()
        created += len(res.data or [])

    return {
        "status": "success",
        "message": f"{created}개 점검 세트가 자동 생성됐습니다.",
        "data": {"factory_id": factory_id, "created": created, "source_rules": len(inspection_rules)},
    }


@router.get("/debug/context/{quote_id}")
async def debug_quote_context(quote_id: str):
    """[개발용] 견적 context 확인"""
    supabase = get_supabase()
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd:
        raise HTTPException(status_code=400, detail="survey_data 없음")
    return {"status": "success", "quote_no": qres.data.get("quote_no"), "context": _survey_data_to_context(sd)}
