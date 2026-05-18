"""Legal Adapter MVP — Translates legal engine output to runtime projections.

Ownership: Runtime Projection Layer.
Does NOT modify legal engine truth.
Does NOT modify document_forms.

GPT-exclusive files (runtime_binding_resolver etc.) are NOT touched.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from db.supabase_client import get_supabase
from services import runtime_task_service as task_svc

logger = logging.getLogger(__name__)

# ----- rule_kind → task_type mapping -----
_RULE_KIND_MAP: dict[str, str] = {
    "INSPECTION": "inspection",
    "PERMIT": "permit",
    "REPORT": "report",
    "TRAINING": "training",
    "APPOINTMENT": "appointment",
    "PROHIBITION": "compliance_check",
}

# rule_kinds that do NOT produce runtime tasks
_RESIDUAL_KINDS = {"PENALTY", "STANDARD"}

# ----- Default document/evidence bindings per task_type -----
_DOC_BINDING: dict[str, dict] = {
    "inspection": {"document_type": "checklist", "title": "점검 체크리스트"},
    "permit": {"document_type": "permit", "title": "작업허가서"},
    "report": {"document_type": "report", "title": "보고서"},
    "training": {"document_type": "form", "title": "교육기록부"},
    "appointment": {"document_type": "certificate", "title": "선임서류"},
}

_EVIDENCE_BINDING: dict[str, list[dict]] = {
    "inspection": [
        {"evidence_type": "photo", "title": "점검 현장 사진"},
    ],
    "permit": [
        {"evidence_type": "signature", "title": "서명"},
        {"evidence_type": "photo", "title": "현장 사진"},
    ],
    "compliance_check": [
        {"evidence_type": "file", "title": "준수 증빙자료"},
    ],
}


# ----- Main entry -----

async def project_rules(
    tenant_id: str,
    facility_id: str,
    matched_rules: list[dict[str, Any]],
    *,
    trace_id: Optional[str] = None,
) -> dict:
    """Convert matched legal rules into runtime task candidates.

    Returns {"tasks": [...], "residuals": [...], "stats": {...}}
    """
    trace = trace_id or str(uuid.uuid4())
    tasks_created: list[dict] = []
    residuals: list[dict] = []
    sb = get_supabase()

    for rule in matched_rules:
        rule_kind = (rule.get("rule_kind") or "").upper()
        rule_id = str(rule.get("id") or rule.get("rule_id") or "")

        # Skip residual kinds
        if rule_kind in _RESIDUAL_KINDS:
            _log_residual(
                sb, tenant_id, facility_id, rule_id,
                rule_kind, f"rule_kind={rule_kind} not projected",
            )
            residuals.append({"rule_id": rule_id, "rule_kind": rule_kind})
            continue

        task_type = _RULE_KIND_MAP.get(rule_kind)
        if not task_type:
            _log_residual(
                sb, tenant_id, facility_id, rule_id,
                rule_kind, f"Unknown rule_kind={rule_kind}",
            )
            residuals.append({"rule_id": rule_id, "rule_kind": rule_kind})
            continue

        # Create runtime_task candidate
        title = rule.get("title") or rule.get("rule_text") or f"{task_type} task"
        task = await task_svc.create_task({
            "tenant_id": tenant_id,
            "facility_id": facility_id,
            "source_engine": "legal",
            "source_ref_id": rule_id,
            "trace_id": trace,
            "task_type": task_type,
            "title": title[:200],
            "description": rule.get("description") or rule.get("rule_text"),
            "priority": _severity_to_priority(rule),
            "metadata": {
                "rule_kind": rule_kind,
                "law_name": rule.get("law_name"),
                "article": rule.get("article"),
            },
        })
        task_id = task["id"]

        # Auto-bind document requirement
        await _bind_document(sb, tenant_id, facility_id, task_id, task_type)

        # Auto-bind evidence requirements
        await _bind_evidence(sb, tenant_id, facility_id, task_id, task_type)

        tasks_created.append(task)

    return {
        "tasks": tasks_created,
        "residuals": residuals,
        "stats": {
            "total_rules": len(matched_rules),
            "projected": len(tasks_created),
            "residual": len(residuals),
        },
    }


# ----- Helpers -----

def _severity_to_priority(rule: dict) -> str:
    sev = (rule.get("severity") or "").lower()
    if sev in ("critical", "very_high"):
        return "critical"
    if sev == "high":
        return "high"
    if sev == "low":
        return "low"
    return "medium"


async def _bind_document(
    sb, tenant_id: str, facility_id: str,
    task_id: str, task_type: str,
) -> None:
    binding = _DOC_BINDING.get(task_type)
    if not binding:
        return
    sb.table("runtime_document_requirement").insert({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "facility_id": facility_id,
        "task_id": task_id,
        "document_type": binding["document_type"],
        "title": binding["title"],
    }).execute()


async def _bind_evidence(
    sb, tenant_id: str, facility_id: str,
    task_id: str, task_type: str,
) -> None:
    bindings = _EVIDENCE_BINDING.get(task_type, [])
    for b in bindings:
        sb.table("runtime_evidence_requirement").insert({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "facility_id": facility_id,
            "task_id": task_id,
            "evidence_type": b["evidence_type"],
            "title": b["title"],
        }).execute()


def _log_residual(
    sb, tenant_id: str, facility_id: str,
    rule_id: str, rule_kind: str, reason: str,
) -> None:
    try:
        sb.table("residual_log").insert({
            "tenant_id": tenant_id,
            "facility_id": facility_id,
            "source_engine": "legal",
            "source_ref_id": rule_id,
            "rule_kind": rule_kind,
            "reason": reason,
        }).execute()
    except Exception:
        logger.warning("residual_log insert failed", exc_info=True)
