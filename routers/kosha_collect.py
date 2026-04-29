"""
KOSHA 데이터 수집 — DB 저장 + 크론 갱신
prefix: /kosha-collect

v1.2.0:
  - 증분수집: 마지막 성공 수집일 이후 신규 데이터만 수집
  - 초기수집: since_date='2024-01-01' 기본값
  - full_refresh 옵션: 전체 다시 수집
  - SERVICE_KEY 우선순위: DATA_GO_KR_SERVICE_KEY > KOSHA_SERVICE_KEY > BUILDING_API_KEY
"""
from __future__ import annotations
import os, logging, httpx, json
from datetime import datetime, timezone
from fastapi import APIRouter, Query, BackgroundTasks
from typing import Optional
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/kosha-collect", tags=["KOSHA데이터수집"])

def _get_service_key() -> str:
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or os.getenv("BUILDING_API_KEY", "")
    )

BASE      = "https://apis.data.go.kr/B552468"
MAX_ROWS  = 100
MAX_PAGES = 100  # 초기수집 시 100 페이지를 넘는 데이터도 수집
INIT_DATE = "2024-01-01"  # 초기수집 기준일


class KoshaAPI:
    @staticmethod
    async def get(path: str, params: dict) -> dict:
        params["serviceKey"] = _get_service_key()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{BASE}/{path}", params=params)
                resp.raise_for_status()
                text = resp.text
                try:
                    data = json.loads(text)
                    if "response" in data and isinstance(data["response"], dict):
                        return data["response"]
                    return data
                except Exception:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(text)
                    items = []
                    for item in (root.find(".//items") or []):
                        items.append({c.tag: c.text or "" for c in item})
                    return {"body": {"items": items,
                                    "totalCount": int(root.findtext(".//totalCount") or 0)}}
        except Exception as e:
            log.error("[KOSHA] %s 호출 실패: %s", path, e)
            return {"body": {"items": [], "totalCount": 0}}

    @staticmethod
    def items(resp: dict) -> list:
        body = resp.get("body") or resp.get("data") or {}
        if isinstance(body, dict):
            it = body.get("items", [])
            return it if isinstance(it, list) else []
        return []

    @staticmethod
    def total(resp: dict) -> int:
        body = resp.get("body") or resp.get("data") or {}
        return int(body.get("totalCount", 0)) if isinstance(body, dict) else 0


def _log(target: str, status: str, rows: int = 0, err: str = "", since_date: str = ""):
    try:
        sb = get_supabase()
        sb.table("kosha_collect_log").insert({
            "target": target, "status": status,
            "rows_upserted": rows,
            "error_msg": err or None,
            # since_date 로그 저장 (컨텔럼 파악용)
        }).execute()
    except Exception:
        pass


def _get_last_collected(target: str) -> Optional[str]:
    """target 의 마지막 성공 수집일로부터 증분 시작일 반환. 없으면 INIT_DATE."""
    try:
        sb = get_supabase()
        r = (sb.table("kosha_collect_log")
               .select("collected_at")
               .eq("target", target)
               .eq("status", "success")
               .order("collected_at", desc=True)
               .limit(1)
               .execute())
        if r.data:
            dt = r.data[0]["collected_at"][:10]  # YYYY-MM-DD
            return dt
    except Exception:
        pass
    return INIT_DATE


def _parse_date(val: str) -> Optional[str]:
    """'2024-01-01' 또는 '20240101' 둥 형식 지원 → 'YYYY-MM-DD'"""
    if not val:
        return None
    v = str(val).strip().replace("/", "-")
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return v[:10] if len(v) >= 10 else v


def _after_since(date_str: str, since_date: str) -> bool:
    """date_str >= since_date 인지 확인"""
    d = _parse_date(date_str)
    if not d:
        return True  # 날짜 없으면 포함
    return d >= since_date


# ─────────────────────────────────────────────────────
# 수집함수
# ─────────────────────────────────────────────────────

async def _collect_accident_cases(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    businesses = ["", "제조업", "건설업", "조선업", "서비스업", "기타"]
    total_upserted = 0
    for biz in businesses:
        for page in range(1, MAX_PAGES + 1):
            params = {"callApiId": "국내재해사례 게시판 조회",
                      "pageNo": page, "numOfRows": MAX_ROWS}
            if biz:
                params["business"] = biz
            resp  = await KoshaAPI.get("disaster_api02/getdisaster_api02", params)
            items = KoshaAPI.items(resp)
            if not items:
                break
            rows = []
            stop_early = False
            for i, it in enumerate(items):
                dt = str(it.get("regDt") or it.get("writeDate") or "")
                if dt and not _after_since(dt, since):
                    stop_early = True  # 오래된 데이터 도달 → 얼리 종료
                    continue
                rid = str(it.get("boardNo") or it.get("bbsNo") or f"{biz or 'ALL'}_{page}_{i}")
                rows.append({
                    "id":       rid,
                    "title":    it.get("title") or it.get("bbsTitle") or it.get("subject") or "",
                    "business": it.get("business") or biz,
                    "content":  it.get("content") or it.get("bbsContent") or "",
                    "board_no": str(it.get("boardNo") or it.get("bbsNo") or ""),
                    "reg_dt":   dt,
                    "file_url": it.get("fileUrl") or it.get("fileLink") or "",
                    "raw_json": it,
                })
            if rows:
                sb.table("kosha_accident_cases").upsert(rows, on_conflict="id").execute()
                total_upserted += len(rows)
            if stop_early or len(items) < MAX_ROWS:
                break
    _log("accident_cases", "success", total_upserted, since_date=since)
    return {"target": "accident_cases", "since": since, "upserted": total_upserted}


async def _collect_safety_materials(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("selectMediaList01/getselectMediaList01",
                                   {"pageNo": page, "numOfRows": MAX_ROWS})
        items = KoshaAPI.items(resp)
        if not items:
            break
        rows = []
        for i, it in enumerate(items):
            rid = str(it.get("mediaId") or it.get("id") or f"mat_{page}_{i}")
            rows.append({
                "id":            rid,
                "title":         it.get("title") or it.get("mediaTitle") or "",
                "product_type":  it.get("productType") or "",
                "industry":      it.get("industry") or "",
                "accident_type": it.get("accidentType") or "",
                "url":           it.get("url") or it.get("mediaUrl") or "",
                "raw_json":      it,
            })
        if rows:
            sb.table("kosha_safety_materials").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS:
            break
    _log("safety_materials", "success", total_upserted)
    return {"target": "safety_materials", "upserted": total_upserted}


async def _collect_construction_accidents(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("constDsstr01/getconstDsstr01",
                                   {"pageNo": page, "numOfRows": MAX_ROWS})
        items = KoshaAPI.items(resp)
        if not items:
            break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("occurrenceDate") or it.get("dsstrDt") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("id") or it.get("seq") or f"ca_{page}_{i}")
            rows.append({
                "id":               rid,
                "accident_type":    it.get("accidentType") or it.get("dsstrKnd") or "",
                "work_type":        it.get("workType") or it.get("workKnd") or "",
                "causative":        it.get("causative") or it.get("crtrFtr") or "",
                "occurrence_date":  it.get("occurrenceDate") or it.get("dsstrDt") or "",
                "accident_summary": it.get("accidentSummary") or it.get("dsstrOutl") or "",
                "risk_reduction":   it.get("riskReduction") or it.get("rskRdcMsr") or "",
                "raw_json":         it,
            })
        if rows:
            sb.table("kosha_construction_accidents").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS:
            break
    _log("construction_accidents", "success", total_upserted, since_date=since)
    return {"target": "construction_accidents", "since": since, "upserted": total_upserted}


async def _collect_safety_light(full_refresh: bool = True) -> dict:
    """신호등은 현황 데이터 — 항상 전체 교체"""
    sb = get_supabase()
    rows_all: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("constructSafety/getConstructSafetySignal",
                                   {"pageNo": page, "numOfRows": MAX_ROWS})
        items = KoshaAPI.items(resp)
        if not items:
            break
        for i, it in enumerate(items):
            rid = str(it.get("id") or it.get("siteId") or f"sl_{page}_{i}")
            rows_all.append({
                "id":        rid,
                "site_nm":   it.get("siteNm") or it.get("siteName") or "",
                "sido":      it.get("sido") or "",
                "sigungu":   it.get("sigungu") or "",
                "signal":    it.get("signal") or it.get("signalColor") or "",
                "guide_dt":  it.get("guideDt") or it.get("inspDate") or "",
                "guide_org": it.get("guideOrg") or it.get("orgName") or "",
                "raw_json":  it,
            })
        if len(items) < MAX_ROWS:
            break
    total_upserted = 0
    if rows_all:
        sb.table("kosha_construction_safety_light").delete().neq("id", "__never__").execute()
        sb.table("kosha_construction_safety_light").upsert(rows_all, on_conflict="id").execute()
        total_upserted = len(rows_all)
    _log("construction_safety_light", "success", total_upserted)
    return {"target": "construction_safety_light", "upserted": total_upserted}


async def _collect_risk_assessment(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("riskAssmt/getRiskAssmtAccdtInfo",
                                   {"pageNo": page, "numOfRows": MAX_ROWS})
        items = KoshaAPI.items(resp)
        if not items:
            break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("certDate") or it.get("acptDt") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("id") or it.get("seq") or f"ra_{page}_{i}")
            rows.append({
                "id":           rid,
                "company_nm":   it.get("companyNm") or it.get("siteNm") or it.get("bizNm") or "",
                "sido":         it.get("sido") or "",
                "cert_date":    dt,
                "expiry_date":  it.get("expiryDate") or it.get("vlddDt") or "",
                "industry":     it.get("industry") or "",
                "labor_office": it.get("laborOffice") or it.get("labor_office") or "",
                "raw_json":     it,
            })
        if rows:
            sb.table("kosha_risk_assessment").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS:
            break
    _log("risk_assessment", "success", total_upserted, since_date=since)
    return {"target": "risk_assessment", "since": since, "upserted": total_upserted}


async def _collect_guide(full_refresh: bool = False) -> dict:
    sb = get_supabase()
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("koshaguide/getKoshaGuide",
                                   {"pageNo": page, "numOfRows": MAX_ROWS, "returnType": "json"})
        items = KoshaAPI.items(resp)
        if not items:
            break
        rows = []
        for i, it in enumerate(items):
            rid = str(it.get("guideId") or it.get("guideNo") or f"guide_{page}_{i}")
            rows.append({
                "id":          rid,
                "guide_no":    it.get("guideNo") or it.get("guide_no") or "",
                "guide_title": it.get("guideTitle") or it.get("guideName") or it.get("title") or "",
                "category":    (it.get("category") or it.get("guideCategory") or "").upper(),
                "guide_url":   it.get("guideUrl") or it.get("url") or "",
                "regist_date": it.get("registDate") or it.get("regDt") or "",
                "raw_json":    it,
            })
        if rows:
            sb.table("kosha_guide").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS:
            break
    _log("guide", "success", total_upserted)
    return {"target": "guide", "upserted": total_upserted}


# ─────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────

@router.post("/run")
async def collect_all(
    background_tasks: BackgroundTasks,
    target:       Optional[str] = Query(None, description="특정 대상 (all=전체)"),
    since_date:   str  = Query(INIT_DATE, description="수집 기준일 (YYYY-MM-DD)"),
    full_refresh: bool = Query(False, description="True이면 마지막 수집일 무시하고 since_date부터 재수집"),
    background:   bool = Query(False, description="백그라운드 실행"),
):
    """KOSHA 전체 또는 특정 대상 수집.
    
    초기수집: POST /kosha-collect/run?since_date=2024-01-01&full_refresh=true&background=true
    증분수집: POST /kosha-collect/run  (자동으로 마지막 성공일 이후만)
    """
    targets = [target] if target else ["accident-cases", "safety-materials",
               "construction-accidents", "construction-safety-light",
               "risk-assessment", "guide"]

    async def run_all():
        for t in targets:
            try:
                # 증분수집: full_refresh=False이면 마지막 성공일 조회
                since = since_date if full_refresh else _get_last_collected(t)
                await _dispatch(t, since, full_refresh)
            except Exception as e:
                _log(t, "fail", 0, str(e)[:300])

    if background:
        background_tasks.add_task(run_all)
        return {"status": "queued", "targets": targets,
                "since_date": since_date, "full_refresh": full_refresh}

    results = []
    for t in targets:
        try:
            since = since_date if full_refresh else _get_last_collected(t)
            r = await _dispatch(t, since, full_refresh)
            results.append(r)
        except Exception as e:
            _log(t, "fail", 0, str(e)[:300])
            results.append({"target": t, "error": str(e)[:200]})
    return {"status": "done", "results": results}


async def _dispatch(target: str, since_date: str, full_refresh: bool):
    if target == "accident-cases":
        return await _collect_accident_cases(since_date, full_refresh)
    elif target == "safety-materials":
        return await _collect_safety_materials(since_date, full_refresh)
    elif target == "construction-accidents":
        return await _collect_construction_accidents(since_date, full_refresh)
    elif target == "construction-safety-light":
        return await _collect_safety_light()
    elif target == "risk-assessment":
        return await _collect_risk_assessment(since_date, full_refresh)
    elif target == "guide":
        return await _collect_guide(full_refresh)
    raise ValueError(f"Unknown target: {target}")


# 개별 엔드포인트
@router.post("/accident-cases")
async def collect_accident(
    since_date:   str  = Query(INIT_DATE),
    full_refresh: bool = Query(False)
):
    since = since_date if full_refresh else _get_last_collected("accident-cases")
    return await _collect_accident_cases(since, full_refresh)

@router.post("/safety-materials")
async def collect_materials(full_refresh: bool = Query(False)):
    return await _collect_safety_materials(full_refresh=full_refresh)

@router.post("/construction-accidents")
async def collect_const_acc(
    since_date:   str  = Query(INIT_DATE),
    full_refresh: bool = Query(False)
):
    since = since_date if full_refresh else _get_last_collected("construction-accidents")
    return await _collect_construction_accidents(since, full_refresh)

@router.post("/construction-safety-light")
async def collect_signal():
    return await _collect_safety_light()

@router.post("/risk-assessment")
async def collect_risk(
    since_date:   str  = Query(INIT_DATE),
    full_refresh: bool = Query(False)
):
    since = since_date if full_refresh else _get_last_collected("risk-assessment")
    return await _collect_risk_assessment(since, full_refresh)

@router.post("/guide")
async def collect_guide_ep(full_refresh: bool = Query(False)):
    return await _collect_guide(full_refresh)


@router.get("/status")
def collect_status(limit: int = Query(30, ge=1, le=100)):
    sb = get_supabase()
    logs = (sb.table("kosha_collect_log")
              .select("*")
              .order("collected_at", desc=True)
              .limit(limit)
              .execute())
    counts = {}
    for tbl, dbname in [
        ("accident-cases",            "kosha_accident_cases"),
        ("safety-materials",          "kosha_safety_materials"),
        ("construction-accidents",    "kosha_construction_accidents"),
        ("construction-safety-light", "kosha_construction_safety_light"),
        ("risk-assessment",           "kosha_risk_assessment"),
        ("guide",                     "kosha_guide"),
    ]:
        try:
            r = sb.table(dbname).select("id", count="exact").execute()
            counts[tbl] = r.count or 0
        except Exception:
            counts[tbl] = -1
    key_hint = (_get_service_key() or "")[:8] + "..."
    return {"status": "success", "key_hint": key_hint,
            "db_counts": counts, "recent_logs": logs.data or []}
