"""
routers/document_link_review.py
WO-TAI-DOC-WP03A-LINK-REVIEW-WORKBENCH-001 (read)
WO-TAI-DOC-WP03B-IMPLEMENT-001 (write, CORR-001 applied)
WO-TAI-DOC-WP03B-SIMPLIFY-001 (Owner gate activation)

GET  /api/document-link-review/candidates
GET  /api/document-link-review/candidates/{candidate_id}
POST /api/document-link-review/links
POST /api/document-link-review/links/{id}/submit-review
POST /api/document-link-review/links/{id}/decision
GET  /api/document-link-review/owner-status
GET  /api/document-link-review/links/{id}

Auth: get_current_user + role_code "001" (platform admin only).
Owner gate: TAI_DOC_OWNER_USER_ID env var must be set and match JWT id.
DB writes: via RPC only. No direct INSERT/UPDATE.
"""

from __future__ import annotations

import logging
import os
import uuid as _uuid_mod
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.catalog_aggregator import SupabaseRestClient
from services.document_link_review_read import (
    CandidateDetail,
    CandidatePage,
    CandidateSummary,
    CandidateValidationError,
    get_candidates,
    get_candidate_detail,
    get_csv_class_counts,
    get_link_by_id,
    get_link_audit_history,
    validate_candidate_for_propose,
)
from services.document_link_review_write import (
    DocumentLinkWriteError,
    propose_link,
    transition_link,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/document-link-review",
    tags=["Document link review"],
)

_ADMIN_ROLES = frozenset({"001"})

_VALID_LINK_STATUSES = frozenset({
    "PROPOSED", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETIRED", "NONE",
})
_VALID_RELATION_TYPES = frozenset({
    "SAME_DOCUMENT_CANDIDATE", "AMBIGUOUS", "RELATED_WORKFLOW", "VARIANT",
})
_DB_RELATION_TYPES = frozenset({
    "SAME_DOCUMENT_VERIFIED", "SAME_DOCUMENT_CANDIDATE", "RELATED_FORM",
    "SUPERSEDES", "SUPERSEDED_BY",
})
_WRITE_ERROR_HTTP: dict[str, int] = {
    "DUPLICATE_ACTIVE_PAIR":          409,
    "CONSTRAINT_VIOLATION":           409,
    "GUARD_REJECTED":                 409,
    "INVALID_TRANSITION":             409,
    "LINK_NOT_FOUND":                 404,
    "MALFORMED_RESPONSE":             503,
    "CANDIDATE_NOT_FOUND":            404,
    "CANDIDATE_STALE":                422,
    "CANDIDATE_CANNOT_BE_APPROVED":   422,
    "OWNER_GATE_BLOCKED":             403,
}

_APPROVE_VALID_RELATION_TYPES = frozenset({
    "SAME_DOCUMENT_VERIFIED",
    "RELATED_FORM",
    "SUPERSEDES",
    "SUPERSEDED_BY",
})


def _get_owner_user_id() -> str:
    return os.environ.get("TAI_DOC_OWNER_USER_ID", "").strip()


def _require_owner(user: dict) -> None:
    owner_id = _get_owner_user_id()
    if not owner_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "OWNER_GATE_BLOCKED", "message": "Owner ID가 설정되지 않았습니다."},
        )
    if user.get("id") != owner_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "OWNER_GATE_BLOCKED", "message": "Owner 전용 기능입니다."},
        )


def _generate_owner_approval_ref(actor_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = _uuid_mod.uuid4().hex[:8].upper()
    return f"SYS-UDL-{ts}-{uid}"
_VALID_SORT_FIELDS = frozenset({
    "similarity_score", "saas_title", "ref_title", "relation_type",
})


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role_code") not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "DOCUMENT_LINK_REVIEW_FORBIDDEN",
                "message": "플랫폼 관리자 권한(role_code=001)이 필요합니다.",
            },
        )
    return user


def _serialise_summary(s: CandidateSummary) -> dict[str, Any]:
    return {
        "candidate_id": s.candidate_id,
        "saas_source_code": s.saas_source_code,
        "saas_title": s.saas_title,
        "ref_source_code": s.ref_source_code,
        "ref_title": s.ref_title,
        "similarity_score": s.similarity_score,
        "relation_type": s.relation_type,
        "match_basis": s.match_basis,
        "notes": s.notes,
        "saas_exists": s.saas_exists,
        "ref_exists": s.ref_exists,
        "stale_source": s.stale_source,
        "stale_reason": s.stale_reason,
        "current_link_status": s.current_link_status,
        "active_link_count": s.active_link_count,
    }


def _serialise_detail(d: CandidateDetail) -> dict[str, Any]:
    base = _serialise_summary(d)
    base["saas_document"] = d.saas_document
    base["ref_document"] = d.ref_document
    base["all_links"] = d.all_links
    base["audit_history"] = d.audit_history
    return base


@router.get("/candidates")
def list_candidates(
    q: Optional[str] = Query(None, max_length=200),
    relation_type: Optional[str] = Query(None),
    link_status: Optional[str] = Query(None),
    stale_only: bool = Query(False),
    sort: str = Query("similarity_score"),
    sort_desc: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    List document link review candidates.
    source: data/document_link_candidates.csv (82 rows, read-only snapshot)
    DB: unified_document_link (read-only)
    """
    if relation_type and relation_type not in _VALID_RELATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"relation_type must be one of {sorted(_VALID_RELATION_TYPES)}",
        )
    if link_status and link_status not in _VALID_LINK_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"link_status must be one of {sorted(_VALID_LINK_STATUSES)}",
        )
    if sort not in _VALID_SORT_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"sort must be one of {sorted(_VALID_SORT_FIELDS)}",
        )

    client = SupabaseRestClient()
    try:
        result: CandidatePage = get_candidates(
            client,
            q=q,
            relation_type=relation_type,
            link_status=link_status,
            stale_only=stale_only,
            sort=sort,
            sort_desc=sort_desc,
            page=page,
            per_page=per_page,
        )
    except RuntimeError as exc:
        log.error("document_link_review list error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "total": result.total,
        "page": result.page,
        "per_page": result.per_page,
        "class_counts": result.class_counts,
        "items": [_serialise_summary(s) for s in result.items],
    }


@router.get("/candidates/{candidate_id:path}")
def get_candidate(
    candidate_id: str,
    _user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Candidate detail: CSV data + DB document metadata + link/audit history.
    audit_history and all_links are admin-only — not exposed in public catalog.
    DB: unified_document_link + unified_document_link_audit (read-only)
    """
    client = SupabaseRestClient()
    try:
        detail: Optional[CandidateDetail] = get_candidate_detail(client, candidate_id)
    except RuntimeError as exc:
        log.error("document_link_review detail error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CANDIDATE_NOT_FOUND",
                "message": f"후보 ID '{candidate_id}'를 찾을 수 없습니다.",
            },
        )

    return _serialise_detail(detail)


# ---------------------------------------------------------------------------
# Request models — Write endpoints
# ---------------------------------------------------------------------------

class ProposeLinkRequest(BaseModel):
    candidate_id:  str = Field(..., description="CSV candidate_id ({saas_source_code}__{ref_source_code})")
    relation_type: str = Field(..., description="Must be a valid DB relation_type")
    evidence_note: str = Field(..., min_length=1, description="Evidence supporting this link")


class SubmitReviewRequest(BaseModel):
    review_note: str = Field(
        ..., min_length=1,
        description="검토 근거 — evidence_note에 [REVIEWED:actor:ts] 마커로 append됨.",
    )


class DecisionRequest(BaseModel):
    action: Literal["APPROVE", "REJECT", "RETIRE"] = Field(
        ..., description="APPROVE=UNDER_REVIEW→APPROVED, REJECT=→REJECTED, RETIRE=→RETIRED"
    )
    final_relation_type: Optional[str] = Field(
        None,
        description="APPROVE 시 최종 관계 유형. SAME_DOCUMENT_CANDIDATE인 경우 필수.",
    )


# ---------------------------------------------------------------------------
# Helper: convert DocumentLinkWriteError to HTTPException
# ---------------------------------------------------------------------------

def _get_actor_id(admin: dict) -> str:
    actor_id = admin.get("id") or ""
    if not actor_id:
        raise HTTPException(status_code=503, detail="Actor identity not available")
    return actor_id


def _write_exc(exc: DocumentLinkWriteError) -> HTTPException:
    status = _WRITE_ERROR_HTTP.get(exc.error_code, 422)
    return HTTPException(
        status_code=status,
        detail={"code": exc.error_code, "message": exc.detail or exc.error_code},
    )


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------

@router.post("/links", status_code=201)
def create_link(
    body: ProposeLinkRequest,
    admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Propose a new document link. Creates a PROPOSED row in unified_document_link.
    candidate_id is validated against the CSV snapshot; UUIDs are resolved server-side.
    actor is bound from JWT id (never from request body).
    Auth: 401 no token, 403 role != 001.
    404 if candidate_id not in CSV, 422 if stale/invalid relation_type/empty evidence.
    409 if an active pair already exists.
    """
    if body.relation_type not in _DB_RELATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_RELATION_TYPE",
                "message": f"relation_type must be one of {sorted(_DB_RELATION_TYPES)}",
            },
        )
    actor_id = _get_actor_id(admin)
    rest_client = SupabaseRestClient()
    try:
        saas_uuid, ref_uuid = validate_candidate_for_propose(rest_client, body.candidate_id)
    except CandidateValidationError as exc:
        status = _WRITE_ERROR_HTTP.get(exc.error_code, 422)
        raise HTTPException(
            status_code=status,
            detail={"code": exc.error_code, "message": exc.message},
        )
    except RuntimeError as exc:
        log.error("validate_candidate error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        row = propose_link(
            get_supabase(),
            actor_id=actor_id,
            saas_catalog_id=saas_uuid,
            reference_form_id=ref_uuid,
            relation_type=body.relation_type,
            evidence_note=body.evidence_note,
        )
    except DocumentLinkWriteError as exc:
        raise _write_exc(exc)
    except Exception as exc:
        log.error("propose_link error: %s", exc)
        raise HTTPException(status_code=503, detail="Document link service unavailable")
    return row


@router.post("/links/{link_id}/submit-review", status_code=200)
def submit_review(
    link_id: str,
    body: SubmitReviewRequest,
    admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Advance a PROPOSED link to UNDER_REVIEW.
    body.review_note is required and is appended to evidence_note as [REVIEWED:actor:ts] marker.
    actor is bound from JWT user_id.
    409 if link is not in PROPOSED state or guard rejects.
    404 if link not found.
    """
    actor_id = _get_actor_id(admin)
    try:
        row = transition_link(
            get_supabase(),
            actor_id=actor_id,
            link_id=link_id,
            new_state="UNDER_REVIEW",
            review_note=body.review_note.strip(),
        )
    except DocumentLinkWriteError as exc:
        raise _write_exc(exc)
    except Exception as exc:
        log.error("submit_review error link_id=%r: %s", link_id, exc)
        raise HTTPException(status_code=503, detail="Document link service unavailable")
    return row


@router.get("/owner-status", status_code=200)
def owner_status(
    admin: dict = Depends(_require_admin),
) -> dict[str, bool]:
    """Returns whether the authenticated admin is the designated Owner."""
    owner_id = _get_owner_user_id()
    return {"is_owner": bool(owner_id) and admin.get("id") == owner_id}


@router.post("/links/{link_id}/decision", status_code=200)
def decision(
    link_id: str,
    body: DecisionRequest,
    admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Make a decision on a link. Owner-only (TAI_DOC_OWNER_USER_ID must be set and match JWT id).
    APPROVE: UNDER_REVIEW → APPROVED. Requires final_relation_type if current is SAME_DOCUMENT_CANDIDATE.
    REJECT: PROPOSED or UNDER_REVIEW → REJECTED.
    RETIRE: APPROVED → RETIRED, or REJECTED → RETIRED.
    owner_approval_ref is server-generated; not accepted from client.
    """
    _require_owner(admin)
    actor_id = _get_actor_id(admin)

    rest_client = SupabaseRestClient()
    try:
        link = get_link_by_id(rest_client, link_id)
    except Exception as exc:
        log.error("decision fetch link error link_id=%r: %s", link_id, exc)
        raise HTTPException(status_code=503, detail="Document link service unavailable")

    if link is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "LINK_NOT_FOUND", "message": f"링크를 찾을 수 없습니다: {link_id}"},
        )

    current_state = link.get("review_state", "")

    if body.action == "APPROVE":
        if current_state != "UNDER_REVIEW":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_TRANSITION",
                    "message": f"APPROVE는 UNDER_REVIEW 상태에서만 가능합니다. 현재: {current_state}",
                },
            )
        current_rt = link.get("relation_type", "")
        effective_rt = body.final_relation_type or current_rt
        if effective_rt == "SAME_DOCUMENT_CANDIDATE":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CANDIDATE_CANNOT_BE_APPROVED",
                    "message": "SAME_DOCUMENT_CANDIDATE는 APPROVED 상태로 직접 확정할 수 없습니다. final_relation_type을 지정하세요.",
                },
            )
        if effective_rt not in _APPROVE_VALID_RELATION_TYPES:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_RELATION_TYPE",
                    "message": f"final_relation_type은 {sorted(_APPROVE_VALID_RELATION_TYPES)} 중 하나여야 합니다.",
                },
            )
        evidence = link.get("evidence_note") or ""
        if "[REVIEWED:" not in evidence:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REVIEW_EVIDENCE_REQUIRED",
                    "message": "심사 접수 시 기록된 검토 근거가 없습니다. submit-review를 먼저 실행하세요.",
                },
            )
        owner_ref = _generate_owner_approval_ref(actor_id)
        try:
            row = transition_link(
                get_supabase(),
                actor_id=actor_id,
                link_id=link_id,
                new_state="APPROVED",
                owner_approval_ref=owner_ref,
                final_relation_type=body.final_relation_type,
            )
        except DocumentLinkWriteError as exc:
            raise _write_exc(exc)
        except Exception as exc:
            log.error("decision approve error link_id=%r: %s", link_id, exc)
            raise HTTPException(status_code=503, detail="Document link service unavailable")
        return row

    elif body.action == "REJECT":
        if current_state not in ("PROPOSED", "UNDER_REVIEW"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_TRANSITION",
                    "message": f"REJECT는 PROPOSED 또는 UNDER_REVIEW 상태에서만 가능합니다. 현재: {current_state}",
                },
            )
        try:
            row = transition_link(
                get_supabase(),
                actor_id=actor_id,
                link_id=link_id,
                new_state="REJECTED",
            )
        except DocumentLinkWriteError as exc:
            raise _write_exc(exc)
        except Exception as exc:
            log.error("decision reject error link_id=%r: %s", link_id, exc)
            raise HTTPException(status_code=503, detail="Document link service unavailable")
        return row

    else:  # RETIRE
        if current_state not in ("APPROVED", "REJECTED"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_TRANSITION",
                    "message": f"RETIRE는 APPROVED 또는 REJECTED 상태에서만 가능합니다. 현재: {current_state}",
                },
            )
        owner_ref = _generate_owner_approval_ref(actor_id) if current_state == "APPROVED" else None
        try:
            row = transition_link(
                get_supabase(),
                actor_id=actor_id,
                link_id=link_id,
                new_state="RETIRED",
                owner_approval_ref=owner_ref,
            )
        except DocumentLinkWriteError as exc:
            raise _write_exc(exc)
        except Exception as exc:
            log.error("decision retire error link_id=%r: %s", link_id, exc)
            raise HTTPException(status_code=503, detail="Document link service unavailable")
        return row


@router.get("/links/{link_id}", status_code=200)
def get_link_detail(
    link_id: str,
    admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Return a unified_document_link row with its full audit history.
    404 if link not found.
    """
    client = SupabaseRestClient()
    try:
        link = get_link_by_id(client, link_id)
    except Exception as exc:
        log.error("get_link_detail fetch error link_id=%r: %s", link_id, exc)
        raise HTTPException(status_code=503, detail="Document link service unavailable")

    if link is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "LINK_NOT_FOUND", "message": f"링크를 찾을 수 없습니다: {link_id}"},
        )

    try:
        audit = get_link_audit_history(client, link_id)
    except Exception as exc:
        log.error("get_link_detail audit error link_id=%r: %s", link_id, exc)
        raise HTTPException(status_code=503, detail="Document link service unavailable")

    return {**link, "audit_history": audit}
