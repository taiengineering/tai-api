from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from services.legal_helpers import _normalize_target_code
from services.legal_rules import _is_notify, _resolve_obligation_type
from services.time import business_today

APPOINTMENT_TARGET_MAP = {
    "safety_manager": "안전관리자",
    "health_manager": "보건관리자",
    "safety_health_director": "안전보건관리책임자",
    "safety_health_manager": "안전보건관리담당자",
    "fire_safety_manager": "소방안전관리자",
    "electric_safety_manager": "전기안전관리자",
    "gas_safety_manager": "가스안전관리자",
    "elevator_safety_manager": "승강기안전관리자",
    "energy_manager": "에너지관리자",
    "building_manager": "건축물관리자(유지관리자)",
    "hazardous_material_manager": "위험물안전관리자",
    "city_gas_manager": "도시가스안전관리자",
    "chemical_manager": "유해화학물질관리자",
    "waste_manager": "폐기물처리담당자",
    "environmental_manager": "환경관리인",
}
EXECUTOR_TYPE_MAP = {"anyone": "사업주 누구나", "qualified": "자격자만", "external": "외부기관 위탁", "appointed": "선임된 관리자"}
SUBMIT_ORG_MAP = {"moel": "고용노동부(노동청)", "nfa": "소방서", "kesco": "한국전기안전공사", "kgs": "한국가스안전공사", "me": "지방환경청(환경부)", "mlit": "국토교통부(지자체)", "kosha": "한국산업안전보건공단", "self": "자체보관", "local_gov": "지방자치단체", "keco": "한국환경공단"}
REPORT_METHOD_MAP = {"api": "API(온라인시스템)", "mail": "우편", "visit": "방문", "fax": "팩스", "keep": "자체보관(미제출)"}
RULE_TYPE_MAP = {"001": "appointment", "002": "inspection", "003": "report", "004": "action", "005": "action", "007": "action", "008": "action"}
CYCLE_CODE_MAP = {"001": ("day", 1), "002": ("week", 1), "003": ("month", 1), "004": ("month", 3), "005": ("month", 6), "006": ("year", 1), "007": ("year", 2), "008": ("year", 5), "009": ("year", 4), "010": ("year", 3), "011": ("year", 3), "012": ("year", 10), "013": ("year", 5)}
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


def _get_inspection_cycle_label(rule: dict) -> str:
    val = rule.get("inspection_cycle_value")
    unit = rule.get("cycle_unit_std") or ""
    if not unit:
        code = str(rule.get("inspection_cycle_unit_code") or "")
        _code_to_unit = {"001": "day", "002": "week", "003": "month", "004": "quarter", "005": "half_year", "006": "year", "007": "year", "008": "year", "009": "year", "010": "year", "011": "year", "012": "year", "013": "year"}
        unit = _code_to_unit.get(code, "")
    if not val:
        return ""
    val = int(float(val))
    _short = {"year": "연 1회", "half_year": "반기 1회", "quarter": "분기 1회", "month": "월 1회", "week": "주 1회", "day": "매일"}
    if val == 1:
        return _short.get(unit, f"1{unit}")
    if unit == "year":
        return f"{val}년마다"
    return _short.get(unit, unit).replace("1회", f"{val}회")


def _get_schedule_type(rule: dict) -> str:
    if rule.get("inspection_cycle_unit_code") or rule.get("cycle_unit_std"):
        return "PERIODIC"
    if rule.get("construction_work_type"):
        return "BEFORE_WORK"
    return "ON_DEMAND"


def _get_appointment_target_label(rule: dict) -> str:
    code = _normalize_target_code(rule.get("appointment_target_code", ""))
    return APPOINTMENT_TARGET_MAP.get(code, code)


def format_rule_result(rule: dict, source_label: str = "") -> dict:
    pen_val = rule.get("penalty_value")
    pen_unit = rule.get("penalty_unit_code", "")
    return {
        "rule_id": rule.get("rule_id", ""),
        "rule_type": str(rule.get("rule_type_code", "")),
        "law_name": rule.get("law_name", ""),
        "law_article": rule.get("law_article", ""),
        "description": rule.get("remarks", ""),
        "appointment_target": _get_appointment_target_label(rule),
        "qualification_required": rule.get("appointment_qualification_code", ""),
        "inspection_cycle": _get_inspection_cycle_label(rule),
        "penalty_amount": f"{pen_val} {pen_unit}" if pen_val and pen_unit else (str(pen_val) if pen_val else ""),
        "source_label": source_label,
        "appointment_required": rule.get("appointment_required", False),
        "inspection_required": rule.get("inspection_required", False),
        "action_required": rule.get("action_required", False),
        "report_required": rule.get("report_required", False),
        "obligation_type": _resolve_obligation_type(rule),
        "condition_code": rule.get("condition_code", ""),
        "condition_value": rule.get("condition_value"),
    }


def _calc_due_date(due_days) -> dict:
    if not due_days:
        return {}
    d = int(due_days)
    return {"due_days": d, "due_date": (business_today() + timedelta(days=d)).isoformat(), "urgency": "IMMEDIATE" if d <= 3 else ("URGENT" if d <= 14 else "NORMAL")}


def _get_penalty_fallback(obligation_type: str) -> str:
    _map = {"DOCUMENT": "미보존 시 과태료 부과 가능", "APPOINT": "미선임 시 과태료 부과 가능", "INSPECT": "미실시 시 과태료 부과 가능", "REPORT": "미신고 시 과태료 부과 가능", "NOTIFY": "미신고 시 과태료 부과 가능", "BEFORE_WORK": "미이행 시 과태료 부과 가능", "ACTION": "관련 벌칙 확인 필요", "OTHER": "관련 벌칙 확인 필요"}
    return _map.get((obligation_type or "").upper(), "관련 벌칙 확인 필요")


def format_rule_result_db(rule: Dict[str, Any], article_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    룰 → 결과 dict 포맷.
    
    v5.8.0 (2026-04-23): article_info 파라미터 추가
      - rule_article_mapping을 통해 연결된 law_article 정보를 주입
      - 조문 본문(article_text), 내부 키, 체계(LEGAL/NFPC/NFTC) 포함
      - article_info가 None이면 has_article_text=False (기존 호환)
    """
    obl_summary = (rule.get("obligation_summary") or "").strip()
    remarks_txt = (rule.get("remarks") or "").strip()
    desc = remarks_txt or obl_summary
    target_code = _normalize_target_code(rule.get("appointment_target_code") or "")
    submit_org_code = rule.get("submit_org_code") or ""
    executor_type_code = rule.get("executor_type_code") or ""
    report_method_std = rule.get("report_method_std") or ""
    cycle_code = rule.get("inspection_cycle_unit_code") or ""
    cycle_label = _get_inspection_cycle_label(rule)
    _std = rule.get("cycle_unit_std") or ""
    if _std:
        _std_to_unit = {"year": "year", "half_year": "half_year", "quarter": "quarter", "month": "month", "week": "week", "day": "day"}
        cycle_unit = _std_to_unit.get(_std, _std)
        cycle_int = int(rule.get("inspection_cycle_value") or 0)
    else:
        cycle_unit, cycle_int = CYCLE_CODE_MAP.get(cycle_code, ("", 0))
    schedule_type = _get_schedule_type(rule)
    _obl_type = _resolve_obligation_type(rule)
    _pen_raw = rule.get("penalty_summary") or ""
    _penalty = _pen_raw.strip() if _pen_raw.strip() else _get_penalty_fallback(_obl_type)
    _is_recurring = bool(rule.get("cycle_unit_std"))
    try:
        _due_days = int(float(rule.get("due_days") or 0))
    except (TypeError, ValueError):
        _due_days = 0
    
    result = {
        "rule_id": rule.get("rule_id", ""),
        "rule_type": str(rule.get("rule_type_code") or ""),
        "law_name": rule.get("law_name") or "",
        "law_article": rule.get("law_article") or "",
        "description": desc,
        "obligation_summary": obl_summary,
        "remarks": remarks_txt,
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
        "penalty_amount": _penalty,
        "penalty_summary": _penalty,
        "source_label": "",
        "obligation_type": _obl_type,
        "appointment_required": bool(rule.get("appointment_required")),
        "inspection_required": bool(rule.get("inspection_required")),
        "action_required": bool(rule.get("action_required")),
        "report_required": bool(rule.get("report_required")),
        "notify_required": bool(rule.get("notify_required")),
        "form_code": rule.get("form_code") or "",
        "form_name": rule.get("form_name") or "",
        "form_url": rule.get("form_url") or "",
        "online_system": rule.get("online_system") or "",
        "system_url": rule.get("system_url") or "",
        "tai_feature_code": rule.get("tai_feature_code") or "",
        "qualification_code": rule.get("appointment_qualification_code") or "",
        "due_days": _due_days,
        "is_recurring": _is_recurring,
        "due_info": {} if _is_recurring else _calc_due_date(rule.get("due_days")),
        "sector": rule.get("sector") or "",
        "diagnosis_stage": rule.get("diagnosis_stage"),
        "submit_org_code": submit_org_code,
        "submit_org_label": SUBMIT_ORG_MAP.get(submit_org_code, submit_org_code),
        "report_method_std": report_method_std,
        "report_method_label": REPORT_METHOD_MAP.get(report_method_std, report_method_std),
        "form_name": rule.get("form_name") or "",
        "online_system": rule.get("online_system") or "",
        "system_url": rule.get("system_url") or "",
        "tai_feature_code": rule.get("tai_feature_code") or "",
        "qualification_code": rule.get("appointment_qualification_code") or "",
    }
    
    # v5.8.0 조문 본문 필드 추가
    if article_info:
        result.update({
            "article_id":             article_info.get("article_id"),
            "article_internal_key":   article_info.get("article_internal_key") or "",
            "article_title":          article_info.get("article_title") or "",
            "article_text":           article_info.get("article_text") or "",
            "article_type":           article_info.get("article_type") or "",
            "law_system":             article_info.get("law_system") or "UNKNOWN",
            "article_confidence":     article_info.get("confidence", 0),
            "has_article_text":       bool(article_info.get("article_text")),
        })
    else:
        result.update({
            "article_id":             None,
            "article_internal_key":   "",
            "article_title":          "",
            "article_text":           "",
            "article_type":           "",
            "law_system":             "NOT_MAPPED",
            "article_confidence":     0,
            "has_article_text":       False,
        })
    
    return result


def _classify_rules(rules: list, triggered: dict):
    for rule in rules:
        _classify_one(rule, format_rule_result(rule), triggered)


def _classify_rules_with_source(rule_source_pairs: list, triggered: dict):
    for rule, sl in rule_source_pairs:
        _classify_one(rule, format_rule_result(rule, sl), triggered)


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
        triggered.get(RULE_TYPE_MAP.get(str(rule.get("rule_type_code", "")), "action"), triggered["action"]).append(formatted)


def _classify_rules_db(
    rules: List[Dict[str, Any]],
    triggered: Dict[str, List],
    article_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """
    룰을 의무 유형별로 분류하여 triggered dict에 저장.
    
    v5.8.0: article_contexts 파라미터 추가
      - {rule_id: article_info} 형태의 dict
      - format_rule_result_db에 article_info 주입
      - None이면 조문 본문 없이 처리 (기존 동작)
    
    사용:
        from services.legal_article_loader import fetch_article_contexts
        rule_ids = [r.get("rule_id") for r in matched_rules]
        article_ctx = fetch_article_contexts(supabase, rule_ids)
        _classify_rules_db(matched_rules, triggered, article_ctx)
    """
    seen_appoint: set = set()
    ctx_map = article_contexts or {}
    
    for rule in rules:
        rule_id = rule.get("rule_id", "")
        article_info = ctx_map.get(rule_id)
        formatted = format_rule_result_db(rule, article_info)
        ot = (rule.get("obligation_type") or "").strip().upper()
        
        if ot == "APPOINT":
            target = _normalize_target_code((rule.get("appointment_target_code") or rule.get("rule_id") or "").strip())
            if target and target in seen_appoint:
                continue
            if target:
                seen_appoint.add(target)
            triggered["appointment"].append(formatted)
        elif ot == "INSPECT":
            triggered["inspection"].append(formatted)
        elif ot == "NOTIFY":
            triggered.setdefault("notify", []).append(formatted)
        elif ot == "REPORT":
            triggered["report"].append(formatted)
        elif ot == "ACTION":
            triggered["action"].append(formatted)
        else:
            if rule.get("appointment_required"):
                target = _normalize_target_code((rule.get("appointment_target_code") or rule.get("rule_id") or "").strip())
                if target and target in seen_appoint:
                    continue
                if target:
                    seen_appoint.add(target)
                triggered["appointment"].append(formatted)
            elif rule.get("inspection_required"):
                triggered["inspection"].append(formatted)
            elif rule.get("notify_required"):
                triggered.setdefault("notify", []).append(formatted)
            elif rule.get("report_required"):
                triggered["report"].append(formatted)
            elif rule.get("action_required"):
                triggered["action"].append(formatted)
            else:
                triggered["action"].append(formatted)


def build_result(applicable, not_applicable, all_rules, mode, evaluated_at, engine_version: str, source_pairs=None, include_not_applicable=True, **extra_fields):
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
        "engine_version": engine_version,
        "mode": mode,
        "evaluated_at": evaluated_at,
        "total_rules_checked": len(all_rules),
        "not_applicable_count": len(not_applicable),
        "applicable_count": total,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"],
        "summary": {
            "total": total,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(report_only),
            "notify": len(notify_list),
        },
        **extra_fields,
    }
    if include_not_applicable:
        result["not_applicable"] = [format_rule_result(r) for r in not_applicable]
    return result
