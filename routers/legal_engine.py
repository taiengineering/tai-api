"""
법령 판정 엔진 라우터 — v4.0.0
=================================
v4.0.0 핵심 수정 (이전 버전 완전 비작동 → 정상화):

[근본 문제]
기존 코드는 rule.get("conditions", []) 를 참조했으나
DB에 'conditions' 컬럼이 없어 항상 [] → 모든 룰 False
= 396개 룰 조회해도 항상 0건 매칭 (완전 비작동)

[수정 내용]
1. _check_rule_conditions: DB 실제 컬럼(condition_code/operator/value) 기반으로 전면 재작성
2. context 키 매핑: worker_count→employee_count, total_floor_area→building_area 등 DB 조건 코드와 일치
3. 설문 설비 항목(equip 배열) → is_hazardous_material, elevator_count, gas_capacity_kg 등 추론
4. _classify_rules: rule_type_code 숫자("001"=선임/"002"=점검/"003"=보고/"005"=금지·조치) 기반으로 수정
5. format_rule_result: 올바른 컬럼명 사용 + appointment_target_code/inspection_cycle 한글 변환
6. appointment_target_code 코드 → 한글명 매핑 테이블 추가
7. inspection_cycle_unit_code → 한글 주기 변환 추가

[rule_type_code 의미 (system_codes)]
001=선임, 002=점검, 003=보고, 004=허가, 005=금지·조치, 007=교육, 008=기록보존

[condition_code → context 키 매핑]
employee_count, building_area, electrical_capacity_kw, gas_capacity_kg, gas_capacity_m3,
boiler_capacity_kw, annual_energy_toe, elevator_count, is_multi_use, is_hazardous_material,
is_factory_registered, floor_count, contractor_count, transformer_capacity_kva, construction_amount
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Any, Dict
from datetime import datetime, timezone
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "4.0.0"


# ──────────────────────────────────────────────
# 코드 → 한글명 매핑 테이블
# ──────────────────────────────────────────────

APPOINTMENT_TARGET_MAP = {
    "safety_manager":          "안전관리자",
    "health_manager":          "보건관리자",
    "safety_health_director":  "안전보건관리책임자",
    "safety_health_manager":   "안전보건관리담당자",
    "fire_safety_manager":     "소방안전관리자",
    "electric_safety_manager": "전기안전관리자",
    "gas_safety_manager":      "가스안전관리자",
    "elevator_safety_manager": "승강기안전관리자",
    "energy_manager":          "에너지관리자",
    "building_manager":        "건축물관리자(유지관리자)",
    "hazardous_material_manager": "위험물안전관리자",
    "city_gas_manager":        "도시가스안전관리자",
}

INSPECTION_CYCLE_UNIT_MAP = {
    "003": "월 1회",
    "004": "분기 1회",
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
    "001": "appointment",   # 선임
    "002": "inspection",    # 점검
    "003": "report",        # 보고·신고
    "004": "action",        # 허가
    "005": "action",        # 금지·조치
    "007": "action",        # 교육
    "008": "action",        # 기록보존
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
# 설문 데이터 → DB condition_code 기반 context 변환
# ──────────────────────────────────────────────

def _survey_data_to_context(survey_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    견적 survey_data(JSON) → DB condition_code와 1:1 매핑되는 context dict
    condition_code 목록: employee_count, building_area, electrical_capacity_kw,
    gas_capacity_kg, gas_capacity_m3, boiler_capacity_kw, annual_energy_toe,
    elevator_count, is_multi_use, is_hazardous_material, is_factory_registered,
    floor_count, contractor_count, transformer_capacity_kva, construction_amount
    """
    snap = survey_data.get("survey_snapshot")
    if not isinstance(snap, dict):
        snap = {}

    equip_list = snap.get("equip") or []

    workers = _to_int(survey_data.get("employee_count"), snap.get("workers"))
    area    = _to_float(survey_data.get("floor_area"), snap.get("area"))
    power_kw = _to_float(survey_data.get("electrical_kw"), snap.get("elecKw"))
    floors  = _to_int(snap.get("floors"), survey_data.get("floors_above"))
    gas_kg  = _to_float(snap.get("gasKg"), survey_data.get("gas_kg"))
    boiler_th = _to_float(snap.get("boilerTh"), survey_data.get("boiler_th"))
    outsource = _to_int(snap.get("outsource"), survey_data.get("outsource_count"))

    # 설비 선택 배열에서 설비 유무 추론
    has_chem  = "chem" in equip_list or bool(survey_data.get("equip_chemical"))
    has_elev  = "elev" in equip_list or bool(survey_data.get("equip_elevator"))
    has_gas   = "gas"  in equip_list or gas_kg > 0
    has_boiler = "boiler" in equip_list or boiler_th > 0

    # 공장 등록 여부: KSIC C(제조업) 또는 건물용도 공장 판단
    btype = str(snap.get("btype") or snap.get("bldgUse") or
                survey_data.get("building_type") or "").strip()
    ksic  = str(survey_data.get("ksic_code") or snap.get("ksic_code") or "").strip()
    is_factory = 1 if (btype.startswith("공장") or btype.startswith("제조") or
                       ksic.upper().startswith("C")) else 0

    # 전기 변압기 용량 추정 (수전 용량으로 대체)
    transformer_kva = power_kw  # kW ≈ kVA (역률 1 가정, 보수적)

    # 공사금액 (원 단위, 억원→원 변환)
    cons_eok = _to_float(snap.get("constructionAmt"), survey_data.get("construction_amt"))
    cons_won = cons_eok * 100_000_000 if cons_eok > 0 else 0

    return {
        # 직접 매핑
        "employee_count":        workers,
        "building_area":         area,
        "electrical_capacity_kw": power_kw,
        "floor_count":           floors,
        "contractor_count":      outsource,
        "transformer_capacity_kva": transformer_kva,
        "construction_amount":   cons_won,
        # 가스: kg 단위 설비 선택 시 최소 1 부여
        "gas_capacity_kg":       gas_kg if gas_kg > 0 else (1 if has_gas else 0),
        "gas_capacity_m3":       1 if has_gas else 0,
        # 보일러: 톤/h → kW 환산(1t/h ≈ 700kW) 또는 최소 1
        "boiler_capacity_kw":   boiler_th * 700 if boiler_th > 0 else (1 if has_boiler else 0),
        "boiler_capacity_th":   boiler_th,
        # Boolean 조건 (1=해당, 0=미해당)
        "is_hazardous_material": 1 if has_chem else 0,
        "elevator_count":        1 if has_elev else 0,
        "is_factory_registered": is_factory,
        "is_multi_use":          0,   # 설문에서 판단 불가 → 보수적 처리
        "annual_energy_toe":     0,   # 에너지 사용량 설문 미수집
        # 보고서용 원본 값 보존
        "building_use_code":     btype,
        "ksic_code":             ksic,
    }


def _factory_to_context(factory: dict) -> Dict[str, Any]:
    """
    등록된 factories 레코드 → DB condition_code 기반 context dict
    """
    return {
        "employee_count":           _to_int(factory.get("worker_count")),
        "building_area":            _to_float(factory.get("total_floor_area")),
        "electrical_capacity_kw":   _to_float(factory.get("electric_capacity")),
        "floor_count":              _to_int(factory.get("floors_above")),
        "contractor_count":         _to_int(factory.get("contractor_count")),
        "transformer_capacity_kva": _to_float(factory.get("electric_capacity")),
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
        "building_use_code":        str(factory.get("building_use_code") or ""),
        "ksic_code":                str(factory.get("ksic_code") or ""),
    }


# ──────────────────────────────────────────────
# 핵심: DB 실제 컬럼 기반 조건 체크
# ──────────────────────────────────────────────

def _check_rule_conditions(rule: dict, context: dict) -> bool:
    """
    DB 실제 컬럼(condition_code, condition_operator_code, condition_value) 기반 조건 체크
    기존 rule.get("conditions", []) 참조 방식 → 완전 대체
    """
    condition_code = rule.get("condition_code", "")
    operator       = rule.get("condition_operator_code", "gte")
    value_str      = rule.get("condition_value")

    # 조건 없는 룰은 무조건 적용 대상 (예: 전체 사업장 필수 조항)
    if not condition_code:
        return True

    # context에서 실제 값 조회
    actual = context.get(condition_code)
    if actual is None:
        return False

    # 값이 0인 boolean 조건이면 False
    if condition_code.startswith("is_") and actual == 0:
        return False

    if value_str is None:
        # 값 없이 condition_code만 있으면 → 0 초과이면 적용
        try:
            return float(actual) > 0
        except (TypeError, ValueError):
            return bool(actual)

    try:
        actual_num = float(actual)
        value_num  = float(value_str)

        if operator in ("gte", ">="):
            return actual_num >= value_num
        elif operator in ("lte", "<="):
            return actual_num <= value_num
        elif operator in ("gt", ">"):
            return actual_num > value_num
        elif operator in ("lt", "<"):
            return actual_num < value_num
        elif operator in ("eq", "=", "=="):
            return actual_num == value_num
        elif operator in ("neq", "!=", "<>"):
            return actual_num != value_num
        else:
            return actual_num >= value_num  # 기본: gte

    except (TypeError, ValueError):
        # 숫자 비교 불가 → 문자열 비교
        if operator in ("eq", "=", "=="):
            return str(actual).strip() == str(value_str).strip()
        elif operator in ("in", "contains"):
            return str(value_str) in str(actual)
        return False


# ──────────────────────────────────────────────
# 결과 포맷 — DB 실제 컬럼명 기반
# ──────────────────────────────────────────────

def _get_inspection_cycle_label(rule: dict) -> str:
    """점검주기 한글 생성"""
    val  = rule.get("inspection_cycle_value")
    unit = rule.get("inspection_cycle_unit_code", "")
    if not val and not unit:
        return ""
    unit_label = INSPECTION_CYCLE_UNIT_MAP.get(str(unit), f"({unit})")
    if val:
        return f"{val}{unit_label}" if unit_label.startswith("(") else unit_label
    return unit_label


def _get_appointment_target_label(rule: dict) -> str:
    """선임 대상 한글 반환"""
    code = rule.get("appointment_target_code", "")
    return APPOINTMENT_TARGET_MAP.get(code, code)


def format_rule_result(rule: dict, source_label: str = "") -> dict:
    """
    룰 결과 포맷 — DB 실제 컬럼명 기반 (v4.0.0 전면 재작성)
    """
    rule_type_code = str(rule.get("rule_type_code", ""))
    inspection_cycle = _get_inspection_cycle_label(rule)
    appointment_target = _get_appointment_target_label(rule)

    # penalty 표시 생성
    pen_val  = rule.get("penalty_value")
    pen_unit = rule.get("penalty_unit_code", "")
    if pen_val and pen_unit:
        penalty_amount = f"{pen_val} {pen_unit}"
    elif pen_val:
        penalty_amount = str(pen_val)
    else:
        penalty_amount = ""

    return {
        "rule_id":               rule.get("rule_id", ""),
        "rule_type":             rule_type_code,
        "law_name":              rule.get("law_name", ""),
        "law_article":           rule.get("law_article", ""),
        "description":           rule.get("remarks", ""),
        "appointment_target":    appointment_target,
        "qualification_required": rule.get("appointment_qualification_code", ""),
        "inspection_cycle":      inspection_cycle,
        "penalty_amount":        penalty_amount,
        "source_label":          source_label,
        # 추가 원본 필드
        "appointment_required":  rule.get("appointment_required", False),
        "inspection_required":   rule.get("inspection_required", False),
        "action_required":       rule.get("action_required", False),
        "report_required":       rule.get("report_required", False),
        "condition_code":        rule.get("condition_code", ""),
        "condition_value":       rule.get("condition_value"),
    }


# ──────────────────────────────────────────────
# 분류 함수 — rule_type_code 숫자 기반
# ──────────────────────────────────────────────

def _classify_rules(rules: list, triggered: dict):
    """rule_type_code("001"~"008") 기반 분류"""
    for rule in rules:
        _classify_one(rule, format_rule_result(rule), triggered)


def _classify_rules_with_source(rule_source_pairs: list, triggered: dict):
    """소스 레이블 포함 분류"""
    for rule, source_label in rule_source_pairs:
        _classify_one(rule, format_rule_result(rule, source_label), triggered)


def _classify_one(rule: dict, formatted: dict, triggered: dict):
    """단일 룰을 카테고리에 배분"""
    rule_type_code = str(rule.get("rule_type_code", ""))
    category = RULE_TYPE_MAP.get(rule_type_code, "action")

    # appointment_required/inspection_required 불리언 우선 사용
    if rule.get("appointment_required"):
        triggered["appointment"].append(formatted)
    elif rule.get("inspection_required"):
        triggered["inspection"].append(formatted)
    elif rule.get("report_required"):
        triggered["report"].append(formatted)
    elif rule.get("action_required"):
        triggered["action"].append(formatted)
    else:
        # 불리언 없으면 rule_type_code로 분류
        triggered.get(category, triggered["action"]).append(formatted)


# ──────────────────────────────────────────────
# 조건 평가 함수들
# ──────────────────────────────────────────────

def _evaluate_conditions(context: dict, rules: list) -> tuple:
    """context 기반 룰 매칭 — 공통 함수"""
    applicable = []
    not_applicable = []
    for rule in rules:
        if _check_rule_conditions(rule, context):
            applicable.append(rule)
        else:
            not_applicable.append(rule)
    return applicable, not_applicable


async def _evaluate_equipment_conditions(
    factory_id: str, factory_context: dict, rules: list, supabase
) -> tuple:
    """등록 설비 기반 법령 판정 — 설비 type_code를 context에 추가"""
    eq_res = supabase.table("equipment_assets").select(
        "equipment_type_code, count, capacity"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    registered = eq_res.data or []

    # 등록 설비에서 추가 context 생성
    extra = dict(factory_context)
    for eq in registered:
        tc = eq.get("equipment_type_code", "")
        # 설비 타입 코드 → condition_code 추론
        if tc in ("elevator", "elev"):
            extra["elevator_count"] = max(extra.get("elevator_count", 0), 1)
        elif tc in ("boiler",):
            extra["boiler_capacity_kw"] = max(extra.get("boiler_capacity_kw", 0),
                                              _to_float(eq.get("capacity")) or 1)
        elif tc in ("gas", "gas_tank"):
            extra["gas_capacity_kg"] = max(extra.get("gas_capacity_kg", 0), 1)
        elif tc in ("hazmat", "chemical"):
            extra["is_hazardous_material"] = 1
        elif tc in ("electric", "transformer"):
            cap = _to_float(eq.get("capacity"))
            if cap:
                extra["electrical_capacity_kw"] = max(extra.get("electrical_capacity_kw", 0), cap)
                extra["transformer_capacity_kva"] = max(extra.get("transformer_capacity_kva", 0), cap)

    return _evaluate_conditions(extra, rules)


async def _evaluate_process_conditions(
    factory_id: str, factory_context: dict, rules: list, supabase
) -> tuple:
    """등록 공정 기반 법령 판정"""
    proc_res = supabase.table("factory_process").select(
        "process_id, source"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    process_ids = [
        r["process_id"] for r in (proc_res.data or [])
        if r.get("source") != "MANUAL"
    ]

    if not process_ids:
        return [], rules

    # 공정 → 설비 추론
    eq_res = supabase.table("v_equipment_unified").select(
        "facility_name_std, match_band"
    ).in_("process_id", process_ids).in_("match_band", ["MUST", "CORE"]).execute()

    inferred = set(r["facility_name_std"] for r in (eq_res.data or []))

    # 추론된 설비명 기반으로 context 보강
    extra = dict(factory_context)
    for name in inferred:
        nl = name.lower()
        if "승강기" in nl or "엘리베이터" in nl:
            extra["elevator_count"] = max(extra.get("elevator_count", 0), 1)
        if "보일러" in nl:
            extra["boiler_capacity_kw"] = max(extra.get("boiler_capacity_kw", 0), 1)
        if "가스" in nl:
            extra["gas_capacity_kg"] = max(extra.get("gas_capacity_kg", 0), 1)
        if "위험물" in nl or "화학" in nl:
            extra["is_hazardous_material"] = 1

    return _evaluate_conditions(extra, rules)


# ──────────────────────────────────────────────
# 결과 구성 공통 함수
# ──────────────────────────────────────────────

def _build_result(
    applicable: list,
    not_applicable: list,
    all_rules: list,
    mode: str,
    evaluated_at: str,
    source_pairs=None,
    **extra_fields
) -> dict:
    triggered = {
        "appointment": [],
        "inspection": [],
        "action": [],
        "report": [],
        "not_applicable": [],
    }

    if source_pairs is not None:
        _classify_rules_with_source(source_pairs, triggered)
    else:
        _classify_rules(applicable, triggered)

    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result(r))

    total = (
        len(triggered["appointment"]) +
        len(triggered["inspection"]) +
        len(triggered["action"]) +
        len(triggered["report"])
    )

    return {
        "engine_version":   ENGINE_VERSION,
        "mode":             mode,
        "evaluated_at":     evaluated_at,
        "total_rules_checked": len(all_rules),
        "applicable_count": total,
        "appointment_required": triggered["appointment"],
        "inspection_required":  triggered["inspection"],
        "action_required":      triggered["action"],
        "report_required":      triggered["report"],
        "not_applicable":       triggered["not_applicable"],
        "summary": {
            "total":       total,
            "appointment": len(triggered["appointment"]),
            "inspection":  len(triggered["inspection"]),
            "action":      len(triggered["action"]),
            "report":      len(triggered["report"]),
        },
        **extra_fields,
    }


# ══════════════════════════════════════════════
# API 엔드포인트
# ══════════════════════════════════════════════

@router.post("/apply/{factory_id}")
async def apply_legal_engine(
    factory_id: str,
    body: Optional[dict] = None,
    mode: str = Query("all", description="판정 모드: facility/process/equipment/all"),
):
    """
    시설 등록 기반 법령 판정 (4가지 모드)
    - facility:  시설 기본정보 조건만
    - process:   등록 공정 기반
    - equipment: 등록 설비 기반
    - all:       종합 (기본값)
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
        result_data = _build_result(applicable, not_applicable, all_rules, mode, evaluated_at,
                                    factory_id=factory_id,
                                    triggered_by_source=triggered_by_source)

    elif mode == "process":
        applicable, not_applicable = await _evaluate_process_conditions(
            factory_id, context, all_rules, supabase
        )
        triggered_by_source["process_recommended"] = len(applicable)
        result_data = _build_result(applicable, not_applicable, all_rules, mode, evaluated_at,
                                    factory_id=factory_id,
                                    triggered_by_source=triggered_by_source)

    elif mode == "equipment":
        applicable, not_applicable = await _evaluate_equipment_conditions(
            factory_id, context, all_rules, supabase
        )
        triggered_by_source["registered_equipment"] = len(applicable)
        result_data = _build_result(applicable, not_applicable, all_rules, mode, evaluated_at,
                                    factory_id=factory_id,
                                    triggered_by_source=triggered_by_source)

    else:  # all
        fac_app, _ = _evaluate_conditions(context, all_rules)
        triggered_by_source["factory_condition"] = len(fac_app)

        eq_app, _ = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["registered_equipment"] = len(eq_app)

        proc_app, _ = await _evaluate_process_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["process_recommended"] = len(proc_app)

        rule_map = {}
        for r in fac_app:
            rule_map[r["rule_id"]] = (r, "🏢 시설조건")
        for r in eq_app:
            if r["rule_id"] not in rule_map:
                rule_map[r["rule_id"]] = (r, "⚙️ 등록설비")
        for r in proc_app:
            if r["rule_id"] not in rule_map:
                rule_map[r["rule_id"]] = (r, "🔄 공정추천")

        source_pairs = list(rule_map.values())
        applicable_ids = {r["rule_id"] for r, _ in source_pairs}
        not_applicable = [r for r in all_rules if r["rule_id"] not in applicable_ids]

        result_data = _build_result([], not_applicable, all_rules, mode, evaluated_at,
                                    source_pairs=source_pairs,
                                    factory_id=factory_id,
                                    triggered_by_source=triggered_by_source)

    try:
        supabase.table("legal_applications").upsert({
            "factory_id":     factory_id,
            "engine_version": ENGINE_VERSION,
            "mode":           mode,
            "result_json":    result_data,
            "evaluated_at":   evaluated_at,
        }, on_conflict="factory_id,mode").execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] legal_applications 저장 실패: {e}")

    return {"status": "success", "data": result_data}


@router.post("/apply-quote/{quote_id}")
async def apply_legal_engine_from_quote(quote_id: str):
    """
    견적 survey_data 기반 시설 조건 법령 판정 (v4.0.0 재작성)
    """
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

    context = _survey_data_to_context(sd)

    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    all_rules = rules_res.data or []
    evaluated_at = _now_iso()

    applicable, not_applicable = _evaluate_conditions(context, all_rules)

    # not_applicable은 상위 100건만 전송
    na_cap = 100
    not_applicable_display = not_applicable[:na_cap]
    na_trimmed = len(not_applicable) > na_cap

    # facility_context: 보고서용으로 원본 설문 파생값 포함
    facility_context = {
        "worker_count":      context["employee_count"],
        "total_floor_area":  context["building_area"],
        "electric_capacity": context["electrical_capacity_kw"],
        "building_use_code": context["building_use_code"],
        "ksic_code":         context["ksic_code"],
        # 설비 추론 결과
        "has_elevator":      context["elevator_count"] > 0,
        "has_gas":           context["gas_capacity_kg"] > 0,
        "has_hazmat":        context["is_hazardous_material"] == 1,
        "has_boiler":        context["boiler_capacity_kw"] > 0,
    }

    result_data = _build_result(
        applicable,
        not_applicable_display,
        all_rules,
        "facility",
        evaluated_at,
        quote_id=quote_id,
        quote_no=qres.data.get("quote_no"),
        source="quote_survey",
        facility_context=facility_context,
        not_applicable_total=len(not_applicable),
        not_applicable_truncated=na_trimmed,
        note="견적 설문 기반으로 시설(facility) 조건만 적용했습니다. 등록 설비·공정 기반 판정은 사업장 등록 후 법령엔진을 실행하세요.",
        triggered_by_source={"factory_condition": len(applicable)},
    )

    try:
        supabase.table("quotes").update({
            "legal_result_json":      result_data,
            "legal_evaluated_at":     evaluated_at,
            "legal_applicable_count": result_data["applicable_count"],
            "updated_at":             evaluated_at,
        }).eq("id", quote_id).execute()
        print(f"[LEGAL ENGINE v4] quotes 저장 완료: {quote_id} (적용 {result_data['applicable_count']}건)")
    except Exception as e:
        print(f"[LEGAL ENGINE v4] quotes 저장 실패: {e}")

    return {"status": "success", "data": result_data}


@router.get("/quote-result/{quote_id}")
async def get_legal_result_from_quote(quote_id: str):
    """저장된 견적 법령판정 결과 조회"""
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
            "quote_id":               quote_id,
            "quote_no":               res.data.get("quote_no"),
            "legal_evaluated_at":     res.data.get("legal_evaluated_at"),
            "legal_applicable_count": res.data.get("legal_applicable_count"),
            "result":                 res.data.get("legal_result_json"),
        }
    }


@router.get("/result/{factory_id}")
async def get_legal_result(
    factory_id: str,
    mode: str = Query("all", description="조회할 모드: facility/process/equipment/all"),
):
    """저장된 시설 판정 결과 조회"""
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


@router.get("/debug/context/{quote_id}")
async def debug_quote_context(quote_id: str):
    """
    [개발용] 견적 survey_data에서 추출되는 context 확인
    법령엔진 디버깅 및 설문 필드 매핑 검증용
    """
    supabase = get_supabase()
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다.")
    sd = _parse_survey_data(qres.data.get("survey_data"))
    if not sd:
        raise HTTPException(status_code=400, detail="survey_data 없음")
    context = _survey_data_to_context(sd)
    return {"status": "success", "quote_no": qres.data.get("quote_no"), "context": context}
