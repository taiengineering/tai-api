"""SaaS 반복설정 API. 승인 후 운영설정까지만."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter(prefix='/api/v1/saas-setup', tags=['SaaS 반복설정'])

def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''), os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))

class ApproveRequest(BaseModel):
    user_id: Optional[str] = None
class RejectRequest(BaseModel):
    reason: Optional[str] = None

@router.post('/extract/{session_id}')
async def extract(session_id: str):
    from services.saas_setup_service import SaaSSetupService
    try: return SaaSSetupService.extract_setup_candidates(_get_sb(), session_id)
    except ValueError as e: raise HTTPException(400, str(e))

@router.get('/candidates')
async def list_candidates(session_id: Optional[str]=None, status: Optional[str]=None, limit: int=50):
    from services.saas_setup_service import SaaSSetupService
    return SaaSSetupService.list_candidates(_get_sb(), session_id, status, limit)

@router.post('/approve/{setup_id}')
async def approve(setup_id: str, body: ApproveRequest):
    from services.saas_setup_service import SaaSSetupService
    try: return SaaSSetupService.approve(_get_sb(), setup_id, body.user_id)
    except ValueError as e: raise HTTPException(400, str(e))

@router.post('/reject/{setup_id}')
async def reject(setup_id: str, body: RejectRequest):
    from services.saas_setup_service import SaaSSetupService
    try: return SaaSSetupService.reject(_get_sb(), setup_id, body.reason)
    except ValueError as e: raise HTTPException(400, str(e))

@router.post('/needs-data/{setup_id}')
async def needs_data(setup_id: str):
    from services.saas_setup_service import SaaSSetupService
    try: return SaaSSetupService.request_more_data(_get_sb(), setup_id)
    except ValueError as e: raise HTTPException(400, str(e))

@router.post('/register/{setup_id}')
async def register(setup_id: str, body: ApproveRequest):
    from services.saas_setup_service import SaaSSetupService
    try: return SaaSSetupService.register_to_runtime(_get_sb(), setup_id, body.user_id)
    except ValueError as e: raise HTTPException(400, str(e))
