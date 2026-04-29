"""
routers/weather.py — v1.3.1

기상청 날씨 API — Supabase Edge Function 프록시 방식

v1.3.1 (2026-04-29):
  [FIX] KMA_EDGE_URL 기본값을 서울 프로젝트(vwlahtguyggrhvslabax)로 변경
  구 프로젝트(vwlahtguyggrhvslabax) 삭제 대비

v1.3.0 (2026-04-16 SB-03):
  [ADD] GET /weather/work-stoppage?site_id=

환경변수:
  KMA_EDGE_URL → 미설정 시 SUPABASE_URL 기반 자동 생성
  KMA_SERVICE_KEY → Supabase Function Secret (kma-weather) 에 설정
"""
from __future__ import annotations
import os, logging, httpx
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["날씨·기상"])

# KMA_EDGE_URL 최우선, 없으면 SUPABASE_URL 기반 생성
EDGE_URL = os.environ.get("KMA_EDGE_URL", "")
if not EDGE_URL:
    _sb = os.environ.get("SUPABASE_URL", "https://vwlahtguyggrhvslabax.supabase.co")
    EDGE_URL = f"{_sb}/functions/v1/kma-weather"

# 시·도별 대표 위경도 (기상청 단기예보 격자 기반 근사값)
SIDO_LAT_LON = {
    "서울": (37.5665, 126.9780),
    "경기": (37.2750, 127.0095),
    "인천": (37.4563, 126.7052),
    "부산": (35.1796, 129.0756),
    "대구": (35.8714, 128.6014),
    "광주": (35.1595, 126.8526),
    "대전": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114),
    "세종": (36.4800, 127.2890),
    "강원": (37.8228, 128.1555),
    "충북": (36.6358, 127.4914),
    "충남": (36.5184, 126.8000),
    "전북": (35.8200, 127.1088),
    "전남": (34.8160, 126.4630),
    "경북": (36.4919, 128.8889),
    "경남": (35.4606, 128.2132),
    "제주": (33.4996, 126.5312),
}

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


def _resolve_lat_lon(site: dict) -> tuple[float, float]:
    """
    construction_sites 레코드에서 위경도를 추출.
    우선순위: lat/lon 컬럼 → site_sido 매핑 → 서울 기본값
    """
    lat = site.get("lat") or site.get("latitude")
    lon = site.get("lon") or site.get("longitude")
    if lat and lon:
        return float(lat), float(lon)

    sido = site.get("site_sido") or ""
    for key, (slat, slon) in SIDO_LAT_LON.items():
        if key in sido:
            return slat, slon

    # 기본값: 서울
    return 37.5665, 126.9780


# ── 콘크리트 라우트 먼저 선언 ──────────────────────────────────────────

@router.get("/work-stop-criteria")
def get_work_stop_criteria():
    """산업안전보건기준에 관한 규칙 제37조 작업중지 기준 목록"""
    return {"status":"success","legal_basis":"산업안전보건기준에 관한 규칙 제37조",
            "total":len(WORK_STOP_CRITERIA),"criteria":WORK_STOP_CRITERIA}


@router.get("/work-stoppage")
async def get_work_stoppage_by_site(
    site_id: str = Query(..., description="construction_sites.id"),
):
    """
    v1.3.0 SB-03: 건설현장 기준 작업중지 판정 (FE-SAFE-02 연동).
    """
    supabase = get_supabase()
    try:
        site_res = supabase.table("construction_sites") \
            .select("id, site_name, site_sido, site_sigungu, site_address") \
            .eq("id", site_id).eq("is_active", True).limit(1).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 조회 오류: {e}")

    if not site_res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")

    site = site_res.data[0]
    lat, lon = _resolve_lat_lon(site)

    # Edge Function 호출 (weather/now 액션)
    weather_data = await _edge_call({"action": "now", "lat": str(lat), "lon": str(lon)})

    return {
        "status": "success",
        "site_id":   site_id,
        "site_name": site.get("site_name"),
        "location": {
            "sido":    site.get("site_sido"),
            "sigungu": site.get("site_sigungu"),
            "lat":     lat,
            "lon":     lon,
        },
        "weather": weather_data,
        "legal_basis": "산업안전보건기준에 관한 규칙 제37조",
    }


@router.get("/alert-regions")
async def get_alert_regions(
    reg_type: Optional[str] = Query(None, description="구역 유형 필터 (L=육상, S=해상, 없으면 전체)"),
):
    """기상특보 구역 코드 목록 조회."""
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
