# routers/admin_commercial.py — WO-ADM-COMM-01-BE-READ-001
"""Admin Commercial Console — READ ONLY.

/admin/commercial/versions      GET  — Commercial Version history
/admin/commercial/site-scopes   GET  — Site Scope per CV
/admin/commercial/entitlement-health  GET  — Commercial health per company

인증: get_current_user. 권한: _require_admin (ALL scope 전용).
DB write = 0. pricing engine 호출 = 0.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _require_admin
from services import admin_commercial_svc as svc

router = APIRouter(prefix="/admin/commercial", tags=["admin-commercial"])


@router.get("/versions")
def list_versions(
    contract_id: str = Query(..., description="SaaS contract id (required)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current: dict = Depends(get_current_user),
):
    """Commercial Version append-only history. DB write = 0."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    data = svc.list_commercial_versions(supabase, contract_id, page, page_size)
    return {"status": "success", "data": data}


@router.get("/site-scopes")
def list_site_scopes(
    commercial_version_id: str = Query(..., description="Commercial Version id (required)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    current: dict = Depends(get_current_user),
):
    """Site Scope read per Commercial Version. DB write = 0."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    data = svc.list_site_scopes(supabase, commercial_version_id, page, page_size)
    return {"status": "success", "data": data}


@router.get("/entitlement-health")
def get_entitlement_health(
    company_id: str = Query(..., description="Company id (required)"),
    current: dict = Depends(get_current_user),
):
    """Commercial 상태 관제.

    canonical anomaly (NO_ACTIVE_SAAS_CONTRACT 등) → HTTP 200 + health_status=ERROR.
    미래 예약 Renewal CV 존재 → ERROR 아님 + future_scheduled_cv_ids 포함.
    AUTH 문제만 401/403. 예상치 못한 내부 오류만 5xx.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    data = svc.get_entitlement_health(supabase, company_id)
    return {"status": "success", "data": data}
