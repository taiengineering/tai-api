"""
services/leg_output_adapter.py — LEG Output Adapter v1.0.0

build_result() raw output → Obligation Contract 변환.

원칙:
- 엔진 수정 없음
- 법적 판단 없음
- applies 재판정 없음
- deterministic, stateless
- 모든 obligation은 동일 필드 구조
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

ADAPTER_VERSION = "1.0.0"

TYPE_LABELS = {
    "appointment": "선임",
    "inspection": "점검",
    "action": "조치",
    "report": "신고",
    "notify": "보고",
}

# raw bucket key → obligation_type
BUCKET_TYPE_MAP = {
    "appointment_required": "APPOINT",
    "inspection_required": "INSPECT",
    "action_required": "ACTION",
    "report_required": "REPORT",
}

_BUCKET_KEYS = (
    "appointment_required",
    "inspection_required",
    "action_required",
    "report_required",
)


# ── cleanup ─────────────────────────────────────────

def _clean_label(text: str) -> str:
    """runtime 내부명 제거. 의미 생성 없음."""
    if not text:
        return ""
    text = re.sub(r"\b[A-Z_]+_TASK_CANDIDATE\b", "", text)
    text = re.sub(r"\b[A-Z_]+_TASK_[A-Z_]+\b", "", text)
    text = re.sub(r"\b[A-Z_]+_FAMILY\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_title(item: Dict[str, Any]) -> str:
    """
    obligation title 결정.
    fallback chain — 의미 생성 아님.
    """
    for field in ("obligation_summary", "description", "remarks"):
        val = _clean_label((item.get(field) or "").strip())
        if val and len(val) >= 3:
            return val[:100]

    law = (item.get("law_name") or "").strip()
    art = (item.get("law_article") or "").strip()
    if law and art:
        return f"{law} {art} 관련 의무"
    if law:
        return f"{law} 관련 의무"
    return "관련 법적 의무"


# ── obligation 변환 ──────────────────────────────────

def _to_obligation(
    item: Dict[str, Any],
    source_bucket: str,
    idx: int,
) -> Dict[str, Any]:
    """
    raw rule dict → 통일된 Obligation dict.
    모든 bucket의 item이 동일한 구조로 변환됨.
    """
    rule_id = (item.get("rule_id") or "").strip()
    ob_type = (
        item.get("obligation_type") or BUCKET_TYPE_MAP.get(source_bucket, "ACTION")
    ).upper()

    # notify 분리: report bucket에서 왔는데 notify 플래그가 있으면
    if source_bucket == "report_required":
        if item.get("notify_required"):
            ob_type = "NOTIFY"
        if (item.get("obligation_type") or "").upper() == "NOTIFY":
            ob_type = "NOTIFY"

    obligation_id = rule_id if rule_id else f"OB-{source_bucket}-{idx}"

    return {
        # Identity
        "obligation_id": obligation_id,
        "obligation_type": ob_type,

        # 법령 근거
        "law_name": (item.get("law_name") or "").strip(),
        "law_article": (item.get("law_article") or "").strip(),
        "article_title": _clean_label(item.get("article_title") or ""),
        "article_text": (item.get("article_text") or "").strip(),

        # 의무 내용
        "title": _resolve_title(item),
        "description": _clean_label(
            item.get("description") or item.get("remarks") or ""
        ),

        # 이행 정보
        "schedule_info": {
            "schedule_type": item.get("schedule_type") or "ON_DEMAND",
            "cycle_label": item.get("inspection_cycle") or "",
            "cycle_unit": item.get("inspection_cycle_unit") or "",
            "cycle_int": item.get("inspection_cycle_int") or 0,
            "due_days": item.get("due_days") or 0,
        },

        # 수행 주체
        "executor": {
            "type_code": item.get("executor_type_code") or "",
            "type_label": item.get("executor_type_label") or "",
            "appointment_target": item.get("appointment_target") or "",
            "qualification": (
                item.get("qualification_required") or item.get("qualification_code") or ""
            ),
        },

        # 벌칙
        "penalty_summary": (
            item.get("penalty_summary") or item.get("penalty_amount") or ""
        ),

        # 신고/제출
        "submission": {
            "org_code": item.get("submit_org_code") or "",
            "org_label": item.get("submit_org_label") or "",
            "method": item.get("report_method_std") or "",
            "method_label": item.get("report_method_label") or "",
            "form_name": item.get("form_name") or "",
            "form_url": item.get("form_url") or "",
            "system_name": item.get("online_system") or "",
            "system_url": item.get("system_url") or "",
        },

        # 근거 추적
        "evidence": {
            "rule_id": rule_id,
            "rule_type": item.get("rule_type") or "",
            "condition_code": item.get("condition_code") or "",
            "condition_value": item.get("condition_value"),
            "source_bucket": source_bucket,
        },
    }


# ── dedup / sort ─────────────────────────────────────

def _dedup(obligations: List[Dict]) -> Tuple[List[Dict], int]:
    """rule_id 기준 중복 제거. 첫 번째 유지."""
    seen = set()
    result = []
    removed = 0
    for ob in obligations:
        key = ob["obligation_id"]
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        result.append(ob)
    return result, removed


def _sort_key(ob: Dict) -> tuple:
    """stable sort: law_name → 조문번호(int) → obligation_id."""
    art = ob.get("law_article") or ""
    m = re.search(r"(\d+)", art)
    art_num = int(m.group(1)) if m else 0
    return (ob.get("law_name") or "", art_num, ob.get("obligation_id") or "")


# ── grouping ─────────────────────────────────────────

_TYPE_BUCKET_TO_CODE = {
    "appointment": "APPOINT",
    "inspection": "INSPECT",
    "action": "ACTION",
    "report": "REPORT",
    "notify": "NOTIFY",
}


def _group_by_type(obligations: List[Dict]) -> Dict:
    result = {}
    for bucket_key, label in TYPE_LABELS.items():
        type_code = _TYPE_BUCKET_TO_CODE[bucket_key]
        ids = [
            ob["obligation_id"]
            for ob in obligations
            if ob["obligation_type"] == type_code
        ]
        result[bucket_key] = {
            "label": label,
            "count": len(ids),
            "obligation_ids": ids,
        }
    return result


def _group_by_law(obligations: List[Dict]) -> List[Dict]:
    law_map: Dict[str, Dict] = {}
    for ob in obligations:
        ln = ob.get("law_name") or "기타"
        if ln not in law_map:
            law_map[ln] = {
                "law_name": ln,
                "count": 0,
                "types": {},
                "obligation_ids": [],
            }
        law_map[ln]["count"] += 1
        ot = ob.get("obligation_type", "OTHER")
        law_map[ln]["types"][ot] = law_map[ln]["types"].get(ot, 0) + 1
        law_map[ln]["obligation_ids"].append(ob["obligation_id"])

    return sorted(law_map.values(), key=lambda g: -g["count"])


def _raw_adapter_input(raw: Dict[str, Any], mode: str = "") -> Dict[str, Any]:
    """build_result() 또는 v510 result_data에서 adapter 입력 필드 추출."""
    return {
        "engine_version": raw.get("engine_version", ""),
        "mode": raw.get("mode") or mode,
        "evaluated_at": raw.get("evaluated_at", ""),
        "total_rules_checked": raw.get("total_rules_checked", 0),
        "not_applicable_count": raw.get("not_applicable_count", 0),
        "applicable_count": raw.get("applicable_count", 0),
        "appointment_required": raw.get("appointment_required") or [],
        "inspection_required": raw.get("inspection_required") or [],
        "action_required": raw.get("action_required") or [],
        "report_required": raw.get("report_required") or [],
        "summary": raw.get("summary") or {},
    }


# ── 메인 ─────────────────────────────────────────────

def adapt(raw: Dict[str, Any], *, mode: str = "") -> Dict[str, Any]:
    """
    build_result() raw output → Obligation Contract.

    1. 4개 bucket → 통일된 Obligation list로 변환
    2. label cleanup + title fallback
    3. dedup (obligation_id 기준)
    4. stable sort (law_name → 조문번호 → obligation_id)
    5. grouped_by_type / grouped_by_law (id 참조)
    6. summary / evidence_refs / metadata
    """
    adapter_raw = _raw_adapter_input(raw, mode=mode)

    all_obs: List[Dict] = []
    for bucket in _BUCKET_KEYS:
        items = adapter_raw.get(bucket) or []
        for i, item in enumerate(items):
            all_obs.append(_to_obligation(item, bucket, i))

    input_count = len(all_obs)

    labels_cleaned = 0
    empty_titles_filled = 0
    for ob in all_obs:
        raw_title_fields = (
            (ob.get("evidence") or {}).get("_original_desc")
            or ob.get("title")
        )
        if ob["title"] != raw_title_fields:
            labels_cleaned += 1
        if not ob.get("description"):
            empty_titles_filled += 1

    obligations, duplicates_removed = _dedup(all_obs)
    obligations = sorted(obligations, key=_sort_key)

    grouped_by_type = _group_by_type(obligations)
    grouped_by_law = _group_by_law(obligations)

    evidence_refs = [
        {"law_name": g["law_name"], "count": g["count"]} for g in grouped_by_law
    ]

    engine_summary = adapter_raw.get("summary") or {}
    summary = {
        **engine_summary,
        "law_count": len(evidence_refs),
        "total_rules_checked": adapter_raw.get("total_rules_checked", 0),
    }

    return {
        "engine_version": adapter_raw.get("engine_version", ""),
        "mode": adapter_raw.get("mode", ""),
        "evaluated_at": adapter_raw.get("evaluated_at", ""),
        "adapter_version": ADAPTER_VERSION,
        "obligations": obligations,
        "grouped_by_type": grouped_by_type,
        "grouped_by_law": grouped_by_law,
        "evidence_refs": evidence_refs,
        "summary": summary,
        "metadata": {
            "adapter_stats": {
                "input_count": input_count,
                "output_count": len(obligations),
                "duplicates_removed": duplicates_removed,
                "labels_cleaned": labels_cleaned,
                "empty_titles_filled": empty_titles_filled,
            },
        },
    }
