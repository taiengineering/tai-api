"""
법령진단 엔진 v5.1.0 패치 라우터

변경 내역:
  v5.1.0:
    - CONDITION_CODE_TO_CONTEXT_KEY에 contract_amount → construction_amount 매핑 추가 (버그 수정)
    - CONSTRUCTION context 완성 (site_type, subcon_workers, tunnel, threshold)
    - construction_summary 결과 블록 추가
    - 건설 관련 법령 필터링 강화

이 라우터는 main.py에서 legal_engine_router보다 먼저 등록됨으로
POST /legal-engine/diagnose/step1이 이 파일로 라우팅됨.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime
from db.supabase_client import get_supabase

# 필요한 헬퍼는 legal_engine에서 import
from routers.legal_engine import (
    _truthy, _to_float, _to_int,
    _classify_rules_db, format_rule_result_db,
    _resolve_obligation_type, _risk_level,
    _db_rule_matches_facility,
    DiagnoseStep1Body, ALLOWED_DIAGNOSE_SECTORS,
    _normalize_sector_db,
)

router = APIRouter(prefix="/legal-engine", tags=["법령엔진v510"])

ENGINE_VERSION = "5.1.0"

# 건설 관련 주요 법령명 프리픽스
CONSTRUCTION_RELEVANT_LAW_PREFIXES = [
    "산업안전보건", "중대재해", "건설산업", "건설기술",
    "근로기준", "산업재해보상", "전기안전",
]

# v5.1.0: contract_amount → construction_amount 매핑 추가 (핵심 버그 수정)
CONDITION_CODE_TO_CONTEXT_KEY_V510: Dict[str, str] = {
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
    "contract_amount":          "construction_amount",   # v5.1.0 추가: 핵심 버그 수정
    "contractor_count":         "contractor_count",
    "is_hazardous_material":    "is_hazardous_material",
    "is_multi_use":             "is_multi_use",
    "is_factory_registered":    "is_factory_registered",
    "electric_capacity":        "electric_capacity",     # v5.1.0 추가
    "worker_count":             "worker_count",           # v5.1.0 추가
}


def _input_to_facility_context_v510(sector: str, inp: Dict[str, Any]) -> Dict[str, Any]:
    """v5.1.0: CONSTRUCTION context 완성 (site_type, subcon_workers, threshold)."""
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
        ctx["total_floor_area"]  = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["floor_count"]       = int(inp.get("floor_count") or 0)
        ctx["worker_count"]      = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_high_pressure_gas"]  = 1 if _truthy(inp.get("has_high_pressure_gas"))  else 0
        ctx["has_hazardous_material"] = 1 if _truthy(inp.get("has_hazardous_material")) else 0
        ctx["is_hazardous_material"]  = ctx["has_hazardous_material"]
    elif sec == "MANUFACTURING":
        ctx["ksic_code"]         = str(inp.get("ksic_major") or inp.get("ksic_code") or "")
        ctx["worker_count"]      = int(inp.get("worker_count") or inp.get("employee_count") or 0)
        ctx["electric_capacity"] = float(inp.get("electric_capacity") or 0)
        ctx["has_hazardous_material"]  = 1 if _truthy(inp.get("has_hazardous_material"))  else 0
        ctx["is_hazardous_material"]   = ctx["has_hazardous_material"]
        ctx["has_high_pressure_gas"]   = 1 if _truthy(inp.get("has_high_pressure_gas"))   else 0
        ctx["has_chemical_substance"]  = 1 if _truthy(inp.get("has_chemical_substance"))  else 0
        ctx["has_boiler"]              = 1 if _truthy(inp.get("has_boiler"))              else 0
    elif sec == "CONSTRUCTION":
        eok = float(inp.get("contract_amount_eok") or 0)
        amount = eok * 100_000_000.0
        ctx["construction_amount"] = amount
        ctx["contract_amount"]     = amount   # v5.1.0: condition_code 직접 매핑

        # 공사 종류 (BUILDING=건축, CIVIL=토목, SPECIALTY=전문)
        site_type = str(inp.get("construction_type") or inp.get("site_type") or "BUILDING")
        ctx["construction_type"] = site_type
        ctx["building_use_code"] = site_type
        ctx["is_building"]       = 1 if site_type == "BUILDING" else 0
        ctx["is_civil"]          = 1 if site_type == "CIVIL"    else 0

        # 근로자 수 (하도급 포함)
        direct = int(inp.get("direct_workers") or inp.get("worker_count") or inp.get("employee_count") or 0)
        subcon = int(inp.get("subcon_workers") or 0)
        total  = direct + subcon
        ctx["worker_count"]   = total
        ctx["employee_count"] = total
        ctx["direct_workers"] = direct
        ctx["subcon_workers"] = subcon

        ctx["has_tunnel_bridge"] = 1 if _truthy(inp.get("has_tunnel_bridge")) else 0

        # 안전관리자 선임 기준 (150억/120억)
        threshold = 15_000_000_000 if site_type in ("BUILDING", "SPECIALTY") else 12_000_000_000
        ctx["safety_manager_threshold"] = threshold
    elif sec in ("SPECIAL_FACILITY", "SPECIAL"):
        ctx["building_use_code"] = str(inp.get("facility_type") or "")
        ctx["total_floor_area"]  = float(inp.get("total_floor_area") or inp.get("floor_area") or 0)
        ctx["hospital_beds"]     = int(inp.get("hospital_beds") or 0)
        ctx["student_count"]     = int(inp.get("student_count") or 0)
        ctx["worker_count"]      = int(inp.get("worker_count") or inp.get("employee_count") or 0)
    return ctx


def _db_rule_matches_facility_v510(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """v5.1.0: CONDITION_CODE_TO_CONTEXT_KEY_V510 사용."""
    cc  = rule.get("condition_code")
    cv  = rule.get("condition_value")
    if not cc or cv is None:
        return False
    ctx_key = CONDITION_CODE_TO_CONTEXT_KEY_V510.get(cc, cc)
    actual  = context.get(ctx_key)
    if actual is None:
        actual = context.get(cc)
    if actual is None:
        return False
    try:
        actual_num = float(actual)
        value_num  = float(cv)
    except (TypeError, ValueError):
        op = (rule.get("condition_operator_code") or "eq").lower()
        return str(actual) == str(cv) and op in ("eq", "=", "==")
    op = (rule.get("condition_operator_code") or "gte").lower()
    if op in ("gte", ">="): return actual_num >= value_num
    if op in ("lte", "<="): return actual_num <= value_num
    if op in ("gt",  ">"): return actual_num >  value_num
    if op in ("lt",  "<"): return actual_num <  value_num
    if op in ("eq",  "=", "=="): return actual_num == value_num
    return actual_num >= value_num


def _evaluate_facility_conditions_db_v510(
    facility_ctx: Dict[str, Any], rules: List[Dict[str, Any]], sector: str
) -> tuple:
    """
    v5.1.0: 건설 섹터 필터링 추가.
    CONSTRUCTION 에서 조건 없는 룰은 건설 관련 법령만 포함.
    """
    applicable: List[Dict[str, Any]] = []
    not_applicable: List[Dict[str, Any]] = []

    for rule in rules:
        cc = rule.get("condition_code")
        cv = rule.get("condition_value")
        if not cc or cv is None:
            # 조건 없는 룰: CONSTRUCTION이면 건설 관련 법령만
            if sector == "CONSTRUCTION":
                law = rule.get("law_name") or ""
                if any(prefix in law for prefix in CONSTRUCTION_RELEVANT_LAW_PREFIXES):
                    applicable.append(rule)
                else:
                    not_applicable.append(rule)
            else:
                applicable.append(rule)
        elif _db_rule_matches_facility_v510(rule, facility_ctx):
            applicable.append(rule)
        else:
            not_applicable.append(rule)

    return applicable, not_applicable


def _get_construction_summary(facility_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """v5.1.0: 건설 선임 판정 결과 뼔록."""
    amount    = float(facility_ctx.get("construction_amount") or 0)
    workers   = int(facility_ctx.get("worker_count") or 0)
    site_type = str(facility_ctx.get("construction_type") or facility_ctx.get("building_use_code") or "BUILDING")

    threshold   = 15_000_000_000 if site_type in ("BUILDING", "SPECIALTY") else 12_000_000_000
    sm_required = (amount >= threshold) or (workers >= 50)

    site_label  = "건축" if site_type == "BUILDING" else ("토목" if site_type == "CIVIL" else "전문")
    basis_parts = [f"{site_label} {int(threshold/100_000_000)}억원 {'\uc774\uc0c1' if amount >= threshold else '\ubbf8\ub9cc'}"]
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
            "1억_산업안전보건관리비":          amount >= 100_000_000,
            "50억_유해위험방지계획서":        amount >= 5_000_000_000,
            "50억_기초안전보건교육":          amount >= 5_000_000_000,
            "100억_안전관리계획서":             amount >= 10_000_000_000,
            "120억_안전관리자선임_토목":    site_type == "CIVIL"    and amount >= 12_000_000_000,
            "150억_안전관리자선임_건축":    site_type == "BUILDING" and amount >= 15_000_000_000,
            "200억_안전보건관리책임자":        amount >= 20_000_000_000,
            "1000억_건설안전판정사":                amount >= 100_000_000_000,
        },
    }


# ============================================================
# POST /legal-engine/diagnose/step1  v5.1.0
# main.py에서 legal_engine_router보다 먼저 등록 → 이 필드가 우선 라우팅됨
# ============================================================

@router.post("/diagnose/step1")
async def diagnose_step1_v510(body: DiagnoseStep1Body):
    """
    법령진단 1단계 v5.1.0
    건설 섹터 버그 수정:
    - contract_amount condition_code 매핑 추가
    - CONSTRUCTION context 완성 (하도급, site_type)
    - construction_summary 결과 추가
    """
    sector_raw = body.sector.strip().upper()
    if sector_raw not in ALLOWED_DIAGNOSE_SECTORS:
        raise HTTPException(
            status_code=400,
            detail="sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.",
        )

    factory_id = (body.factory_id or "").strip()
    supabase   = get_supabase()

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
        "building_use_type":   body.building_use_type,
        "employee_count":      body.employee_count,
        "floor_area":          body.floor_area,
        "worker_count":        body.worker_count,
        "total_floor_area":    body.total_floor_area,
        "electric_capacity":   body.electric_capacity,
        "floor_count":         body.floor_count,
        "contract_amount_eok": body.contract_amount_eok,
        "ksic_major":          body.ksic_major,
        "facility_type":       body.facility_type,
    }
    for k, v in flat_fields.items():
        if v is not None and k not in inp:
            inp[k] = v

    facility_ctx = _input_to_facility_context_v510(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()

    # v5.1.0: 건설 필터링 포함 조건 평가
    applicable, not_applicable = _evaluate_facility_conditions_db_v510(
        facility_ctx, all_rules, sector_raw
    )

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

    law_names     = sorted({x.get("law_name") for x in applicable if x.get("law_name")})
    appointment_n = len(triggered["appointment"])
    risk          = _risk_level(total_applicable, appointment_n)

    # obligations 배열
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

    # v5.1.0: 건설 섹터 전용 요약 추가
    if sector_raw == "CONSTRUCTION":
        result_data["construction_summary"] = _get_construction_summary(facility_ctx)

    # ── DB 저장 (factory_id 있을 때만) ──
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
            print(f"[DIAGNOSE STEP1 v510] factory_diagnosis_results 저장 실패: {e}")

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
                print(f"[DIAGNOSE STEP1 v510] diagnosis_rule_results 저장 실패: {e}")

    result_data["diagnosis_id"] = diagnosis_id
    return {"status": "success", "data": result_data}
