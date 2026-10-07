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

v1.3.0 (OBJ02-C2A-CORR-14): Full runtime authorization — all document instance endpoints
  require authentication + tenant scope via company_scope helpers.
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, Response
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
from services.document_signature_svc import SignatureError, apply_profile_to_document
from services.document_engine.catalog_resolver import resolve_catalog_runtime_schema
from services.document_engine.renderer import html_to_pdf as _html_to_pdf
from routers.auth import get_current_user
from db.supabase_client import get_supabase
from services.company_scope import (
    _ensure_own_company,
    _ensure_factory_own,
    _forced_company_id,
    require_scope_ids,
    scoped_filter,
    apply_scoped_filter,
    DENY,
)

router = APIRouter(prefix="/document-engine", tags=["문서엔진"])


def _check_doc_scope(sb, doc_id: str, current_user: dict) -> dict:
    """Load runtime_document_data and verify tenant/factory ownership.
    Raises HTTP 404 if not found or out of scope.
    Returns {id, company_id, factory_id, status} dict.
    """
    res = (
        sb.table("runtime_document_data")
        .select("id,company_id,factory_id,status")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "document not found")
    doc = res.data
    _ensure_own_company(
        doc.get("company_id"),
        current_user,
        sb,
        "document not found",
        resource_factory_id=doc.get("factory_id"),
    )
    return doc


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
def create_document(
    body: DocumentCreateIn,
    current_user: dict = Depends(get_current_user),
):
    """문서 생성 (DRAFT 상태)"""
    sb = get_supabase()
    created_by = str(current_user.get("id") or "").strip() or None

    # CORR-19: server-side scope resolution — client-supplied ids not trusted
    scope = require_scope_ids(current_user, sb, ["company_id", "factory_id"])
    company_id = scope.get("company_id")

    # factory_id: FACTORY/TEAM tiers get server-assigned factory; others may opt-in
    factory_id = scope.get("factory_id")
    if factory_id is None and body.factory_id:
        # COMPANY/ALL tier supplying optional factory — verify ownership
        _ensure_factory_own(sb, body.factory_id, current_user)
        factory_id = body.factory_id

    try:
        result = svc.create_document(
            body.form_schema_id,
            factory_id,
            company_id,
            created_by,
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
    current_user: dict = Depends(get_current_user),
):
    """문서 목록 조회"""
    sb = get_supabase()
    filt = scoped_filter(current_user, sb, ["company_id", "factory_id"])
    if filt is DENY:
        return {
            "status": "success",
            "data": {"items": [], "total": 0, "page": page, "page_size": page_size},
        }
    eff_company_id = filt.get("company_id") or company_id
    eff_factory_id = filt.get("factory_id") or factory_id
    result = svc.list_documents(eff_factory_id, eff_company_id, status, page, page_size)
    return {"status": "success", "data": result}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """문서 상세 조회"""
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    result = svc.get_document(doc_id)
    if not result:
        raise HTTPException(404, "document not found")
    return {"status": "success", "data": result}


@router.patch("/documents/{doc_id}")
def update_document(
    doc_id: str,
    body: DocumentUpdateIn,
    current_user: dict = Depends(get_current_user),
):
    """문서 데이터 수정 (runtime_data_json, evidence_links)"""
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    try:
        # CORR-20: updated_by bound to authenticated user, body value ignored
        effective_updated_by = str(current_user.get("id") or "").strip() or None
        result = svc.update_document(
            doc_id,
            body.runtime_data_json,
            body.evidence_links,
            effective_updated_by,
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
    # Scope check — confirm_document_atomic handles its own authz internally
    if body.to_status != "APPROVED_BY_HUMAN":
        _sb = get_supabase()
        _check_doc_scope(_sb, doc_id, current_user)

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

    # 그 외 전이: actor_id bound to authenticated user (CORR-20)
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


@router.get("/transitions")
def list_transitions():
    """허용된 상태 전이 규칙 목록"""
    return {"status": "success", "data": svc.get_transitions()}


# ═══════════════════════════════════════════════════════
# 4. Evidence
# ═══════════════════════════════════════════════════════

@router.post("/documents/{doc_id}/evidence")
def add_evidence(
    doc_id: str,
    body: EvidenceLinkIn,
    current_user: dict = Depends(get_current_user),
):
    """증빙 파일 링크 등록"""
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    result = svc.link_evidence(
        doc_id,
        body.evidence_type,
        body.storage_path,
        body.file_name,
        body.file_size,
        body.mime_type,
        body.linked_field_id,
        str(current_user.get("id") or "").strip() or None,  # CORR-20: server-bound
    )
    return {"status": "success", "data": result}


@router.get("/documents/{doc_id}/evidence")
def list_evidence(doc_id: str, current_user: dict = Depends(get_current_user)):
    """문서의 증빙 목록"""
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    return {"status": "success", "data": svc.list_evidence(doc_id)}


# ═══════════════════════════════════════════════════════
# 5. Generated Document
# ═══════════════════════════════════════════════════════

@router.post("/documents/{doc_id}/generate")
async def generate_document(
    doc_id: str,
    body: GenerateDocumentIn,
    current_user: dict = Depends(get_current_user),
):
    """문서 생성 (입력값만 사용, auto fill 금지).

    CONTRACT D (OBJ02-C2A):
    - Renders canonical HTML via render_document_html() (no InspectionFetcher/TbmFetcher)
    - export_type=PDF: Gotenberg via renderer.html_to_pdf(), returns application/pdf
    - export_type=HTML: returns HTML
    - Transient export: does NOT insert into generated_document table
    """
    export_fmt = (body.export_type or "HTML").upper()
    if export_fmt not in ("HTML", "PDF"):
        raise HTTPException(
            422,
            f"unsupported export_type: {body.export_type!r}; supported: HTML, PDF",
        )

    _check_doc_scope(get_supabase(), doc_id, current_user)

    try:
        html_str = svc.render_document_html(doc_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"render failed: {e}")

    if export_fmt == "PDF":
        try:
            pdf_bytes = await _html_to_pdf(html_str)
        except Exception as e:
            raise HTTPException(500, f"PDF generation failed: {e}")
        return Response(content=pdf_bytes, media_type="application/pdf")

    return HTMLResponse(content=html_str)


@router.get("/documents/{doc_id}/generated")
def list_generated(doc_id: str, current_user: dict = Depends(get_current_user)):
    """생성된 문서 목록"""
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
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


@router.post("/documents/{doc_id}/signature/{field_key}/apply-profile")
def apply_signature(
    doc_id: str,
    field_key: str,
    current_user: dict = Depends(get_current_user),
):
    """Canonical profile signature application endpoint (OBJ02-C2-SIG-B).

    Copies the authenticated user's registered profile signature as an immutable
    snapshot into runtime_data_json[field_key]. The signer_user_id and signed_at
    are set server-side — no client-supplied values are trusted.

    Requires: document in editable status, field_key exists with input_type=signature,
              user has a registered profile signature.
    """
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    try:
        result = apply_profile_to_document(doc_id, field_key, current_user)
        return {"status": "success", "data": result}
    except SignatureError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(404, msg)
        if "forbidden" in msg or "cross-user" in msg:
            raise HTTPException(403, msg)
        if "DOCUMENT_SIGNATURE_CONFLICT" in msg:
            raise HTTPException(409, detail=msg)
        raise HTTPException(400, msg)


@router.get("/documents/{doc_id}/audit-log")
def get_audit_log(doc_id: str, current_user: dict = Depends(get_current_user)):
    """문서 감사 로그"""
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    return {"status": "success", "data": svc.get_audit_log(doc_id)}


# ═══════════════════════════════════════════════════════
# 7. Canonical Render (CONTRACT C, OBJ02-C2A)
# ═══════════════════════════════════════════════════════

@router.get("/documents/{doc_id}/render")
def render_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """Canonical HTML render of runtime document (입력값만, auto fill 금지).

    CONTRACT C (OBJ02-C2A):
    Returns deterministic HTML from runtime_document_data + schema.
    Does NOT call InspectionFetcher or TbmFetcher.
    """
    sb = get_supabase()
    _check_doc_scope(sb, doc_id, current_user)
    try:
        html_str = svc.render_document_html(doc_id)
        return HTMLResponse(content=html_str)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"render failed: {e}")


# ═══════════════════════════════════════════════════════
# 8. Catalog Runtime API (CONTRACT A, OBJ02-C2A)
# ═══════════════════════════════════════════════════════

@router.get("/catalog/{doc_id}")
def get_catalog_runtime(doc_id: str):
    """Catalog + runtime schema state for a given document_forms.doc_id string.

    CONTRACT A (OBJ02-C2A):
    Returns catalog metadata + runtime availability + fields + checklists + evidence_fields.
    can_create=true ONLY when availability==READY_FOR_EDIT.

    Catalog schema metadata is unauthenticated (schema definitions are not tenant-specific).

    Args:
        doc_id: document_forms.doc_id string (e.g. "DOC-BLD-002"), NOT a UUID.
    """
    sb = get_supabase()

    # Lookup document_forms row by doc_id string
    cat_res = (
        sb.table("document_forms")
        .select("id,doc_id,doc_name,sector,category")
        .eq("doc_id", doc_id)
        .execute()
    )
    if not cat_res.data:
        raise HTTPException(404, f"catalog document not found: {doc_id}")
    catalog_row = cat_res.data[0]
    catalog_document_id = catalog_row["id"]  # UUID

    try:
        resolved = resolve_catalog_runtime_schema(catalog_document_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    availability = resolved["availability"]
    can_create = availability == "READY_FOR_EDIT"

    runtime_block = {
        "active_schema_id": resolved.get("active_schema_id"),
        "active_schema_status": resolved.get("active_schema_status"),
        "candidate_schema_id": resolved.get("candidate_schema_id"),
        "candidate_schema_status": resolved.get("candidate_schema_status"),
        "availability": availability,
        "can_create": can_create,
    }

    return {
        "status": "success",
        "data": {
            "catalog": catalog_row,
            "runtime": runtime_block,
            "fields": resolved["fields"],
            "checklists": resolved["checklists"],
            "evidence_fields": resolved["evidence_fields"],
            "supported_export_formats": ["HTML", "PDF"],
        },
    }
