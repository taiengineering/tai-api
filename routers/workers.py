"""작업자 관리 라우터 — WORKER-01.
작업자 등록/초대/목록/수정. worker_registry 테이블 기반.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from db.supabase_client import get_supabase

router = APIRouter(prefix="/workers", tags=["작업자"])


def _now():
    return datetime.now(timezone.utc).isoformat()


class WorkerInviteBody(BaseModel):
    factory_id: str
    company_id: str
    name: str
    phone: str
    job_type_code: Optional[str] = None
    job_type_name: Optional[str] = None
    department: Optional[str] = None
    contractor_name: Optional[str] = None
    created_by: Optional[str] = None


class WorkerPatchBody(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    job_type_code: Optional[str] = None
    job_type_name: Optional[str] = None
    contractor_name: Optional[str] = None
    is_active: Optional[bool] = None
    status_code: Optional[str] = None
    push_token: Optional[str] = None
    app_installed: Optional[bool] = None


@router.post("/invite")
def invite_worker(body: WorkerInviteBody):
    """작업자 초대 — worker_registry INSERT + SMS 발송."""
    sb = get_supabase()
    now = _now()

    # 중복 확인 (같은 사업장 + 전화번호)
    existing = sb.table('worker_registry').select('id').eq(
        'factory_id', body.factory_id
    ).eq('phone', body.phone).eq('is_active', True).execute()
    if existing.data:
        raise HTTPException(409, '이미 등록된 작업자입니다.')

    row = {
        'factory_id': body.factory_id,
        'company_id': body.company_id,
        'name': body.name,
        'phone': body.phone,
        'job_type_code': body.job_type_code,
        'job_type_name': body.job_type_name,
        'department': body.department,
        'contractor_name': body.contractor_name,
        'status_code': 'INVITED',
        'is_active': True,
        'app_installed': False,
        'invite_sent_at': now,
        'created_by': body.created_by,
        'created_at': now,
        'updated_at': now,
    }
    r = sb.table('worker_registry').insert(row).execute()
    if not r.data:
        raise HTTPException(500, '작업자 등록 실패')

    worker = r.data[0]

    # SMS 초대 발송 시도
    sms_sent = False
    try:
        factory = sb.table('factories').select(
            'name'
        ).eq('id', body.factory_id).limit(1).execute()
        fname = factory.data[0]['name'] if factory.data else '사업장'
        # 메세지미 SMS 발송 (기존 연동 활용)
        from services.inbox_notify_svc import send_sms_via_messagemi
        send_sms_via_messagemi(
            phone=body.phone,
            message=(
                f'[TAI Safe] {body.name}님, '
                f'{fname} 안전점검 앱에 초대되었습니다. '
                f'다운로드: https://taieng.co.kr/app'
            ),
        )
        sms_sent = True
    except Exception:
        # SMS 실패해도 등록은 성공
        sms_sent = False

    return {
        'status': 'success',
        'data': worker,
        'sms_sent': sms_sent,
    }


@router.get('/factory/{factory_id}')
def list_workers(
    factory_id: str,
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """사업장의 작업자 목록."""
    sb = get_supabase()
    q = sb.table('worker_registry').select(
        '*', count='exact'
    ).eq('factory_id', factory_id)
    if status_code:
        q = q.eq('status_code', status_code)
    offset = (page - 1) * page_size
    r = q.eq('is_active', True).order(
        'created_at', desc=True
    ).range(offset, offset + page_size - 1).execute()
    return {
        'status': 'success',
        'data': r.data or [],
        'total': r.count or 0,
        'page': page,
    }


@router.get('/home/{worker_id}')
def worker_home(worker_id: str):
    """작업자 홈 — 오늘 할 점검, 미완료, 최근 알림."""
    sb = get_supabase()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    worker = sb.table('worker_registry').select(
        'id, name, factory_id, company_id, status_code'
    ).eq('id', worker_id).limit(1).execute()
    if not worker.data:
        raise HTTPException(404, '작업자를 찾을 수 없습니다.')
    w = worker.data[0]

    # 오늘 할 점검
    today_schedules = sb.table('work_schedules').select(
        'id, planned_date, status_code, inspection_set_id'
    ).eq('factory_id', w['factory_id']).eq(
        'planned_date', today
    ).in_('status_code', ['planned', 'in_progress']).execute()

    # 미완료 (overdue)
    overdue = sb.table('work_schedules').select(
        'id, planned_date, status_code', count='exact'
    ).eq('factory_id', w['factory_id']).eq(
        'status_code', 'planned'
    ).lt('planned_date', today).limit(0).execute()

    return {
        'status': 'success',
        'data': {
            'worker': w,
            'today_tasks': today_schedules.data or [],
            'today_count': len(today_schedules.data or []),
            'overdue_count': overdue.count or 0,
        },
    }


@router.patch('/{worker_id}')
def patch_worker(worker_id: str, body: WorkerPatchBody):
    """작업자 정보 수정."""
    sb = get_supabase()
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(400, '수정할 항목이 없습니다.')
    updates['updated_at'] = _now()
    r = sb.table('worker_registry').update(
        updates
    ).eq('id', worker_id).execute()
    if not r.data:
        raise HTTPException(404, '작업자를 찾을 수 없습니다.')
    return {'status': 'success', 'data': r.data[0]}


@router.get('/{worker_id}')
def get_worker(worker_id: str):
    """작업자 단건 조회."""
    sb = get_supabase()
    r = sb.table('worker_registry').select(
        '*'
    ).eq('id', worker_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, '작업자를 찾을 수 없습니다.')
    return {'status': 'success', 'data': r.data[0]}
