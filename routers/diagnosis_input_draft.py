"""유료진단 상세입력 단계별 임시저장 API.

결제 완료 후 시설→공정→설비 입력을 단계별로 저장/복원한다.
진단 전용 구조를 새로 만들지 않고, 최종 제출 시 데이터는
factory_process / equipment_assets (SaaS 동일 구조)로 이관된다.

저장 단위: (user_id, order_id) 1건 = 진단 1회.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os

router = APIRouter(prefix='/diagnosis/draft', tags=['진단 상세입력 임시저장'])


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL', ''),
                         os.environ.get('SUPABASE_SERVICE_ROLE_KEY', ''))


class DraftSaveRequest(BaseModel):
    user_id: str
    order_id: Optional[str] = None
    sector: str
    tier_code: Optional[str] = None
    current_step: Optional[str] = None          # FACILITY | PROCESS | EQUIPMENT | DONE
    facility_data: Optional[Dict[str, Any]] = None
    process_data: Optional[Dict[str, Any]] = None
    equipment_data: Optional[Dict[str, Any]] = None


# ── 임시저장 (단계 저장, upsert) ──

@router.post('/save')
async def save_draft(body: DraftSaveRequest):
    """현재 단계까지의 입력을 임시저장. (user_id, order_id) 기준 upsert.

    전달된 *_data 만 갱신하고 나머지는 보존한다.
    """
    sb = _get_sb()
    try:
        q = sb.table('diagnosis_input_draft').select('*').eq('user_id', body.user_id)
        if body.order_id:
            q = q.eq('order_id', body.order_id)
        else:
            q = q.is_('order_id', 'null')
        existing = q.limit(1).execute()

        patch: Dict[str, Any] = {'sector': body.sector, 'updated_at': 'now()'}
        if body.tier_code is not None:
            patch['tier_code'] = body.tier_code
        if body.current_step is not None:
            patch['current_step'] = body.current_step
        if body.facility_data is not None:
            patch['facility_data'] = body.facility_data
        if body.process_data is not None:
            patch['process_data'] = body.process_data
        if body.equipment_data is not None:
            patch['equipment_data'] = body.equipment_data

        if existing.data:
            row_id = existing.data[0]['id']
            res = sb.table('diagnosis_input_draft').update(patch).eq('id', row_id).execute()
            saved = res.data[0] if res.data else existing.data[0]
        else:
            patch['user_id'] = body.user_id
            patch['order_id'] = body.order_id
            patch.setdefault('current_step', 'FACILITY')
            res = sb.table('diagnosis_input_draft').insert(patch).execute()
            saved = res.data[0] if res.data else {}

        return {'status': 'success', 'data': saved}
    except Exception as e:
        raise HTTPException(500, f'임시저장 실패: {e}')


# ── 임시저장 불러오기 ──

@router.get('/load')
async def load_draft(user_id: str, order_id: Optional[str] = None):
    """저장된 임시입력 복원. 없으면 data=null."""
    sb = _get_sb()
    try:
        q = sb.table('diagnosis_input_draft').select('*').eq('user_id', user_id)
        if order_id:
            q = q.eq('order_id', order_id)
        res = q.order('updated_at', desc=True).limit(1).execute()
        return {'status': 'success', 'data': (res.data[0] if res.data else None)}
    except Exception as e:
        raise HTTPException(500, f'불러오기 실패: {e}')


# ── 제출(최종 확정) — 상태만 SUBMITTED 로 전환 ──
# 실제 factory_process / equipment_assets 이관은 후속 단계에서 연결.

@router.post('/submit')
async def submit_draft(body: DraftSaveRequest):
    """3단계 입력 완료 후 제출 상태로 전환."""
    sb = _get_sb()
    try:
        q = sb.table('diagnosis_input_draft').select('id').eq('user_id', body.user_id)
        if body.order_id:
            q = q.eq('order_id', body.order_id)
        existing = q.limit(1).execute()
        if not existing.data:
            raise HTTPException(404, '임시저장된 입력을 찾을 수 없습니다')
        row_id = existing.data[0]['id']
        res = sb.table('diagnosis_input_draft').update(
            {'status': 'SUBMITTED', 'current_step': 'DONE', 'updated_at': 'now()'}
        ).eq('id', row_id).execute()
        return {'status': 'success', 'data': (res.data[0] if res.data else {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f'제출 실패: {e}')
