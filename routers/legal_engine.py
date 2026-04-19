"""
법령 판정 엔진 라우터 — v5.7.0
=================================
v5.7.0 (2026-04-19):
  BE-11: 무료 진단 결과 데이터 품질 개선
  Task 1: remarks 우선 → obligation_summary 폴백 (사람 언어 표시)
  Task 2: penalty_summary 빈 값 시 의무 유형별 기본 문구 (_get_penalty_fallback)
  Task 3: 건축법 제35조 중복 → remarks 우선으로 각 의무 구분 자동 해결
  Task 4: cycle_unit_std 있는 상시의무 → due_info: {} (D-day 미표시)
  Task 5: result_data에 risk_reason 필드 추가

v5.6.8 (2026-04-15):
  BE-1: diagnose/step1 완료 시 inspection_sets 자동 생성 (모든 섹터)
  BE-3: contract_amount_eok 필드 설명 추가 (단위: 억원 명확화)

v5.6.7 (2026-04-07):
  CONSTRUCTION sector에서 diagnose/step1 완료 시
  generate_schedules_from_diagnosis(factory_id) 자동 트리거

v5.6.3:
  - DiagnoseStep1Body에 설비 수치 필드 추가 (스케줄 정확도 향상)
    · gas_capacity_kg    — 가스 저장량(kg) 직접 입력 → 100kg/300kg 단계별 점검 판정 가능
    · gas_capacity_m3    — 도시가스 사용량(m3)
    · boiler_capacity_kw — 보일러 용량(kW) 직접 입력
    · annual_energy_toe  — 연간 에너지 사용량(TOE)
    · has_high_pressure_gas  — 가스 보유 불리언 (수치 미입력 시 사용)
    · has_boiler             — 보일러 보유 불리언
    · has_hazardous_material — 위험물 보유 불리언
    · has_chemical_substance — 유해화학물질 보유 불리언
    · elevator_count         — 승강기 대수 직접 입력
  설계 원칙: 수치 입력 우선, 없으면 boolean → 1(최소값) 폴백
  이로써 gas_capacity_kg=250 입력 시 >= 100 룰은 발동, >= 300 룰은 미발동 등
  단계별 정확한 점검 의무 판정이 가능함.

v5.6.2: inspection_cycle 4필드 완비, schedule_type 분류 (PERIODIC/BEFORE_WORK/ON_DEMAND)
v5.6.1: MANUFACTURING gas/boiler boolean→수치 변환, elevator_count BUILDING 지원
v5.6.0: submit_org_code / executor_type_code / report_method_std 반환 추가
v5.5.2: appointment_target_code 기준 중복 제거
v5.5.0: SECTOR_RULE_GROUPS 딕셔너리 도입
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone, date, timedelta
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "5.7.0"  # v5.7.0: BE-11 데이터 품질 개선


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
    "chemical_manager":           "유해화학물질관리자",
    "waste_manager":              "폐기물처리담당자",
    "environmental_manager":      "환경관리인",
}

APPOINTMENT_TARGET_NORMALIZE = {
    "소방안전관리자":           "fire_safety_manager",
    "승강기 안전관리자":        "elevator_safety_manager",
    "위험물안전관리자":         "hazardous_material_manager",
    "위험물안전관리자 대리자":  "hazardous_material_manager",
    "위험물운반자":             "hazardous_material_manager",
    "안전관리자":               "safety_manager",
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

EXECUTOR_TYPE_MAP = {
    "anyone":    "사업주 누구나",
    "qualified": "자격자만",
    "external":  "외부기관 위탁",
    "appointed": "선임된 관리자",
}

SUBMIT_ORG_MAP = {
    "moel":      "고용노동부(노동청)",
    "nfa":       "소방서",
    "kesco":     "한국전기안전공사",
    "kgs":       "한국가스안전공사",
    "me":        "지방환경청(환경부)",
    "mlit":      "국토교통부(지자체)",
    "kosha":     "한국산업안전보건공단",
    "self":      "자체보관",
    "local_gov": "지방자치단체",
    "keco":      "한국환경공단",
}

REPORT_METHOD_MAP = {
    "api":   "API(온라인시스템)",
    "mail":  "우편",
    "visit": "방문",
    "fax":   "팩스",
    "keep":  "자체보관(미제출)",
}

SECTOR_RULE_GROUPS: Dict[str, List[str]] = {
    "BUILDING": ["COMMON", "BUILDING", "BUILDING_MANUFACTURING", "BUILDING_CONSTRUCTION"],
    "MANUFACTURING": ["COMMON", "MANUFACTURING", "CONSTRUCTION_MANUFACTURING", "BUILDING_MANUFACTURING"],
    "CONSTRUCTION": ["COMMON", "CONSTRUCTION", "CONSTRUCTION_MANUFACTURING", "BUILDING_CONSTRUCTION"],
    "SPECIAL_FACILITY": ["COMMON", "SPECIAL_FACILITY", "BUILDING", "BUILDING_MANUFACTURING"],
    "SPECIAL": ["COMMON", "SPECIAL_FACILITY", "BUILDING", "BUILDING_MANUFACTURING"],
}


def get_sector_groups(sector: str) -> List[str]:
    return SECTOR_RULE_GROUPS.get(sector.strip().upper(), [sector.strip().upper()])


_CONSTRUCTION_AMOUNT_THRESHOLDS: Dict[str, int] = {
    "건축": 15_000_000_000, "토목": 12_000_000_000,
    "공통": 12_000_000_000, "기타": 12_000_000_000,
}


def get_effective_worker_count(factory: dict) -> int:
    sec = str(factory.get("sector") or factory.get("site_type") or "").upper()
    base = int(factory.get("employee_count") or factory.get("worker_count") or 0)
    if sec == "CONSTRUCTION":
        sub = int(factory.get("subcontractor_worker_count") or 0)
        return base + sub
    return base


def get_construction_amount_threshold(factory: dict) -> int:
    return _CONSTRUCTION_AMOUNT_THRESHOLDS.get(factory.get("construction_type") or "건축", 15_000_000_000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_survey_data(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None: return None
    if isinstance(raw, dict): return raw
    if isinstance(raw, str):
        try: return json.loads(raw)
        except json.JSONDecodeError: return None
    return None


def _to_float(*vals) -> float:
    for v in vals:
        if v is None or v == "": continue
        try: return float(v)
        except (TypeError, ValueError): continue
    return 0.0


def _to_int(*vals) -> int:
    for v in vals:
        if v is None or v == "": continue
        try: return int(float(v))
        except (TypeError, ValueError): continue
    return 0


def _normalize_target_code(code: str) -> str:
    if not code: return code
    return APPOINTMENT_TARGET_NORMALIZE.get(code, code)


def _survey_data_to_context(survey_data: Dict[str, Any]) -> Dict[str, Any]:
    snap = survey_data.get("survey_snapshot")
    if not isinstance(snap, dict): snap = {}
    equip_list = snap.get("equip") or []
    workers   = _to_int(survey_data.get("employee_count"), snap.get("workers"))
    area      = _to_float(survey_data.get("floor_area"), snap.get("area"))
    power_kw  = _to_float(survey_data.get("electrical_kw"), snap.get("elecKw"))
    floors    = _to_int(snap.get("floors"), survey_data.get("floors_above"))
    gas_kg    = _to_float(snap.get("gasKg"), survey_data.get("gas_kg"))
    boiler_th = _to_float(snap.get("boilerTh"), survey_data.get("boiler_th"))
    outsource = _to_int(snap.get("outsource"), survey_data.get("outsource_count"))
    has_chem  = "chem" in equip_list or bool(survey_data.get("equip_chemical"))
    has_elev  = "elev" in equip_list or bool(survey_data.get("equip_elevator"))
    has_gas   = "gas"  in equip_list or gas_kg > 0
    has_boiler= "boiler" in equip_list or boiler_th > 0
    btype = str(snap.get("btype") or snap.get("bldgUse") or survey_data.get("building_type") or "").strip()
    ksic  = str(survey_data.get("ksic_code") or snap.get("ksic_code") or "").strip()
    is_factory = 1 if (btype.startswith("공장") or btype.startswith("제조") or ksic.upper().startswith("C")) else 0
    cons_eok = _to_float(snap.get("constructionAmt"), survey_data.get("construction_amt"))
    return {
        "employee_count": workers, "building_area": area,
        "electrical_capacity_kw": power_kw, "floor_count": floors,
        "contractor_count": outsource, "transformer_capacity_kva": power_kw,
        "construction_amount": cons_eok * 100_000_000 if cons_eok > 0 else 0,
        "gas_capacity_kg": gas_kg if gas_kg > 0 else (1 if has_gas else 0),
        "gas_capacity_m3": 1 if has_gas else 0,
        "boiler_capacity_kw": boiler_th * 700 if boiler_th > 0 else (1 if has_boiler else 0),
        "boiler_capacity_th": boiler_th,
        "is_hazardous_material": 1 if has_chem else 0,
        "elevator_count": 1 if has_elev else 0,
        "is_factory_registered": is_factory, "is_multi_use": 0,
        "annual_energy_toe": 0, "building_use_code": btype, "ksic_code": ksic,
    }


def _factory_to_context(factory: dict) -> Dict[str, Any]:
    ctx = {
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
    sec = str(factory.get("sector") or factory.get("site_type") or "").upper()
    if sec == "CONSTRUCTION":
        effective = get_effective_worker_count(factory)
        threshold = get_construction_amount_threshold(factory)
        ctx["worker_count"]              = effective
        ctx["subcontractor_worker_count"] = int(factory.get("subcontractor_worker_count") or 0)
        ctx["construction_type"]          = factory.get("construction_type") or "건축"
        ctx["safety_manager_threshold"]   = threshold
    else:
        ctx["worker_count"] = ctx["employee_count"]
    return ctx


def _check_rule_conditions(rule: dict, context: dict) -> bool:
    cc = rule.get("condition_code", "")
    operator = rule.get("condition_operator_code", "gte")
    value_str = rule.get("condition_value")
    if not cc: return True
    actual = context.get(cc)
    if actual is None: return False
    if cc.startswith("is_") and actual == 0: return False
    if value_str is None:
        try: return float(actual) > 0
        except (TypeError, ValueError): return bool(actual)
    try:
        an, vn = float(actual), float(value_str)
        if operator in ("gte", ">="): return an >= vn
        elif operator in ("lte", "<="): return an <= vn
        elif operator in ("gt", ">"): return an > vn
        elif operator in ("lt", "<"): return an < vn
        elif operator in ("eq", "=", "=="): return an == vn
        elif operator in ("neq", "!=", "<>"): return an != vn
        else: return an >= vn
    except (TypeError, ValueError):
        if operator in ("eq", "=", "=="): return str(actual).strip() == str(value_str).strip()
        elif operator in ("in", "contains"): return str(value_str) in str(actual)
        return False


def _resolve_obligation_type(rule: dict) -> str:
    ot = (rule.get("obligation_type") or "").strip().upper()
    if ot: return ot
    if rule.get("appointment_required"): return "APPOINT"
    if rule.get("notify_required"): return "NOTIFY"
    if rule.get("report_required"): return "REPORT"
    if rule.get("inspection_required"): return "INSPECT"
    if rule.get("action_required"): return "ACTION"
    return "OTHER"


def _is_notify(rule: dict) -> bool:
    return (rule.get("obligation_type") or "").strip().upper() == "NOTIFY" or bool(rule.get("notify_required"))


def _is_report(rule: dict) -> bool:
    ot = (rule.get("obligation_type") or "").strip().upper()
    if ot == "REPORT": return True
    return bool(rule.get("report_required")) and not _is_notify(rule)


def _get_inspection_cycle_label(rule: dict) -> str:
    """정규화된 주기 라벨 생성 (cycle_unit_std 기반, unit_code fallback)."""
    val = rule.get("inspection_cycle_value")
    unit = rule.get("cycle_unit_std") or ""
    schedule = _get_schedule_type(rule)

    # cycle_unit_std 없으면 unit_code에서 역산
    if not unit:
        code = str(rule.get("inspection_cycle_unit_code") or "")
        _CODE_TO_UNIT = {
            "001": "day", "002": "week", "003": "month",
            "004": "quarter", "005": "half_year", "006": "year",
            "007": "year", "008": "year", "009": "year",
            "010": "year", "011": "year", "012": "year", "013": "year",
        }
        unit = _CODE_TO_UNIT.get(code, "")

    if not val:
        return ""

    val = int(float(val))

    _SHORT = {
        "year": "연 1회", "half_year": "반기 1회", "quarter": "분기 1회",
        "month": "월 1회", "week": "주 1회", "day": "매일",
    }

    if val == 1:
        return _SHORT.get(unit, f"1{unit}")

    # val > 1: year만 기간 모델("N년마다"), 나머지는 빈도 모델("X N회")
    if unit == "year":
        return f"{val}년마다"
    # half_year/quarter/month 등: "반기 2회", "분기 3회", "월 2회"
    base = _SHORT.get(unit, unit)
    return base.replace("1회", f"{val}회")


def _get_schedule_type(rule: dict) -> str:
    if rule.get("inspection_cycle_unit_code") or rule.get("cycle_unit_std"):
        return "PERIODIC"
    if rule.get("construction_work_type"): return "BEFORE_WORK"
    return "ON_DEMAND"


def _get_appointment_target_label(rule: dict) -> str:
    code = _normalize_target_code(rule.get("appointment_target_code", ""))
    return APPOINTMENT_TARGET_MAP.get(code, code)


def format_rule_result(rule: dict, source_label: str = "") -> dict:
    pen_val = rule.get("penalty_value")
    pen_unit = rule.get("penalty_unit_code", "")
    return {
        "rule_id": rule.get("rule_id", ""), "rule_type": str(rule.get("rule_type_code", "")),
        "law_name": rule.get("law_name", ""), "law_article": rule.get("law_article", ""),
        "description": rule.get("remarks", ""), "appointment_target": _get_appointment_target_label(rule),
        "qualification_required": rule.get("appointment_qualification_code", ""),
        "inspection_cycle": _get_inspection_cycle_label(rule),
        "penalty_amount": f"{pen_val} {pen_unit}" if pen_val and pen_unit else (str(pen_val) if pen_val else ""),
        "source_label": source_label, "appointment_required": rule.get("appointment_required", False),
        "inspection_required": rule.get("inspection_required", False),
        "action_required": rule.get("action_required", False), "report_required": rule.get("report_required", False),
        "obligation_type": _resolve_obligation_type(rule),
        "condition_code": rule.get("condition_code", ""), "condition_value": rule.get("condition_value"),
    }


def _calc_due_date(due_days) -> dict:
    if not due_days: return {}
    d = int(due_days)
    return {"due_days": d, "due_date": (date.today() + timedelta(days=d)).isoformat(),
            "urgency": "IMMEDIATE" if d <= 3 else ("URGENT" if d <= 14 else "NORMAL")}


# ── BE-11 Task 2: penalty_summary 빈 값 시 의무 유형별 기본 문구 ──────────
def _get_penalty_fallback(obligation_type: str) -> str:
    """
    penalty_summary 빈 문자열일 때 의무 유형에 따라 기본 안내 문구 반환.

    실제 법적 벌칙이 없는 의무(행정지도 대상)와 구분하기 위해
    obligation_type별로 다른 문구를 사용한다.
    """
    _MAP = {
        "DOCUMENT":    "미보존 시 과태료 부과 가능",
        "APPOINT":     "미선임 시 과태료 부과 가능",
        "INSPECT":     "미실시 시 과태료 부과 가능",
        "REPORT":      "미신고 시 과태료 부과 가능",
        "NOTIFY":      "미신고 시 과태료 부과 가능",
        "BEFORE_WORK": "미이행 시 과태료 부과 가능",
        "ACTION":      "관련 벌칙 확인 필요",
        "OTHER":       "관련 벌칙 확인 필요",
    }
    return _MAP.get((obligation_type or "").upper(), "관련 벌칙 확인 필요")


def format_rule_result_db(rule: Dict[str, Any]) -> Dict[str, Any]:
    """
    v5.7.0: BE-11 데이터 품질 개선
      - Task 1: remarks 우선 → obligation_summary 폴백 (사람 언어)
      - Task 2: penalty_summary 빈 값 시 _get_penalty_fallback 적용
      - Task 4: cycle_unit_std 있으면 due_info: {} (상시 의무 D-day 미표시)
    """
    # Task 1: remarks 우선, obligation_summary 폴백
    desc = (rule.get("remarks") or rule.get("obligation_summary") or "").strip()

    target_code = _normalize_target_code(rule.get("appointment_target_code") or "")
    submit_org_code    = rule.get("submit_org_code") or ""
    executor_type_code = rule.get("executor_type_code") or ""
    report_method_std  = rule.get("report_method_std") or ""
    cycle_code  = rule.get("inspection_cycle_unit_code") or ""
    cycle_label = _get_inspection_cycle_label(rule)
    # cycle_unit_std 우선, unit_code fallback
    _std = rule.get("cycle_unit_std") or ""
    if _std:
        _STD_TO_UNIT = {"year": "year", "half_year": "half_year", "quarter": "quarter", "month": "month", "week": "week", "day": "day"}
        cycle_unit = _STD_TO_UNIT.get(_std, _std)
        cycle_int = int(rule.get("inspection_cycle_value") or 0)
    else:
        cycle_unit, cycle_int = CYCLE_CODE_MAP.get(cycle_code, ("", 0))
    schedule_type = _get_schedule_type(rule)

    # Task 2: penalty_summary 빈 값 처리
    _obl_type = _resolve_obligation_type(rule)
    _pen_raw  = rule.get("penalty_summary") or ""
    _penalty  = _pen_raw.strip() if _pen_raw.strip() else _get_penalty_fallback(_obl_type)

    # Task 4: 상시 의무(cycle_unit_std 있음)는 due_info 억제
    _is_recurring = bool(rule.get("cycle_unit_std"))

    return {
        "rule_id": rule.get("rule_id", ""), "rule_type": str(rule.get("rule_type_code") or ""),
        "law_name": rule.get("law_name") or "", "law_article": rule.get("law_article") or "",
        "description": desc, "obligation_summary": desc,
        "appointment_target": APPOINTMENT_TARGET_MAP.get(target_code, target_code),
        "qualification_required": rule.get("qualification_type") or "",
        "inspection_cycle": cycle_label,
        "inspection_cycle_code": cycle_code,
        "inspection_cycle_unit": cycle_unit,
        "inspection_cycle_int": cycle_int,
        "schedule_type": schedule_type,
        "cycle_base_type": rule.get("cycle_base_type") or "",
        "cycle_base_guide": rule.get("cycle_base_guide") or "",
        "construction_work_type": rule.get("construction_work_type") or "",
        "executor_type_code": executor_type_code,
        "executor_type_label": EXECUTOR_TYPE_MAP.get(executor_type_code, executor_type_code),
        "condition_code": rule.get("condition_code") or "",
        "condition_value": rule.get("condition_value"),
        "penalty_amount": _penalty, "penalty_summary": _penalty,
        "source_label": "", "obligation_type": _obl_type,
        "appointment_required": bool(rule.get("appointment_required")),
        "inspection_required": bool(rule.get("inspection_required")),
        "action_required": bool(rule.get("action_required")),
        "report_required": bool(rule.get("report_required")),
        "notify_required": bool(rule.get("notify_required")),
        "form_code": rule.get("form_code") or "", "form_url": rule.get("form_url") or "",
        "due_days": rule.get("due_days"),
        "is_recurring": _is_recurring,                                      # Task 4
        "due_info": {} if _is_recurring else _calc_due_date(rule.get("due_days")),  # Task 4
        "sector": rule.get("sector") or "", "diagnosis_stage": rule.get("diagnosis_stage"),
        "submit_org_code": submit_org_code,
        "submit_org_label": SUBMIT_ORG_MAP.get(submit_org_code, submit_org_code),
        "report_method_std": report_method_std,
        "report_method_label": REPORT_METHOD_MAP.get(report_method_std, report_method_std),
    }


def _classify_rules(rules: list, triggered: dict):
    for rule in rules: _classify_one(rule, format_rule_result(rule), triggered)


def _classify_rules_with_source(rule_source_pairs: list, triggered: dict):
    for rule, sl in rule_source_pairs: _classify_one(rule, format_rule_result(rule, sl), triggered)


def _classify_one(rule: dict, formatted: dict, triggered: dict):
    if rule.get("appointment_required"): triggered["appointment"].append(formatted)
    elif rule.get("inspection_required"): triggered["inspection"].append(formatted)
    elif rule.get("report_required"): triggered["report"].append(formatted)
    elif rule.get("action_required"): triggered["action"].append(formatted)
    else: triggered.get(RULE_TYPE_MAP.get(str(rule.get("rule_type_code", "")), "action"), triggered["action"]).append(formatted)


def _classify_rules_db(rules: List[Dict[str, Any]], triggered: Dict[str, List]) -> None:
    seen_appoint: set = set()
    for rule in rules:
        formatted = format_rule_result_db(rule)
        ot = (rule.get("obligation_type") or "").strip().upper()
        if ot == "APPOINT":
            target = _normalize_target_code((rule.get("appointment_target_code") or rule.get("rule_id") or "").strip())
            if target and target in seen_appoint: continue
            if target: seen_appoint.add(target)
            triggered["appointment"].append(formatted)
        elif ot == "INSPECT": triggered["inspection"].append(formatted)
        elif ot == "NOTIFY": triggered.setdefault("notify", []).append(formatted)
        elif ot == "REPORT": triggered["report"].append(formatted)
        elif ot == "ACTION": triggered["action"].append(formatted)
        else:
            if rule.get("appointment_required"):
                target = _normalize_target_code((rule.get("appointment_target_code") or rule.get("rule_id") or "").strip())
                if target and target in seen_appoint: continue
                if target: seen_appoint.add(target)
                triggered["appointment"].append(formatted)
            elif rule.get("inspection_required"): triggered["inspection"].append(formatted)
            elif rule.get("notify_required"): triggered.setdefault("notify", []).append(formatted)
            elif rule.get("report_required"): triggered["report"].append(formatted)
            elif rule.get("action_required"): triggered["action"].append(formatted)
            else: triggered["action"].append(formatted)


def _evaluate_conditions(context: dict, rules: list) -> tuple:
    a, na = [], []
    for rule in rules: (a if _check_rule_conditions(rule, context) else na).append(rule)
    return a, na


async def _evaluate_equipment_conditions(factory_id, factory_context, rules, supabase):
    eq_res = supabase.table("equipment_assets").select("equipment_type_code, quantity, capacity_value").eq("factory_id", factory_id).execute()
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
    if not process_ids: return [], rules
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


def _build_result(applicable, not_applicable, all_rules, mode, evaluated_at, source_pairs=None, include_not_applicable=True, **extra_fields):
    triggered = {"appointment": [], "inspection": [], "action": [], "report": []}
    if source_pairs is not None: _classify_rules_with_source(source_pairs, triggered)
    else: _classify_rules(applicable, triggered)
    total = sum(len(triggered[k]) for k in triggered)
    rep_list = triggered["report"]
    notify_list = [x for x in rep_list if _is_notify(x)]
    report_only = [x for x in rep_list if not _is_notify(x)]
    result = {
        "engine_version": ENGINE_VERSION, "mode": mode, "evaluated_at": evaluated_at,
        "total_rules_checked": len(all_rules), "not_applicable_count": len(not_applicable),
        "applicable_count": total, "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"], "action_required": triggered["action"],
        "report_required": triggered["report"],
        "summary": {"total": total, "appointment": len(triggered["appointment"]),
                    "inspection": len(triggered["inspection"]), "action": len(triggered["action"]),
                    "report": len(report_only), "notify": len(notify_list)},
        **extra_fields,
    }
    if include_not_applicable: result["not_applicable"] = [format_rule_result(r) for r in not_applicable]
    return result


@router.post("/apply/{factory_id}")
async def apply_legal_engine(factory_id: str, body: Optional[dict] = None, mode: str = Query("all")):
    supabase = get_supabase()
    if body and body.get("mode"): mode = body["mode"]
    if mode not in ("facility", "process", "equipment", "all"):
        raise HTTPException(status_code=400, detail="mode는 facility/process/equipment/all 중 하나여야 합니다.")
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).single().execute()
    if not fac_res.data: raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    factory = fac_res.data
    factory_sector = str(factory.get("sector") or "BUILDING").upper()
    sector_groups = get_sector_groups(factory_sector)
    rules_res = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).in_("sector", sector_groups).execute()
    all_rules = rules_res.data or []
    evaluated_at = _now_iso()
    context = _factory_to_context(factory)
    triggered_by_source: Dict[str, Any] = {"factory_condition": 0, "registered_equipment": 0, "process_recommended": 0, "sector_groups": sector_groups}
    sec = str(factory.get("sector") or factory.get("site_type") or "").upper()
    if sec == "CONSTRUCTION":
        triggered_by_source.update({"construction_type": factory.get("construction_type"), "total_worker_count": get_effective_worker_count(factory), "subcontractor_count": int(factory.get("subcontractor_worker_count") or 0), "threshold_used": get_construction_amount_threshold(factory)})
    if mode == "facility":
        applicable, not_applicable = _evaluate_conditions(context, all_rules)
        triggered_by_source["factory_condition"] = len(applicable); source_pairs = None
    elif mode == "process":
        applicable, not_applicable = await _evaluate_process_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["process_recommended"] = len(applicable); source_pairs = None
    elif mode == "equipment":
        applicable, not_applicable = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["registered_equipment"] = len(applicable); source_pairs = None
    else:
        fac_app, _ = _evaluate_conditions(context, all_rules); triggered_by_source["factory_condition"] = len(fac_app)
        eq_app, _  = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase); triggered_by_source["registered_equipment"] = len(eq_app)
        proc_app, _ = await _evaluate_process_conditions(factory_id, context, all_rules, supabase); triggered_by_source["process_recommended"] = len(proc_app)
        rule_map = {}
        for r in fac_app:  rule_map[r["rule_id"]] = (r, "🏢 시설조건")
        for r in eq_app:   rule_map.setdefault(r["rule_id"], (r, "⚙️ 등록설비"))
        for r in proc_app: rule_map.setdefault(r["rule_id"], (r, "🔄 공정추천"))
        source_pairs = list(rule_map.values())
        applicable_ids = {r["rule_id"] for r, _ in source_pairs}
        not_applicable = [r for r in all_rules if r["rule_id"] not in applicable_ids]; applicable = []
    result_for_db = _build_result(applicable, not_applicable, all_rules, mode, evaluated_at, source_pairs=source_pairs, include_not_applicable=True, factory_id=factory_id, triggered_by_source=triggered_by_source)
    result_for_response = _build_result(applicable, not_applicable, all_rules, mode, evaluated_at, source_pairs=source_pairs, include_not_applicable=False, factory_id=factory_id, triggered_by_source=triggered_by_source)
    try: supabase.table("factories").update({"legal_result_json": result_for_db, "last_diagnosis_at": evaluated_at, "diagnosis_status": "DONE", "legal_applicable_count": result_for_db.get("applicable_count", 0), "updated_at": evaluated_at}).eq("id", factory_id).execute()
    except Exception as e: print(f"[LEGAL ENGINE] factories 저장 실패: {e}")
    try: supabase.table("legal_applications").upsert({"factory_id": factory_id, "engine_version": ENGINE_VERSION, "mode": mode, "result_json": result_for_db, "evaluated_at": evaluated_at}, on_conflict="factory_id,mode").execute()
    except Exception as e: print(f"[LEGAL ENGINE] legal_applications 저장 실패 (무시): {e}")
    return {"status": "success", "data": result_for_response}


@router.post("/apply-quote/{quote_id}")
async def apply_legal_engine_from_quote(quote_id: str):
    supabase = get_supabase()
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data: raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd: raise HTTPException(status_code=400, detail="survey_data가 없습니다.")
    context = _survey_data_to_context(sd)
    rules_res = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).execute()
    all_rules = rules_res.data or []
    evaluated_at = _now_iso()
    applicable, not_applicable = _evaluate_conditions(context, all_rules)
    result_data = _build_result(applicable, not_applicable, all_rules, "facility", evaluated_at, include_not_applicable=False, quote_id=quote_id, quote_no=qres.data.get("quote_no"), source="quote_survey", not_applicable_total=len(not_applicable), triggered_by_source={"factory_condition": len(applicable)})
    try: supabase.table("quotes").update({"legal_result_json": result_data, "legal_evaluated_at": evaluated_at, "legal_applicable_count": result_data["applicable_count"], "updated_at": evaluated_at}).eq("id", quote_id).execute()
    except Exception as e: print(f"[LEGAL ENGINE] quotes 저장 실패: {e}")
    return {"status": "success", "data": result_data}


class DiagnoseStep1Body(BaseModel):
    factory_id: Optional[str] = Field(None)
    sector: str = Field(...)
    input: Optional[Dict[str, Any]] = Field(default_factory=dict)
    building_use_type: Optional[str] = None
    employee_count: Optional[int] = None
    floor_area: Optional[float] = None
    worker_count: Optional[int] = None
    total_floor_area: Optional[float] = None
    electric_capacity: Optional[float] = None
    floor_count: Optional[int] = None
    # BE-3: 단위 명확화 — 억원(100,000,000원) 단위. 150억 → 150 입력. 원화(원) 입력 시 오판정 발생
    contract_amount_eok: Optional[float] = Field(
        None,
        description="공사금액 단위: 억원(1억=100,000,000원). 예) 150억원 공사 → 150 입력. "
                    "원화(원) 단위로 입력하면 판정 오류 발생.",
    )
    ksic_major: Optional[str] = None
    facility_type: Optional[str] = None
    elevator_count: Optional[int] = Field(None)
    gas_capacity_kg: Optional[float] = Field(None)
    gas_capacity_m3: Optional[float] = Field(None)
    boiler_capacity_kw: Optional[float] = Field(None)
    annual_energy_toe: Optional[float] = Field(None)
    has_high_pressure_gas: Optional[bool] = Field(None)
    has_boiler: Optional[bool] = Field(None)
    has_hazardous_material: Optional[bool] = Field(None)
    has_chemical_substance: Optional[bool] = Field(None)
    construction_type: Optional[str] = None
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    electrical_capacity_kw: Optional[float] = None
    has_tunnel_bridge: Optional[bool] = None
    has_blasting: Optional[bool] = None
    has_crane: Optional[bool] = None
    has_high_work: Optional[bool] = Field(None)


ALLOWED_DIAGNOSE_SECTORS = frozenset({"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"})

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
    "contract_amount":          "construction_amount",
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
    if v is True: return True
    if v in (False, None, "", 0): return False
    if isinstance(v, (int, float)): return v != 0
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _input_to_facility_context(sector: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    sec = sector.strip().upper()
    ctx: Dict[str, Any] = {
        "worker_count": 0, "total_floor_area": 0.0, "electric_capacity": 0.0,
        "building_use_code": "", "ksic_code": "", "floor_count": 0,
        "construction_amount": 0.0, "contract_amount": 0.0,
        "is_hazardous_material": 0, "is_multi_use": 0, "is_factory_registered": 0,
        "has_high_pressure_gas": 0, "has_hazardous_material": 0, "has_chemical_substance": 0,
        "has_boiler": 0, "has_tunnel_bridge": 0, "hospital_beds": 0, "student_count": 0,
        "gas_capacity_kg": 0, "gas_capacity_m3": 0, "boiler_capacity_kw": 0,
        "elevator_count": 0, "annual_energy_toe": 0,
    }
    if sec == "BUILDING":
        ctx["building_use_code"]     = str(inp.get("building_use") or inp.get("building_use_type") or inp.get("building_use_code") or "")
        ctx["total_floor_area"]      = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["building_area"]         = ctx["total_floor_area"]
        ctx["floor_count"]           = int(inp.get("floor_count") or 0)
        ctx["worker_count"]          = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"]     = float(inp.get("electric_capacity") or 0)
        ctx["electrical_capacity_kw"]= ctx["electric_capacity"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["gas_capacity_kg"]       = float(inp.get("gas_capacity_kg") or 0) or ctx["has_high_pressure_gas"]
        ctx["gas_capacity_m3"]       = float(inp.get("gas_capacity_m3") or 0)
        ctx["has_hazardous_material"]= 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["elevator_count"]        = int(inp.get("elevator_count") or 0) or (1 if _truthy(inp.get("has_elevator")) else 0)
        ctx["annual_energy_toe"]     = float(inp.get("annual_energy_toe") or 0)
        ctx["has_boiler"]            = 1 if _truthy(inp.get("has_boiler")) else 0
        ctx["boiler_capacity_kw"]    = float(inp.get("boiler_capacity_kw") or 0) or ctx["has_boiler"]
    elif sec == "MANUFACTURING":
        ctx["ksic_code"]             = str(inp.get("ksic_major") or inp.get("ksic_code") or "")
        ctx["worker_count"]          = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"]     = float(inp.get("electric_capacity") or 0)
        ctx["electrical_capacity_kw"]= ctx["electric_capacity"]
        ctx["has_hazardous_material"]= 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"] = ctx["has_hazardous_material"]
        ctx["has_high_pressure_gas"] = 1 if _truthy(inp.get("has_high_pressure_gas")) else 0
        ctx["gas_capacity_kg"]       = float(inp.get("gas_capacity_kg") or 0) or ctx["has_high_pressure_gas"]
        ctx["gas_capacity_m3"]       = float(inp.get("gas_capacity_m3") or 0) or (1 if _truthy(inp.get("has_city_gas")) else 0)
        ctx["has_boiler"]            = 1 if _truthy(inp.get("has_boiler")) else 0
        ctx["boiler_capacity_kw"]    = float(inp.get("boiler_capacity_kw") or 0) or ctx["has_boiler"]
        ctx["has_chemical_substance"]= 1 if _truthy(inp.get("has_chemical_substance")) else 0
        ctx["elevator_count"]        = int(inp.get("elevator_count") or 0) or (1 if _truthy(inp.get("has_elevator")) else 0)
        ctx["annual_energy_toe"]     = float(inp.get("annual_energy_toe") or 0)
        ctx["building_area"]         = float(inp.get("building_area") or inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["total_floor_area"]      = ctx["building_area"]
        ksic = ctx["ksic_code"].upper()
        ctx["is_factory_registered"] = 1 if (_truthy(inp.get("is_factory_registered")) or ksic.startswith("C")) else 0
    elif sec == "CONSTRUCTION":
        eok = float(inp.get("contract_amount_eok") or 0)
        amount = eok * 100_000_000.0
        ctx["construction_amount"] = amount; ctx["contract_amount"] = amount
        raw_site = str(inp.get("construction_type") or inp.get("site_type") or "건축")
        SITE_KO = {"BUILDING": "건축", "CIVIL": "토목", "SPECIALTY": "공통"}
        site_type = SITE_KO.get(raw_site.upper(), raw_site)
        ctx["construction_type"] = site_type; ctx["building_use_code"] = site_type
        ctx["is_building"] = 1 if site_type in ("건축", "BUILDING") else 0
        ctx["is_civil"]    = 1 if site_type in ("토목", "CIVIL")    else 0
        direct = int(inp.get("direct_workers") or inp.get("worker_count") or inp.get("employee_count") or 0)
        subcon = int(inp.get("subcon_workers") or inp.get("subcontractor_worker_count") or 0)
        ctx["worker_count"] = direct + subcon; ctx["employee_count"] = direct + subcon
        ctx["direct_workers"] = direct; ctx["subcon_workers"] = subcon; ctx["subcontractor_worker_count"] = subcon
        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0
        ctx["has_blasting"]      = 1 if _truthy(inp.get("has_blasting"))      else 0
        ctx["has_crane"]         = 1 if _truthy(inp.get("has_crane"))          else 0
        ctx["has_high_work"]     = 1 if _truthy(inp.get("has_high_work"))     else 0
        elec_kw = float(inp.get("electrical_capacity_kw") or inp.get("electric_capacity") or 0)
        ctx["electric_capacity"] = elec_kw; ctx["electrical_capacity_kw"] = elec_kw; ctx["transformer_capacity_kva"] = elec_kw
        ctx["safety_manager_threshold"] = get_construction_amount_threshold({"construction_type": site_type})
    elif sec in ("SPECIAL_FACILITY", "SPECIAL"):
        ctx["building_use_code"] = str(inp.get("facility_type") or "")
        ctx["total_floor_area"]  = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["hospital_beds"]     = int(inp.get("hospital_beds") or 0)
        ctx["student_count"]     = int(inp.get("student_count") or 0)
        ctx["worker_count"]      = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["building_area"]     = ctx["total_floor_area"]
    return ctx


def _risk_level(applicable_count: int, appointment_n: int) -> str:
    if applicable_count >= 12 or appointment_n >= 4: return "HIGH"
    if applicable_count >= 5  or appointment_n >= 1: return "MEDIUM"
    return "LOW"


def _numeric_compare(actual: float, operator: str, value: float) -> bool:
    op = (operator or "gte").lower()
    try:
        if op in ("gte", ">="): return actual >= value
        if op in ("lte", "<="): return actual <= value
        if op in ("gt",  ">" ): return actual > value
        if op in ("lt",  "<" ): return actual < value
        if op in ("eq",  "=", "=="): return actual == value
    except (TypeError, ValueError): return False
    return False


def _db_rule_matches_facility(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
    cc = rule.get("condition_code"); cv = rule.get("condition_value")
    if not cc or cv is None: return False
    ctx_key = CONDITION_CODE_TO_CONTEXT_KEY.get(cc, cc)
    actual = context.get(ctx_key)
    if actual is None: actual = context.get(cc)
    if actual is None: return False
    try:
        an, vn = float(actual), float(cv)
    except (TypeError, ValueError):
        return str(actual) == str(cv) and (rule.get("condition_operator_code") or "eq").lower() in ("eq", "=", "==")
    return _numeric_compare(an, rule.get("condition_operator_code") or "gte", vn)


def _evaluate_facility_conditions_db(facility_ctx: Dict[str, Any], rules: List[Dict[str, Any]], sector: str = "") -> tuple:
    applicable: List[Dict[str, Any]] = []; not_applicable: List[Dict[str, Any]] = []
    for rule in rules:
        rule_sector = (rule.get("sector") or "").upper()
        cc = rule.get("condition_code"); cv = rule.get("condition_value")
        if not cc or cv is None:
            if rule_sector in ("COMMON", "CONSTRUCTION_MANUFACTURING", "BUILDING_CONSTRUCTION", "BUILDING_MANUFACTURING"):
                applicable.append(rule)
            elif sector == "CONSTRUCTION":
                law = rule.get("law_name") or ""; ot = (rule.get("obligation_type") or "").upper(); article = rule.get("law_article") or ""
                if (ot in ("APPOINT", "NOTIFY") and "산업안전보건법" in law and "16조" in article):
                    if float(facility_ctx.get("worker_count") or 0) >= 50: applicable.append(rule)
                    else: not_applicable.append(rule)
                elif any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES): applicable.append(rule)
                else: not_applicable.append(rule)
            else: applicable.append(rule)
        elif _db_rule_matches_facility(rule, facility_ctx): applicable.append(rule)
        else: not_applicable.append(rule)
    return applicable, not_applicable


def _get_construction_summary(facility_ctx: Dict[str, Any]) -> Dict[str, Any]:
    amount    = float(facility_ctx.get("construction_amount") or 0)
    workers   = int(facility_ctx.get("worker_count") or 0)
    site_type = str(facility_ctx.get("construction_type") or facility_ctx.get("building_use_code") or "건축")
    subcon    = int(facility_ctx.get("subcon_workers") or facility_ctx.get("subcontractor_worker_count") or 0)
    direct    = int(facility_ctx.get("direct_workers") or (workers - subcon))
    threshold = get_construction_amount_threshold({"construction_type": site_type})
    sm_required = (amount >= threshold) or (workers >= 50)
    SITE_LABEL = {"건축": "건축", "토목": "토목", "공통": "공통", "기타": "기타", "BUILDING": "건축", "CIVIL": "토목", "SPECIALTY": "공통"}
    site_label = SITE_LABEL.get(site_type, site_type)
    _threshold_eok = int(threshold / 100_000_000)
    basis_parts = [f"{site_label} {_threshold_eok}억원 {'이상' if amount >= threshold else '미만'}"]
    if workers >= 50: basis_parts.append(f"근로자(하도급 포함) {workers}명 >= 50명")
    return {
        "site_type": site_type, "contract_amount": amount,
        "contract_amount_eok": round(amount / 100_000_000, 2) if amount else 0,
        "total_workers": workers, "direct_workers": direct, "subcon_workers": subcon,
        "safety_manager_required": sm_required, "safety_manager_basis": ", ".join(basis_parts),
        "threshold_used": threshold,
        "key_thresholds_met": {
            "1억_산업안전보건관리비":    amount >= 100_000_000,
            "50억_유해위험방지계획서":   amount >= 5_000_000_000,
            "50억_기초안전보건교육":     amount >= 5_000_000_000,
            "100억_안전관리계획서":      amount >= 10_000_000_000,
            "120억_안전관리자선임_토목": site_type in ("토목", "CIVIL")    and amount >= 12_000_000_000,
            "150억_안전관리자선임_건축": site_type in ("건축", "BUILDING") and amount >= 15_000_000_000,
            "200억_안전보건관리책임자":  amount >= 20_000_000_000,
            "1000억_건설안전판정사":     amount >= 100_000_000_000,
            "50명이상_안전관리자선임":   workers >= 50,
            "300명이상_안전관리자선임":  workers >= 300,
        },
    }


@router.post("/diagnose/step1")
async def diagnose_step1(body: DiagnoseStep1Body):
    sector_raw = body.sector.strip().upper()
    if sector_raw not in ALLOWED_DIAGNOSE_SECTORS:
        raise HTTPException(status_code=400, detail="sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.")
    factory_id = (body.factory_id or "").strip()
    supabase = get_supabase()
    _fac_company_id = None  # BE-1: inspection_sets 자동생성용
    if factory_id:
        # BE-3: company_id도 함께 조회 (inspection_sets 생성에 필요)
        fac_check = supabase.table("factories").select("id, company_id").eq("id", factory_id).limit(1).execute()
        if not fac_check.data: raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
        _fac_company_id = fac_check.data[0].get("company_id")

    sector_groups = get_sector_groups(_normalize_sector_db(sector_raw))
    rules_res = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).in_("sector", sector_groups).eq("diagnosis_stage", 1).execute()
    all_rules = rules_res.data or []

    inp = dict(body.input or {})
    flat_fields = {
        "building_use_type": body.building_use_type, "employee_count": body.employee_count,
        "floor_area": body.floor_area, "worker_count": body.worker_count,
        "total_floor_area": body.total_floor_area, "electric_capacity": body.electric_capacity,
        "floor_count": body.floor_count, "contract_amount_eok": body.contract_amount_eok,
        "ksic_major": body.ksic_major, "facility_type": body.facility_type,
        "elevator_count": body.elevator_count,
        "gas_capacity_kg": body.gas_capacity_kg, "gas_capacity_m3": body.gas_capacity_m3,
        "boiler_capacity_kw": body.boiler_capacity_kw, "annual_energy_toe": body.annual_energy_toe,
        "has_high_pressure_gas": body.has_high_pressure_gas, "has_boiler": body.has_boiler,
        "has_hazardous_material": body.has_hazardous_material, "has_chemical_substance": body.has_chemical_substance,
        "construction_type": body.construction_type, "direct_workers": body.direct_workers,
        "subcon_workers": body.subcon_workers, "electrical_capacity_kw": body.electrical_capacity_kw,
        "has_tunnel_bridge": body.has_tunnel_bridge, "has_blasting": body.has_blasting,
        "has_crane": body.has_crane, "has_high_work": body.has_high_work,
    }
    for k, v in flat_fields.items():
        if v is not None and k not in inp: inp[k] = v

    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()
    applicable, not_applicable = _evaluate_facility_conditions_db(facility_ctx, all_rules, sector_raw)

    triggered: Dict[str, List] = {"appointment": [], "inspection": [], "notify": [], "report": [], "action": [], "not_applicable": []}
    _classify_rules_db(applicable, triggered)
    for r in not_applicable: triggered["not_applicable"].append(format_rule_result_db(r))

    total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
    law_names = sorted({x.get("law_name") for x in applicable if x.get("law_name")})
    obligations: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        if triggered[key]: obligations.append({"category": key, "label": label, "items": triggered[key]})
    if triggered["report"]: obligations.append({"category": "report", "label": "신고", "items": triggered["report"]})
    if triggered["notify"]: obligations.append({"category": "notify", "label": "보고", "items": triggered["notify"]})

    rules_table: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        for row in triggered[key]: rules_table.append({"category": label, **row})
    for row in triggered["report"]: rules_table.append({"category": "신고", **row})
    for row in triggered["notify"]: rules_table.append({"category": "보고", **row})

    appointment_n = len(triggered["appointment"])
    risk = _risk_level(total_applicable, appointment_n)
    law_cats: List[str] = []; seen: set = set()
    for x in applicable:
        c = (x.get("law_category_code") or x.get("law_name") or "").strip()
        if c and c not in seen: seen.add(c); law_cats.append(c)

    # Task 1: remarks 우선 → obligation_summary 폴백 (사람 언어 표시)
    key_obligations: List[str] = []
    for x in applicable[:20]:
        t = (x.get("remarks") or x.get("obligation_summary") or "").strip()
        if t and t not in key_obligations: key_obligations.append(t)

    insp_by_type = {
        "PERIODIC":    [r for r in triggered["inspection"] if r.get("schedule_type") == "PERIODIC"],
        "BEFORE_WORK": [r for r in triggered["inspection"] if r.get("schedule_type") == "BEFORE_WORK"],
        "ON_DEMAND":   [r for r in triggered["inspection"] if r.get("schedule_type") == "ON_DEMAND"],
    }

    # Task 5: risk_reason 필드 생성
    all_items_flat = (
        triggered["appointment"] + triggered["inspection"] +
        triggered["action"] + triggered["report"] + triggered["notify"]
    )
    urgent_count = len([r for r in all_items_flat if (r.get("due_info") or {}).get("urgency") == "URGENT"])
    _max_pen = next(
        (r.get("penalty_summary") or r.get("penalty_amount") or ""
         for r in all_items_flat
         if (r.get("penalty_summary") or r.get("penalty_amount") or "").strip()
         and "확인 필요" not in (r.get("penalty_summary") or "")
         and "부과 가능" not in (r.get("penalty_summary") or "")),
        ""
    )
    risk_reason = f"적용 법령 {len(law_names)}개, 법적 의무 {total_applicable}건"
    if urgent_count > 0:
        risk_reason += f", 긴급 이행 {urgent_count}건"
    if _max_pen:
        risk_reason += f", 최대 {_max_pen}"

    result_data = {
        "factory_id": factory_id or None, "sector": sector_raw, "sector_groups": sector_groups,
        "step": 1, "engine_version": ENGINE_VERSION, "evaluated_at": evaluated_at,
        "facility_context": facility_ctx, "risk_level": risk,
        "risk_reason": risk_reason,  # Task 5
        "applicable_law_categories": law_cats, "appointment_required_flag": appointment_n > 0,
        "key_obligations": key_obligations, "law_badges": law_names,
        "obligations": obligations, "rules_table": rules_table,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "not_applicable": triggered["not_applicable"][:100],
        "not_applicable_total": len(not_applicable),
        "total_rules_checked": len(all_rules), "applicable_count": total_applicable,
        "inspection_schedule_ready": {
            "periodic_count":    len(insp_by_type["PERIODIC"]),
            "before_work_count": len(insp_by_type["BEFORE_WORK"]),
            "on_demand_count":   len(insp_by_type["ON_DEMAND"]),
            "periodic":          insp_by_type["PERIODIC"],
            "before_work":       insp_by_type["BEFORE_WORK"],
        },
        "summary": {
            "total": total_applicable, "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]), "action": len(triggered["action"]),
            "report": len(triggered["report"]), "notify": len(triggered["notify"]),
            "form_linked": sum(1 for r in applicable if (r.get("form_code") or "").strip()),
        },
    }
    if sector_raw == "CONSTRUCTION": result_data["construction_summary"] = _get_construction_summary(facility_ctx)

    diagnosis_id = None
    if factory_id:
        try: supabase.table("factory_diagnosis_results").update({"is_latest": False}).eq("factory_id", factory_id).eq("sector", sector_raw).eq("is_latest", True).execute()
        except Exception: pass
        try:
            save_res = supabase.table("factory_diagnosis_results").insert({"factory_id": factory_id, "sector": sector_raw, "diagnosis_stage": 1, "input_data": inp, "result_data": result_data, "rule_count": total_applicable, "is_latest": True}).execute()
            if save_res.data: diagnosis_id = save_res.data[0].get("id")
        except Exception as e: print(f"[DIAGNOSE STEP1] factory_diagnosis_results 저장 실패: {e}")
        if diagnosis_id and applicable:
            try:
                rule_rows = [{"diagnosis_id": diagnosis_id, "rule_code": r.get("rule_id") or r.get("rule_code") or "", "rule_name": (r.get("remarks") or r.get("obligation_summary") or "").strip(), "law_name": r.get("law_name") or "", "law_article": r.get("law_article") or "", "obligation": (r.get("remarks") or r.get("obligation_summary") or "").strip(), "obligation_type": _resolve_obligation_type(r), "due_date": None, "status": "PENDING", "form_code": r.get("form_code") or None} for r in applicable]
                for i in range(0, len(rule_rows), 50): supabase.table("diagnosis_rule_results").insert(rule_rows[i:i+50]).execute()
            except Exception as e: print(f"[DIAGNOSE STEP1] diagnosis_rule_results 저장 실패: {e}")

    # v5.6.7: CONSTRUCTION sector 법령진단 완료 시 일정 자동생성 트리거
    if factory_id and sector_raw == "CONSTRUCTION" and diagnosis_id:
        try:
            from routers.legal_engine_patch import generate_schedules_from_diagnosis
            generate_schedules_from_diagnosis(factory_id)
        except Exception as e:
            print(f"[AUTO_SCHEDULE] 건설현장 일정 자동생성 실패: {e}")

    # v5.6.8 BE-1: inspection_sets 자동 생성 (모든 섹터)
    if factory_id and diagnosis_id and applicable:
        try:
            from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis
            auto_create_inspection_sets_from_diagnosis(supabase, factory_id, _fac_company_id, applicable)
        except Exception as e:
            print(f"[AUTO_INSPECT_SETS] inspection_sets 자동생성 실패: {e}")

    result_data["diagnosis_id"] = diagnosis_id
    return {"status": "success", "data": result_data}


@router.get("/quote-result/{quote_id}")
async def get_legal_result_from_quote(quote_id: str):
    supabase = get_supabase()
    res = supabase.table("quotes").select("id, quote_no, legal_result_json, legal_evaluated_at, legal_applicable_count").eq("id", quote_id).single().execute()
    if not res.data: raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    if not res.data.get("legal_result_json"): raise HTTPException(status_code=404, detail="판정 결과 없음.")
    return {"status": "success", "data": {"quote_id": quote_id, "quote_no": res.data.get("quote_no"), "legal_evaluated_at": res.data.get("legal_evaluated_at"), "legal_applicable_count": res.data.get("legal_applicable_count"), "result": res.data.get("legal_result_json")}}


@router.get("/result/{factory_id}")
async def get_legal_result(factory_id: str, mode: str = Query("all")):
    supabase = get_supabase()
    try:
        fac = supabase.table("factories").select("legal_result_json, last_diagnosis_at, legal_applicable_count, diagnosis_status").eq("id", factory_id).single().execute()
        if fac.data and fac.data.get("legal_result_json"):
            rj = fac.data["legal_result_json"]; rj.pop("not_applicable", None)
            return {"status": "success", "data": {**rj, "last_diagnosis_at": fac.data.get("last_diagnosis_at"), "legal_applicable_count": fac.data.get("legal_applicable_count"), "diagnosis_status": fac.data.get("diagnosis_status")}}
    except Exception: pass
    try:
        res = supabase.table("legal_applications").select("*").eq("factory_id", factory_id).eq("mode", mode).order("evaluated_at", desc=True).limit(1).execute()
        if res.data:
            rj = res.data[0].get("result_json", {}); rj.pop("not_applicable", None)
            return {"status": "success", "data": rj}
    except Exception: pass
    raise HTTPException(status_code=404, detail="판정 결과 없음.")


@router.get("/summary/{factory_id}")
async def get_legal_summary(factory_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("legal_applications").select("mode, evaluated_at, result_json").eq("factory_id", factory_id).order("evaluated_at", desc=True).limit(4).execute()
    except Exception: return {"status": "success", "data": {"factory_id": factory_id, "results": []}}
    results = [{"mode": row.get("mode", "all"), "evaluated_at": row.get("evaluated_at"), "summary": row.get("result_json", {}).get("summary", {}), "engine_version": row.get("result_json", {}).get("engine_version", "")} for row in (res.data or [])]
    return {"status": "success", "data": {"factory_id": factory_id, "results": results}}


@router.post("/create-inspection-sets/{factory_id}")
async def create_inspection_sets_from_legal(factory_id: str):
    supabase = get_supabase()
    fac = supabase.table("factories").select("id, company_id, legal_result_json").eq("id", factory_id).single().execute()
    if not fac.data: raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    company_id  = fac.data.get("company_id")
    result_json = fac.data.get("legal_result_json")
    inspection_rules: List[Dict[str, Any]] = result_json.get("inspection_required", []) if result_json else []
    if not inspection_rules: return {"status": "success", "message": "생성할 점검 항목이 없습니다.", "data": {"created": 0}}
    existing_res = supabase.table("inspection_sets").select("legal_rule_id").eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").eq("is_active", True).execute()
    existing_rule_ids = {r["legal_rule_id"] for r in (existing_res.data or []) if r.get("legal_rule_id")}
    insert_rows = []
    for rule in inspection_rules:
        rule_id = rule.get("rule_id", "")
        if rule_id in existing_rule_ids: continue
        law_name = rule.get("law_name", "")
        cycle_code = rule.get("inspection_cycle_code") or ""
        cycle_unit, cycle_value = CYCLE_CODE_MAP.get(cycle_code, ("year", 1))
        schedule_type = rule.get("schedule_type") or "PERIODIC"
        _unit_label = "년" if cycle_unit == "year" else "개월"
        insert_rows.append({
            "company_id": company_id, "factory_id": factory_id,
            "inspection_set_name": f"{law_name} 점검", "inspection_set_code": rule_id, "legal_rule_id": rule_id,
            "law_name": law_name, "law_article": rule.get("law_article", ""),
            "cycle_unit": cycle_unit, "cycle_value": cycle_value, "cycle_base_type": "LAST_INSPECTION",
            "cycle_base_guide": (f"마지막 점검일로부터 {cycle_value}{_unit_label}마다" if schedule_type == "PERIODIC"
                                 else f"작업({rule.get('construction_work_type','')}) 시작 전 실시"),
            "description": rule.get("description", ""), "source": "LEGAL_ENGINE", "is_active": True,
            "anchor_confirmed": False, "status_code": "PENDING_ANCHOR",
        })
    if not insert_rows: return {"status": "success", "message": f"모두 기존 유지 ({len(existing_rule_ids)}개)", "data": {"created": 0}}
    created = 0
    for i in range(0, len(insert_rows), 20):
        res = supabase.table("inspection_sets").insert(insert_rows[i:i+20]).execute()
        created += len(res.data or [])
    return {"status": "success", "message": f"{created}개 생성", "data": {"created": created}}


@router.get("/debug/context/{quote_id}")
async def debug_quote_context(quote_id: str):
    supabase = get_supabase()
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data: raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd: raise HTTPException(status_code=400, detail="survey_data 없음")
    return {"status": "success", "quote_no": qres.data.get("quote_no"), "context": _survey_data_to_context(sd)}


def _evaluate_condition(rule: dict, input_data: dict) -> bool:
    def check(field, operator, value, data):
        if not field or field not in data: return True
        actual = data[field]
        if actual is None: return False
        try:
            if operator == '>=': return float(actual) >= float(value)
            elif operator == '<=': return float(actual) <= float(value)
            elif operator == '>': return float(actual) > float(value)
            elif operator == '<': return float(actual) < float(value)
            elif operator == '==': return str(actual) == str(value)
            elif operator == 'IN': return str(actual) in [v.strip() for v in str(value).split(',')]
            elif operator == 'NOT_IN': return str(actual) not in [v.strip() for v in str(value).split(',')]
            elif operator == '==true': return actual is True or str(actual).lower() == 'true'
            elif operator == '==false': return actual is False or str(actual).lower() == 'false'
        except Exception: return False
        return True
    c1_ok = check(rule.get('condition_1_field'), rule.get('condition_1_operator'), rule.get('condition_1_value'), input_data)
    if not c1_ok: return False
    c2_field = rule.get('condition_2_field')
    if c2_field:
        c2_ok = check(c2_field, rule.get('condition_2_operator'), rule.get('condition_2_value'), input_data)
        mode = rule.get('condition_mode', 'AND')
        if mode == 'AND' and not c2_ok: return False
        if mode == 'OR' and not (c1_ok or c2_ok): return False
    return True


def _determine_risk_level(rule_count: int) -> str:
    if rule_count >= 10: return 'HIGH'
    elif rule_count >= 5: return 'MEDIUM'
    return 'LOW'


def _save_diagnosis_result(supabase, factory_id: str, sector: str, stage: int, input_data: dict, matched_rules: list) -> dict:
    try: supabase.table('factory_diagnosis_results').update({'is_latest': False}).eq('factory_id', factory_id).eq('is_latest', True).execute()
    except Exception: pass
    law_categories = list(dict.fromkeys(r.get('law_name', '') for r in matched_rules if r.get('law_name')))
    key_obligations = [r.get('remarks') or r.get('obligation_summary') or r.get('rule_name', '') for r in matched_rules[:5]]
    has_appointment = any(r.get('rule_type') == 'APPOINTMENT' or r.get('appointment_required') for r in matched_rules)
    result_data = {'applicable_law_categories': law_categories, 'appointment_required': has_appointment, 'key_obligations': key_obligations, 'risk_level': _determine_risk_level(len(matched_rules)), 'rules': [{'rule_code': r.get('rule_code') or r.get('rule_id'), 'rule_name': r.get('remarks') or r.get('rule_name') or r.get('obligation_summary', ''), 'law_name': r.get('law_name', ''), 'law_article': r.get('law_article', ''), 'obligation': r.get('remarks') or r.get('obligation_summary') or r.get('rule_name', ''), 'rule_type': r.get('rule_type') or str(r.get('rule_type_code', '')), 'stage': r.get('diagnosis_stage', 1)} for r in matched_rules]}
    try:
        res = supabase.table('factory_diagnosis_results').insert({'factory_id': factory_id, 'sector': sector, 'diagnosis_stage': stage, 'input_data': input_data, 'result_data': result_data, 'rule_count': len(matched_rules), 'is_latest': True}).execute()
        return res.data[0] if res.data else {}
    except Exception as e: print(f"[DIAGNOSIS] 결과 저장 실패: {e}"); return {'result_data': result_data}


def _create_report_events_from_rules(supabase, factory_id: str, matched_rules: list):
    for rule in matched_rules:
        form_code = rule.get('form_code')
        if not form_code: continue
        try:
            if supabase.table('report_events').select('id').eq('factory_id', factory_id).eq('form_code', form_code).eq('status', 'PENDING').execute().data: continue
        except Exception: pass
        due_days = rule.get('due_days') or 14
        try: supabase.table('report_events').insert({'factory_id': factory_id, 'rule_code': rule.get('rule_code') or rule.get('rule_id'), 'form_code': form_code, 'trigger_date': date.today().isoformat(), 'due_date': (date.today() + timedelta(days=due_days)).isoformat(), 'status': 'PENDING'}).execute()
        except Exception as e: print(f"[DIAGNOSIS] report_events 생성 실패: {e}")


@router.post("/diagnose/step2")
def diagnose_step2(body: dict):
    supabase = get_supabase()
    factory_id = body.get('factory_id'); diagnosis_id = body.get('diagnosis_id')
    work_types: List[str] = list(body.get('construction_work_types') or [])
    work_type_codes_direct: List[str] = body.get('work_type_codes') or []
    kcsc_process_ids: List[str] = body.get('kcsc_process_ids') or []
    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table('factory_diagnosis_results').select('*').eq('id', diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception: pass
    sector = (prev or {}).get('sector', body.get('sector', 'CONSTRUCTION'))
    input_data = dict((prev or {}).get('input_data') or {}); input_data.update({'processes': body.get('processes', []), 'construction_types': body.get('construction_types', []), 'sector': sector})
    kcsc_processes: List[Dict] = []; kcsc_process_summary: List[Dict] = []
    if kcsc_process_ids:
        try:
            kcsc_res = supabase.table('kcsc_process_master').select('id, process_name, work_type_code, work_type_label, risk_level').in_('id', kcsc_process_ids).eq('is_active', True).execute()
            kcsc_processes = kcsc_res.data or []
        except Exception as e: print(f"[STEP2] kcsc_process_master 조회 실패: {e}")
        work_types = list(set(work_types + [p['work_type_code'] for p in kcsc_processes if p.get('work_type_code')]))
        input_data['kcsc_process_ids'] = kcsc_process_ids
        for p in kcsc_processes: kcsc_process_summary.append({'process_id': p['id'], 'process_name': p.get('process_name', ''), 'work_type_code': p.get('work_type_code'), 'work_type_label': p.get('work_type_label'), 'risk_level': p.get('risk_level', 'MEDIUM'), 'has_legal_rules': p.get('work_type_code') is not None})
    if work_type_codes_direct: work_types = list(set(work_types + work_type_codes_direct))
    sector_groups = get_sector_groups(sector)
    q = supabase.table('master_building_legal_rules').select('*').in_('sector', sector_groups).lte('diagnosis_stage', 2).eq('is_active', True)
    if sector == 'CONSTRUCTION' and work_types: q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({','.join(work_types)})")
    rules = q.execute().data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    diagnosis = {}
    if factory_id:
        diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 2, input_data, matched)
        _create_report_events_from_rules(supabase, factory_id, matched)
    prev_codes = {r.get('rule_code') for r in (prev or {}).get('result_data', {}).get('rules', []) if prev} if prev else set()
    added = [r for r in matched if (r.get('rule_code') or r.get('rule_id')) not in prev_codes]
    result = diagnosis.get('result_data', {})
    return {'status': 'success', 'diagnosis_id': diagnosis.get('id'), 'stage': 2, 'engine_version': ENGINE_VERSION, 'sector': sector, 'sector_groups': sector_groups, 'rule_count': len(matched), 'added_rule_count': len(added), 'kcsc_process_summary': kcsc_process_summary, 'summary': {'applicable_law_categories': result.get('applicable_law_categories', []), 'appointment_required': result.get('appointment_required', False), 'key_obligations': result.get('key_obligations', []), 'risk_level': result.get('risk_level', 'LOW')}, 'rules': result.get('rules', []), 'added_rules': [{'rule_code': r.get('rule_code') or r.get('rule_id'), 'rule_name': r.get('remarks') or r.get('rule_name') or r.get('obligation_summary', ''), 'law_article': r.get('law_article', '')} for r in added]}


@router.post("/diagnose/step3")
def diagnose_step3(body: dict):
    supabase = get_supabase()
    factory_id = body.get('factory_id')
    if not factory_id: raise HTTPException(status_code=400, detail='factory_id 필수')
    diagnosis_id = body.get('diagnosis_id')
    equipments: List[Dict] = list(body.get('equipments') or [])
    kcsc_work_ids: List[str] = list(body.get('kcsc_work_ids') or [])
    prev = None
    if diagnosis_id:
        try:
            prev_res = supabase.table('factory_diagnosis_results').select('*').eq('id', diagnosis_id).single().execute()
            prev = prev_res.data
        except Exception: pass
    sector = (prev or {}).get('sector', 'MANUFACTURING')
    input_data = dict((prev or {}).get('input_data') or {}); input_data['sector'] = sector
    extra_equipment_codes: List[str] = []; kcsc_work_summary: List[Dict] = []
    if kcsc_work_ids:
        try:
            for w in (supabase.table('kcsc_work_master').select('id, title, is_hazardous, hazard_type, equipment_type_codes, work_type_code').in_('id', kcsc_work_ids).execute().data or []):
                eq_codes = w.get('equipment_type_codes') or []
                extra_equipment_codes.extend(eq_codes)
                kcsc_work_summary.append({'work_id': w['id'], 'title': w.get('title', ''), 'is_hazardous': w.get('is_hazardous', False), 'equipment_codes': eq_codes})
            extra_equipment_codes = list(set(extra_equipment_codes))
        except Exception as e: print(f"[STEP3] kcsc_work_master 조회 실패: {e}")
    for code in extra_equipment_codes:
        if not any(e.get('equipment_code') == code for e in equipments): equipments.append({'equipment_code': code})
    input_data['equipments'] = equipments
    sector_groups_s3 = get_sector_groups(sector)
    q = supabase.table('master_building_legal_rules').select('*').in_('sector', sector_groups_s3).eq('diagnosis_stage', 3).eq('is_active', True)
    if sector == 'CONSTRUCTION' and extra_equipment_codes: q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({','.join(extra_equipment_codes)})")
    rules = q.execute().data or []
    matched = [r for r in rules if _evaluate_condition(r, input_data)]
    diagnosis = _save_diagnosis_result(supabase, factory_id, sector, 3, input_data, matched)
    return {'status': 'success', 'diagnosis_id': diagnosis.get('id'), 'stage': 3, 'sector': sector, 'engine_version': ENGINE_VERSION, 'rule_count': len(matched), 'kcsc_work_summary': kcsc_work_summary}


@router.get("/diagnose/{factory_id}/latest")
def get_latest_diagnosis(factory_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table('factory_diagnosis_results').select('*').eq('factory_id', factory_id).eq('is_latest', True).order('created_at', desc=True).limit(1).execute()
        if not res.data: raise HTTPException(status_code=404, detail='진단 결과 없음')
        return {'status': 'success', 'data': res.data[0]}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnose/{factory_id}/history")
def get_diagnosis_history(factory_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50)):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    res = supabase.table('factory_diagnosis_results').select('id, sector, diagnosis_stage, rule_count, is_latest, created_at', count='exact').eq('factory_id', factory_id).order('created_at', desc=True).range(offset, offset + page_size - 1).execute()
    return {'status': 'success', 'data': {'items': res.data or [], 'total': res.count or 0, 'page': page, 'page_size': page_size}}
