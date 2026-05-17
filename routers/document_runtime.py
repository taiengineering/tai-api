"""document_runtime.py — Runtime Document Payload API (PHASE F)

PDF 생성이 아니라 Runtime Document Projection 반환.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db.supabase_client import get_supabase
from services.runtime_binding_resolver import resolve_document_runtime
from services.conditional_rendering_resolver import resolve_conditional_fields
from services.field_completeness_engine import (
    evaluate_field_completeness, calculate_document_completeness
)
from services.evidence_binding_engine import (
    get_evidence_for_document, bind_evidence_to_fields
)

router = APIRouter(prefix="/document-runtime", tags=["Document Runtime"])


@router.get("/{document_type}")
async def get_runtime_document(
    document_type: str,
    facility_id: Optional[str] = Query(None),
):
    """Runtime Document Projection 반환"""
    context = {"facility_id": facility_id} if facility_id else {}
    payload = resolve_document_runtime(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    # PHASE C: conditional rendering
    for section in payload.get("sections", []):
        section["fields"] = resolve_conditional_fields(
            section["fields"], context
        )

    # PHASE D: completeness
    completeness = calculate_document_completeness(payload.get("sections", []))
    payload["completeness"] = completeness

    return payload


@router.post("/render")
async def render_runtime_document(body: dict):
    """Runtime context 기반 문서 렌더링"""
    document_type = body.get("document_type")
    context = body.get("context", {})

    if not document_type:
        raise HTTPException(400, "document_type required")

    payload = resolve_document_runtime(document_type, context)
    if "error" in payload:
        raise HTTPException(404, payload["error"])

    for section in payload.get("sections", []):
        section["fields"] = resolve_conditional_fields(section["fields"], context)

    completeness = calculate_document_completeness(payload.get("sections", []))
    payload["completeness"] = completeness

    # evidence binding
    evidence_list = get_evidence_for_document(document_type, context)
    evidence_summary = bind_evidence_to_fields(payload.get("sections", []), evidence_list)
    payload["evidence_summary"] = evidence_summary

    return payload


@router.get("/completeness/{document_type}")
async def get_completeness(
    document_type: str,
    facility_id: Optional[str] = Query(None),
):
    """Field-level completeness summary"""
    context = {"facility_id": facility_id} if facility_id else {}
    payload = resolve_document_runtime(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    for section in payload.get("sections", []):
        section["fields"] = resolve_conditional_fields(section["fields"], context)

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
    context = {"facility_id": facility_id} if facility_id else {}
    payload = resolve_document_runtime(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

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
    """Rendering Integrity Verification (PHASE G)"""
    context = {"facility_id": facility_id} if facility_id else {}
    payload = resolve_document_runtime(document_type, context)

    if "error" in payload:
        raise HTTPException(404, payload["error"])

    issues = []
    for section in payload.get("sections", []):
        for field in section.get("fields", []):
            # orphan field (no source)
            if not field.get("source"):
                issues.append({"type": "missing_source_mapping", "field": field["field_code"]})
            # render null mismatch
            if field.get("required_level") == "MANDATORY" and not field.get("resolved"):
                issues.append({"type": "mandatory_unresolved", "field": field["field_code"]})
            # hidden mandatory
            if not field.get("visible", True) and field.get("required_level") == "MANDATORY":
                issues.append({"type": "hidden_mandatory_field", "field": field["field_code"]})

    return {
        "document_type": document_type,
        "total_issues": len(issues),
        "integrity_status": "CLEAN" if not issues else "HAS_ISSUES",
        "issues": issues[:50],
    }
