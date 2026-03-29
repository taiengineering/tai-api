"""
법령 판정 엔진 라우터 — v3.0.0
v3 변경사항:
  POST /legal-engine/apply/{factory_id} — mode 파라미터 추가
    mode: facility  (시설기준만)
    mode: process   (등록 공정 기반)
    mode: equipment (등록 설비 기반)
    mode: all       (종합가동 - 기존 v2.0.0 동일, 기본값)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

ENGINE_VERSION = "3.0.0"


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

    evaluated_at = datetime.now().isoformat()
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
        # 시설 조건 판정
        fac_applicable, _ = _evaluate_facility_conditions(factory, all_rules)
        triggered_by_source["factory_condition"] = len(fac_applicable)

        # 등록 설비 판정
        equip_applicable, _ = await _evaluate_equipment_conditions(
            factory_id, factory, all_rules, supabase
        )
        triggered_by_source["registered_equipment"] = len(equip_applicable)

        # 공정 기반 판정
        proc_applicable, _ = await _evaluate_process_conditions(
            factory_id, factory, all_rules, supabase
        )
        triggered_by_source["process_recommended"] = len(proc_applicable)

        # 통합 중복 제거 (rule_id 기준, 소스 표시)
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

        # 미적용
        applicable_ids = set(r["rule_id"] for r in applicable_only)
        not_applicable = [r for r in all_rules if r["rule_id"] not in applicable_ids]

        _classify_rules_with_source(applicable_combined, triggered)
        for r in not_applicable:
            triggered["not_applicable"].append(format_rule_result(r))

    # 3. 결과 저장
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

    # legal_applications 테이블에 저장 (있는 경우)
    try:
        supabase.table("legal_applications").upsert({
            "factory_id": factory_id,
            "engine_version": ENGINE_VERSION,
            "mode": mode,
            "result_json": result_data,
            "evaluated_at": evaluated_at,
        }, on_conflict="factory_id,mode").execute()
    except Exception:
        pass  # 테이블 없어도 결과 반환

    return {"status": "success", "data": result_data}


# ──────────────────────────────────────────────
# POST /legal-engine/apply-quote/{quote_id}
# 견적 survey_data 기반 시설 조건 법령 판정 (facility만)
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
    evaluated_at = datetime.now().isoformat()

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
    equip_std_set = set(e.get("equipment_std", "") for e in registered_equip)
    equip_type_set = set(e.get("equipment_type_code", "") for e in registered_equip)

    applicable = []
    not_applicable = []

    for rule in rules:
        target_equip = rule.get("target_equipment_std", "")
        target_type = rule.get("target_equipment_type", "")

        matched = False
        if target_equip and target_equip in equip_std_set:
            matched = True
        elif target_type and target_type in equip_type_set:
            matched = True
        elif not target_equip and not target_type:
            # 설비 조건 없는 룰 → 시설 조건으로 폴백
            workers = factory.get("worker_count") or 0
            area = factory.get("total_floor_area") or 0
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
    # 등록 공정 조회 (MANUAL 제외)
    proc_res = supabase.table("factory_process").select(
        "process_id, source"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    process_ids = [
        r["process_id"] for r in (proc_res.data or [])
        if r.get("source") != "MANUAL"
    ]

    if not process_ids:
        return [], rules

    # 공정 → 설비 추론 (v_equipment_unified MUST/CORE)
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
            # 설비 조건 없는 룰 → 시설 조건 폴백
            workers = factory.get("worker_count") or 0
            area = factory.get("total_floor_area") or 0
            if _check_rule_conditions(rule, {"worker_count": workers, "total_floor_area": area}):
                applicable.append(rule)
            else:
                not_applicable.append(rule)
        else:
            not_applicable.append(rule)

    return applicable, not_applicable


def _check_rule_conditions(rule: dict, context: dict) -> bool:
    """룰 조건 체크 (간단 버전)"""
    conditions = rule.get("conditions", [])
    if not conditions:
        return False

    for cond in conditions:
        field = cond.get("field", "")
        operator = cond.get("operator", "gte")
        value = cond.get("value")

        if value is None:
            continue

        actual = context.get(field)
        if actual is None:
            continue

        try:
            actual_num = float(actual)
            value_num = float(value)
            if operator in ("gte", ">=") and actual_num >= value_num:
                return True
            elif operator in ("lte", "<=") and actual_num <= value_num:
                return True
            elif operator in ("gt", ">") and actual_num > value_num:
                return True
            elif operator in ("lt", "<") and actual_num < value_num:
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
