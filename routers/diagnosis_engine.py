"""법령진단서비스 API.

법령진단은 '결과 출력'까지 한다.
반복설정/스케줄/업무/위반을 확정하지 않는다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os

router = APIRouter(prefix='/api/v1/diagnosis-engine', tags=['법령진단서비스'])


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''),
                         os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))


class DiagnosisRequest(BaseModel):
    factory_id: str
    input_data: Dict[str, Any] = {}


# ── 법령진단 실행 ──

@router.post('/evaluate')
async def evaluate_facility(body: DiagnosisRequest):
    """법령진단 실행. Candidate 결과만 출력. 반복설정 등록 안 함."""
    from services.diagnosis_service import DiagnosisService
    try:
        sb = _get_sb()
        result = DiagnosisService.evaluate(sb, body.factory_id, body.input_data)
        session_id = result['diagnosis_id']
        try:
            from services.saas_setup_service import SaaSSetupService
            SaaSSetupService.extract_setup_candidates(sb, session_id)
        except Exception as _saas_err:
            import logging
            logging.getLogger("saas.setup.hook").warning(
                "SaaS setup extract hook failed (non-blocking): %s", _saas_err
            )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get('/session/{session_id}')
async def get_session(session_id: str):
    """진단 세션 상세 조회."""
    from services.diagnosis_service import DiagnosisService
    result = DiagnosisService.get_session(_get_sb(), session_id)
    if not result:
        raise HTTPException(404, 'Session not found')
    return result


@router.get('/sessions')
async def list_sessions(factory_id: Optional[str] = None, limit: int = 20):
    """진단 세션 목록."""
    from services.diagnosis_service import DiagnosisService
    return DiagnosisService.list_sessions(_get_sb(), factory_id, limit)
