"""관제홈 라우터 (WO-13 OpsHome).

Goal: G-ms4je4z3-33eada
- GET /ops/home — 대기 큐 + 이상 신호 + 오늘의 숫자. 얇은 위임.
"""
from fastapi import APIRouter

from services.ops_home_svc import get_home

router = APIRouter(prefix="/ops", tags=["관제홈"])


@router.get("/home")
def ops_home():
    """관제홈 종합 — 오늘 처리할 일."""
    return {"status": "success", "data": get_home()}
