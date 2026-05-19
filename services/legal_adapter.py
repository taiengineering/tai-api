"""Legal Adapter v2 — Contract Adapter for Binding Engine.

Converts legal matched_rules → RuntimeCandidateInput → Binding Engine.
Does NOT create runtime_task directly (candidate → activation → runtime).

Backward-compatible: project_rules() returns candidates instead of tasks.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from models.runtime_candidate_contract import RuntimeCandidateInput
from services.runtime_binding_engine import project_candidate, log_residual

logger = logging.getLogger(__name__)

# ----- rule_kind → candidate_type mapping -----
_RULE_KIND_MAP: dict[str, str] = {
    "INSPECTION": "inspection",
    "PERMIT": "permit",
    "REPORT": "report",
    "TRAINING": "training",
    "APPOINTMENT": "appointment",
    "PROHIBITION": "compliance_check",
}

_RESIDUAL_KINDS = {"PENALTY", "STANDARD"}

# ----- Default document/evidence suggestions per candidate_type -----
_DOC_SUGGESTIONS: dict[str, list[dict]] = {
    "inspection": [{"document_type": "checklist", "title": "점검 체크리스트"}],
    "permit": [{"document_type": "permit", "title": "작업허가서"}],
    "report": [{"document_type": "report", "title": "보고서"}],
    "training": [{"document_type": "form", "title": "교육기록부"}],
    "appointment": [{"document_type": "certificate", "title": "선임서류"}],
}

_EVI_SUGGESTIONS: dict[str, list[dict]] = {
    "inspection": [{"evidence_type": "photo", "title": "점검 현장 사진"}],
    "permit": [
        {"evidence_type": "signature", "title": "서명"},
        {"evidence_type": "photo", "title": "현장 사진"},
    ],
    "compliance_check": [{"evidence_type": "file", "title": "준수 증빙자료"}],
}


def _severity_to_priority(rule: dict) -> str:
    sev = (rule.get("severity") or "").lower()
    if sev in ("critical", "very_high"):
        return "critical"
    if sev == "high":
        return "high"
    if sev == "low":
        return "low"
    return "medium"


async def project_rules(
    tenant_id: str,
    facility_id: str,
    matched_rules: list[dict[str, Any]],
    *,
    trace_id: Optional[str] = None,
) -> dict:
    """Convert legal matched_rules into runtime candidates via Binding Engine.

    Returns {"candidates": [...], "residuals": [...], "stats": {...}}
    """
    trace = trace_id or str(uuid.uuid4())
    candidates_created: list[dict] = []
    residuals: list[dict] = []

    for rule in matched_rules:
        rule_kind = (rule.get("rule_kind") or "").upper()
        rule_id = str(rule.get("id") or rule.get("rule_id") or "")

        if rule_kind in _RESIDUAL_KINDS:
            await log_residual(
                tenant_id=tenant_id,
                facility_id=facility_id,
                source_engine="legal",
                source_ref_id=rule_id,
                candidate_type=rule_kind.lower(),
                reason=f"rule_kind={rule_kind} not projected",
                raw_data=rule,
            )
            residuals.append({"rule_id": rule_id, "rule_kind": rule_kind})
            continue

        candidate_type = _RULE_KIND_MAP.get(rule_kind)
        if not candidate_type:
            await log_residual(
                tenant_id=tenant_id,
                facility_id=facility_id,
                source_engine="legal",
                source_ref_id=rule_id,
                candidate_type=rule_kind.lower() if rule_kind else "unknown",
                reason=f"Unknown rule_kind={rule_kind}",
                raw_data=rule,
            )
            residuals.append({"rule_id": rule_id, "rule_kind": rule_kind})
            continue

        title = rule.get("title") or rule.get("rule_text") or f"{candidate_type} task"

        inp = RuntimeCandidateInput(
            candidate_type=candidate_type,
            title=title[:200],
            description=rule.get("description") or rule.get("rule_text"),
            source_engine="legal",
            source_ref_id=rule_id,
            tenant_id=tenant_id,
            facility_id=facility_id,
            trace_id=trace,
            priority=_severity_to_priority(rule),
            payload={
                "rule_kind": rule_kind,
                "law_name": rule.get("law_name"),
                "article": rule.get("article"),
            },
            source_trace={"original_rule": rule},
            document_suggestions=_DOC_SUGGESTIONS.get(candidate_type, []),
            evidence_suggestions=_EVI_SUGGESTIONS.get(candidate_type, []),
        )

        result = await project_candidate(inp)
        candidates_created.append(result)

    return {
        "candidates": candidates_created,
        "residuals": residuals,
        "stats": {
            "total_rules": len(matched_rules),
            "projected": len(candidates_created),
            "residual": len(residuals),
        },
    }
