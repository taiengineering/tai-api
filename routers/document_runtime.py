"""document_runtime.py — Runtime Document Payload API (PHASE F)

PDF 생성이 아니라 Runtime Document Projection 반환.

WP-SEC0-B: 전 엔드포인트 인증 게이트 + facility_id 소유권 검증 (fail-closed).
  - get_current_user Depends 모든 라우트 적용
  - facility_id 미제공: 인증된 사용자 통과 (빈 context 유지)
  - facility_id 제공 시: runtime_facility_profile 존재 확인 (없으면 403);
    소유권 검증 경로 없음 → FACILITY_OWNERSHIP_MAPPING=BLOCKED (503 반환).
    근거: 운영 DB 실측 — runtime_facility_profile.id ≠ factories.id (0/50건 일치).
    factories 연결 경로 확보 후 Owner 승인 시 구현 예정.
  - POST /render context: facility_id만 신뢰, 나머지 키 제거 (신뢰하지 않음)
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.runtime_binding_resolver import resolve_document_runtime
from services.conditional_rendering_resolver import resolve_conditional_fields
from services.field_completeness_engine import (
    evaluate_field_completeness, calculate_document_completeness
)
from services.evidence_binding_engine import (
    get_evidence_for_document, bind_evidence_to_fields
)

router = APIRouter(prefix="/document-runtime", tags=["Document Runtime"])


def _validate_facility_ownership(facility_id: str, current_user: dict) -> None:
    """facility_id → runtime_facility_profile 존재 확인 후 소유권 검증.

    소유권 검증 경로 없음 (FACILITY_OWNERSHIP_MAPPING=BLOCKED):
      운영 DB 실측 결과 runtime_facility_profile.id ≠ factories.id (0/50건 일치).
      factories/companies 연결 컬럼이 runtime_facility_profile에 없으므로
      ownership을 검증할 수 없음 → fail-closed (503).
    facility 미존재 → 403 (존재 숨김).
    """
    sb = get_supabase()
    result = sb.table("runtime_facility_profile").select("id").eq(
        "id", facility_id
    ).limit(1).execute()
    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="facility를 찾을 수 없거나 접근 권한이 없습니다",
        )
    # FACILITY_OWNERSHIP_MAPPING=BLOCKED: runtime_facility_profile과 factories 간
    # 소유권 검증 경로 미확인. Owner 승인 후 구현 예정.
    raise HTTPException(
        status_code=503,
        detail=(
            "FACILITY_OWNERSHIP_MAPPING=BLOCKED: 시설 소유권 검증 경로 미확인. "
            "runtime_facility_profile과 factories 간 연결 컬럼 부재. "
            "Owner 승인 후 구현 예정."
        ),
    )


@router.get("/{document_type}")
async def get_runtime_document(
    document_type: str,
    facility_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Runtime Document Projection 반환"""
    if facility_id:
        _validate_facility_ownership(facility_id, current_user)

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
async def render_runtime_document(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Runtime context 기반 문서 렌더링"""
    document_type = body.get("document_type")
    if not document_type:
        raise HTTPException(400, "document_type required")

    # context는 신뢰하지 않음 — facility_id만 허용, 나머지 키 제거
    raw_context = body.get("context", {})
    raw_context = raw_context if isinstance(raw_context, dict) else {}
    facility_id = raw_context.get("facility_id")
    if facility_id:
        _validate_facility_ownership(facility_id, current_user)
    context = {"facility_id": facility_id} if facility_id else {}

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
    current_user: dict = Depends(get_current_user),
):
    """Field-level completeness summary"""
    if facility_id:
        _validate_facility_ownership(facility_id, current_user)

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
    current_user: dict = Depends(get_current_user),
):
    """Evidence binding summary"""
    if facility_id:
        _validate_facility_ownership(facility_id, current_user)

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
    current_user: dict = Depends(get_current_user),
):
    """Rendering Integrity Verification (PHASE G)"""
    if facility_id:
        _validate_facility_ownership(facility_id, current_user)

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
