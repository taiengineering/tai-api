"""document_runtime.py — Runtime Document Payload API (PHASE F)

PDF 생성이 아니라 Runtime Document Projection 반환.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Any, Optional

from services.runtime_binding_resolver import resolve_document_runtime
from services.conditional_rendering_resolver import resolve_conditional_fields
from services.field_completeness_engine import (
    calculate_document_completeness,
)
from services.evidence_binding_engine import (
    get_evidence_for_document,
    bind_evidence_to_fields,
)
from services.runtime_document_context import build_runtime_context
from services.rendering_integrity import compute_rendering_integrity

router = APIRouter(prefix="/document-runtime", tags=["Document Runtime"])


def _hydrate_runtime_payload(document_type: str, context: dict[str, Any]) -> dict[str, Any]:
    """스키마 resolve → 조건부 필드 → completeness → evidence → integrity."""
    payload = resolve_document_runtime(document_type, context)
    if "error" in payload:
        return payload

    for section in payload.get("sections", []):
        section["fields"] = resolve_conditional_fields(section["fields"], context)

    evidence_list = get_evidence_for_document(document_type, context)
    evidence_summary = bind_evidence_to_fields(payload.get("sections", []), evidence_list)
    payload["evidence_summary"] = evidence_summary

    completeness = calculate_document_completeness(payload.get("sections", []))
    payload["completeness"] = completeness

    payload["rendering_integrity"] = compute_rendering_integrity(
        payload.get("sections", []),
        evidence_summary,
    )
    return payload


@router.get("/{document_type}")
async def get_runtime_document(
    document_type: str,
    facility_id: Optional[str] = Query(None),
):
    """Runtime Document Projection 반환 (evidence·integrity 포함)."""
    context = build_runtime_context(facility_id, None)
    payload = _hydrate_runtime_payload(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    return payload


@router.post("/render")
async def render_runtime_document(body: dict = Body(...)):
    """Runtime context 기반 문서 렌더링 — context overrides로 조건 시뮬레이션 가능."""
    facility_id = body.get("facility_id") or (body.get("context") or {}).get("facility_id")
    overrides = dict(body.get("context") or {})
    overrides.pop("facility_id", None)
    document_type = body.get("document_type")

    if not document_type:
        raise HTTPException(400, "document_type required")

    context = build_runtime_context(facility_id, overrides)
    payload = _hydrate_runtime_payload(document_type, context)
    if "error" in payload:
        raise HTTPException(404, payload["error"])

    return payload


@router.get("/completeness/{document_type}")
async def get_completeness(
    document_type: str,
    facility_id: Optional[str] = Query(None),
):
    """Field-level completeness summary"""
    context = build_runtime_context(facility_id, None)
    payload = resolve_document_runtime(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    for section in payload.get("sections", []):
        section["fields"] = resolve_conditional_fields(section["fields"], context)

    evidence_list = get_evidence_for_document(document_type, context)
    bind_evidence_to_fields(payload.get("sections", []), evidence_list)

    completeness = calculate_document_completeness(payload.get("sections", []))

    return {
        "document_type": document_type,
        "completeness": completeness,
    }


@router.get("/evidence-binding/{document_type}")
async def get_evidence_binding(
    document_type: str,
    facility_id: Optional[str] = Query(None),
):
    """Evidence binding summary"""
    context = build_runtime_context(facility_id, None)
    payload = resolve_document_runtime(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    for section in payload.get("sections", []):
        section["fields"] = resolve_conditional_fields(section["fields"], context)

    evidence_list = get_evidence_for_document(document_type, context)
    evidence_summary = bind_evidence_to_fields(payload.get("sections", []), evidence_list)

    return {
        "document_type": document_type,
        "evidence": evidence_summary,
    }


@router.get("/integrity/{document_type}")
async def check_rendering_integrity(
    document_type: str,
    facility_id: Optional[str] = Query(None),
):
    """Rendering Integrity Verification"""
    context = build_runtime_context(facility_id, None)
    payload = _hydrate_runtime_payload(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    ri = payload.get("rendering_integrity") or {}
    return {
        "document_type": document_type,
        "total_issues": ri.get("total_issues", 0),
        "integrity_status": ri.get("integrity_status"),
        "rollup_status": ri.get("rollup_status"),
        "critical_count": ri.get("critical_count", 0),
        "warning_count": ri.get("warning_count", 0),
        "issues": ri.get("issues", []),
    }
