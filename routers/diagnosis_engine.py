"""법령진단서비스 API. 결과 출력까지만."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os

router = APIRouter(prefix='/api/v1/diagnosis-engine', tags=['법령진단서비스'])

def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''), os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))

class DiagnosisRequest(BaseModel):
    factory_id: str
    input_data: Dict[str, Any] = {}

@router.post('/evaluate')
async def evaluate_facility(body: DiagnosisRequest):
    from services.diagnosis_service import DiagnosisService
    try: return DiagnosisService.evaluate(_get_sb(), body.factory_id, body.input_data)
    except Exception as e: raise HTTPException(500, str(e))

@router.get('/session/{session_id}')
async def get_session(session_id: str):
    from services.diagnosis_service import DiagnosisService
    result = DiagnosisService.get_session(_get_sb(), session_id)
    if not result: raise HTTPException(404, 'Not found')
    return result

@router.get('/sessions')
async def list_sessions(factory_id: Optional[str] = None, limit: int = 20):
    from services.diagnosis_service import DiagnosisService
    return DiagnosisService.list_sessions(_get_sb(), factory_id, limit)
