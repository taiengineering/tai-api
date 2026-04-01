"""
법령 판정 엔진 라우터 — v5.2.0
=================================
v5.2.0: 건설 법령진단 공정·작업 KCSC 연동
  - diagnose/step2: kcsc_process_ids → kcsc_process_master에서 work_type_code 자동 조회
    기존 construction_work_types 직접 입력 하위 호환 유지
    응답에 kcsc_process_summary 추가
  - diagnose/step3: construction_work_ids / kcsc_work_ids → kcsc_work_master에서
    equipment_type_codes 자동 조회, 기존 equipments 직접 입력 하위 호환 유지
    응답에 kcsc_work_summary, equipment_codes_applied 추가
v5.1.0: 건설 섹터 법령엔진 버그 수정
  1. CONDITION_CODE_TO_CONTEXT_KEY에 "contract_amount": "construction_amount" 추가 (핵심 버그)
  2. CONSTRUCTION context 완성 (site_type, subcon_workers, contract_amount 직접 매핑)
  3. diagnose/step1 결과에 construction_summary 블록 추가
v4.4.3: create-inspection-sets 타임아웃 근본 해결
v4.4.0: diagnose/step1 DB 저장 추가
v4.2.0: 3단계 진단 API 추가
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone, date, timedelta
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "5.2.0"  # v5.2.0: 건설 KCSC 공정·작업 연동


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
    "001": "일 1회", "002": "주 1회", "003": "월 1회",
    "004": "분기 1회", "005": "반기 1회", "006": "연 1회",
    "007": "2년마다", "008": "5년마다", "009": "4년마다",
    "010": "3년마다", "011": "3년마다", "012": "10년마다",
    "013": "5년마다(시설)",
}

CYCLE_CODE_MAP = {
    "001": ("day",   1),
    "002": ("week",  1),
    "003": ("month", 1),
    "004": ("month", 3),
    "005": ("month", 6),
    "006": ("year",  1),
    "007": ("year",  2),
    "008": ("year",  5),
    "009": ("year",  4),
    "010": ("year",  3),
    "011": ("year",  3),
    "012": ("year", 10),
    "013": ("year",  5),
}

RULE_TYPE_MAP = {
    "001": "appointment", "002": "inspection", "003": "report",
    "004": "action", "005": "action", "007": "action", "008": "action",
}

CONSTRUCTION_RELEVANT_LAW_PREFIXES = [
    "산업안전보건", "중대재해", "건설산업", "건설기술",
    "근로기준", "산업재해보상", "전기안전",
]


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
# obligation_type 결정
# ──────────────────────────────────────────────

def _resolve_obligation_type(rule: dict) -> str:
    ot = (rule.get("obligation_type") or "").strip().upper()
    if ot:
        return ot
    if rule.get("appointment_required"):
        return "APPOINT"
    if rule.get("notify_required"):
        return "NOTIFY"
    if rule.get("report_required"):
        return "REPORT"
    if rule.get("inspection_required"):
        return "INSPECT"
    if rule.get("action_required"):
        return "ACTION"
    return "OTHER"


def _is_notify(rule: dict) -> bool:
    ot = (rule.get("obligation_type") or "").strip().upper()
    return ot == "NOTIFY" or bool(rule.get("notify_required"))


def _is_report(rule: dict) -> bool:
    ot = (rule.get("obligation_type") or "").strip().upper()
    if ot == "REPORT":
        return True
    return bool(rule.get("report_required")) and not _is_notify(rule)


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
        "obligation_type":       _resolve_obligation_type(rule),
        "condition_code":        rule.get("condition_code", ""),
        "condition_value":       rule.get("condition_value"),
    }


def _calc_due_date(due_days) -> dict:
    if not due_days:
        return {}
    d = int(due_days)
    due_date = (date.today() + timedelta(days=d)).isoformat()
    urgency = "IMMEDIATE" if d <= 3 else ("URGENT" if d <= 14 else "NORMAL")
    return {"due_days": d, "due_date": due_date, "urgency": urgency}


def format_rule_result_db(rule: Dict[str, Any]) -> Dict[str, Any]:
    desc = (rule.get("obligation_summary") or rule.get("remarks") or "").strip()
    return {
        "rule_id":               rule.get("rule_id", ""),
        "rule_type":             str(rule.get("rule_type_code") or ""),
        "law_name":              rule.get("law_name") or "",
        "law_article":           rule.get("law_article") or "",
        "description":           desc,
        "obligation_summary":    desc,
        "appointment_target":    rule.get("appointment_target_code") or "",
        "qualification_required": rule.get("qualification_type") or "",
        "inspection_cycle":      "",
        "penalty_amount":        rule.get("penalty_summary") or "",
        "penalty_summary":       rule.get("penalty_summary") or "",
        "source_label":          "",
        "obligation_type":       _resolve_obligation_type(rule),
        "appointment_required":  bool(rule.get("appointment_required")),
        "inspection_required":   bool(rule.get("inspection_required")),
        "action_required":       bool(rule.get("action_required")),
        "report_required":       bool(rule.get("report_required")),
        "notify_required":       bool(rule.get("notify_required")),
        "form_code":             rule.get("form_code") or "",
        "form_url":              rule.get("form_url") or "",
        "due_days":              rule.get("due_days"),
        "due_info":              _calc_due_date(rule.get("due_days")),
        "sector":                rule.get("sector") or "",
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
    if rule.get("appointment_required"):
        triggered["appointment"].append(formatted)
    elif rule.get("inspection_required"):
        triggered["inspection"].append(formatted)
    elif rule.get("report_required"):
        triggered["report"].append(formatted)
    elif rule.get("action_required"):
        triggered["action"].append(formatted)
    else:
        triggered.get(RULE_TYPE_MAP.get(str(rule.get("rule_type_code", "")), "action"),
                      triggered["action"]).append(formatted)


def _classify_rules_db(rules: List[Dict[str, Any]], triggered: Dict[str, List]) -> None:
    for rule in rules:
        formatted = format_rule_result_db(rule)
        ot = (rule.get("obligation_type") or "").strip().upper()
        if rule.get("appointment_required") or ot == "APPOINT":
            triggered["appointment"].append(formatted)
        elif rule.get("inspection_required") or ot == "INSPECT":
            triggered["inspection"].append(formatted)
        elif rule.get("notify_required") or ot == "NOTIFY":
            triggered.setdefault("notify", []).append(formatted)
        elif rule.get("report_required") or ot == "REPORT":
            triggered["report"].append(formatted)
        elif rule.get("action_required") or ot == "ACTION":
            triggered["action"].append(formatted)
        else:
            triggered["action"].append(formatted)


# ──────────────────────────────────────────────
# 조건 평가
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
    rep_list = triggered["report"]
    notify_list = [x for x in rep_list if _is_notify(x)]
    report_only = [x for x in rep_list if not _is_notify(x)]

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
            "report":      len(report_only),
            "notify":      len(notify_list),
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
    """시설 등록 기반 법령 판정 (v5.2.0 — 하위 호환 유지)"""
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
    else:
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


# ──────────────────────────────────────────────
# Pydantic 모델
# ──────────────────────────────────────────────

class DiagnoseStep1Body(BaseModel):
    factory_id: Optional[str] = Field(None, description="factories.id (없으면 익명 진단)")
    sector: str = Field(..., description="BUILDING | MANUFACTURING | CONSTRUCTION | SPECIAL_FACILITY")
    input: Optional[Dict[str, Any]] = Field(default_factory=dict)

    building_use_type: Optional[str] = None
    employee_count: Optional[int] = None
    floor_area: Optional[float] = None
    worker_count: Optional[int] = None
    total_floor_area: Optional[float] = None
    electric_capacity: Optional[float] = None
    floor_count: Optional[int] = None
    contract_amount_eok: Optional[float] = None
    ksic_major: Optional[str] = None
    facility_type: Optional[str] = None


ALLOWED_DIAGNOSE_SECTORS = frozenset(
    {"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"}
)

CONDITION_CODE_TO_CONTEXT_KEY: Dict[str, str] = {
    "employee_count":           "worker_count",
    "building_area":            "total_floor_area",
    "electrical_capacity_kw":   "electric_capacity",
    "floor_count":              "floor_count",
    "elevator_count":           "elevator_count",
    "boiler_capacity_kw":       "boiler_capacity_kw",
    "boiler_capacity_th":       "boiler_capacity_th",
    "gas_capacity_kg":          "gas_capacity_kg",
    "gas_capacity_m3":          "gas_capacity_m3",
    "transformer_capacity_kva": "transformer_capacity_kva",
    "annual_energy_toe":        "annual_energy_toe",
    "construction_amount":      "construction_amount",
    "contract_amount":          "construction_amount",   # v5.1.0: 핵심 버그 수정
    "contractor_count":         "contractor_count",
    "is_hazardous_material":    "is_hazardous_material",
    "is_multi_use":             "is_multi_use",
    "is_factory_registered":    "is_factory_registered",
    "electric_capacity":        "electric_capacity",
    "worker_count":             "worker_count",
}


def _normalize_sector_db(sector: str) -> str:
    return sector.strip().upper()


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
    sec = sector.strip().upper()
    ctx: Dict[str, Any] = {
        "worker_count": 0, "total_floor_area": 0.0, "electric_capacity": 0.0,
        "building_use_code": "", "ksic_code": "", "floor_count": 0,
        "construction_amount": 0.0, "contract_amount": 0.0,
        "is_hazardous_material": 0, "is_multi_use": 0,
        "is_factory_registered": 0, "has_high_pressure_gas": 0,
        "has_hazardous_material": 0, "has_chemical_substance": 0,
        "has_boiler": 0, "has_tunnel_bridge": 0, "hospital_beds": 0, "student_count": 0,
    }
    if sec == "BUILDING":
        ctx["building_use_code"] = str(inp.get("building_use") or inp.get("building_use_type") or inp.get("building_use_code") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["floor_count"] = int(inp.get("floor_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
    elif sec == "MANUFACTURING":
        ctx["ksic_code"] = str(inp.get("ksic_major") or inp.get("ksic_code") or "")
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["has_chemical_substance"] = 1 if _truthy(inp.get("has_chemical_substance")) else 0
        ctx["has_boiler"] = 1 if _truthy(inp.get("has_boiler")) else 0
    elif sec == "CONSTRUCTION":
        eok = float(inp.get("contract_amount_eok") or 0)
        amount = eok * 100_000_000.0
        ctx["construction_amount"] = amount
        ctx["contract_amount"]     = amount

        site_type = str(inp.get("construction_type") or inp.get("site_type") or "BUILDING")
        ctx["construction_type"] = site_type
        ctx["building_use_code"] = site_type
        ctx["is_building"]       = 1 if site_type == "BUILDING" else 0
        ctx["is_civil"]          = 1 if site_type == "CIVIL"    else 0

        direct = int(inp.get("direct_workers") or inp.get("worker_count") or inp.get("employee_count") or 0)
        subcon = int(inp.get("subcon_workers") or 0)
        ctx["worker_count"]   = direct + subcon
        ctx["employee_count"] = direct + subcon
        ctx["direct_workers"] = direct
        ctx["subcon_workers"] = subcon

        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0

        threshold = 15_000_000_000 if site_type in ("BUILDING", "SPECIALTY") else 12_000_000_000
        ctx["safety_manager_threshold"] = threshold
    elif sec in ("SPECIAL_FACILITY", "SPECIAL"):
        ctx["building_use_code"] = str(inp.get("facility_type") or "")
        ctx["total_floor_area"] = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["hospital_beds"] = int(inp.get("hospital_beds") or 0)
        ctx["student_count"] = int(inp.get("student_count") or 0)
        ctx["worker_count"] = int(inp.get("worker_count") or inp.get("employee_count") or 0)
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
        if op in ("gte", ">="): return actual >= value
        if op in ("lte", "<="): return actual <= value
        if op in ("gt", ">"): return actual > value
        if op in ("lt", "<"): return actual < value
        if op in ("eq", "=", "=="): return actual == value
    except (TypeError, ValueError):
        return False
    return False


def _db_rule_matches_facility(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
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


def _evaluate_facility_conditions_db(
    facility_ctx: Dict[str, Any], rules: List[Dict[str, Any]], sector: str = ""
) -> tuple:
    applicable: List[Dict[str, Any]] = []
    not_applicable: List[Dict[str, Any]] = []
    for rule in rules:
        cc = rule.get("condition_code")
        cv = rule.get("condition_value")
        if not cc or cv is None:
            if sector == "CONSTRUCTION":
                law = rule.get("law_name") or ""
                if any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES):
                    applicable.append(rule)
                else:
                    not_applicable.append(rule)
            else:
                applicable.append(rule)
        elif _db_rule_matches_facility(rule, facility_ctx):
            applicable.append(rule)
        else:
            not_applicable.append(rule)
    return applicable, not_applicable


# ──────────────────────────────────────────────
# v5.1.0: 건설 선임 판정 요약 블록
# ──────────────────────────────────────────────

def _get_construction_summary(facility_ctx: Dict[str, Any]) -> Dict[str, Any]:
    amount    = float(facility_ctx.get("construction_amount") or 0)
    workers   = int(facility_ctx.get("worker_count") or 0)
    site_type = str(facility_ctx.get("construction_type") or facility_ctx.get("building_use_code") or "BUILDING")

    threshold   = 15_000_000_000 if site_type in ("BUILDING", "SPECIALTY") else 12_000_000_000
    sm_required = (amount >= threshold) or (workers >= 50)

    site_label  = "건축" if site_type == "BUILDING" else ("토목" if site_type == "CIVIL" else "전문")
    basis_parts = [f"{site_label} {int(threshold/100_000_000)}억원 {'이상' if amount >= threshold else '미만'}"]
    if workers >= 50:
        basis_parts.append("근로자 50명 이상")

    return {
        "site_type":                site_type,
        "contract_amount":          amount,
        "contract_amount_eok":      round(amount / 100_000_000, 2) if amount else 0,
        "total_workers":            workers,
        "direct_workers":           int(facility_ctx.get("direct_workers") or 0),
        "subcon_workers":           int(facility_ctx.get("subcon_workers") or 0),
        "safety_manager_required":  sm_required,
        "safety_manager_basis":     ", ".join(basis_parts),
        "key_thresholds_met": {
            "1억_산업안전보건관리비":       amount >= 100_000_000,
            "50억_유해위험방지계획서":      amount >= 5_000_000_000,
            "50억_기초안전보건교육":        amount >= 5_000_000_000,
            "100억_안전관리계획서":         amount >= 10_000_000_000,
            "120억_안전관리자선임_토목":    site_type == "CIVIL"    and amount >= 12_000_000_000,
            "150억_안전관리자선임_건축":    site_type == "BUILDING" and amount >= 15_000_000_000,
            "200억_안전보건관리책임자":     amount >= 20_000_000_000,
            "1000억_건설안전판정사":        amount >= 100_000_000_000,
        },
    }


# ──────────────────────────────────────────────
# POST /legal-engine/diagnose/step1  v5.1.0
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
    supabase = get_supabase()

    if factory_id:
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

    inp = dict(body.input or {})
    flat_fields = {
        "building_use_type": body.building_use_type,
        "employee_count":    body.employee_count,
        "floor_area":        body.floor_area,
        "worker_count":      body.worker_count,
        "total_floor_area":  body.total_floor_area,
        "electric_capacity": body.electric_capacity,
        "floor_count":       body.floor_count,
        "contract_amount_eok": body.contract_amount_eok,
        "ksic_major":        body.ksic_major,
        "facility_type":     body.facility_type,
    }
    for k, v in flat_fields.items():
        if v is not None and k not in inp:
            inp[k] = v

    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()

    applicable, not_applicable = _evaluate_facility_conditions_db(facility_ctx, all_rules, sector_raw)

    triggered: Dict[str, List] = {
        "appointment": [], "inspection": [], "notify": [], "report": [], "action": [], "not_applicable": [],
    }
    _classify_rules_db(applicable, triggered)
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result_db(r))

    total_applicable = (
        len(triggered["appointment"]) + len(triggered["inspection"])
        + len(triggered["notify"]) + len(triggered["report"])
        + len(triggered["action"])
    )

    law_names = sorted({x.get("law_name") for x in applicable if x.get("law_name")})

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
        rules_out.append({
            "rule_id":     x.get("rule_id"),
            "law_name":    x.get("law_name") or "",
            "law_article": x.get("law_article") or "",
            "obligation":  (x.get("obligation_summary") or x.get("remarks") or "").strip(),
        })

    result_data = {
        "factory_id":                factory_id or None,
        "sector":                    sector_raw,
        "step":                      1,
        "engine_version":            ENGINE_VERSION,
        "evaluated_at":              evaluated_at,
        "facility_context":          facility_ctx,
        "risk_level":                risk,
        "applicable_law_categories": law_cats,
        "appointment_required_flag": appointment_n > 0,
        "key_obligations":           key_obligations,
        "rules":                     rules_out,
        "law_badges":                law_names,
        "obligations":               obligations,
        "rules_table":               rules_table,
        "appointment_required":      triggered["appointment"],
        "inspection_required":       triggered["inspection"],
        "action_required":           triggered["action"],
        "report_required":           triggered["report"] + triggered["notify"],
        "not_applicable":            triggered["not_applicable"][:100],
        "not_applicable_total":      len(not_applicable),
        "total_rules_checked":       len(all_rules),
        "applicable_count":          total_applicable,
        "summary": {
            "total":       total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection":  len(triggered["inspection"]),
            "action":      len(triggered["action"]),
            "report":      len(triggered["report"]),
            "notify":      len(triggered["notify"]),
            "form_linked": sum(1 for r in applicable if (r.get("form_code") or "").strip()),
        },
    }

    if sector_raw == "CONSTRUCTION":
        result_data["construction_summary"] = _get_construction_summary(facility_ctx)

    diagnosis_id = None
    if factory_id:
        try:
            supabase.table("factory_diagnosis_results") \
                .update({"is_latest": False}) \
                .eq("factory_id", factory_id) \
                .eq("sector", sector_raw) \
                .eq("is_latest", True) \
                .execute()
        except Exception:
            pass
        try:
            save_res = supabase.table("factory_diagnosis_results").insert({
                "factory_id":      factory_id,
                "sector":          sector_raw,
                "diagnosis_stage": 1,
                "input_data":      inp,
                "result_data":     result_data,
                "rule_count":      total_applicable,
                "is_latest":       True,
            }).execute()
            if save_res.data:
                diagnosis_id = save_res.data[0].get("id")
        except Exception as e:
            print(f"[DIAGNOSE STEP1] factory_diagnosis_results 저장 실패: {e}")

        if diagnosis_id and applicable:
            try:
                rule_rows = []
                for rule in applicable:
                    rule_rows.append({
                        "diagnosis_id":    diagnosis_id,
                        "rule_code":       rule.get("rule_id") or rule.get("rule_code") or "",
                        "rule_name":       (rule.get("obligation_summary") or rule.get("remarks") or "").strip(),
                        "law_name":        rule.get("law_name") or "",
                        "law_article":     rule.get("law_article") or "",
                        "obligation":      (rule.get("obligation_summary") or "").strip(),
                        "obligation_type": _resolve_obligation_type(rule),
                        "due_date":        None,
                        "status":          "PENDING",
                        "form_code":       rule.get("form_code") or None,
                    })
                for i in range(0, len(rule_rows), 50):
                    supabase.table("diagnosis_rule_results").insert(rule_rows[i:i + 50]).execute()
            except Exception as e:
                print(f"[DIAGNOSE STEP1] diagnosis_rule_results 저장 실패: {e}")

    result_data["diagnosis_id"] = diagnosis_id
    return {"status": "success", "data": result_data}


@router.get("/quote-result/{quote_id}")
async def get_legal_result_from_quote(quote_id: str):
    supabase = get_supabase()
    res = supabase.table("quotes").select(
        "id, quote_no, legal_result_json, legal_evaluated_at, legal_applicable_count"
    ).eq("id", quote_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    if not res.data.get("legal_result_json"):
        raise HTTPException(status_code=404, detail="판정 결과 없음.")
    return {"status": "success", "data": {
        "quote_id": quote_id, "quote_no": res.data.get("quote_no"),
        "legal_evaluated_at": res.data.get("legal_evaluated_at"),
        "legal_applicable_count": res.data.get("legal_applicable_count"),
        "result": res.data.get("legal_result_json"),
    }}


@router.get("/result/{factory_id}")
async def get_legal_result(factory_id: str, mode: str = Query("all")):
    supabase = get_supabase()
    try:
        fac = supabase.table("factories").select(
            "legal_result_json, last_diagnosis_at, legal_applicable_count, diagnosis_status"
        ).eq("id", factory_id).single().execute()
        if fac.data and fac.data.get("legal_result_json"):
            rj = fac.data["legal_result_json"]
            rj.pop("not_applicable", None)
            return {"status": "success", "data": {
                **rj,
                "last_diagnosis_at":      fac.data.get("last_diagnosis_at"),
                "legal_applicable_count": fac.data.get("legal_applicable_count"),
                "diagnosis_status":       fac.data.get("diagnosis_status"),
            }}
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
            "mode": row.get("mode", "all"), "evaluated_at": row.get("evaluated_at"),
            "summary": rj.get("summary", {}), "engine_version": rj.get("engine_version", ""),
        })
    return {"status": "success", "data": {"factory_id": factory_id, "results": results}}


@router.post("/create-inspection-sets/{factory_id}")
async def create_inspection_sets_from_legal(factory_id: str):
    """v4.4.3: obligation_type=INSPECT 필터 + 배치 20건"""
    supabase = get_supabase()
    fac = supabase.table("factories").select(
        "id, company_id, legal_result_json"
    ).eq("id", factory_id).single().execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    company_id      = fac.data.get("company_id")
    result_json     = fac.data.get("legal_result_json")
    inspection_rules: List[Dict[str, Any]] = []

    if result_json:
        inspection_rules = result_json.get("inspection_required", [])

    if not inspection_rules:
        try:
            diag_res = supabase.table("factory_diagnosis_results") \
                .select("id") \
                .eq("factory_id", factory_id) \
                .eq("is_latest", True) \
                .order("created_at", desc=True) \
                .limit(1).execute()
            if diag_res.data:
                diagnosis_id = diag_res.data[0].get("id")
                drr_res = supabase.table("diagnosis_rule_results") \
                    .select("rule_code, rule_name, law_name, law_article, obligation, form_code") \
                    .eq("diagnosis_id", diagnosis_id) \
                    .eq("obligation_type", "INSPECT") \
                    .execute()
                drr_rows = drr_res.data or []
                if drr_rows:
                    rule_codes = [r.get("rule_code") for r in drr_rows if r.get("rule_code")]
                    masters_res = supabase.table("master_building_legal_rules") \
                        .select(
                            "rule_id, obligation_type, inspection_required, "
                            "inspection_cycle_value, inspection_cycle_unit_code, "
                            "cycle_unit_std, cycle_base_type, cycle_base_guide"
                        ) \
                        .in_("rule_id", rule_codes) \
                        .eq("is_active", True) \
                        .execute()
                    inspect_master_map = {m["rule_id"]: m for m in (masters_res.data or [])}
                    for r in drr_rows:
                        rc = r.get("rule_code", "")
                        m = inspect_master_map.get(rc, {})
                        inspection_rules.append({
                            "rule_id":          rc,
                            "law_name":         r.get("law_name", ""),
                            "law_article":      r.get("law_article", ""),
                            "description":      r.get("obligation", ""),
                            "inspection_cycle": INSPECTION_CYCLE_UNIT_MAP.get(
                                str(m.get("inspection_cycle_unit_code") or ""), ""
                            ),
                            "form_code":        r.get("form_code"),
                            "_master":          m,
                        })
        except Exception as e:
            print(f"[CREATE-INSP-SETS] fallback 조회 실패: {e}")

    if not inspection_rules:
        return {"status": "success", "message": "생성할 점검 항목이 없습니다.", "data": {"created": 0}}

    existing_res = supabase.table("inspection_sets") \
        .select("legal_rule_id") \
        .eq("factory_id", factory_id) \
        .eq("source", "LEGAL_ENGINE") \
        .eq("is_active", True) \
        .execute()
    existing_rule_ids = {r["legal_rule_id"] for r in (existing_res.data or []) if r.get("legal_rule_id")}

    insert_rows = []
    for rule in inspection_rules:
        rule_id = rule.get("rule_id", "")
        if rule_id in existing_rule_ids:
            continue
        m           = rule.get("_master", {})
        law_name    = rule.get("law_name", "")
        cycle_label = rule.get("inspection_cycle", "")
        cycle_unit_code = str(m.get("inspection_cycle_unit_code") or "")
        if cycle_unit_code in CYCLE_CODE_MAP:
            cycle_unit, cycle_value = CYCLE_CODE_MAP[cycle_unit_code]
        else:
            cycle_unit_std = (m.get("cycle_unit_std") or "").lower()
            UNIT_STD_MAP = {"year": "year", "month": "month", "day": "day", "week": "week"}
            cycle_unit  = UNIT_STD_MAP.get(cycle_unit_std, "year")
            cycle_value = int(m.get("inspection_cycle_value") or 1)
            if not cycle_unit_std:
                if "월 1회" in cycle_label or "매월" in cycle_label: cycle_unit, cycle_value = "month", 1
                elif "반기" in cycle_label: cycle_unit, cycle_value = "month", 6
                elif "분기" in cycle_label: cycle_unit, cycle_value = "month", 3
                elif "2년" in cycle_label: cycle_unit, cycle_value = "year", 2
                elif "3년" in cycle_label: cycle_unit, cycle_value = "year", 3
                elif "4년" in cycle_label: cycle_unit, cycle_value = "year", 4
                elif "5년" in cycle_label: cycle_unit, cycle_value = "year", 5
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
            "cycle_base_type":     m.get("cycle_base_type") or "LAST_INSPECTION",
            "cycle_base_guide":    m.get("cycle_base_guide") or (
                f"마지막 점검일로부터 {cycle_value}{'년' if cycle_unit == 'year' else '개월'}마다"
            ),
            "description":         rule.get("description", ""),
            "source":              "LEGAL_ENGINE",
            "is_active":           True,
            "anchor_confirmed":    False,
            "status_code":         "PENDING_ANCHOR",
        })

    if not insert_rows:
        return {"status": "success", "message": f"모든 점검 세트가 이미 존재합니다. ({len(existing_rule_ids)}개 유지)",
                "data": {"created": 0, "skipped": len(existing_rule_ids), "source_rules": len(inspection_rules)}}

    created = 0
    for i in range(0, len(insert_rows), 20):
        res = supabase.table("inspection_sets").insert(insert_rows[i:i + 20]).execute()
        created += len(res.data or [])

    return {"status": "success", "message": f"{created}개 점검 세트가 생성됐습니다. ({len(existing_rule_ids)}개 기존 유지)",
            "data": {"factory_id": factory_id, "created": created, "skipped": len(existing_rule_ids),
                     "source_rules": len(inspection_rules)}}


@router.get("/debug/context/{quote_id}")
async def debug_quote_context(quote_id: str):
    supabase = get_supabase()
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd:
        raise HTTPException(status_code=400, detail="survey_data 없음")
    return {"status": "success", "quote_no": qres.data.get("quote_no"), "context": _survey_data_to_context(sd)}


# ══════════════════════════════════════════════
# 3단계 진단 헬퍼 (v4.2.0)
# ══════════════════════════════════════════════

def _evaluate_condition(rule: dict, input_data: dict) -> bool:
    def check(field, operator, value, data):
        if not field or field not in data:
            return True
        actual = data[field]
        if actual is None:
            return False
        try:
            if operator == '>=': return float(actual) >= float(value)
            elif operator == '<=': return float(actual) <= float(value)
            elif operator == '>': return float(actual) > float(value)
            elif operator == '<': return float(actual) < float(value)
            elif operator == '==': return str(actual) == str(value)
            elif operator == 'IN':
                vals = [v.strip() for v in str(value).split(',')]
                return str(actual) in vals
            elif operator == 'NOT_IN':
                vals = [v.strip() for v in str(value).split(',')]
                return str(actual) not in vals
            elif operator == '==true': return actual is True or str(actual).lower() == 'true'
            elif operator == '==false': return actual is False or str(actual).lower() == 'false'
        except Exception:
            return False
        return True

    c1_ok = check(rule.get('condition_1_field'), rule.get('condition_1_operator'),
                  rule.get('condition_1_value'), input_data)
    if not c1_ok:
        return False
    c2_field = rule.get('condition_2_field')
    if c2_field:
        c2_ok = check(c2_field, rule.get('condition_2_operator'), rule.get('condition_2_value'), input_data)
        mode = rule.get('condition_mode', 'AND')
        if mode == 'AND' and not c2_ok:
            return False
        if mode == 'OR' and not (c1_ok or c2_ok):
            return False
    return True


def _determine_risk_level(rule_count: int) -> str:
    if rule_count >= 10: return 'HIGH'
    elif rule_count >= 5: return 'MEDIUM'
    return 'LOW'


def _save_diagnosis_result(supabase, factory_id: str, sector: str, stage: int,
                            input_data: dict, matched_rules: list) -> dict:
    try:
        supabase.table('factory_diagnosis_results').update(
            {'is_latest': False}
        ).eq('factory_id', factory_id).eq('is_latest', True).execute()
    except Exception:
        pass
    law_categories = list(dict.fromkeys(r.get('law_name', '') for r in matched_rules if r.get('law_name')))
    key_obligations = [r.get('obligation_summary') or r.get('rule_name', '') for r in matched_rules[:5]]
    has_appointment = any(r.get('rule_type') == 'APPOINTMENT' or r.get('appointment_required') for r in matched_rules)
    result_data = {
        'applicable_law_categories': law_categories,
        'appointment_required': has_appointment,
        'key_obligations': key_obligations,
        'risk_level': _determine_risk_level(len(matched_rules)),
        'rules': [{'rule_code': r.get('rule_code') or r.get('rule_id'), 'rule_name': r.get('rule_name') or r.get('remarks', ''),
                   'law_name': r.get('law_name', ''), 'law_article': r.get('law_article', ''),
                   'obligation': r.get('obligation_summary') or r.get('rule_name', ''),
                   'rule_type': r.get('rule_type') or str(r.get('rule_type_code', '')),
                   'stage': r.get('diagnosis_stage', 1)} for r in matched_rules]
    }
    try:
        res = supabase.table('factory_diagnosis_results').insert({
            'factory_id': factory_id, 'sector': sector, 'diagnosis_stage': stage,
            'input_data': input_data, 'result_data': result_data,
            'rule_count': len(matched_rules), 'is_latest': True,
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        print(f"[DIAGNOSIS] 결과 저장 실패: {e}")
        return {'result_data': result_data}


def _create_report_events_from_rules(supabase, factory_id: str, matched_rules: list):
    event_types = {'REPORT', 'APPOINTMENT', 'NOTIFICATION'}
    for rule in matched_rules:
        rule_type = rule.get('rule_type') or ''
        if rule_type not in event_types and not rule.get('report_required'):
            continue
        form_code = rule.get('form_code')
        if not form_code:
            continue
        try:
            existing = supabase.table('report_events').select('id')\
                .eq('factory_id', factory_id).eq('form_code', form_code).eq('status', 'PENDING').execute()
            if existing.data:
                continue
        except Exception:
            pass
        due_days = rule.get('due_days') or 14
        due_date = (date.today() + timedelta(days=due_days)).isoformat()
        try:
            supabase.table('report_events').insert({
                'factory_id': factory_id, 'rule_code': rule.get('rule_code') or rule.get('rule_id'),
                'form_code': form_code, 'trigger_date': date.today().isoformat(),
                'due_date': due_date, 'status': 'PENDING',
            }).execute()
        except Exception as e:
            print(f"[DIAGNOSIS] report_events 생성 실패: {e}")


# ──────────────────────────────────────────────
# POST /legal-engine/diagnose/step2  v5.2.0
# ──────────────────────────────────────────────

@router.post("/diagnose/step2")
def diagnose_step2(body: dict):
    """
    건설 법령진단 2단계 — 공종별 법령 판정
    v5.2.0: kcsc_process_ids → kcsc_process_master에서 work_type_code 자동 조회
    기존 construction_work_types 직접 입력 하위 호환 유지
    """
    supabase   = get_supabase()
    factory_id = body.get('factory_id')
    diagnosis_id        = body.get('diagnosis_id')
    processes           = body.get('processes', [])
    construction_types  = body.get('construction_types', [])
    work_types: List[str]       = list(body.get('construction_work_types') or [])  # 기존 하위 호환
    kcsc_process_ids: List[str] = body.get('kcsc_process_ids') or []               # v5.2.0 신규

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table('factory_diagnosis_results').select('*').eq('id', diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass

    sector     = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = dict((prev or {}).get('input_data') or {})
    input_data['processes']          = processes
    input_data['construction_types'] = construction_types
    input_data['sector']             = sector

    # v5.2.0: KCSC 공정 ID → work_type_code 자동 조회
    kcsc_processes: List[Dict]      = []
    kcsc_process_summary: List[Dict] = []

    if kcsc_process_ids:
        try:
            kcsc_res = supabase.table('kcsc_process_master') \
                .select('id, process_name, work_type_code, work_type_label, risk_level') \
                .in_('id', kcsc_process_ids) \
                .eq('is_active', True) \
                .execute()
            kcsc_processes = kcsc_res.data or []
        except Exception as e:
            print(f"[STEP2] kcsc_process_master 조회 실패: {e}")

        # work_type_code 추출 (NULL 제외, 중복 제거) + 기존 직접 입력 합산
        kcsc_work_types = list(set(
            p['work_type_code'] for p in kcsc_processes if p.get('work_type_code')
        ))
        work_types = list(set(work_types + kcsc_work_types))

        # input_data에 KCSC 정보 저장
        input_data['kcsc_process_ids'] = kcsc_process_ids
        input_data['kcsc_processes']   = kcsc_processes

        # 응답용 공정 요약
        for p in kcsc_processes:
            kcsc_process_summary.append({
                'process_id':      p['id'],
                'process_name':    p.get('process_name', ''),
                'work_type_code':  p.get('work_type_code'),
                'work_type_label': p.get('work_type_label'),
                'risk_level':      p.get('risk_level', 'MEDIUM'),
                'has_legal_rules': p.get('work_type_code') is not None,
            })

    # 법령 룰 조회
    q = supabase.table('master_building_legal_rules').select('*').eq(
        'sector', sector
    ).lte('diagnosis_stage', 2).eq('is_active', True)

    # CONSTRUCTION + 공종 필터
    if sector == 'CONSTRUCTION' and work_types:
        work_type_csv = ",".join(work_types)
        q = q.or_(
            f"construction_work_type.is.null,construction_work_type.in.({work_type_csv})"
        )

    res     = q.execute()
    rules   = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
    _create_report_events_from_rules(supabase, factory_id, matched)

    prev_codes = set()
    if prev:
        prev_rules = (prev.get('result_data') or {}).get('rules', [])
        prev_codes = {r.get('rule_code') for r in prev_rules}
    added  = [r for r in matched if (r.get('rule_code') or r.get('rule_id')) not in prev_codes]
    result = diagnosis.get('result_data', {})

    work_type_summary: Dict[str, int] = {}
    if work_types:
        for r in matched:
            wt = r.get('construction_work_type') or 'COMMON'
            work_type_summary[wt] = work_type_summary.get(wt, 0) + 1

    return {
        'status':               'success',
        'diagnosis_id':         diagnosis.get('id'),
        'stage':                2,
        'engine_version':       ENGINE_VERSION,
        'sector':               sector,
        'rule_count':           len(matched),
        'added_rule_count':     len(added),
        'kcsc_process_ids':     kcsc_process_ids,
        'kcsc_process_summary': kcsc_process_summary,
        'filtered_by_work_types': work_types if work_types else None,
        'work_type_summary':    work_type_summary if work_types else None,
        'summary': {
            'applicable_law_categories': result.get('applicable_law_categories', []),
            'appointment_required':      result.get('appointment_required', False),
            'key_obligations':           result.get('key_obligations', []),
            'risk_level':                result.get('risk_level', 'LOW'),
        },
        'rules': result.get('rules', []),
        'added_rules': [{
            'rule_code':       r.get('rule_code') or r.get('rule_id'),
            'rule_name':       r.get('rule_name') or r.get('remarks', ''),
            'law_article':     r.get('law_article', ''),
            'work_type':       r.get('construction_work_type'),
            'work_type_label': r.get('construction_work_type_label'),
        } for r in added],
    }


# ──────────────────────────────────────────────
# POST /legal-engine/diagnose/step3  v5.2.0
# ──────────────────────────────────────────────

@router.post("/diagnose/step3")
def diagnose_step3(body: dict):
    """
    건설 법령진단 3단계 — 설비·작업 법령 판정
    v5.2.0:
    - construction_work_ids: PTW 작업 ID → construction_works.kcsc_work_id 조회
    - kcsc_work_ids: KCSC 작업 마스터 ID → equipment_type_codes 자동 조회
    - 기존 equipments 직접 입력 하위 호환 유지
    응답: equipment_codes_applied, kcsc_work_summary 추가
    """
    supabase   = get_supabase()
    factory_id = body.get('factory_id')
    diagnosis_id = body.get('diagnosis_id')
    equipments: List[Dict]          = list(body.get('equipments') or [])   # 기존 하위 호환
    construction_work_ids: List[str] = body.get('construction_work_ids') or []  # v5.2.0 신규
    kcsc_work_ids: List[str]         = list(body.get('kcsc_work_ids') or [])    # v5.2.0 신규

    if not factory_id:
        raise HTTPException(status_code=400, detail='factory_id 필수')

    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table('factory_diagnosis_results').select('*').eq('id', diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception:
            pass

    sector     = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = dict((prev or {}).get('input_data') or {})
    input_data['sector'] = sector

    extra_equipment_codes: List[str] = []
    kcsc_work_summary: List[Dict]    = []

    # v5.2.0 Step A: PTW 등록 작업 → kcsc_work_id 조회
    if construction_work_ids:
        try:
            ptw_res = supabase.table('construction_works') \
                .select('id, work_name, kcsc_work_id') \
                .in_('id', construction_work_ids) \
                .execute()
            ptw_works = ptw_res.data or []
            kcsc_ids_from_ptw = [w['kcsc_work_id'] for w in ptw_works if w.get('kcsc_work_id')]
            kcsc_work_ids = list(set(kcsc_work_ids + kcsc_ids_from_ptw))
        except Exception as e:
            print(f"[STEP3] construction_works 조회 실패 (테이블 없을 수 있음): {e}")

    # v5.2.0 Step B: KCSC 작업 마스터 → equipment_type_codes 자동 조회
    if kcsc_work_ids:
        try:
            kcsc_work_res = supabase.table('kcsc_work_master') \
                .select('id, title, is_hazardous, hazard_type, equipment_type_codes, work_type_code') \
                .in_('id', kcsc_work_ids) \
                .execute()
            kcsc_works = kcsc_work_res.data or []

            for w in kcsc_works:
                eq_codes = w.get('equipment_type_codes') or []
                extra_equipment_codes.extend(eq_codes)
                kcsc_work_summary.append({
                    'work_id':         w['id'],
                    'title':           w.get('title', ''),
                    'is_hazardous':    w.get('is_hazardous', False),
                    'hazard_type':     w.get('hazard_type'),
                    'equipment_codes': eq_codes,
                    'work_type_code':  w.get('work_type_code'),
                })

            extra_equipment_codes = list(set(extra_equipment_codes))
        except Exception as e:
            print(f"[STEP3] kcsc_work_master 조회 실패: {e}")

    # v5.2.0: 기존 equipments 배열에 KCSC 조회 결과 합산 (중복 제외)
    for code in extra_equipment_codes:
        if not any(e.get('equipment_code') == code for e in equipments):
            equipments.append({'equipment_code': code})

    input_data['equipments']            = equipments
    input_data['construction_work_ids'] = construction_work_ids
    input_data['kcsc_work_ids']         = kcsc_work_ids
    input_data['extra_equipment_codes'] = extra_equipment_codes

    # 3단계 룰 조회
    q = supabase.table('master_building_legal_rules').select('*') \
        .eq('sector', sector) \
        .eq('diagnosis_stage', 3) \
        .eq('is_active', True)

    # v5.2.0: CONSTRUCTION + 설비/공종 코드 필터
    if sector == 'CONSTRUCTION' and extra_equipment_codes:
        eq_csv = ','.join(extra_equipment_codes)
        q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({eq_csv})")

    res     = q.execute()
    rules   = res.data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]

    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 3, input_data, matched)

    # 점검 일정 생성
    inspection_schedules = []
    today = date.today()
    for equip in equipments:
        eq_code = equip.get('equipment_code', '')
        last_dt = equip.get('last_inspection_date')
        cycle_years = 2
        if last_dt:
            try:
                last      = date.fromisoformat(last_dt)
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
                    'status': 'OVERDUE' if days_left < 0 else ('URGENT' if days_left <= 30 else 'NORMAL'),
                })
            except Exception:
                pass

    overdue_count  = sum(1 for s in inspection_schedules if s['status'] == 'OVERDUE')
    upcoming_count = sum(1 for s in inspection_schedules if s['status'] == 'URGENT')

    return {
        'status':                  'success',
        'diagnosis_id':            diagnosis.get('id'),
        'stage':                   3,
        'sector':                  sector,
        'engine_version':          ENGINE_VERSION,
        'rule_count':              len(matched),
        'equipment_codes_applied': extra_equipment_codes,   # v5.2.0 신규
        'kcsc_work_summary':       kcsc_work_summary,       # v5.2.0 신규
        'inspection_schedules':    inspection_schedules,
        'overdue_count':           overdue_count,
        'upcoming_count':          upcoming_count,
    }


@router.get("/diagnose/{factory_id}/latest")
def get_latest_diagnosis(factory_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table('factory_diagnosis_results').select('*')\
            .eq('factory_id', factory_id).eq('is_latest', True)\
            .order('created_at', desc=True).limit(1).execute()
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
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    res = supabase.table('factory_diagnosis_results').select(
        'id, sector, diagnosis_stage, rule_count, is_latest, created_at', count='exact'
    ).eq('factory_id', factory_id).order('created_at', desc=True)\
     .range(offset, offset + page_size - 1).execute()
    return {
        'status': 'success',
        'data': {'items': res.data or [], 'total': res.count or 0, 'page': page, 'page_size': page_size},
    }
