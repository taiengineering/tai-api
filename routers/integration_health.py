"""연동 상태 관제 라우터 (WO-10 IntegrationHealth).

Goal: G-ms4je4z3-33eada
- GET /integrations/health — 핵심 연동 env 상태 + 정부 API 집계(네트워크 불필요, 항상 응답).
- POST /integrations/probe — 내부 API 헬스 probe(실 HTTP, tai-api 자기 도메인).
- 얇은 위임: services.integration_health_svc.
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.integration_health_svc import get_health, probe_internal

router = APIRouter(prefix="/integrations", tags=["연동관제"])


class ProbeBody(BaseModel):
    group: Optional[str] = None
    base_url: Optional[str] = None
    limit: int = 50


@router.get("/health")
def integrations_health():
    """핵심 연동 env 상태 + 정부 API 집계."""
    return {"status": "success", "data": get_health()}


@router.post("/probe")
def integrations_probe(body: ProbeBody):
    """내부 API 헬스 probe 실행."""
    result = probe_internal(group=body.group, base_url=body.base_url, limit=body.limit)
    return {"status": "success", "data": result}
