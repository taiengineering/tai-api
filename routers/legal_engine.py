"""
법령 판정 엔진 라우터 — v4.2.0
=================================
v4.2.0: 3단계 진단 API 추가
  - POST /legal-engine/diagnose/step1  (1단계: 기초진단)
  - POST /legal-engine/diagnose/step2  (2단계: 공정진단)
  - POST /legal-engine/diagnose/step3  (3단계: 설비진단)
  - GET  /legal-engine/diagnose/{factory_id}/latest
  - GET  /legal-engine/diagnose/{factory_id}/history
  - 헬퍼: _evaluate_condition(), _save_diagnosis_result(), _create_report_events_from_rules()
  - DB: factory_diagnosis_results, diagnosis_rule_results 테이블 활용
  - 기존 /apply, /apply-quote, /result 등 하위 호환 유지

v4.1.2: not_applicable 응답 제거 (경량화)
v4.1.1: equipment_assets is_active 컬럼 없음 → 필터 제거
v4.1.0: 파이프라인 전체 연결
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone, date, timedelta
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "4.2.0"


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
# 조건 체크 (기존 엔진용)
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
# 조건 평가 (기존 엔진)
# ──────────────────────────────────────────────

def _evaluate_conditions(context: dict, rules: list) -> tuple:
    applicable, not_applicable = [], []
    for rule in rules:
        (applicable if _check_rule_conditions(rule, context) else not_applicable).append(rule)
    return applicable, not_applicable


async def _evaluate_equipment_conditions(factory_id, factory_context, rules, supabase):
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
# 결과 구성
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
        "not_applicable_count":  len(not_applicable),
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

    if include_not_applicable:
        result["not_applicable"] = [format_rule_result(r) for r in not_applicable]

    return result


# ══════════════════════════════════════════════
# 기존 API 엔드포인트 (하위 호환)
# ══════════════════════════════════════════════

@router.post("/apply/{factory_id}")
async def apply_legal_engine(
    factory_id: str,
    body: Optional[dict] = None,
    mode: str = Query("all"),
):
    """시설 등록 기반 법령 판정 (v4.2.0 — 하위 호환 유지)"""
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

    result_for_db = _build_result(
        applicable, not_applicable, all_rules, mode, evaluated_at,
        source_pairs=source_pairs, include_not_applicable=True,
        factory_id=factory_id, triggered_by_source=triggered_by_source,
    )
    result_for_response = _build_result(
        applicable, not_applicable, all_rules, mode, evaluated_at,
        source_pairs=source_pairs, include_not_applicable=False,
        factory_id=factory_id, triggered_by_source=triggered_by_source,
    )

    try:
        supabase.table("factories").update({
            "legal_result_json":      result_for_db,
            "last_diagnosis_at":      evaluated_at,
            "diagnosis_status":       "DONE",
            "legal_applicable_count": result_for_db.get("applicable_count", 0),
            "updated_at":             evaluated_at,
        }).eq("id", factory_id).execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] factories 저장 실패: {e}")

    try:
        supabase.table("legal_applications").upsert({
            "factory_id":     factory_id,
            "engine_version": ENGINE_VERSION,
            "mode":           mode,
            "result_json":    result_for_db,
            "evaluated_at":   evaluated_at,
        }, on_conflict="factory_id,mode").execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] legal_applications 저장 실패 (무시): {e}")

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


class DiagnoseStep1Body(BaseModel):
    """법령 진단 1단계 — 시설 ID + 섹터 + 섹터별 input 객체"""

    factory_id: str = Field(..., description="factories.id")
    sector: str = Field(
        ...,
        description="BUILDING | MANUFACTURING | CONSTRUCTION | SPECIAL_FACILITY",
    )
    input: Dict[str, Any] = Field(default_factory=dict)


ALLOWED_DIAGNOSE_SECTORS = frozenset(
    {"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"}
)

# master_building_legal_rules.condition_code → 시설 컨텍스트 키 (factories / 설문과 동일 의미)
CONDITION_CODE_TO_CONTEXT_KEY: Dict[str, str] = {
    "employee_count": "worker_count",
    "building_area": "total_floor_area",
    "electrical_capacity_kw": "electric_capacity",
    "floor_count": "floor_count",
    "elevator_count": "elevator_count",
    "boiler_capacity_kw": "boiler_capacity_kw",
    "boiler_capacity_th": "boiler_capacity_th",
    "gas_capacity_kg": "gas_capacity_kg",
    "gas_capacity_m3": "gas_capacity_m3",
    "transformer_capacity_kva": "transformer_capacity_kva",
    "annual_energy_toe": "annual_energy_toe",
    "construction_amount": "construction_amount",
    "contractor_count": "contractor_count",
    "is_hazardous_material": "is_hazardous_material",
    "is_multi_use": "is_multi_use",
    "is_factory_registered": "is_factory_registered",
}


def _normalize_sector_db(sector: str) -> str:
    u = sector.strip().upper()
    if u == "SPECIAL_FACILITY":
        return "SPECIAL"
    return u


def _truthy(v: Any) -> bool:
    if v is True:
        return True
    if v in (False, None, "", 0):
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _input_to_facility_context(sector: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    """프론트 섹터별 input → 룰 매칭용 컨텍스트."""
    sec = sector.strip().upper()
    ctx: Dict[str, Any] = {
        "worker_count": 0,
        "total_floor_area": 0.0,
        "electric_capacity": 0.0,
        "building_use_code": "",
        "ksic_code": "",
        "floor_count": 0,
        "construction_amount": 0.0,
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
    }
    if sec == "BUILDING":
        ctx["building_use_code"] = str(inp.get("building_use") or inp.get("building_use_code") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or 0)
        ctx["floor_count"] = int(inp.get("floor_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
    elif sec == "MANUFACTURING":
        ctx["ksic_code"] = str(inp.get("ksic_major") or inp.get("ksic_code") or "")
        ctx["worker_count"] = int(inp.get("worker_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["has_chemical_substance"] = 1 if _truthy(inp.get("has_chemical_substance")) else 0
        ctx["has_boiler"] = 1 if _truthy(inp.get("has_boiler")) else 0
    elif sec == "CONSTRUCTION":
        eok = float(inp.get("contract_amount_eok") or 0)
        ctx["construction_amount"] = eok * 100_000_000.0
        ctx["worker_count"] = int(inp.get("worker_count") or 0)
        ctx["building_use_code"] = str(inp.get("construction_type") or "")
        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0
    elif sec in ("SPECIAL_FACILITY", "SPECIAL"):
        ctx["building_use_code"] = str(inp.get("facility_type") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or 0)
        ctx["hospital_beds"] = int(inp.get("hospital_beds") or 0)
        ctx["student_count"] = int(inp.get("student_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or 0)
    return ctx


def _risk_level(applicable_count: int, appointment_n: int) -> str:
    if applicable_count >= 12 or appointment_n >= 4:
        return "HIGH"
    if applicable_count >= 5 or appointment_n >= 1:
        return "MEDIUM"
    return "LOW"


def _numeric_compare(actual: float, operator: str, value: float) -> bool:
    op = (operator or "gte").lower()
    try:
        if op in ("gte", ">="):
            return actual >= value
        if op in ("lte", "<="):
            return actual <= value
        if op in ("gt", ">"):
            return actual > value
        if op in ("lt", "<"):
            return actual < value
        if op in ("eq", "=", "=="):
            return actual == value
    except (TypeError, ValueError):
        return False
    return False


def _db_rule_matches_facility(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """DB 정규화 룰( condition_code / condition_operator_code / condition_value ) 시설 매칭."""
    cc = rule.get("condition_code")
    cv = rule.get("condition_value")
    if not cc or cv is None:
        return False
    ctx_key = CONDITION_CODE_TO_CONTEXT_KEY.get(cc, cc)
    actual = context.get(ctx_key)
    if actual is None:
        actual = context.get(cc)
    if actual is None:
        return False
    try:
        actual_num = float(actual)
        value_num = float(cv)
    except (TypeError, ValueError):
        return str(actual) == str(cv) and (rule.get("condition_operator_code") or "eq").lower() in ("eq", "=", "==")
    op = rule.get("condition_operator_code") or "gte"
    return _numeric_compare(actual_num, op, value_num)


def format_rule_result_db(rule: Dict[str, Any]) -> Dict[str, Any]:
    """master_building_legal_rules 행 → 프론트/기존 format_rule_result 호환."""
    desc = (rule.get("obligation_summary") or rule.get("remarks") or "").strip()
    return {
        "rule_id": rule.get("rule_id", ""),
        "rule_type": str(rule.get("rule_type_code") or ""),
        "law_name": rule.get("law_name") or "",
        "law_article": rule.get("law_article") or "",
        "description": desc,
        "appointment_target": rule.get("appointment_target_code") or "",
        "qualification_required": rule.get("qualification_type") or "",
        "inspection_cycle": "",
        "penalty_amount": (rule.get("penalty_summary") or "") or "",
        "source_label": "",
    }


def _classify_rules_db(rules: List[Dict[str, Any]], triggered: Dict[str, List]) -> None:
    """DB 플래그(appointment_required 등)로 분류."""
    for rule in rules:
        formatted = format_rule_result_db(rule)
        if rule.get("appointment_required"):
            triggered["appointment"].append(formatted)
        elif rule.get("inspection_required"):
            triggered["inspection"].append(formatted)
        elif rule.get("report_required"):
            triggered["report"].append(formatted)
        elif rule.get("action_required"):
            triggered["action"].append(formatted)
        else:
            triggered["action"].append(formatted)


def _evaluate_facility_conditions_db(factory: Dict[str, Any], rules: List[Dict[str, Any]]) -> tuple:
    applicable: List[Dict[str, Any]] = []
    not_applicable: List[Dict[str, Any]] = []
    for rule in rules:
        if _db_rule_matches_facility(rule, factory):
            applicable.append(rule)
        else:
            not_applicable.append(rule)
    return applicable, not_applicable


# ──────────────────────────────────────────────
# POST /legal-engine/diagnose/step1
# 법령 진단 1단계 — factory_id + 섹터·input (diagnosis_stage = 1 룰)
# ──────────────────────────────────────────────
@router.post("/diagnose/step1")
async def diagnose_step1(body: DiagnoseStep1Body):
    sector_raw = body.sector.strip().upper()
    if sector_raw not in ALLOWED_DIAGNOSE_SECTORS:
        raise HTTPException(
            status_code=400,
            detail="sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.",
        )

    factory_id = (body.factory_id or "").strip()
    if not factory_id:
        raise HTTPException(status_code=400, detail="factory_id가 필요합니다.")

    supabase = get_supabase()
    fac_check = supabase.table("factories").select("id").eq("id", factory_id).limit(1).execute()
    if not fac_check.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    sector_db = _normalize_sector_db(sector_raw)
    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .eq("sector", sector_db)
        .eq("diagnosis_stage", 1)
        .execute()
    )
    all_rules = rules_res.data or []

    inp = body.input if isinstance(body.input, dict) else {}
    facility_ctx = _input_to_facility_context(sector_raw, inp)

    evaluated_at = datetime.now().isoformat()
    applicable, not_applicable = _evaluate_facility_conditions_db(facility_ctx, all_rules)

    triggered: Dict[str, List] = {
        "appointment": [],
        "inspection": [],
        "action": [],
        "report": [],
        "not_applicable": [],
    }
    _classify_rules_db(applicable, triggered)
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result_db(r))

    total_applicable = (
        len(triggered["appointment"])
        + len(triggered["inspection"])
        + len(triggered["action"])
        + len(triggered["report"])
    )

    law_names = sorted(
        {x.get("law_name") for x in applicable if x.get("law_name")}
    )

    cat_labels = [
        ("appointment", "선임"),
        ("inspection", "점검"),
        ("action", "조치"),
        ("report", "신고"),
    ]
    obligations: List[Dict[str, Any]] = []
    for key, label in cat_labels:
        items = triggered[key]
        if items:
            obligations.append({"category": key, "label": label, "items": items})

    rules_table: List[Dict[str, Any]] = []
    for key, label in cat_labels:
        for row in triggered[key]:
            rules_table.append({"category": label, **row})

    appointment_n = len(triggered["appointment"])
    risk = _risk_level(total_applicable, appointment_n)

    law_cats: List[str] = []
    seen: set = set()
    for x in applicable:
        c = (x.get("law_category_code") or x.get("law_name") or "").strip()
        if c and c not in seen:
            seen.add(c)
            law_cats.append(c)

    key_obligations: List[str] = []
    for x in applicable[:20]:
        t = (x.get("obligation_summary") or x.get("remarks") or "").strip()
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
            }
        )

    result_data = {
        "factory_id": factory_id,
        "sector": sector_raw,
        "step": 1,
        "engine_version": ENGINE_VERSION,
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
        "report_required": triggered["report"],
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
        },
    }
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
    """v4.1.2: factories 우선 조회 — not_applicable 제외하고 반환"""
    supabase = get_supabase()
    try:
        fac = supabase.table("factories").select(
            "legal_result_json, last_diagnosis_at, legal_applicable_count, diagnosis_status"
        ).eq("id", factory_id).single().execute()
        if fac.data and fac.data.get("legal_result_json"):
            rj = fac.data["legal_result_json"]
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


@router.post("/create-inspection-sets/{factory_id}")
async def create_inspection_sets_from_legal(factory_id: str):
    """inspection_sets 자동 생성 (멱등성 보장)"""
    supabase = get_supabase()
    fac = supabase.table("factories").select(
        "id, company_id, legal_result_json"
    ).eq("id", factory_id).single().execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    result_json = fac.data.get("legal_result_json")
    if not result_json:
        raise HTTPException(status_code=400, detail="법령판정 결과가 없습니다.")

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


# ══════════════════════════════════════════════
# 3단계 진단 헬퍼 함수 (v4.2.0 신규)
# ══════════════════════════════════════════════

def _evaluate_condition(rule: dict, input_data: dict) -> bool:
    """
    3단계 진단용 조건 평가.
    condition_1_field/operator/value, condition_2_field/operator/value 평가.
    IN / NOT_IN / >= / <= / == / ==true / ==false 연산자 지원.
    """
    def check(field, operator, value, data):
        if not field or field not in data:
            return True  # 해당 필드 없으면 조건 스킵
        actual = data[field]
        if actual is None:
            return False
        try:
            if operator == '>=':
                return float(actual) >= float(value)
            elif operator == '<=':
                return float(actual) <= float(value)
            elif operator == '>':
                return float(actual) > float(value)
            elif operator == '<':
                return float(actual) < float(value)
            elif operator == '==':
                return str(actual) == str(value)
            elif operator == 'IN':
                vals = [v.strip() for v in str(value).split(',')]
                return str(actual) in vals
            elif operator == 'NOT_IN':
                vals = [v.strip() for v in str(value).split(',')]
                return str(actual) not in vals
            elif operator == '==true':
                return actual is True or str(actual).lower() == 'true'
            elif operator == '==false':
                return actual is False or str(actual).lower() == 'false'
        except Exception:
            return False
        return True

    c1_ok = check(
        rule.get('condition_1_field'),
        rule.get('condition_1_operator'),
        rule.get('condition_1_value'),
        input_data
    )
    if not c1_ok:
        return False

    c2_field = rule.get('condition_2_field')
    if c2_field:
        c2_ok = check(
            c2_field,
            rule.get('condition_2_operator'),
            rule.get('condition_2_value'),
            input_data
        )
        mode = rule.get('condition_mode', 'AND')
        if mode == 'AND' and not c2_ok:
            return False
        if mode == 'OR' and not (c1_ok or c2_ok):
            return False

    return True


def _determine_risk_level(rule_count: int) -> str:
    if rule_count >= 10:
        return 'HIGH'
    elif rule_count >= 5:
        return 'MEDIUM'
    return 'LOW'


def _save_diagnosis_result(
    supabase, factory_id: str, sector: str, stage: int,
    input_data: dict, matched_rules: list
) -> dict:
    """진단 결과 저장. 이전 최신 결과는 is_latest=False."""
    # 기존 최신 결과 무효화
    try:
        supabase.table('factory_diagnosis_results').update(
            {'is_latest': False}
        ).eq('factory_id', factory_id).eq('is_latest', True).execute()
    except Exception:
        pass

    law_categories = list(dict.fromkeys(
        r.get('law_name', '') for r in matched_rules if r.get('law_name')
    ))
    key_obligations = [
        r.get('obligation_summary') or r.get('rule_name', '')
        for r in matched_rules[:5]
    ]
    has_appointment = any(
        r.get('rule_type') == 'APPOINTMENT' or r.get('appointment_required')
        for r in matched_rules
    )

    result_data = {
        'applicable_law_categories': law_categories,
        'appointment_required':      has_appointment,
        'key_obligations':           key_obligations,
        'risk_level':                _determine_risk_level(len(matched_rules)),
        'rules': [
            {
                'rule_code':   r.get('rule_code') or r.get('rule_id'),
                'rule_name':   r.get('rule_name') or r.get('remarks', ''),
                'law_name':    r.get('law_name', ''),
                'law_article': r.get('law_article', ''),
                'obligation':  r.get('obligation_summary') or r.get('rule_name', ''),
                'rule_type':   r.get('rule_type') or str(r.get('rule_type_code', '')),
                'stage':       r.get('diagnosis_stage', 1),
            }
            for r in matched_rules
        ]
    }

    try:
        res = supabase.table('factory_diagnosis_results').insert({
            'factory_id':      factory_id,
            'sector':          sector,
            'diagnosis_stage': stage,
            'input_data':      input_data,
            'result_data':     result_data,
            'rule_count':      len(matched_rules),
            'is_latest':       True,
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        print(f"[DIAGNOSIS] 결과 저장 실패: {e}")
        return {'result_data': result_data}


def _create_report_events_from_rules(
    supabase, factory_id: str, matched_rules: list
):
    """REPORT / APPOINTMENT 타입 룰에서 report_events 자동 생성."""
    event_types = {'REPORT', 'APPOINTMENT', 'NOTIFICATION'}
    for rule in matched_rules:
        rule_type = rule.get('rule_type') or ''
        if rule_type not in event_types and not rule.get('report_required'):
            continue
        form_code = rule.get('form_code')
        if not form_code:
            continue
        # 중복 방지
        try:
            existing = supabase.table('report_events').select('id') \
                .eq('factory_id', factory_id) \
                .eq('form_code', form_code) \
                .eq('status', 'PENDING').execute()
            if existing.data:
                continue
        except Exception:
            pass
        due_days = rule.get('due_days') or 14
        due_date = (date.today() + timedelta(days=due_days)).isoformat()
        try:
            supabase.table('report_events').insert({
                'factory_id':   factory_id,
                'rule_code':    rule.get('rule_code') or rule.get('rule_id'),
                'form_code':    form_code,
                'trigger_date': date.today().isoformat(),
                'due_date':     due_date,
                'status':       'PENDING',
            }).execute()
        except Exception as e:
            print(f"[DIAGNOSIS] report_events 생성 실패: {e}")


# ══════════════════════════════════════════════
# 3단계 진단 API (v4.2.0) — 1단계는 상단 POST /diagnose/step1 (Pydantic) 단일 정의
# ══════════════════════════════════════════════


@router.post("/diagnose/step2")
def diagnose_step2(body: dict):
    """
    2단계 공정 진단 (유료).
    1단계 결과 + 공정 선택 → 법령별 의무 목록 + 신고 일정.

    body:
    {
      "factory_id": "uuid",
      "diagnosis_id": "1단계 diagnosis_id (선택)",
      "processes": ["process_code1", "process_code2"],
      "construction_types": []
    }
    """
    supabase = get_supabase()

    factory_id         = body.get('factory_id')
    diagnosis_id       = body.get('diagnosis_id')
    processes          = body.get('processes', [])
    construction_types = body.get('construction_types', [])

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

    # 1단계 결과 조회
    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table('factory_diagnosis_results').select('*') \
                .eq('id', diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass

    sector     = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = dict((prev or {}).get('input_data') or {})
    input_data['processes']          = processes
    input_data['construction_types'] = construction_types
    input_data['sector']             = sector

    # stage<=2 룰 조회
    res = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .lte('diagnosis_stage', 2) \
        .eq('is_active', True) \
        .execute()
    rules   = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
    _create_report_events_from_rules(supabase, factory_id, matched)

    # 1단계 대비 추가된 룰
    prev_codes = set()
    if prev:
        prev_rules = (prev.get('result_data') or {}).get('rules', [])
        prev_codes = {r.get('rule_code') for r in prev_rules}
    added = [r for r in matched if (r.get('rule_code') or r.get('rule_id')) not in prev_codes]

    result = diagnosis.get('result_data', {})
    return {
        'status':            'success',
        'diagnosis_id':      diagnosis.get('id'),
        'stage':             2,
        'sector':            sector,
        'rule_count':        len(matched),
        'added_rule_count':  len(added),
        'summary': {
            'applicable_law_categories': result.get('applicable_law_categories', []),
            'appointment_required':      result.get('appointment_required', False),
            'key_obligations':           result.get('key_obligations', []),
            'risk_level':                result.get('risk_level', 'LOW'),
        },
        'rules': result.get('rules', []),
        'added_rules': [
            {
                'rule_code':   r.get('rule_code') or r.get('rule_id'),
                'rule_name':   r.get('rule_name') or r.get('remarks', ''),
                'law_article': r.get('law_article', ''),
            }
            for r in added
        ],
    }


@router.post("/diagnose/step3")
def diagnose_step3(body: dict):
    """
    3단계 설비 진단 (유료).
    2단계 결과 + 설비 등록 → 설비별 법정검사 D-day 자동 계산.

    body:
    {
      "factory_id": "uuid",
      "diagnosis_id": "2단계 diagnosis_id (선택)",
      "equipments": [
        {
          "equipment_code": "ELEVATOR",
          "capacity": 1000,
          "unit": "kg",
          "installed_date": "2020-01-01",
          "last_inspection_date": "2023-06-01"
        }
      ]
    }
    """
    supabase    = get_supabase()
    factory_id  = body.get('factory_id')
    diagnosis_id = body.get('diagnosis_id')
    equipments  = body.get('equipments', [])

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table('factory_diagnosis_results').select('*') \
                .eq('id', diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass

    sector     = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = dict((prev or {}).get('input_data') or {})
    input_data['equipments'] = equipments
    input_data['sector']     = sector

    # stage<=3 전체 룰
    res = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .lte('diagnosis_stage', 3) \
        .eq('is_active', True) \
        .execute()
    rules   = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 3, input_data, matched)

    # 설비별 법정검사 D-day 계산
    inspection_schedules = []
    today = date.today()
    for equip in equipments:
        eq_code    = equip.get('equipment_code', '')
        last_dt    = equip.get('last_inspection_date')
        cycle_years = 2  # 기본값 (추후 DB 기준으로 확장)
        if last_dt:
            try:
                last = date.fromisoformat(last_dt)
                next_due  = date(last.year + cycle_years, last.month, last.day)
                days_left = (next_due - today).days
                inspection_schedules.append({
                    'equipment_code':       eq_code,
                    'capacity':             equip.get('capacity'),
                    'unit':                 equip.get('unit'),
                    'last_inspection_date': last_dt,
                    'next_due_date':        next_due.isoformat(),
                    'cycle_years':          cycle_years,
                    'days_left':            days_left,
                    'status': 'OVERDUE'  if days_left < 0
                              else ('URGENT' if days_left <= 30 else 'NORMAL'),
                })
            except Exception:
                pass

    overdue_count  = sum(1 for s in inspection_schedules if s['status'] == 'OVERDUE')
    upcoming_count = sum(1 for s in inspection_schedules if s['status'] == 'URGENT')

    return {
        'status':               'success',
        'diagnosis_id':         diagnosis.get('id'),
        'stage':                3,
        'sector':               sector,
        'rule_count':           len(matched),
        'inspection_schedules': inspection_schedules,
        'overdue_count':        overdue_count,
        'upcoming_count':       upcoming_count,
    }


@router.get("/diagnose/{factory_id}/latest")
def get_latest_diagnosis(factory_id: str):
    """최신 진단 결과 조회"""
    supabase = get_supabase()
    try:
        res = supabase.table('factory_diagnosis_results').select('*') \
            .eq('factory_id', factory_id) \
            .eq('is_latest', True) \
            .order('created_at', desc=True) \
            .limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail='진단 결과 없음')
        return {'status': 'success', 'data': res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnose/{factory_id}/history")
def get_diagnosis_history(
    factory_id: str,
    page:      int = Query(1,  ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """진단 이력 목록"""
    supabase = get_supabase()
    offset = (page - 1) * page_size
    res = supabase.table('factory_diagnosis_results').select(
        'id, sector, diagnosis_stage, rule_count, is_latest, created_at',
        count='exact'
    ).eq('factory_id', factory_id) \
     .order('created_at', desc=True) \
     .range(offset, offset + page_size - 1).execute()
    return {
        'status': 'success',
        'data': {
            'items':     res.data or [],
            'total':     res.count or 0,
            'page':      page,
            'page_size': page_size,
        }
    }
