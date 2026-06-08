"""
[ISOLATED] runtime_metadata_resolution → master_building_legal_rules 호환 dict.

소비자 진단(Phase 2)은 compiler_core 경로. 본 모듈은 diagnosis_runtime_step1 등 legacy용.

기계적 필드 매핑만 수행. Supabase/FastAPI import 없음.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from services.rule_v2_adapter import (
    OBLIGATION_TYPE_TO_RULE_TYPE_CODE,
    _apply_obligation_flags,
)

_APPOINT_KW = ("선임", "선정", "지정", "배치", "위촉", "관리자")
_INSPECT_KW = ("점검", "검사", "측정", "진단", "검진", "평가", "조사")
_REPORT_KW = ("신고", "등록", "허가", "인가", "승인", "제출", "신청")
_NOTIFY_KW = ("보고", "통보", "통지", "기록", "보존", "작성", "계획서")
_TASK_TYPE_TO_OBLIGATION: Dict[str, str] = {
    "APPOINTMENT_TASK_CANDIDATE": "APPOINT",
    "DESIGNATE_TASK_CANDIDATE": "APPOINT",
    "REPORT_TASK_CANDIDATE": "REPORT",
    "NOTIFY_TASK_CANDIDATE": "NOTIFY",
    "INSTALL_TASK_CANDIDATE": "ACTION",
    "MEASURE_TASK_CANDIDATE": "INSPECT",
    "INSPECT_TASK_CANDIDATE": "INSPECT",
}
_FAMILY_TO_OBLIGATION: Dict[str, str] = {
    "APPOINT_FAMILY": "APPOINT",
    "REPORT_FAMILY": "REPORT",
    "NOTIFY_FAMILY": "NOTIFY",
    "INSTALL_FAMILY": "ACTION",
    "MEASURE_FAMILY": "INSPECT",
    "INSPECT_FAMILY": "INSPECT",
    "MANDATORY_FAMILY": "ACTION",
    "PERMISSIVE_FAMILY": "ACTION",
}
_NUMERIC_CONDITION = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?:명|인|㎡|m2|m²|kW|KW|kg|억|만)?",
    re.IGNORECASE,
)


def project_metadata_to_v1(
    row: Dict[str, Any],
    *,
    sector_hint: Optional[str] = None,
    task_hint: Optional[Dict[str, Any]] = None,
    obligation_slot: Optional[Dict[str, Any]] = None,
    penalty_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """runtime_metadata_resolution 1건 → v1 호환 dict."""
    law_name = (row.get("source_law_name") or "").strip()
    law_article = _format_article_no(row.get("source_article_no"))
    runtime_name = (row.get("runtime_name") or "").strip()
    who = (row.get("who_value") or "").strip()
    when = (row.get("when_value") or "").strip()
    how = (row.get("how_value") or "").strip()
    parsed_task = _parse_technical_runtime_name(runtime_name)

    obl_summary = _build_obligation_summary(
        runtime_name=runtime_name,
        law_name=law_name,
        law_article=law_article,
        who=who,
        when=when,
        how=how,
        parsed_task=parsed_task,
    )
    remarks_parts = [p for p in (who, when, how) if p]
    remarks = " | ".join(remarks_parts)

    task_hint_merged = task_hint or parsed_task
    obligation_type = _resolve_runtime_obligation_type(
        runtime_name,
        who_value=who,
        when_value=when,
        how_value=how,
        task_hint=task_hint_merged,
        obligation_slot=obligation_slot,
    )
    rule_type_code = OBLIGATION_TYPE_TO_RULE_TYPE_CODE.get(obligation_type, "004")
    cycle_value, cycle_unit_code, cycle_unit_std = _schedule_to_cycle_fields(row.get("schedule_json"))
    due_days = _schedule_to_due_days(row.get("schedule_json"))

    sector = (sector_hint or row.get("sector") or "ALL").strip().upper()
    if sector == "ALL" and sector_hint:
        sector = sector_hint.strip().upper()

    v1: Dict[str, Any] = {
        "rule_id": str(row.get("id") or ""),
        "rule_type_code": rule_type_code,
        "law_name": law_name,
        "law_article": law_article,
        "obligation_summary": obl_summary,
        "remarks": remarks,
        "obligation_type": obligation_type,
        "appointment_required": False,
        "inspection_required": False,
        "action_required": False,
        "report_required": False,
        "notify_required": False,
        "appointment_target_code": "",
        "appointment_qualification_code": "",
        "qualification_type": "",
        "inspection_cycle_value": cycle_value,
        "inspection_cycle_unit_code": cycle_unit_code,
        "cycle_unit_std": cycle_unit_std,
        "cycle_base_type": "",
        "cycle_base_guide": when,
        "due_days": due_days,
        "condition_code": "",
        "condition_value": None,
        "condition_operator_code": "gte",
        "construction_work_type": "",
        "construction_work_type_label": "",
        "submit_org_code": "",
        "executor_type_code": "",
        "report_method_std": "",
        "penalty_summary": (penalty_summary or row.get("evidence_value") or "").strip(),
        "penalty_value": None,
        "penalty_unit_code": "",
        "form_code": "",
        "form_name": "",
        "form_url": "",
        "online_system": "",
        "system_url": "",
        "tai_feature_code": "",
        "sector": sector,
        "diagnosis_stage": 1,
        "is_active": True,
    }
    _apply_obligation_flags(v1, obligation_type)
    _apply_runtime_condition(v1, row)
    return v1


def project_metadata_batch(
    rows: List[Dict[str, Any]],
    *,
    sector_hint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return [
        project_metadata_to_v1(r, sector_hint=sector_hint)
        for r in rows
        if r.get("id")
    ]


def filter_runtime_for_sector(
    rules: List[Dict[str, Any]],
    sector_db: str,
) -> List[Dict[str, Any]]:
    """sector=ALL 또는 요청 sector와 일치하는 규칙만."""
    target = (sector_db or "").strip().upper()
    if not target:
        return list(rules)
    out: List[Dict[str, Any]] = []
    for rule in rules:
        sec = (rule.get("sector") or "").strip().upper()
        if sec in ("", "ALL", "COMMON") or sec == target:
            out.append(rule)
    return out


def _resolve_runtime_obligation_type(
    runtime_name: str,
    *,
    who_value: str = "",
    when_value: str = "",
    how_value: str = "",
    task_hint: Optional[Dict[str, Any]] = None,
    obligation_slot: Optional[Dict[str, Any]] = None,
) -> str:
    if task_hint:
        tt = (task_hint.get("task_type") or "").strip().upper()
        if tt in _TASK_TYPE_TO_OBLIGATION:
            return _TASK_TYPE_TO_OBLIGATION[tt]
        fam = (task_hint.get("source_action_family") or task_hint.get("obligation_family") or "").strip().upper()
        if fam in _FAMILY_TO_OBLIGATION:
            return _FAMILY_TO_OBLIGATION[fam]

    if obligation_slot:
        fam = (obligation_slot.get("family_name") or "").strip().upper()
        if fam in _FAMILY_TO_OBLIGATION:
            return _FAMILY_TO_OBLIGATION[fam]
        token = (obligation_slot.get("raw_token") or obligation_slot.get("canonical_token") or "").strip()
        if "하여야" in token or "해야" in token:
            return _infer_from_text(runtime_name, who_value, when_value, how_value, token)

    return _infer_from_text(runtime_name, who_value, when_value, how_value)


def _infer_from_text(*parts: str) -> str:
    text = " ".join(p for p in parts if p).strip()
    if any(k in text for k in _APPOINT_KW):
        return "APPOINT"
    if any(k in text for k in _INSPECT_KW):
        return "INSPECT"
    if any(k in text for k in _REPORT_KW):
        return "REPORT"
    if any(k in text for k in _NOTIFY_KW):
        return "NOTIFY"
    return "ACTION"


_GENERIC_ACTOR = frozenset({"사업주", "경영책임자", "사용자", "employer"})


def _build_obligation_summary(
    *,
    runtime_name: str,
    law_name: str,
    law_article: str,
    who: str,
    when: str,
    how: str,
    parsed_task: Optional[Dict[str, Any]],
) -> str:
    if not _is_technical_runtime_name(runtime_name):
        return runtime_name or _join_meaningful_parts(who, when, how) or runtime_name

    parts = _meaningful_parts(who, when, how)
    if parts:
        return _join_meaningful_parts(*parts)

    task_label = _runtime_label_from_task(parsed_task)
    law_bit = " ".join(p for p in (law_name, law_article) if p).strip()
    if task_label and law_bit:
        return f"{law_bit} — {task_label}"
    if task_label:
        return task_label
    return runtime_name


def _meaningful_parts(*parts: str) -> List[str]:
    out: List[str] = []
    for p in parts:
        s = (p or "").strip()
        if not s or _is_technical_runtime_name(s):
            continue
        if s in _GENERIC_ACTOR:
            continue
        if s not in out:
            out.append(s)
    return out


def _join_meaningful_parts(*parts: str) -> str:
    cleaned = _meaningful_parts(*parts)
    if not cleaned:
        generic = [(p or "").strip() for p in parts if (p or "").strip() and not _is_technical_runtime_name((p or "").strip())]
        if generic:
            return generic[0]
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return " · ".join(cleaned)


def _first_human_text(*parts: str) -> str:
    return _join_meaningful_parts(*parts)


def _runtime_label_from_task(task_hint: Optional[Dict[str, Any]]) -> str:
    if not task_hint:
        return ""
    tt = (task_hint.get("task_type") or "").replace("_TASK_CANDIDATE", "").replace("_", " ").strip()
    fam = (task_hint.get("source_action_family") or "").replace("_FAMILY", "").replace("_", " ").strip()
    if tt and fam and tt.lower() != fam.lower():
        return f"{tt} ({fam})"
    return tt or fam


def _is_technical_runtime_name(name: str) -> bool:
    u = (name or "").upper()
    return "TASK_CANDIDATE" in u or "_FAMILY" in u


def _parse_technical_runtime_name(name: str) -> Optional[Dict[str, Any]]:
    """`APPOINTMENT_TASK_CANDIDATE: APPOINT_FAMILY` → task_hint dict."""
    if not _is_technical_runtime_name(name):
        return None
    left, _, right = name.partition(":")
    task_type = left.strip().upper()
    family = right.strip().upper()
    hint: Dict[str, Any] = {}
    if task_type:
        hint["task_type"] = task_type
    if family:
        hint["source_action_family"] = family
        hint["obligation_family"] = family
    return hint or None


def _format_article_no(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if s.startswith("제") and "조" in s:
        return s
    digits = re.sub(r"[^\d]", "", s)
    if digits:
        return f"제{digits}조"
    return s


def _schedule_to_cycle_fields(schedule_json: Any) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    obj = _parse_json_dict(schedule_json)
    if not obj:
        return None, None, None

    periodic = obj.get("정기") or obj.get("periodic")
    if isinstance(periodic, dict):
        period = str(periodic.get("period") or periodic.get("unit") or "").strip()
        val = periodic.get("value")
        if period in ("년", "year", "YEAR"):
            return int(val or 1), "006", "year"
        if period in ("월", "month", "MONTH"):
            return int(val or 1), "003", "month"

    unit = str(obj.get("unit") or "").strip()
    val = obj.get("value")
    if unit in ("년", "year") and val is not None:
        return int(val), "006", "year"
    if unit in ("월", "month") and val is not None:
        return int(val), "003", "month"
    if obj.get("type") == "CONTINUOUS":
        return None, None, None
    return None, None, None


def _schedule_to_due_days(schedule_json: Any) -> Optional[int]:
    obj = _parse_json_dict(schedule_json)
    if not obj:
        return None
    unit = str(obj.get("unit") or "").strip()
    val = obj.get("value")
    if val is None:
        return None
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        return None
    if unit in ("일", "day", "DAY") and n > 0:
        return n
    return None


def _parse_json_dict(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _apply_runtime_condition(v1: Dict[str, Any], row: Dict[str, Any]) -> None:
    if v1.get("condition_code"):
        return
    cv = row.get("condition_value")
    if cv is None or (isinstance(cv, str) and not str(cv).strip()):
        return
    text = str(cv).strip()
    m = _NUMERIC_CONDITION.search(text.replace(",", ""))
    if not m:
        return
    try:
        num = float(m.group("value"))
    except (TypeError, ValueError):
        return
    if "㎡" in text or "m2" in text.lower():
        v1["condition_code"] = "building_area"
        v1["condition_value"] = num
        return
    if "kW" in text.upper() or "kw" in text:
        v1["condition_code"] = "electric_capacity"
        v1["condition_value"] = num
        return
    if "억" in text:
        v1["condition_code"] = "construction_amount"
        v1["condition_value"] = num * 100_000_000
        return
    if "명" in text or "인" in text:
        v1["condition_code"] = "employee_count"
        v1["condition_value"] = num
        return
