"""
routers/matching.py — v1.3.0
전문가 매칭 HTTP 엔드포인트 (비즈니스 로직: services/matching_svc.py)

prefix: /matching  (main.py에서 지정)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from routers.auth import get_current_user
from routers.matching_deps import _require_admin
from schemas.matching import (
    MatchResultCreateBody,
    MatchingRequestBody,
    ProposalBody,
    StatusUpdateBody,
)
from services import matching_svc as ms

router = APIRouter()


def _svc_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ms.MatchingSvcError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/requests")
def create_request(
    body: MatchingRequestBody,
    current_user: dict = Depends(get_current_user),
):
    if not current_user.get("identity_verified"):
        raise HTTPException(status_code=403, detail="본인인증이 필요합니다.")
    return _svc_call(ms.create_matching_request, body, current_user["id"])


@router.get("/requests/my")
def my_requests(
    user_id: str = Query(..., description="회원 UUID"),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    if current_user["id"] != user_id:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    return _svc_call(ms.list_my_requests, user_id, status, page, size)


@router.get("/requests")
def list_requests(
    expert_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="제목 검색"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    return _svc_call(
        ms.list_requests_admin,
        expert_type,
        status,
        source,
        company_id,
        keyword,
        date_from,
        date_to,
        page,
        size,
    )


@router.get("/requests/{request_id}")
def get_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    return _svc_call(
        ms.get_request_detail,
        request_id,
        current_user["id"],
        current_user.get("role_code"),
    )


@router.patch("/requests/{request_id}/status")
def update_status(
    request_id: str,
    body: StatusUpdateBody,
    current_user: dict = Depends(_require_admin),
):
    return _svc_call(ms.update_request_status, request_id, body, current_user["id"])


@router.get("/admin/stats")
def admin_stats(current_user: dict = Depends(_require_admin)):
    return _svc_call(ms.admin_stats_simple)


@router.post("/results/match")
def create_match_result(
    body: MatchResultCreateBody,
    current_user: dict = Depends(_require_admin),
):
    return _svc_call(ms.create_match_result_record, body, current_user["id"])


@router.post("/results/{result_id}/notify")
def notify_expert(
    result_id: str,
    current_user: dict = Depends(_require_admin),
):
    return _svc_call(ms.notify_expert_for_result, result_id)


@router.post("/results/{result_id}/view")
def mark_viewed(
    result_id: str,
    current_user: dict = Depends(get_current_user),
):
    return _svc_call(ms.mark_result_viewed, result_id, current_user["id"])


@router.post("/results/{result_id}/propose")
def submit_proposal(
    result_id: str,
    body: ProposalBody,
    current_user: dict = Depends(get_current_user),
):
    return _svc_call(ms.submit_proposal_for_result, result_id, body, current_user["id"])


@router.get("/requests/{request_id}/proposals")
def list_proposals(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    return _svc_call(
        ms.list_proposals_data,
        request_id,
        current_user.get("role_code"),
        current_user["id"],
    )


@router.post("/results/{result_id}/select")
def select_expert(
    result_id: str,
    current_user: dict = Depends(get_current_user),
):
    return _svc_call(
        ms.select_expert_result,
        result_id,
        current_user["id"],
        current_user.get("role_code"),
    )


@router.get("/my-proposals")
def my_proposals(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    return _svc_call(
        ms.my_proposals_list,
        current_user["id"],
        status,
        page,
        size,
    )


@router.get("/admin/dashboard")
def admin_dashboard(current_user: dict = Depends(_require_admin)):
    return _svc_call(ms.get_dashboard_stats)


@router.get("/admin/pipeline")
def admin_pipeline(
    expert_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    return _svc_call(ms.get_pipeline, expert_type, page, size)
