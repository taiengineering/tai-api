"""TAI 문서엔진 API v1.0.0

Prefix: /document-engine
Guardrails:
  - 상태 전이는 runtime_state_transition_rule 기준만
  - APPROVED_BY_HUMAN 시 reviewer_id 필수
  - review_comment 필수 (REJECT/RETURN)
  - 모든 상태 변경 audit log 기록
  - generated_document는 입력된 값만 사용
  - 누락값은 빈 값 유지
  - evidence는 실제 파일만
  - source_trace 항상 유지

v1.1.0 (WP-DOCUMENT-ARCH-05B-B1): APPROVED_BY_HUMAN 전이를 인증·인가·원자 트랜잭션으로
  강제한다. status route 에 get_current_user 를 부착하고, to_status==APPROVED_BY_HUMAN 은
  confirm_document_atomic() 로 분기한다. 나머지 전이는 기존 svc.change_status() 유지.

v1.2.0 (WP-DOCUMENT-ARCH-05B-B1-CORR-01): SUBMITTED_FOR_REVIEW 도 submitted_by 를
  반드시 인증 사용자로 기록한다(위조 차단). Confirm 권한은 제출자 본인.
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from schemas.document_engine import (
    DocumentCreateIn,
    DocumentUpdateIn,
    StatusChangeIn,
    EvidenceLinkIn,
    GenerateDocumentIn,
)
from services import document_engine_svc as svc
from services.document_confirm_svc import confirm_document_atomic, ConfirmError
from routers.auth import get_current_user

router = APIRouter(prefix="/document-engine", tags=["문서엔진"])


# ═══════════════════════════════════════════════════════
# 1. Runtime Form Schema
# ═══════════════════════════════════════════════════════

@router.get("/schemas")
def list_schemas(
    document_family: Optional[str] = Query(None),
    form_type: Optional[str] = Query(
        None, description="OFFICIAL|CUSTOM|INTERNAL"
    ),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Runtime Form Schema 목록 조회"""
    result = svc.list_form_schemas(
        document_family, form_type, status, page, page_size
    )
    return {"status": "success", "data": result}


@router.get("/schemas/{schema_id}")
def get_schema_detail(schema_id: str):
    """Schema 상세: fields + checklists + evidence_fields"""
    result = svc.get_form_schema_detail(schema_id)
    if not result:
        raise HTTPException(404, "schema not found")
    return {"status": "success", "data": result}


# ═══════════════════════════════════════════════════════
# 2. Runtime Document CRUD
# ═══════════════════════════════════════════════════════

@router.post("/documents")
def create_document(body: DocumentCreateIn):
    """문서 생성 (DRAFT 상태)"""
    try:
        result = svc.create_document(
            body.form_schema_id,
            body.factory_id,
            body.company_id,
            body.created_by,
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/documents")
def list_documents(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """문서 목록 조회"""
    result = svc.list_documents(
        factory_id, company_id, status, page, page_size
    )
    return {"status": "success", "data": result}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str):
    """문서 상세 조회"""
    result = svc.get_document(doc_id)
    if not result:
        raise HTTPException(404, "document not found")
    return {"status": "success", "data": result}


@router.patch("/documents/{doc_id}")
def update_document(doc_id: str, body: DocumentUpdateIn):
    """문서 데이터 수정 (runtime_data_json, evidence_links)"""
    try:
        result = svc.update_document(
            doc_id,
            body.runtime_data_json,
            body.evidence_links,
            body.updated_by,
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════
# 3. 상태 전이
# ═══════════════════════════════════════════════════════

@router.post("/documents/{doc_id}/status")
def change_status(
    doc_id: str,
    body: StatusChangeIn,
    current_user: dict = Depends(get_current_user),
):
    """상태 전이 — runtime_state_transition_rule 기준만 허용.

    APPROVED_BY_HUMAN 은 인증·인가·원자 트랜잭션(confirm_document_atomic)으로 처리한다.
    승인 전에 get_document/PostgREST ownership/scope 사전조회를 하지 않는다(TOCTOU 방지) —
    모든 판정은 트랜잭션 내부에서 SELECT ... FOR UPDATE 이후 값으로 이뤄진다.

    SUBMITTED_FOR_REVIEW 는 submitted_by 를 반드시 인증 사용자로 기록한다
    (body.actor_id 사칭 차단). Confirm(APPROVED_BY_HUMAN)은 제출자 본인만 가능하므로,
    제출 시점의 submitted_by 위조를 막는 것이 확정 권한 무결성의 전제다.
    """
    if body.to_status == "SUBMITTED_FOR_REVIEW":
        # submitter identity binding — svc 는 그대로 두고 라우터가 인증 actor 만 전달.
        user_id = str(current_user.get("id") or "").strip()
        if not user_id:
            raise HTTPException(401, "authenticated user identity unavailable")
        if body.actor_id is not None and str(body.actor_id) != user_id:
            raise HTTPException(403, "actor_id does not match authenticated user")
        try:
            result = svc.change_status(
                doc_id, body.to_status, user_id, body.comment
            )
            return {"status": "success", "data": result}
        except ValueError as e:
            raise HTTPException(400, str(e))

    if body.to_status == "APPROVED_BY_HUMAN":
        try:
            result = confirm_document_atomic(
                doc_id,
                actor_id=body.actor_id,
                comment=body.comment,
                current_user=current_user,
            )
            return {"status": "success", "data": result}
        except ConfirmError as e:
            raise HTTPException(e.http_status, e.detail)

    # 그 외 전이는 기존 경로 유지
    try:
        result = svc.change_status(
            doc_id, body.to_status, body.actor_id, body.comment
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/transitions")
def list_transitions():
    """허용된 상태 전이 규칙 목록"""
    return {"status": "success", "data": svc.get_transitions()}


# ═══════════════════════════════════════════════════════
# 4. Evidence
# ═══════════════════════════════════════════════════════

@router.post("/documents/{doc_id}/evidence")
def add_evidence(doc_id: str, body: EvidenceLinkIn):
    """증빙 파일 링크 등록"""
    doc = svc.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    result = svc.link_evidence(
        doc_id,
        body.evidence_type,
        body.storage_path,
        body.file_name,
        body.file_size,
        body.mime_type,
        body.linked_field_id,
        body.uploaded_by,
    )
    return {"status": "success", "data": result}


@router.get("/documents/{doc_id}/evidence")
def list_evidence(doc_id: str):
    """문서의 증빙 목록"""
    return {"status": "success", "data": svc.list_evidence(doc_id)}


# ═══════════════════════════════════════════════════════
# 5. Generated Document
# ═══════════════════════════════════════════════════════

@router.post("/documents/{doc_id}/generate")
def generate_document(doc_id: str, body: GenerateDocumentIn):
    """문서 생성 (입력값만 사용, auto fill 금지)"""
    try:
        result = svc.generate_document(doc_id, body.export_type)
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/documents/{doc_id}/generated")
def list_generated(doc_id: str):
    """생성된 문서 목록"""
    return {"status": "success", "data": svc.list_generated(doc_id)}


# ═══════════════════════════════════════════════════════
# 6. Metrics & Audit
# ═══════════════════════════════════════════════════════

@router.get("/metrics")
def get_metrics():
    """전체 Runtime 메트릭"""
    return {"status": "success", "data": svc.get_metrics()}


@router.get("/metrics/factory/{factory_id}")
def get_factory_metrics(factory_id: str):
    """시설별 메트릭"""
    return {
        "status": "success",
        "data": svc.get_metrics_by_factory(factory_id),
    }


@router.get("/documents/{doc_id}/audit-log")
def get_audit_log(doc_id: str):
    """문서 감사 로그"""
    return {"status": "success", "data": svc.get_audit_log(doc_id)}
