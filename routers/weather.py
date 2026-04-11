"""
routers/weather.py — v1.0.0

기상청 Open API 연동 날씨 라우터

Endpoints:
  GET /weather/now?lat=&lon=          현재 날씨 + 작업중지 판단
  GET /weather/alert?region_code=     기상특보 조회
  GET /weather/work-stop-criteria     작업중지 기준 목록 (법령 기반)

환경변수:
  KMA_SERVICE_KEY   기상청 API 인증키 (data.go.kr 발급)

기상청 격자 변환:
  위도/경도 → 기상청 격자(nx, ny) 자동 변환
  알고리즘 출처: 기상청 수치예보모델 공식 변환식
"""
from __future__ import annotations
import os, math, logging, httpx
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["날씨·기상"])

# ── 기상청 API 기본값 ────────────────────────────────────────────────────
KMA_BASE   = "http://apis.data.go.kr/1360000"
ULTRA_URL  = f"{KMA_BASE}/VilageFcstInfoService_2.0/getUltraSrtNcst"  # 초단기실황
FCST_URL   = f"{KMA_BASE}/VilageFcstInfoService_2.0/getUltraSrtFcst"  # 초단기예보
WARN_URL   = f"{KMA_BASE}/WarningInfoService/getWthrWrnList"           # 기상특보

# ── 격자 변환 상수 (기상청 공식 알고리즘) ─────────────────────────────────
_RE    = 6371.00877   # 지구 반경 km
_GRID  = 5.0          # 격자 간격 km
_SLAT1 = 30.0         # 투영 위도1
_SLAT2 = 60.0         # 투영 위도2
_OLON  = 126.0        # 기준점 경도
_OLAT  = 38.0         # 기준점 위도
_XO    = 43           # 기준점 X좌표
_YO    = 136          # 기준점 Y좌표


def _latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """위도/경도 → 기상청 격자(nx, ny) 변환"""
    DEGRAD = math.pi / 180.0
    re    = _RE / _GRID
    slat1 = _SLAT1 * DEGRAD
    slat2 = _SLAT2 * DEGRAD
    olon  = _OLON  * DEGRAD
    olat  = _OLAT  * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.pow(math.tan(math.pi * 0.25 + slat1 * 0.5), sn) * math.cos(slat1) / sn
    ro = re * sf / math.pow(math.tan(math.pi * 0.25 + olat * 0.5), sn)

    ra    = re * sf / math.pow(math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5), sn)
    theta = lon * DEGRAD - olon
    if theta >  math.pi: theta -= 2.0 * math.pi
    if theta < -math.pi: theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + _XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + _YO + 0.5)
    return nx, ny


def _kma_key() -> str:
    key = os.environ.get("KMA_SERVICE_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="KMA_SERVICE_KEY 환경변수 미설정")
    return key


def _base_date_time() -> tuple[str, str]:
    """기상청 초단기실황 기준시각 산출 (정시 발표, 45분 이후부터 사용 가능)"""
    now = datetime.now(timezone(timedelta(hours=9)))  # KST
    # 발표 시각: 정시 기준, 45분 후부터 유효
    if now.minute < 45:
        now = now - timedelta(hours=1)
    base_date = now.strftime("%Y%m%d")
    base_time = now.strftime("%H00")
    return base_date, base_time


# ── 카테고리 코드 해석 ────────────────────────────────────────────────────
PTY_CODE = {
    "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
    "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림",
}


def _parse_ultra(items: list) -> dict:
    """초단기실황 카테고리 목록 → 날씨 딕셔너리"""
    d: dict = {}
    for item in items:
        cat = item.get("category", "")
        val = item.get("obsrValue", "")
        if cat == "T1H":  d["temperature"]   = float(val)  # 기온 ℃
        elif cat == "RN1": d["rain_1h"]       = float(val)  # 1시간 강수량 mm
        elif cat == "WSD": d["wind_speed"]    = float(val)  # 풍속 m/s
        elif cat == "VEC": d["wind_direction"]= float(val)  # 풍향 deg
        elif cat == "REH": d["humidity"]      = float(val)  # 습도 %
        elif cat == "PTY": d["precip_type"]   = PTY_CODE.get(val, val)
        elif cat == "UUU": d["wind_u"]        = float(val)
        elif cat == "VVV": d["wind_v"]        = float(val)
    return d


# ── 작업중지 기준 (산업안전보건기준에 관한 규칙 제37조 근거) ─────────────────
WORK_STOP_CRITERIA = [
    {
        "code":      "STRONG_WIND",
        "name":      "강풍",
        "condition": "순간풍속 초당 10m 이상",
        "threshold": {"type": "wind_speed", "value": 10.0, "unit": "m/s"},
        "legal_basis": "산업안전보건기준에 관한 규칙 제37조 제1항 제2호",
        "scope":     "타워크레인, 건설용 리프트, 항타기·항발기 등 양중작업",
    },
    {
        "code":      "HEAVY_RAIN",
        "name":      "강우",
        "condition": "1시간 강수량 1mm 이상",
        "threshold": {"type": "rain_1h", "value": 1.0, "unit": "mm/h"},
        "legal_basis": "산업안전보건기준에 관한 규칙 제37조 제1항 제1호",
        "scope":     "타워크레인, 건설용 리프트, 달비계, 사다리식 통로 등",
    },
    {
        "code":      "HEAVY_SNOW",
        "name":      "강설",
        "condition": "1시간 적설량 1cm 이상",
        "threshold": {"type": "snow_1h", "value": 1.0, "unit": "cm/h"},
        "legal_basis": "산업안전보건기준에 관한 규칙 제37조 제1항 제3호",
        "scope":     "타워크레인, 건설용 리프트, 달비계, 사다리식 통로 등",
    },
    {
        "code":      "THUNDER",
        "name":      "뇌전",
        "condition": "뇌전(천둥·번개) 발생",
        "threshold": {"type": "thunder", "value": 1, "unit": "발생여부"},
        "legal_basis": "산업안전보건기준에 관한 규칙 제37조 제1항 제4호",
        "scope":     "달비계, 높이 2m 이상 작업발판, 화물취급 작업 등",
    },
]


def _judge_work_stop(weather: dict) -> list[dict]:
    """현재 날씨 기준 작업중지 항목 판정"""
    triggered = []
    wind = weather.get("wind_speed", 0.0)
    rain = weather.get("rain_1h", 0.0)
    precip = weather.get("precip_type", "없음")

    if wind >= 10.0:
        triggered.append({"code": "STRONG_WIND", "name": "강풍",
                          "value": f"{wind}m/s", "threshold": "10m/s"})
    if rain >= 1.0:
        triggered.append({"code": "HEAVY_RAIN", "name": "강우",
                          "value": f"{rain}mm/h", "threshold": "1mm/h"})
    if "눈" in precip and rain >= 1.0:
        triggered.append({"code": "HEAVY_SNOW", "name": "강설",
                          "value": precip, "threshold": "1cm/h"})

    return triggered


# ── 엔드포인트 ─────────────────────────────────────────────────────────

@router.get("/work-stop-criteria")
def get_work_stop_criteria():
    """산업안전보건기준에 관한 규칙 제37조 작업중지 기준 목록"""
    return {
        "status": "success",
        "legal_basis": "산업안전보건기준에 관한 규칙 제37조",
        "total": len(WORK_STOP_CRITERIA),
        "criteria": WORK_STOP_CRITERIA,
    }


@router.get("/now")
async def get_weather_now(
    lat: float = Query(..., description="위도 (예: 37.5665)"),
    lon: float = Query(..., description="경도 (예: 126.9780)"),
):
    """
    현재 날씨 조회 + 작업중지 판단.
    위도/경도 → 기상청 격자(nx, ny) 자동 변환.
    기상청 초단기실황 API 사용 (KMA_SERVICE_KEY 필요).
    """
    key = _kma_key()
    nx, ny = _latlon_to_grid(lat, lon)
    base_date, base_time = _base_date_time()

    params = {
        "serviceKey": key,
        "numOfRows":  "100",
        "pageNo":     "1",
        "dataType":   "JSON",
        "base_date":  base_date,
        "base_time":  base_time,
        "nx":         str(nx),
        "ny":         str(ny),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ULTRA_URL, params=params)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="기상청 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"기상청 API 연결 실패: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"기상청 API 오류: HTTP {resp.status_code}")

    raw  = resp.json()
    body = raw.get("response", {}).get("body", {})
    items = body.get("items", {}).get("item", [])

    if not items:
        result_code = raw.get("response", {}).get("header", {}).get("resultCode", "")
        raise HTTPException(
            status_code=502,
            detail=f"기상청 응답 없음 (resultCode={result_code}, base={base_date} {base_time})"
        )

    weather   = _parse_ultra(items)
    triggered = _judge_work_stop(weather)

    work_stop = len(triggered) > 0
    level     = "danger" if work_stop else "normal"

    return {
        "status":    "success",
        "location":  {"lat": lat, "lon": lon, "nx": nx, "ny": ny},
        "observed":  {"base_date": base_date, "base_time": base_time},
        "weather":   weather,
        "work_stop": {
            "required":  work_stop,
            "level":     level,
            "triggered": triggered,
            "message":   (
                f"작업중지 필요: {', '.join(t['name'] for t in triggered)}" if work_stop
                else "작업 진행 가능"
            ),
        },
    }


@router.get("/alert")
async def get_weather_alert(
    region_code: Optional[str] = Query(None, description="지역 코드 (없으면 전국)"),
):
    """
    기상특보 조회.
    region_code 미입력 시 전국 특보 반환.
    특보 종류: 강풍/풍랑/호우/대설/건조/해일/한파/태풍/황사/안개/뇌전 등
    """
    key = _kma_key()
    now = datetime.now(timezone(timedelta(hours=9)))

    params = {
        "serviceKey": key,
        "numOfRows":  "100",
        "pageNo":     "1",
        "dataType":   "JSON",
        "stnId":      region_code or "",
        "fromTmFc":   now.strftime("%Y%m%d0000"),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(WARN_URL, params=params)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="기상청 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"기상청 API 연결 실패: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"기상청 API 오류: HTTP {resp.status_code}")

    raw   = resp.json()
    body  = raw.get("response", {}).get("body", {})
    items = body.get("items", {}).get("item", []) or []
    total = body.get("totalCount", 0)

    # 작업중지 관련 특보 코드
    WORK_STOP_WARN = {"강풍", "호우", "대설", "태풍", "뇌전", "풍랑"}
    alerts = []
    for item in items:
        warn_type = item.get("wrnTyp", "")
        alerts.append({
            "type":        warn_type,
            "level":       item.get("wrnLvl", ""),
            "region":      item.get("areaName", ""),
            "issued_at":   item.get("tmFc", ""),
            "expires_at":  item.get("tmEf", ""),
            "description": item.get("cntnt", ""),
            "work_stop_related": warn_type in WORK_STOP_WARN,
        })

    work_stop_alerts = [a for a in alerts if a["work_stop_related"]]

    return {
        "status":             "success",
        "region_code":        region_code or "전국",
        "observed_at":        now.isoformat(),
        "total":              total,
        "alerts":             alerts,
        "work_stop_alerts":   work_stop_alerts,
        "has_work_stop_alert": len(work_stop_alerts) > 0,
    }
