"""
routers/weather.py — v1.0.3

기상청 Open API 연동 날씨 라우터

Endpoints:
  GET /weather/work-stop-criteria     작업중지 기준 목록 (법령 기반)
  GET /weather/debug                  [개발용] KMA API 원본 응답 확인
  GET /weather/now?lat=&lon=          현재 날씨 + 작업중지 판단
  GET /weather/alert?region_code=     기상특보 조회

환경변수:
  KMA_SERVICE_KEY   기상청 API 인증키 (data.go.kr 발급, 인코딩 원본 그대로 저장)

v1.0.3:
  - serviceKey: unquote 제거 → 원본(인코딩) 키를 URL에 직접 포함
  - data.go.kr 발급 키는 인코딩된 상태 그대로 ?serviceKey= 에 사용해야 함
"""
from __future__ import annotations
import os, math, logging, httpx
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["날씨·기상"])

KMA_BASE  = "https://apis.data.go.kr/1360000"
ULTRA_URL = f"{KMA_BASE}/VilageFcstInfoService_2.0/getUltraSrtNcst"
WARN_URL  = f"{KMA_BASE}/WarningInfoService/getWthrWrnList"

_RE    = 6371.00877
_GRID  = 5.0
_SLAT1 = 30.0
_SLAT2 = 60.0
_OLON  = 126.0
_OLAT  = 38.0
_XO    = 43
_YO    = 136


def _latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
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
    return int(ra * math.sin(theta) + _XO + 0.5), int(ro - ra * math.cos(theta) + _YO + 0.5)


def _kma_key() -> str:
    key = os.environ.get("KMA_SERVICE_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="KMA_SERVICE_KEY 환경변수 미설정")
    return key  # 인코딩 원본 그대로 반환 (URL에 직접 포함)


def _base_date_time() -> tuple[str, str]:
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.minute < 45:
        now = now - timedelta(hours=1)
    return now.strftime("%Y%m%d"), now.strftime("%H00")


async def _kma_get(base_url: str, params: dict) -> httpx.Response:
    """
    serviceKey를 URL에 직접 포함 (인코딩 원본), 나머지 파라미터는 urlencode.
    httpx params 사용 시 이중인코딩 문제 → URL 직접 조합 방식 사용.
    """
    key  = params.pop("serviceKey")
    qs   = urlencode(params)
    url  = f"{base_url}?serviceKey={key}&{qs}"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        return await client.get(url)


PTY_CODE = {
    "0": "없음", "1": "비", "2": "비/눈", "3": "눈",
    "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림",
}


def _parse_ultra(items: list) -> dict:
    d: dict = {}
    for item in items:
        cat, val = item.get("category", ""), item.get("obsrValue", "")
        if cat == "T1H":   d["temperature"]    = float(val)
        elif cat == "RN1": d["rain_1h"]        = float(val)
        elif cat == "WSD": d["wind_speed"]     = float(val)
        elif cat == "VEC": d["wind_direction"] = float(val)
        elif cat == "REH": d["humidity"]       = float(val)
        elif cat == "PTY": d["precip_type"]    = PTY_CODE.get(val, val)
        elif cat == "UUU": d["wind_u"]         = float(val)
        elif cat == "VVV": d["wind_v"]         = float(val)
    return d


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


def _judge_work_stop(weather: dict) -> list[dict]:
    triggered = []
    wind, rain, precip = weather.get("wind_speed",0.0), weather.get("rain_1h",0.0), weather.get("precip_type","없음")
    if wind >= 10.0: triggered.append({"code":"STRONG_WIND","name":"강풍","value":f"{wind}m/s","threshold":"10m/s"})
    if rain >= 1.0:  triggered.append({"code":"HEAVY_RAIN","name":"강우","value":f"{rain}mm/h","threshold":"1mm/h"})
    if "눈" in precip and rain >= 1.0: triggered.append({"code":"HEAVY_SNOW","name":"강설","value":precip,"threshold":"1cm/h"})
    return triggered


# ── 엔드포인트 ─────────────────────────────────────────────────────────

@router.get("/work-stop-criteria")
def get_work_stop_criteria():
    return {"status":"success","legal_basis":"산업안전보건기준에 관한 규칙 제37조",
            "total":len(WORK_STOP_CRITERIA),"criteria":WORK_STOP_CRITERIA}


@router.get("/debug")
async def weather_debug():
    """[개발용] KMA 인증 상태 및 원본 응답 확인"""
    key = _kma_key()
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.minute < 45: now -= timedelta(hours=1)
    params = {"serviceKey":key,"numOfRows":"1","pageNo":"1","dataType":"JSON",
              "base_date":now.strftime("%Y%m%d"),"base_time":now.strftime("%H00"),"nx":"60","ny":"127"}
    try:
        resp = await _kma_get(ULTRA_URL, params)
        try: body = resp.json()
        except: body = resp.text[:500]
        return {"key_prefix":key[:8]+"...","http_status":resp.status_code,"response":body}
    except Exception as e:
        return {"error":type(e).__name__,"detail":str(e)[:200]}


@router.get("/now")
async def get_weather_now(
    lat: float = Query(..., description="위도 (예: 37.5665)"),
    lon: float = Query(..., description="경도 (예: 126.9780)"),
):
    """현재 날씨 + 작업중지 판단 (기상청 초단기실황)"""
    key = _kma_key()
    nx, ny = _latlon_to_grid(lat, lon)
    base_date, base_time = _base_date_time()
    params = {"serviceKey":key,"numOfRows":"100","pageNo":"1","dataType":"JSON",
              "base_date":base_date,"base_time":base_time,"nx":str(nx),"ny":str(ny)}
    try:
        resp = await _kma_get(ULTRA_URL, params)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="기상청 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"기상청 API 연결 실패: {e}")

    if resp.status_code != 200:
        try: err = resp.json()
        except: err = resp.text[:200]
        raise HTTPException(status_code=502, detail=f"기상청 HTTP {resp.status_code}: {err}")

    raw = resp.json()
    items = raw.get("response",{}).get("body",{}).get("items",{}).get("item",[])
    if not items:
        rc = raw.get("response",{}).get("header",{}).get("resultCode","")
        raise HTTPException(status_code=502, detail=f"기상청 응답 없음 (resultCode={rc}, {base_date} {base_time})")

    weather   = _parse_ultra(items)
    triggered = _judge_work_stop(weather)
    work_stop = bool(triggered)
    return {
        "status":"success",
        "location":{"lat":lat,"lon":lon,"nx":nx,"ny":ny},
        "observed":{"base_date":base_date,"base_time":base_time},
        "weather":weather,
        "work_stop":{"required":work_stop,"level":"danger" if work_stop else "normal",
                     "triggered":triggered,
                     "message":f"작업중지 필요: {', '.join(t['name'] for t in triggered)}" if work_stop else "작업 진행 가능"},
    }


@router.get("/alert")
async def get_weather_alert(
    region_code: Optional[str] = Query(None, description="지역 코드 (없으면 전국)"),
):
    """기상특보 조회"""
    key = _kma_key()
    now = datetime.now(timezone(timedelta(hours=9)))
    params = {"serviceKey":key,"numOfRows":"100","pageNo":"1","dataType":"JSON",
              "stnId":region_code or "","fromTmFc":now.strftime("%Y%m%d0000")}
    try:
        resp = await _kma_get(WARN_URL, params)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="기상청 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"기상청 API 연결 실패: {e}")

    if resp.status_code != 200:
        try: err = resp.json()
        except: err = resp.text[:200]
        raise HTTPException(status_code=502, detail=f"기상청 HTTP {resp.status_code}: {err}")

    raw   = resp.json()
    body  = raw.get("response",{}).get("body",{})
    items = body.get("items",{}).get("item",[]) or []
    WORK_STOP_WARN = {"강풍","호우","대설","태풍","뇌전","풍랑"}
    alerts = [{"type":i.get("wrnTyp",""),"level":i.get("wrnLvl",""),"region":i.get("areaName",""),
               "issued_at":i.get("tmFc",""),"expires_at":i.get("tmEf",""),"description":i.get("cntnt",""),
               "work_stop_related":i.get("wrnTyp","") in WORK_STOP_WARN} for i in items]
    ws = [a for a in alerts if a["work_stop_related"]]
    return {"status":"success","region_code":region_code or "전국","observed_at":now.isoformat(),
            "total":body.get("totalCount",0),"alerts":alerts,"work_stop_alerts":ws,"has_work_stop_alert":bool(ws)}
