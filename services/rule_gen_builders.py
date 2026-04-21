from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.rule_gen_helpers import _is_blank, _normalize_submit_org_code, _safe_float, _safe_int, _to_bool


def _build_master_payload(row: dict, rule_id: str) -> dict:
    ob_type = row.get("obligation_type")
    cond_val_num = _safe_float(row.get("condition_value"))
    submit_org_code = _normalize_submit_org_code(row.get("submit_org_code"))
    return {
        "rule_id": rule_id,
        "sector": row.get("sector") or "BUILDING",
        "law_name": row.get("law_name"),
        "law_article": row.get("law_article"),
        "obligation_type": ob_type,
        "obligation_summary": row.get("obligation_summary"),
        "remarks": row.get("remarks"),
        "penalty_summary": row.get("penalty_summary"),
        "penalty_value": _safe_int(row.get("penalty_value")),
        "appointment_target_code": row.get("appointment_target"),
        "appointment_qualification_code": row.get("appointment_qualification_code"),
        "appointment_qualification_level_code": row.get("appointment_qualification_level_code"),
        "appointment_count_value": _safe_int(row.get("appointment_count_value")),
        "condition_code": row.get("condition_code"),
        "condition_operator_code": row.get("condition_operator", "gte"),
        "condition_value": cond_val_num,
        "inspection_cycle_value": _safe_int(row.get("inspection_cycle_value")),
        "inspection_cycle_unit_code": row.get("inspection_cycle_unit_code"),
        "cycle_base_guide": row.get("cycle_base_guide"),
        "form_code": row.get("form_code"),
        "form_name": row.get("form_name"),
        "submit_org_code": submit_org_code,
        "report_method_code": row.get("report_method_code"),
        "report_method_std": row.get("report_method_std"),
        "online_system": row.get("online_system"),
        "system_url": row.get("system_url"),
        "tai_feature_code": row.get("tai_feature_code"),
        "due_days": _safe_int(row.get("due_days")),
        "appointment_required": _to_bool(row.get("appointment_required")) or ob_type == "APPOINT",
        "inspection_required": _to_bool(row.get("inspection_required")) or ob_type == "INSPECT",
        "notify_required": _to_bool(row.get("notify_required")) or ob_type == "NOTIFY",
        "report_required": _to_bool(row.get("report_required")) or ob_type == "REPORT",
        "action_required": _to_bool(row.get("action_required")) or ob_type == "ACTION",
        "diagnosis_stage": _safe_int(row.get("diagnosis_stage")) or 1,
        "is_active": True,
        "source_api": "AI_GENERATED",
    }


def _build_reparse_prompt(rule: dict, full_context: str, few_shot_examples: List[dict]) -> str:
    return f"""다음 기존 master 룰의 빈 필드(null/빈문자)만 보강하세요.
기존 값이 있는 필드는 그대로 유지하세요.
출력은 JSON object 1개만 반환하세요.

[기존 룰]
{json.dumps(rule, ensure_ascii=False)}

[같은 법령의 잘 채워진 예시]
{json.dumps(few_shot_examples[:5], ensure_ascii=False)}

[법령 원문 풀 컨텍스트]
{(full_context or "")[:18000]}

반드시 아래 키를 포함한 JSON object를 반환:
penalty_summary, penalty_value, form_code, form_name, submit_org_code,
due_days, report_method_code, report_method_std, appointment_qualification_code,
appointment_qualification_level_code, appointment_count_value,
inspection_cycle_value, inspection_cycle_unit_code, cycle_base_guide,
online_system, system_url, tai_feature_code, remarks, condition_code,
condition_operator_code, condition_value
"""


def _build_draft_row(law_name: str, law_article: str, article_id: Optional[str], article_text: str, rule: Dict[str, Any]) -> dict:
    return {
        "law_name": law_name,
        "law_article": law_article,
        "article_id": article_id,
        "article_text": article_text[:2000],
        "draft_rule_id": rule.get("draft_rule_id"),
        "obligation_type": rule.get("obligation_type"),
        "sector": rule.get("sector"),
        "condition_code": rule.get("condition_code"),
        "condition_operator": rule.get("condition_operator", "gte"),
        "condition_value": str(rule["condition_value"]) if rule.get("condition_value") is not None else None,
        "obligation_summary": rule.get("obligation_summary"),
        "penalty_summary": rule.get("penalty_summary"),
        "appointment_target": rule.get("appointment_target"),
        "diagnosis_stage": rule.get("diagnosis_stage", 1),
        "ai_confidence": rule.get("ai_confidence"),
        "ai_reasoning": rule.get("ai_reasoning"),
        "ai_flags": rule.get("ai_flags"),
        "status": "PENDING",
    }


def _pick_reparse_targets(rows: List[dict], limit: int) -> List[dict]:
    def _blank_score(r: dict) -> int:
        fields = [
            "penalty_summary",
            "penalty_value",
            "form_code",
            "form_name",
            "submit_org_code",
            "report_method_code",
            "appointment_qualification_code",
            "inspection_cycle_value",
            "inspection_cycle_unit_code",
            "cycle_base_guide",
            "remarks",
        ]
        return sum(1 for f in fields if _is_blank(r.get(f)))

    rows_sorted = sorted(rows, key=_blank_score, reverse=True)
    return rows_sorted[:limit]
