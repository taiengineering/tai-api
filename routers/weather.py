"""
routers/weather.py — v1.0.5

기상청 API Hub 연동 날씨 라우터

【현재 상태】
  apihub.kma.go.kr + authKey 인증 성공 (401 해결)
  403: VilageFcstInfoService_2.0 활용신청 필요
  → /weather/debug 에서 3개 API 경로 동시 테스트 지원:
      1. typ02/openApi/VilageFcstInfoService_2.0  (단기예보, 활용신청 필요)
      2. typ01/url/kma_sfctm2.php                (AWS 지점관측, 신청 불필요 가능)
      3. typ01/url/kma_wnd.php                   (AWS 풍속, 신청 불필요 가능)

Endpoints:
  GET /weather/work-stop-criteria
  GET /weather/debug
  GET /weather/now?lat=&lon=
  GET /weather/alert?region_code=

환경변수:
  KMA_SERVICE_KEY  = apihub.kma.go.kr 인증키 (authKey)
"""
from __future__ import annotations
import os, math, logging, httpx
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["날씨·기상"])

KMA_HUB    = "https://apihub.kma.go.kr/api"
ULTRA_URL  = f"{KMA_HUB}/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst"
WARN_URL   = f"{KMA_HUB}/typ02/openApi/WarningInfoService/getWthrWrnList"
AWS_URL    = f"{KMA_HUB}/typ01/url/kma_sfctm2.php"   # 방재기상관측 분자료

_RE=6371.00877;_GRID=5.0;_SLAT1=30.0;_SLAT2=60.0;_OLON=126.0;_OLAT=38.0;_XO=43;_YO=136


def _latlon_to_grid(lat:float,lon:float)->tuple[int,int]:
    D=math.pi/180.0;re=_RE/_GRID
    s1,s2,ol,oa=_SLAT1*D,_SLAT2*D,_OLON*D,_OLAT*D
    sn=math.log(math.cos(s1)/math.cos(s2))/math.log(math.tan(math.pi*.25+s2*.5)/math.tan(math.pi*.25+s1*.5))
    sf=math.pow(math.tan(math.pi*.25+s1*.5),sn)*math.cos(s1)/sn
    ro=re*sf/math.pow(math.tan(math.pi*.25+oa*.5),sn)
    ra=re*sf/math.pow(math.tan(math.pi*.25+lat*D*.5),sn)
    th=(lon*D-ol)*sn
    if th>math.pi:th-=2*math.pi
    if th<-math.pi:th+=2*math.pi
    return int(ra*math.sin(th)+_XO+.5),int(ro-ra*math.cos(th)+_YO+.5)


def _auth_key()->str:
    k=os.environ.get("KMA_SERVICE_KEY","")
    if not k: raise HTTPException(503,detail="KMA_SERVICE_KEY 미설정")
    return k


def _kst()->datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _base_date_time()->tuple[str,str]:
    now=_kst()
    if now.minute<45: now-=timedelta(hours=1)
    return now.strftime("%Y%m%d"),now.strftime("%H00")


async def _hub_get(base_url:str,params:dict)->httpx.Response:
    """authKey 직접 URL 포함, 나머지 urlencode"""
    key=params.pop("authKey")
    url=f"{base_url}?authKey={key}&{urlencode(params)}"
    async with httpx.AsyncClient(timeout=15,follow_redirects=True) as c:
        return await c.get(url)


PTY_CODE={"0":"없음","1":"비","2":"비/눈","3":"눈","5":"빗방울","6":"빗방울눈날림","7":"눈날림"}

def _parse_ultra(items:list)->dict:
    d:dict={}
    for i in items:
        c,v=i.get("category",""),i.get("obsrValue","")
        if c=="T1H": d["temperature"]=float(v)
        elif c=="RN1": d["rain_1h"]=float(v)
        elif c=="WSD": d["wind_speed"]=float(v)
        elif c=="VEC": d["wind_direction"]=float(v)
        elif c=="REH": d["humidity"]=float(v)
        elif c=="PTY": d["precip_type"]=PTY_CODE.get(v,v)
        elif c=="UUU": d["wind_u"]=float(v)
        elif c=="VVV": d["wind_v"]=float(v)
    return d


WORK_STOP_CRITERIA=[
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

def _judge_work_stop(weather:dict)->list[dict]:
    t=[]
    w=weather.get("wind_speed",0.0);r=weather.get("rain_1h",0.0);p=weather.get("precip_type","없음")
    if w>=10.0: t.append({"code":"STRONG_WIND","name":"강풍","value":f"{w}m/s","threshold":"10m/s"})
    if r>=1.0:  t.append({"code":"HEAVY_RAIN","name":"강우","value":f"{r}mm/h","threshold":"1mm/h"})
    if "눈" in p and r>=1.0: t.append({"code":"HEAVY_SNOW","name":"강설","value":p,"threshold":"1cm/h"})
    return t


# ── 엔드포인트 ─────────────────────────────────────────────────────────

@router.get("/work-stop-criteria")
def get_work_stop_criteria():
    return {"status":"success","legal_basis":"산업안전보건기준에 관한 규칙 제37조",
            "total":len(WORK_STOP_CRITERIA),"criteria":WORK_STOP_CRITERIA}


@router.get("/debug")
async def weather_debug():
    """
    [개발용] 3개 API 경로 동시 테스트.
    활용신청 없이 바로 사용 가능한 경로 탐색.
    """
    key = _auth_key()
    now = _kst()
    if now.minute < 45: now -= timedelta(hours=1)
    bd  = now.strftime("%Y%m%d")
    bt  = now.strftime("%H00")
    tm  = now.strftime("%Y%m%d%H%M")   # 분단위

    results = {}

    # 1. typ02 OpenAPI 초단기실황 (활용신청 필요)
    try:
        r = await _hub_get(ULTRA_URL, {"authKey":key,"numOfRows":"1","pageNo":"1",
                                        "dataType":"JSON","base_date":bd,"base_time":bt,"nx":"60","ny":"127"})
        try: b = r.json()
        except: b = r.text[:300]
        results["typ02_ultra"] = {"status": r.status_code, "body": b}
    except Exception as e:
        results["typ02_ultra"] = {"error": str(e)[:100]}

    # 2. typ01 AWS 방재기상관측 분자료 (활용신청 불필요 가능)
    try:
        r = await _hub_get(AWS_URL, {"authKey":key,"tm":tm,"stn":"108","disp":"1","help":"1"})
        body = r.text[:500]
        results["typ01_aws"] = {"status": r.status_code, "body": body}
    except Exception as e:
        results["typ01_aws"] = {"error": str(e)[:100]}

    # 3. typ02 기상특보 (활용신청 필요 여부 확인)
    try:
        r = await _hub_get(WARN_URL, {"authKey":key,"numOfRows":"1","pageNo":"1",
                                       "dataType":"JSON","fromTmFc":now.strftime("%Y%m%d0000")})
        try: b = r.json()
        except: b = r.text[:300]
        results["typ02_warn"] = {"status": r.status_code, "body": b}
    except Exception as e:
        results["typ02_warn"] = {"error": str(e)[:100]}

    return {"key_prefix": key[:8]+"...", "kst": now.isoformat(), "tests": results}


@router.get("/now")
async def get_weather_now(
    lat: float = Query(..., description="위도 (예: 37.5665)"),
    lon: float = Query(..., description="경도 (예: 126.9780)"),
):
    """현재 날씨 + 작업중지 판단 (API Hub 초단기실황)"""
    key=_auth_key()
    nx,ny=_latlon_to_grid(lat,lon)
    bd,bt=_base_date_time()
    params={"authKey":key,"numOfRows":"100","pageNo":"1","dataType":"JSON",
            "base_date":bd,"base_time":bt,"nx":str(nx),"ny":str(ny)}
    try:
        resp=await _hub_get(ULTRA_URL,params)
    except httpx.TimeoutException:
        raise HTTPException(504,detail="기상청 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(503,detail=f"연결 실패: {e}")

    if resp.status_code!=200:
        try: err=resp.json()
        except: err=resp.text[:200]
        raise HTTPException(502,detail=f"API Hub {resp.status_code}: {err}")

    raw=resp.json()
    items=raw.get("response",{}).get("body",{}).get("items",{}).get("item",[])
    if not items:
        rc=raw.get("response",{}).get("header",{}).get("resultCode","")
        raise HTTPException(502,detail=f"응답 없음 resultCode={rc}, {bd} {bt}")

    weather=_parse_ultra(items)
    triggered=_judge_work_stop(weather)
    ws=bool(triggered)
    return {
        "status":"success",
        "location":{"lat":lat,"lon":lon,"nx":nx,"ny":ny},
        "observed":{"base_date":bd,"base_time":bt},
        "weather":weather,
        "work_stop":{"required":ws,"level":"danger" if ws else "normal","triggered":triggered,
                     "message":f"작업중지 필요: {', '.join(t['name'] for t in triggered)}" if ws else "작업 진행 가능"},
    }


@router.get("/alert")
async def get_weather_alert(
    region_code: Optional[str] = Query(None, description="지역 코드 (없으면 전국)"),
):
    """기상특보 조회 (API Hub)"""
    key=_auth_key()
    now=_kst()
    params={"authKey":key,"numOfRows":"100","pageNo":"1","dataType":"JSON",
            "stnId":region_code or "","fromTmFc":now.strftime("%Y%m%d0000")}
    try:
        resp=await _hub_get(WARN_URL,params)
    except httpx.TimeoutException:
        raise HTTPException(504,detail="타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(503,detail=f"연결 실패: {e}")

    if resp.status_code!=200:
        try: err=resp.json()
        except: err=resp.text[:200]
        raise HTTPException(502,detail=f"API Hub {resp.status_code}: {err}")

    raw=resp.json()
    body=raw.get("response",{}).get("body",{})
    items=body.get("items",{}).get("item",[]) or []
    WS={"강풍","호우","대설","태풍","뇌전","풍랑"}
    alerts=[{"type":i.get("wrnTyp",""),"level":i.get("wrnLvl",""),"region":i.get("areaName",""),
             "issued_at":i.get("tmFc",""),"expires_at":i.get("tmEf",""),"description":i.get("cntnt",""),
             "work_stop_related":i.get("wrnTyp","") in WS} for i in items]
    ws=[a for a in alerts if a["work_stop_related"]]
    return {"status":"success","region_code":region_code or "전국","observed_at":now.isoformat(),
            "total":body.get("totalCount",0),"alerts":alerts,"work_stop_alerts":ws,"has_work_stop_alert":bool(ws)}
