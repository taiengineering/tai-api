"""
routers/document_link_review.py
WO-TAI-DOC-WP03A-LINK-REVIEW-WORKBENCH-001

GET /api/document-link-review/candidates
GET /api/document-link-review/candidates/{candidate_id}

Auth: get_current_user + role_code "001" (platform admin only).
DB writes: 0.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from routers.auth import get_current_user
from services.catalog_aggregator import SupabaseRestClient
from services.document_link_review_read import (
    CandidateDetail,
    CandidatePage,
    CandidateSummary,
    get_candidates,
    get_candidate_detail,
    get_csv_class_counts,
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
