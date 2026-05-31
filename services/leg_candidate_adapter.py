from __future__ import annotations
import re, uuid
from typing import Any, Dict, List

ADAPTER_VERSION = "1.0.0"
RUNTIME_NAME_SOURCE_TYPE = {
    "REPORT_TASK_CANDIDATE": "REPORT", "INSTALL_TASK_CANDIDATE": "INSTALL",
    "APPOINTMENT_TASK_CANDIDATE": "APPOINT", "NOTIFY_TASK_CANDIDATE": "NOTIFY",
    "MANAGE_TASK_CANDIDATE": "MANAGE", "INSPECTION_TASK_CANDIDATE": "INSPECT",
    "VERIFY_TASK_CANDIDATE": "VERIFY", "DESIGNATE_TASK_CANDIDATE": "DESIGNATE",
    "MEASURE_TASK_CANDIDATE": "MEASURE", "EXECUTE_TASK_CANDIDATE": "EXECUTE",
    "TRAINING_TASK_CANDIDATE": "TRAINING", "PRESERVE_TASK_CANDIDATE": "PRESERVE",
    "RECORD_TASK_CANDIDATE": "RECORD",
}

def _clean(text):
    if not text: return ""
    text = re.sub(r'\b[A-Z_]+_TASK_CANDIDATE\b', '', text)
    text = re.sub(r'\b[A-Z_]+_TASK_[A-Z_]+\b', '', text)
    text = re.sub(r'\b[A-Z_]+_FAMILY\b', '', text)
    text = re.sub(r':\s*$', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def _resolve_source_type(runtime_name):
    if not runtime_name: return ""
    for prefix, stype in RUNTIME_NAME_SOURCE_TYPE.items():
        if runtime_name.upper().startswith(prefix): return stype
    return ""

def _make_candidate(item, source_bucket):
    runtime_name = (item.get("runtime_name") or "").strip()
    source_type = (item.get("obligation_type") or _resolve_source_type(runtime_name) or "").upper()
    rule_id = (item.get("rule_id") or "").strip()
    candidate_id = rule_id if rule_id else str(uuid.uuid4())
    condition_code = (item.get("condition_code") or "").strip()
    condition_value = item.get("condition_value")
    condition_exists = bool(condition_code or condition_value is not None)
    return {
        "candidate_id": candidate_id, "source_type": source_type, "source_bucket": source_bucket,
        "law_name": (item.get("law_name") or "").strip(),
        "article_no": (item.get("law_article") or "").strip(),
        "article_title": _clean(item.get("article_title") or ""),
        "article_text": (item.get("article_text") or "").strip(),
        "who": _clean(item.get("appointment_target") or item.get("executor_type_label") or ""),
        "when": _clean(item.get("inspection_cycle") or item.get("cycle_base_guide") or ""),
        "where": "", "what": _clean(item.get("description") or item.get("obligation_summary") or item.get("remarks") or ""),
        "how": _clean(runtime_name), "why": (item.get("law_name") or "").strip(),
        "condition_exists": condition_exists, "condition_code": condition_code,
        "condition_value": condition_value, "condition_source": (item.get("condition_source") or "").strip(),
        "parent_reference": "",
        "evidence_chain": [{"rule_id": rule_id, "rule_type": (item.get("rule_type") or "").strip(), "source_bucket": source_bucket}] if rule_id else [],
        "schedule_type": (item.get("schedule_type") or "").strip(),
        "cycle_unit": (item.get("inspection_cycle_unit") or "").strip(),
        "cycle_int": item.get("inspection_cycle_int") or 0,
        "due_days": item.get("due_days") or 0,
        "executor_type": (item.get("executor_type_code") or "").strip(),
        "qualification": (item.get("qualification_code") or item.get("qualification_required") or "").strip(),
        "penalty_summary": (item.get("penalty_summary") or item.get("penalty_amount") or "").strip(),
        "submit_org": (item.get("submit_org_label") or item.get("submit_org_code") or "").strip(),
        "submit_method": (item.get("report_method_label") or item.get("report_method_std") or "").strip(),
        "form_name": (item.get("form_name") or "").strip(),
        "form_url": (item.get("form_url") or "").strip(),
        "system_url": (item.get("system_url") or "").strip(),
    }

def to_candidate_contract(raw):
    candidates = []
    for bucket in ("appointment_required","inspection_required","action_required","report_required"):
        for item in (raw.get(bucket) or []):
            candidates.append(_make_candidate(item, bucket))
    law_counts = {}
    for c in candidates:
        ln = c["law_name"] or "기타"
        law_counts[ln] = law_counts.get(ln, 0) + 1
    evidence_refs = [{"law_name": ln, "count": cnt} for ln, cnt in sorted(law_counts.items(), key=lambda x: -x[1])]
    type_counts = {}
    for c in candidates:
        st = c["source_type"] or "UNKNOWN"
        type_counts[st] = type_counts.get(st, 0) + 1
    return {
        "engine_version": raw.get("engine_version",""), "mode": raw.get("mode",""),
        "evaluated_at": raw.get("evaluated_at",""), "adapter_version": ADAPTER_VERSION,
        "candidates": candidates,
        "metadata": {
            "candidate_count": len(candidates), "total_rules_checked": raw.get("total_rules_checked",0),
            "laws_count": len(evidence_refs), "source_type_counts": type_counts,
            "adapter_stats": {"input_buckets": {
                "appointment": len(raw.get("appointment_required") or []),
                "inspection": len(raw.get("inspection_required") or []),
                "action": len(raw.get("action_required") or []),
                "report": len(raw.get("report_required") or []),
            }},
        },
        "evidence_refs": evidence_refs,
    }
