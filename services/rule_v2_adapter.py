"""
services/rule_v2_adapter.py — master_rule_v2 → master_building_legal_rules 호환 dict.

기계적 필드 매핑만 수행. Supabase/FastAPI import 없음.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# rule_kind → 독립 v1 규칙 여부 (OBLIGATION/PROHIBITION만 adapt)
STANDALONE_RULE_KINDS = frozenset({"OBLIGATION", "PROHIBITION"})

# v2 obligation_category(한글) → v1 obligation_type
OBLIGATION_CATEGORY_TO_TYPE: Dict[str, str] = {
    "선임": "APPOINT",
    "점검": "INSPECT",
    "신고": "REPORT",
    "보고": "NOTIFY",
    "서류": "NOTIFY",
    "조치": "ACTION",
    "작업_전": "ACTION",
    "기타": "ACTION",
}

# v2 action_category_code → v1 obligation_type
ACTION_CATEGORY_TO_TYPE: Dict[str, str] = {
    "inspection": "INSPECT",
    "risk_assessment": "INSPECT",
    "measurement": "INSPECT",
    "education": "ACTION",
    "report": "REPORT",
    "installation": "ACTION",
    "recordkeeping": "NOTIFY",
    "notification": "NOTIFY",
    "action": "ACTION",
    "work_method": "ACTION",
    "approval": "REPORT",
    "protection": "ACTION",
    "system_management": "ACTION",
    "other": "ACTION",
}

# v1 obligation_type → rule_type_code
OBLIGATION_TYPE_TO_RULE_TYPE_CODE: Dict[str, str] = {
    "APPOINT": "001",
    "INSPECT": "002",
    "REPORT": "003",
    "NOTIFY": "003",
    "ACTION": "004",
}

# v2 scope threshold criterion_code → v1 condition_code
CRITERION_TO_CONDITION_CODE: Dict[str, str] = {
    "employee": "employee_count",
    "area_floor": "building_area",
    "construction_amount": "construction_amount",
    "capacity_power": "electric_capacity",
    "height": "floor_count",
    "capacity_weight": "gas_capacity_kg",
    "capacity_pressure": "gas_capacity_kg",
    "count_unit": "floor_count",
}

OPERATOR_V2_TO_V1: Dict[str, str] = {
    "GTE": "gte",
    "LTE": "lte",
    "GT": "gt",
    "LT": "lt",
    "EQ": "eq",
}

WHEN_CYCLE_TYPE_TO_UNIT: Dict[str, Tuple[str, str]] = {
    "DAILY": ("day", "001"),
    "WEEKLY": ("week", "002"),
    "MONTHLY": ("month", "003"),
    "YEARLY": ("year", "006"),
}

WHEN_CYCLE_UNIT_TO_UNIT: Dict[str, Tuple[str, str]] = {
    "DAY": ("day", "001"),
    "WEEK": ("week", "002"),
    "MONTH": ("month", "003"),
    "YEAR": ("year", "006"),
}

_APPOINT_KW = ("선임", "선정", "지정", "배치", "위촉")
_INSPECT_KW = ("점검", "검사", "측정", "진단", "검진", "검측")
_REPORT_KW = ("신고", "등록", "허가", "인가", "승인", "제출")
_NOTIFY_KW = ("보고", "통보", "통지", "알려", "보존", "기록")


def adapt_v2_to_v1(
    v2_rule: Dict[str, Any],
    *,
    relation: Optional[Dict[str, Any]] = None,
    scope: Optional[Dict[str, Any]] = None,
    penalty_rule: Optional[Dict[str, Any]] = None,
    sector_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    master_rule_v2 1건 → master_building_legal_rules 호환 dict.

    PENALTY/CONDITION/EXCEPTION/DELEGATION/DEFINITION/EXEMPTION 등은
    독립 규칙이 아니므로 None 반환.
    """
    rule_kind = (v2_rule.get("rule_kind") or "").strip().upper()
    if rule_kind not in STANDALONE_RULE_KINDS:
        return None

    law_name, law_article = _resolve_law_fields(v2_rule)
    obligation_type = _resolve_v2_obligation_type(v2_rule)
    rule_type_code = OBLIGATION_TYPE_TO_RULE_TYPE_CODE.get(obligation_type, "004")

    sectors = _as_str_list(v2_rule.get("sectors"))
    sector = _pick_sector(sectors, sector_hint)

    obl_summary = (
        (v2_rule.get("why_obligation_summary") or "").strip()
        or (v2_rule.get("what_action_text_raw") or "").strip()
        or (v2_rule.get("what_action") or "").strip()
    )
    remarks = (v2_rule.get("what_action_text_raw") or v2_rule.get("when_text_raw") or "").strip()

    cycle_value, cycle_unit_code, cycle_unit_std = _resolve_cycle_fields(v2_rule)
    due_days = v2_rule.get("when_due_days")
    if due_days is None and (v2_rule.get("when_cycle_type") or "").upper() == "DUE":
        due_days = cycle_value

    v1: Dict[str, Any] = {
        "rule_id": str(
            v2_rule.get("id") or v2_rule.get("rule_id") or v2_rule.get("rule_code") or ""
        ),
        "rule_type_code": rule_type_code,
        "law_name": law_name,
        "law_article": law_article,
        "law_category_code": (
            (v2_rule.get("law_category_code") or "").strip()
            or ((scope or {}).get("layer") or "").strip()
            if isinstance(scope, dict)
            else (v2_rule.get("law_category_code") or "").strip()
        ),
        "obligation_summary": obl_summary,
        "remarks": remarks,
        "obligation_type": obligation_type,
        "appointment_required": False,
        "inspection_required": False,
        "action_required": False,
        "report_required": False,
        "notify_required": False,
        "appointment_target_code": (v2_rule.get("appointment_target_code") or "").strip(),
        "appointment_qualification_code": (v2_rule.get("appointment_qualification_code") or "").strip(),
        "qualification_type": (v2_rule.get("qualification_type") or "").strip(),
        "inspection_cycle_value": cycle_value,
        "inspection_cycle_unit_code": cycle_unit_code,
        "cycle_unit_std": cycle_unit_std,
        "cycle_base_type": (v2_rule.get("when_cycle_type") or v2_rule.get("cycle_base_type") or "").strip(),
        "cycle_base_guide": (v2_rule.get("when_base_event") or v2_rule.get("cycle_base_guide") or "").strip(),
        "due_days": due_days,
        "condition_code": "",
        "condition_value": None,
        "condition_operator_code": "gte",
        "construction_work_type": _first_or_empty(v2_rule.get("scope_construction_types")),
        "construction_work_type_label": (v2_rule.get("construction_work_type_label") or "").strip(),
        "submit_org_code": (v2_rule.get("submit_org_code") or "").strip(),
        "executor_type_code": _map_executor_type(v2_rule.get("who_executor")),
        "report_method_std": (v2_rule.get("report_method_std") or "").strip(),
        "penalty_summary": (v2_rule.get("penalty_summary") or "").strip(),
        "penalty_value": v2_rule.get("penalty_value"),
        "penalty_unit_code": (v2_rule.get("penalty_unit_code") or "").strip(),
        "form_code": (v2_rule.get("form_code") or v2_rule.get("how_form") or "").strip(),
        "form_name": (v2_rule.get("form_name") or "").strip(),
        "form_url": (v2_rule.get("form_url") or "").strip(),
        "online_system": (v2_rule.get("online_system") or "").strip(),
        "system_url": (v2_rule.get("online_system_url") or v2_rule.get("system_url") or "").strip(),
        "tai_feature_code": (v2_rule.get("tai_feature_code") or "").strip(),
        "sector": sector,
        "diagnosis_stage": int(v2_rule.get("diagnosis_stage") or 1),
        "is_active": _v2_is_active(v2_rule),
    }

    _apply_obligation_flags(v1, obligation_type)
    _apply_v2_inline_scope(v1, v2_rule)
    if scope:
        _apply_scope_bundle(v1, scope)
    _apply_penalty(v1, relation=relation, penalty_rule=penalty_rule)

    return v1


def adapt_v2_batch(
    v2_rules: List[Dict[str, Any]],
    relations: Optional[Dict[str, Dict[str, Any]]] = None,
    scopes: Optional[Dict[str, Dict[str, Any]]] = None,
    penalty_rules: Optional[Dict[str, Dict[str, Any]]] = None,
    sector_hint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """master_rule_v2 배치 → v1 호환 리스트 (OBLIGATION/PROHIBITION만)."""
    rel_map = relations or {}
    scope_map = scopes or {}
    penalty_map = penalty_rules or {}

    results: List[Dict[str, Any]] = []
    for v2 in v2_rules:
        rid = str(v2.get("id") or v2.get("rule_id") or "")
        rel = rel_map.get(rid)
        penalty_rule = None
        if rel:
            target_id = str(rel.get("target_rule_id") or "")
            penalty_rule = penalty_map.get(target_id)
        v1 = adapt_v2_to_v1(
            v2,
            relation=rel,
            scope=scope_map.get(rid),
            penalty_rule=penalty_rule,
            sector_hint=sector_hint,
        )
        if v1 is not None:
            results.append(v1)
    return results


def merge_scope_with_thresholds(
    scope_row: Dict[str, Any],
    thresholds: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """master_rule_scope + threshold rows → adapt_v2_to_v1(scope=...) 입력."""
    bundle = dict(scope_row)
    ths = thresholds if thresholds is not None else scope_row.get("thresholds")
    if ths:
        bundle["thresholds"] = list(ths)
    return bundle


def build_relation_map(
    relation_rows: List[Dict[str, Any]],
    *,
    relation_type: str = "has_penalty",
) -> Dict[str, Dict[str, Any]]:
    """source_rule_id(OBLIGATION/PROHIBITION) → relation row."""
    out: Dict[str, Dict[str, Any]] = {}
    want = (relation_type or "").strip().lower()
    for row in relation_rows:
        rt = (row.get("relation_type") or "").strip().lower()
        if want and rt != want:
            continue
        src = str(row.get("source_rule_id") or "")
        if src:
            out[src] = row
    return out


def build_scope_map(
    mapping_rows: List[Dict[str, Any]],
    scope_by_id: Dict[str, Dict[str, Any]],
    thresholds_by_scope_id: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """rule_id → scope bundle (master_rule_scope_mapping + scope + thresholds)."""
    th_map = thresholds_by_scope_id or {}
    out: Dict[str, Dict[str, Any]] = {}
    for m in mapping_rows:
        rule_id = str(m.get("rule_id") or "")
        scope_id = str(m.get("scope_id") or "")
        if not rule_id or not scope_id:
            continue
        scope_row = scope_by_id.get(scope_id)
        if not scope_row:
            continue
        bundle = merge_scope_with_thresholds(scope_row, th_map.get(scope_id))
        out[rule_id] = bundle
    return out


def filter_v2_rules_for_sector(
    v2_rules: List[Dict[str, Any]],
    sector_db: str,
) -> List[Dict[str, Any]]:
    """sectors[]에 sector_db가 포함된 행만 (빈 sectors는 제외)."""
    target = (sector_db or "").strip().upper()
    if not target:
        return list(v2_rules)
    out: List[Dict[str, Any]] = []
    for row in v2_rules:
        sectors = [s.strip().upper() for s in _as_str_list(row.get("sectors"))]
        if sectors and target in sectors:
            out.append(row)
    return out


def filter_v2_rules_construction_work_types(
    v2_rules: List[Dict[str, Any]],
    work_types: List[str],
) -> List[Dict[str, Any]]:
    """v1 construction_work_type 필터와 동일 의미: 공종 미지정 또는 목록 포함."""
    if not work_types:
        return list(v2_rules)
    allowed = {w.strip() for w in work_types if w and str(w).strip()}
    if not allowed:
        return list(v2_rules)
    out: List[Dict[str, Any]] = []
    for row in v2_rules:
        types = {str(t).strip() for t in _as_str_list(row.get("scope_construction_types"))}
        if not types:
            out.append(row)
            continue
        if types & allowed:
            out.append(row)
    return out


# ── internal helpers ─────────────────────────────────────


def _resolve_v2_obligation_type(v2_rule: Dict[str, Any]) -> str:
    existing = (v2_rule.get("obligation_type") or "").strip().upper()
    if existing in ("APPOINT", "INSPECT", "REPORT", "NOTIFY", "ACTION"):
        return existing

    cat = (v2_rule.get("obligation_category") or "").strip()
    if cat in OBLIGATION_CATEGORY_TO_TYPE:
        return OBLIGATION_CATEGORY_TO_TYPE[cat]

    action_cat = (v2_rule.get("action_category_code") or "").strip().lower()
    if action_cat in ACTION_CATEGORY_TO_TYPE:
        return ACTION_CATEGORY_TO_TYPE[action_cat]

    what_action = (v2_rule.get("what_action") or "").strip()
    if what_action in OBLIGATION_CATEGORY_TO_TYPE:
        return OBLIGATION_CATEGORY_TO_TYPE[what_action]

    text = " ".join(
        [
            v2_rule.get("why_obligation_summary") or "",
            v2_rule.get("what_action_text_raw") or "",
            v2_rule.get("what_action") or "",
            v2_rule.get("when_text_raw") or "",
        ]
    ).strip()
    if not text:
        return "ACTION"

    for kw in _APPOINT_KW:
        if kw in text:
            return "APPOINT"
    for kw in _INSPECT_KW:
        if kw in text:
            return "INSPECT"
    for kw in _REPORT_KW:
        if kw in text:
            return "REPORT"
    for kw in _NOTIFY_KW:
        if kw in text:
            return "NOTIFY"
    return "ACTION"


def _resolve_law_fields(v2_rule: Dict[str, Any]) -> Tuple[str, str]:
    law_name = (v2_rule.get("law_name") or "").strip()
    law_article = (v2_rule.get("law_article") or v2_rule.get("article_no") or "").strip()
    if law_name and law_article:
        return law_name, _normalize_article_ref(law_article)

    citation = (v2_rule.get("why_law_citation") or "").strip()
    if citation:
        parsed_name, parsed_article = _parse_why_law_citation(citation)
        return parsed_name or law_name, parsed_article or law_article

    return law_name, _normalize_article_ref(law_article)


def _parse_why_law_citation(citation: str) -> Tuple[str, str]:
    m = re.search(
        r"(제\s*\d+\s*조(?:\s*의\s*\d+\s*조)?(?:\s*제\s*\d+\s*항)?(?:\s*제\s*\d+\s*호)?)",
        citation,
    )
    if not m:
        return citation.strip(), ""
    article = re.sub(r"\s+", "", m.group(1))
    law_name = citation[: m.start()].strip()
    return law_name, article


def _normalize_article_ref(article: Any) -> str:
    s = str(article or "").strip()
    if not s:
        return ""
    if s.startswith("제") and "조" in s:
        return re.sub(r"\s+", "", s)
    if str(article).isdigit():
        return f"제{article}조"
    return s


def _resolve_cycle_fields(v2_rule: Dict[str, Any]) -> Tuple[Any, str, str]:
    cycle_type = (v2_rule.get("when_cycle_type") or "").strip().upper()
    cycle_unit = (v2_rule.get("when_cycle_unit") or "").strip().upper()
    cycle_value = v2_rule.get("when_cycle_value") or v2_rule.get("inspection_cycle_value")

    if cycle_type in WHEN_CYCLE_TYPE_TO_UNIT:
        std, code = WHEN_CYCLE_TYPE_TO_UNIT[cycle_type]
        val = cycle_value if cycle_value is not None else 1
        return val, code, std
    if cycle_unit in WHEN_CYCLE_UNIT_TO_UNIT:
        std, code = WHEN_CYCLE_UNIT_TO_UNIT[cycle_unit]
        return cycle_value, code, std

    legacy_code = (v2_rule.get("inspection_cycle_unit_code") or "").strip()
    legacy_std = (v2_rule.get("cycle_unit_std") or "").strip()
    if legacy_code or legacy_std:
        return cycle_value, legacy_code, legacy_std
    return cycle_value, "", ""


def _apply_obligation_flags(v1: Dict[str, Any], obligation_type: str) -> None:
    ot = (obligation_type or "").upper()
    if ot == "APPOINT":
        v1["appointment_required"] = True
    elif ot == "INSPECT":
        v1["inspection_required"] = True
    elif ot == "REPORT":
        v1["report_required"] = True
    elif ot == "NOTIFY":
        v1["notify_required"] = True
    else:
        v1["action_required"] = True


def _apply_v2_inline_scope(v1: Dict[str, Any], v2_rule: Dict[str, Any]) -> None:
    if v1.get("condition_code"):
        return
    if v2_rule.get("scope_min_employees") is not None:
        v1["condition_code"] = "employee_count"
        v1["condition_value"] = v2_rule.get("scope_min_employees")
        return
    if v2_rule.get("scope_min_area_sqm") is not None:
        v1["condition_code"] = "building_area"
        v1["condition_value"] = v2_rule.get("scope_min_area_sqm")
        return
    if v2_rule.get("scope_min_construction_amount") is not None:
        v1["condition_code"] = "construction_amount"
        v1["condition_value"] = v2_rule.get("scope_min_construction_amount")


def _apply_scope_bundle(v1: Dict[str, Any], scope: Dict[str, Any]) -> None:
    if not v1.get("law_category_code"):
        v1["law_category_code"] = (scope.get("layer") or "").strip()

    thresholds = scope.get("thresholds")
    if isinstance(thresholds, list) and thresholds and not v1.get("condition_code"):
        t0 = thresholds[0]
        crit = (t0.get("criterion_code") or "").strip()
        cond = CRITERION_TO_CONDITION_CODE.get(crit, crit)
        if cond:
            v1["condition_code"] = cond
            v1["condition_value"] = t0.get("normalized_value")
            if v1["condition_value"] is None:
                v1["condition_value"] = t0.get("numeric_value")
            op = (t0.get("operator") or "").strip().upper()
            v1["condition_operator_code"] = OPERATOR_V2_TO_V1.get(op, "gte")

    if scope.get("condition_code") and not v1.get("condition_code"):
        v1["condition_code"] = scope.get("condition_code") or ""
        v1["condition_value"] = scope.get("condition_value")
        v1["condition_operator_code"] = scope.get("condition_operator_code") or "gte"


def _apply_penalty(
    v1: Dict[str, Any],
    *,
    relation: Optional[Dict[str, Any]],
    penalty_rule: Optional[Dict[str, Any]],
) -> None:
    if penalty_rule:
        pen = (penalty_rule.get("penalty_summary") or penalty_rule.get("why_obligation_summary") or "").strip()
        if pen:
            v1["penalty_summary"] = pen
    if relation:
        rel_pen = (relation.get("penalty_text") or relation.get("penalty_summary") or "").strip()
        if rel_pen:
            v1["penalty_summary"] = rel_pen


def _v2_is_active(v2_rule: Dict[str, Any]) -> bool:
    """v2 마스터는 대량이 status=DRAFT — 진단용으로 DEPRECATED만 제외."""
    if "is_active" in v2_rule and v2_rule.get("is_active") is not None:
        return bool(v2_rule.get("is_active"))
    status = (v2_rule.get("status") or "").strip().upper()
    if status == "DEPRECATED":
        return False
    return True


def _map_executor_type(who_executor: Any) -> str:
    s = (who_executor or "").strip()
    if not s:
        return ""
    if "자격" in s:
        return "qualified"
    if "외부" in s or "위탁" in s:
        return "external"
    if "선임" in s or "관리자" in s:
        return "appointed"
    if "사업주" in s:
        return "anyone"
    return ""


def _pick_sector(sectors: List[str], sector_hint: Optional[str]) -> str:
    hint = (sector_hint or "").strip().upper()
    normalized = [s.strip().upper() for s in sectors if s]
    if hint and hint in normalized:
        return hint
    if normalized:
        return normalized[0]
    return hint


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _first_or_empty(value: Any) -> str:
    items = _as_str_list(value)
    return items[0] if items else ""
