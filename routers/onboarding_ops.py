"""온보딩 체크리스트 라우터 (WO-17 OnboardingChecklist).

Goal: G-ms4je4z3-33eada
- GET /companies/{id}/onboarding — 회사 온보딩 4단계 진행 현황.
"""
from fastapi import APIRouter

from services.onboarding_svc import get_checklist

router = APIRouter(prefix="/companies", tags=["온보딩"])


@router.get("/{company_id}/onboarding")
def company_onboarding(company_id: str):
    """회사 온보딩 체크리스트(파생 판정)."""
    return {"status": "success", "data": get_checklist(company_id)}
