"""
routers/weather.py — v1.1.0

기상청 날씨 API — Supabase Edge Function 프록시 방식

【구조】
  Railway (api.taieng.co.kr) → Supabase Edge Function (kma-weather) → apihub.kma.go.kr
  
  Railway IP 차단 우회: precedent collect 과 동일한 방식
  KMA_SERVICE_KEY는 Supabase Function Secret 에 설정 필요 (Railway와 동일 값)

Endpoints:
  GET /weather/work-stop-criteria   법령 기반 작업중지 기준 (Edge Function 불필요)
  GET /weather/debug                Edge Function 경유 3개 API 동시 테스트
  GET /weather/now?lat=&lon=        현재 날씨 + 작업중지 판단
  GET /weather/alert?region_code=   기상특보 조회

환경변수:
  KMA_SERVICE_KEY  — Supabase Function Secret 에 설정 (Railway 환경변수는 참조 안 함)
  
  ※ Supabase 대시보드 > Edge Functions > kma-weather > Secrets
    KMA_SERVICE_KEY = (apihub.kma.go.kr authKey)
"""
from __future__ import annotations
import os, logging, httpx
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["날씨·기상"])

EDGE_URL = os.environ.get(
    "KMA_EDGE_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/kma-weather"
)

WORK_STOP_CRITERIA = [
    {"code":"STRONG_WIND","name":"강풍","condition":"순간풍속 초당 10m 이상",
     "threshold":{"type":"wind_speed","value":10.0,"unit":"m/s"},
     "legal_basis":"산업안전보건기준에 관한 규칙 제37조 제1항 제2호",
     "scope":"타워크레인, 건설용 리프트, 항타기·항발기 등 양중작업"},
    {"code":"HEAVY_RAIN","name":"강우","condition":"1시간 강수량 1mm 이상",
     "threshold":{"type":"rain_1h","value":1.0,"unit":"mm/h"},
     "legal_basis":"산업안전보건기준에 관한 규칙 제37조 제1항 제1호",
     "scope":"타워크레인, 건설용 리프트, 달비계, 사다리식 통로 등"},
    {"code":"HEAVY_SNOW","name":"강설","condition":"1시간 적설량 1cm 이상",
     "threshold":{"type":"snow_1h","value":1.0,"unit":"cm/h"},
     "legal_basis":"산업안전보건기준에 관한 규칙 제37조 제1항 제3호",
     "scope":"타워크레인, 건설용 리프트, 달비계, 사다리식 통로 등"},
    {"code":"THUNDER","name":"뇌전","condition":"뇌전(천둥·번개) 발생",
     "threshold":{"type":"thunder","value":1,"unit":"발생여부"},
     "legal_basis":"산업안전보건기준에 관한 규칙 제37조 제1항 제4호",
     "scope":"달비계, 높이 2m 이상 작업발판, 화물취급 작업 등"},
]


async def _edge_call(payload: dict, timeout: int = 20) -> dict:
    """Supabase Edge Function 호출 공통 함수"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.post(EDGE_URL, json=payload)
        if resp.status_code >= 400:
            try: err = resp.json()
            except: err = resp.text[:200]
            raise HTTPException(status_code=502,
                                detail=f"Edge Function {resp.status_code}: {err}")
        return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Edge Function 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"Edge Function 연결 실패: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {str(e)[:100]}")


@router.get("/work-stop-criteria")
def get_work_stop_criteria():
    """산업안전보건기준에 관한 규칙 제37조 작업중지 기준 목록"""
    return {"status":"success","legal_basis":"산업안전보건기준에 관한 규칙 제37조",
            "total":len(WORK_STOP_CRITERIA),"criteria":WORK_STOP_CRITERIA}


@router.get("/debug")
async def weather_debug():
    """
    [개발용] Supabase Edge Function 경유 3개 API 동시 테스트.
    KMA_SERVICE_KEY 가 Supabase Function Secret 에 설정되어 있어야 합니다.
    """
    return await _edge_call({"action": "debug"}, timeout=30)


@router.get("/now")
async def get_weather_now(
    lat: float = Query(..., description="위도 (예: 37.5665)"),
    lon: float = Query(..., description="경도 (예: 126.9780)"),
):
    """현재 날씨 + 작업중지 판단 (Edge Function 경유 → apihub.kma.go.kr)"""
    return await _edge_call({"action": "now", "lat": str(lat), "lon": str(lon)})


@router.get("/alert")
async def get_weather_alert(
    region_code: Optional[str] = Query(None, description="지역 코드 (없으면 전국)"),
):
    """기상특보 조회 (Edge Function 경유)"""
    payload: dict = {"action": "alert"}
    if region_code:
        payload["region_code"] = region_code
    return await _edge_call(payload)
