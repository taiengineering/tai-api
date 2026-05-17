"""SaaS 반복설정 API.

SaaS는 자동 의무등록기가 아니다.
진단 결과 중 반복관리 후보를 승인받아 운영설정까지 한다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter(prefix='/api/v1/saas-setup', tags=['SaaS 반복설정'])


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''),
                         os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))


class ApproveRequest(BaseModel):
    user_id: Optional[str] = None

class RejectRequest(BaseModel):
    reason: Optional[str] = None


# ── 후보 추출 ──

@router.post('/extract/{session_id}')
async def extract_setup_candidates(session_id: str):
    """진단 결과에서 반복관리 후보 추출. 자동 등록 안 함."""
    from services.saas_setup_service import SaaSSetupService
    try:
        return SaaSSetupService.extract_setup_candidates(_get_sb(), session_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── 후보 목록 ──

@router.get('/candidates')
async def list_candidates(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    from services.saas_setup_service import SaaSSetupService
    return SaaSSetupService.list_candidates(_get_sb(), session_id, status, limit)


# ── 승인 ──

@router.post('/approve/{setup_id}')
async def approve_setup(setup_id: str, body: ApproveRequest):
    """사용자 승인. 승인 후에만 Runtime 등록 가능."""
    from services.saas_setup_service import SaaSSetupService
    try:
        return SaaSSetupService.approve(_get_sb(), setup_id, body.user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── 거절 ──

@router.post('/reject/{setup_id}')
async def reject_setup(setup_id: str, body: RejectRequest):
    from services.saas_setup_service import SaaSSetupService
    try:
        return SaaSSetupService.reject(_get_sb(), setup_id, body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── 추가 데이터 요청 ──

@router.post('/needs-data/{setup_id}')
async def needs_more_data(setup_id: str):
    from services.saas_setup_service import SaaSSetupService
    try:
        return SaaSSetupService.request_more_data(_get_sb(), setup_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Runtime 등록 (승인된 것만) ──

@router.post('/register/{setup_id}')
async def register_to_runtime(setup_id: str, body: ApproveRequest):
    """승인된 항목만 Runtime에 등록. rollback 가능."""
    from services.saas_setup_service import SaaSSetupService
    try:
        return SaaSSetupService.register_to_runtime(_get_sb(), setup_id, body.user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
