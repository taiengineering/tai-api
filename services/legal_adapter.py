"""Legal Adapter v2.1 — Contract Adapter for Binding Engine + Inspection Bridge.

Converts legal matched_rules → RuntimeCandidateInput → Binding Engine.
Does NOT create runtime_task directly (candidate → activation → runtime).

v2.1: Also creates inspection_sets for inspection-anchor.html compatibility.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from db.supabase_client import get_supabase
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

# ----- candidate_type → obligation_type (inspection_sets용) -----
_CANDIDATE_TO_OBLIGATION: dict[str, str] = {
    "inspection": "INSPECT",
    "appointment": "APPOINT",
    "report": "REPORT",
    "training": "DOCUMENT",
    "compliance_check": "ACTION",
    "permit": "DOCUMENT",
}

_DEFAULT_CYCLES: dict[str, tuple] = {
    "INSPECT": ("year", 1),
    "APPOINT": ("year", 1),
    "REPORT": ("year", 1),
    "DOCUMENT": ("year", 1),
    "ACTION": ("year", 1),
}

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


def _create_inspection_set(
    tenant_id: str,
    facility_id: str,
    candidate_type: str,
    title: str,
    description: str | None,
    rule: dict[str, Any],
) -> None:
    """Create inspection_set alongside runtime_candidate (bridge).

    Dedup: factory_id + law_name + law_article.
    """
    try:
        sb = get_supabase()
        law_name = rule.get("law_name") or ""
        law_article = rule.get("article") or ""

        if not law_name:
            return

        # 중복 방지
        existing = (
            sb.table("inspection_sets")
            .select("id")
            .eq("factory_id", facility_id)
            .eq("law_name", law_name)
            .eq("law_article", law_article)
            .limit(1)
            .execute()
        )
        if existing.data:
            return

        obl_type = _CANDIDATE_TO_OBLIGATION.get(candidate_type, "OTHER")
        cycle_unit, cycle_value = _DEFAULT_CYCLES.get(obl_type, ("year", 1))

        row = {
            "id": str(uuid.uuid4()),
            "company_id": tenant_id,
            "factory_id": facility_id,
            "inspection_set_name": (title or "")[:200],
            "law_name": law_name,
            "law_article": law_article,
            "obligation_type": obl_type,
            "obligation_summary": description or title,
            "cycle_unit": cycle_unit,
            "cycle_value": cycle_value,
            "source": "LEGAL_ENGINE",
            "is_active": True,
        }
        sb.table("inspection_sets").insert(row).execute()
        logger.info(
            "Inspection set created: %s | %s %s", title[:40], law_name, law_article
        )
    except Exception as e:
        logger.warning("Failed to create inspection_set (non-blocking): %s", e)


async def project_rules(
    tenant_id: str,
    facility_id: str,
    matched_rules: list[dict[str, Any]],
    *,
    trace_id: Optional[str] = None,
) -> dict:
    """Convert legal matched_rules into runtime candidates via Binding Engine.

    Also creates inspection_sets for inspection-anchor.html compatibility.
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

        # Bridge: inspection_sets 동시 생성
        _create_inspection_set(
            tenant_id=tenant_id,
            facility_id=facility_id,
            candidate_type=candidate_type,
            title=title[:200],
            description=rule.get("description") or rule.get("rule_text"),
            rule=rule,
        )

    return {
        "candidates": candidates_created,
        "residuals": residuals,
        "stats": {
            "total_rules": len(matched_rules),
            "projected": len(candidates_created),
            "residual": len(residuals),
        },
    }
