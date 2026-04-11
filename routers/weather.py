"""
routers/weather.py — v1.2.0

기상청 날씨 API — Supabase Edge Function 프록시 방식

Endpoints:
  GET /weather/work-stop-criteria         법령 기반 작업중지 기준
  GET /weather/alert-regions              특보구역 코드 목록 조회  ← v1.2.0 추가
  GET /weather/debug                      Edge Function 테스트
  GET /weather/now?lat=&lon=             현재 날씨 + 작업중지 판단
  GET /weather/alert?region_code=        기상특보 조회

환경변수:
  KMA_SERVICE_KEY → Supabase Function Secret (kma-weather) 에 설정
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


# ── 콘크리트 라우트 먼저 선언 (파라미터 라우트보다 앞) ─────────────────────

@router.get("/work-stop-criteria")
def get_work_stop_criteria():
    """산업안전보건기준에 관한 규칙 제37조 작업중지 기준 목록"""
    return {"status":"success","legal_basis":"산업안전보건기준에 관한 규칙 제37조",
            "total":len(WORK_STOP_CRITERIA),"criteria":WORK_STOP_CRITERIA}


@router.get("/alert-regions")
async def get_alert_regions(
    reg_type: Optional[str] = Query(None, description="구역 유형 필터 (L=육상, S=해상, 없으면 전체)"),
):
    """
    기상특보 구역 코드 목록 조회.
    apihub.kma.go.kr 예특보 > 기상특보 > 1.1 특보구역 API 사용.
    region_code 파라미터에 사용할 REG_ID 목록을 반환합니다.
    """
    return await _edge_call({"action": "alert-regions", "reg_type": reg_type or ""})


@router.get("/debug")
async def weather_debug():
    """[개발용] Supabase Edge Function 경유 API 테스트"""
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
    region_code: Optional[str] = Query(None, description="특보구역 코드 (없으면 전국, /alert-regions 참조)"),
):
    """기상특보 조회 (Edge Function 경유)"""
    payload: dict = {"action": "alert"}
    if region_code:
        payload["region_code"] = region_code
    return await _edge_call(payload)
