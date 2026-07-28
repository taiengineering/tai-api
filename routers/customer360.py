"""고객360 통합 집계 라우터 (WO-6 Customer360).

Goal: G-ms4je4z3-33eada
- 얇은 라우터: 집계 로직은 services/customer360_svc.py 위임(400줄 규칙).
- prefix /companies 로 기존 companies 라우터와 동일 네임스페이스.
  경로 GET /companies/{company_id}/360.
"""
from fastapi import APIRouter, HTTPException, Query

from services.customer360_svc import Customer360Error, get_summary

router = APIRouter(prefix="/companies", tags=["customer360"])


@router.get("/{company_id}/360")
def get_company_360(company_id: str, audit_limit: int = Query(default=10, ge=1, le=50)):
    """회사 통합 집계 — 시설·회원·결제·구독·진단·크레딧·증빙·환불·감사 요약."""
    try:
        data = get_summary(company_id, audit_limit=audit_limit)
    except Customer360Error as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": data}
