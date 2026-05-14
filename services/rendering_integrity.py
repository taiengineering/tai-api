"""Rendering integrity scan — deterministic rules, no AI."""
from __future__ import annotations

from typing import Any, Optional


def compute_rendering_integrity(
    sections: list[dict[str, Any]],
    evidence_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    for section in sections:
        for field in section.get("fields", []):
            fc = field.get("field_code") or "?"
            if not field.get("source"):
                issues.append(
                    {
                        "severity": "WARNING",
                        "type": "missing_source_mapping",
                        "field": fc,
                    }
                )
            if field.get("required_level") == "MANDATORY" and not field.get("resolved"):
                issues.append(
                    {
                        "severity": "CRITICAL",
                        "type": "mandatory_unresolved",
                        "field": fc,
                    }
                )
            if not field.get("visible", True) and field.get("required_level") == "MANDATORY":
                issues.append(
                    {
                        "severity": "CRITICAL",
                        "type": "hidden_mandatory_field",
                        "field": fc,
                    }
                )
            if field.get("source") and not field.get("resolved") and field.get("required_level") == "OPTIONAL":
                issues.append(
                    {
                        "severity": "WARNING",
                        "type": "render_mismatch",
                        "field": fc,
                        "detail": field.get("resolve_reason"),
                    }
                )

    evs = evidence_summary or {}
    for ev in evs.get("orphan_evidence") or []:
        if isinstance(ev, dict):
            issues.append(
                {
                    "severity": "WARNING",
                    "type": "orphan_evidence",
                    "evidence_id": ev.get("id"),
                    "detail": ev.get("evidence_type"),
                }
            )
        else:
            issues.append(
                {
                    "severity": "WARNING",
                    "type": "orphan_evidence",
                    "evidence_id": ev,
                }
            )

    for fc in evs.get("missing_evidence_fields") or []:
        issues.append(
            {
                "severity": "CRITICAL",
                "type": "missing_evidence",
                "field": fc,
            }
        )

    critical = sum(1 for i in issues if i.get("severity") == "CRITICAL")
    warn = sum(1 for i in issues if i.get("severity") == "WARNING")

    if not issues:
        status = "PASS"
    elif critical:
        status = "CRITICAL"
    else:
        status = "WARNING"

    return {
        "integrity_status": "CLEAN" if not issues else "HAS_ISSUES",
        "rollup_status": status,
        "total_issues": len(issues),
        "critical_count": critical,
        "warning_count": warn,
        "issues": issues[:80],
    }
