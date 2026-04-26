"""
KOSHA 데이터 수집 — DB 저장 + 크론 갱신
prefix: /kosha-collect

v1.0.0:
  POST /kosha-collect/run           전체 수집 (대상 선택 가능)
  POST /kosha-collect/accident-cases
  POST /kosha-collect/safety-materials
  POST /kosha-collect/construction-accidents
  POST /kosha-collect/construction-safety-light
  POST /kosha-collect/risk-assessment
  POST /kosha-collect/guide
  GET  /kosha-collect/status         수집 로그 확인

커론 스케줄 (수집 후 pg_cron에서 HTTP 호출):
  신호등: 매일 06:00, 12:00, 18:00 KST
  재해사례: 매일 02:00 KST
  기타: 매주 월요일 03:00 KST
"""
from __future__ import annotations
import os, logging, httpx, json
from fastapi import APIRouter, Query, BackgroundTasks
from typing import Optional
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/kosha-collect", tags=["KOSHA데이터수집"])

SERVICE_KEY = os.getenv("KOSHA_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b"))
BASE = "https://apis.data.go.kr/B552468"
MAX_ROWS = 100   # 한 페이지 최대
MAX_PAGES = 50   # 최대 페이지


# ──────────────────────────────────────────────────────────
class KoshaAPI:
    """KOSHA API 호출 헬퍼"""

    @staticmethod
    async def get(path: str, params: dict) -> dict:
        params["serviceKey"] = SERVICE_KEY
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
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


def _log(target: str, status: str, rows: int = 0, err: str = ""):
    try:
        sb = get_supabase()
        sb.table("kosha_collect_log").insert({
            "target": target, "status": status,
            "rows_upserted": rows, "error_msg": err or None
        }).execute()
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
async def _collect_accident_cases(since_year: int = 2024) -> dict:
    """국내재해사례 수집"""
    sb = get_supabase()
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
            for i, it in enumerate(items):
                # 날짜 필터 (since_year 이후만)
                dt = str(it.get("regDt") or it.get("writeDate") or "")
                if dt and dt[:4].isdigit() and int(dt[:4]) < since_year:
                    continue
                rid = str(it.get("boardNo") or it.get("bbsNo") or
                          f"{biz or 'ALL'}_{page}_{i}")
                rows.append({
                    "id":         rid,
                    "title":      it.get("title") or it.get("bbsTitle") or it.get("subject") or "",
                    "business":   it.get("business") or biz,
                    "content":    it.get("content") or it.get("bbsContent") or "",
                    "board_no":   str(it.get("boardNo") or it.get("bbsNo") or ""),
                    "reg_dt":     dt,
                    "file_url":   it.get("fileUrl") or it.get("fileLink") or "",
                    "raw_json":   it,
                })

            if rows:
                sb.table("kosha_accident_cases").upsert(rows, on_conflict="id").execute()
                total_upserted += len(rows)

            if len(items) < MAX_ROWS:
                break

    _log("accident_cases", "success", total_upserted)
    return {"target": "accident_cases", "upserted": total_upserted}


async def _collect_safety_materials(since_year: int = 2024) -> dict:
    """안전보건자료 수집"""
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
                "id":           rid,
                "title":        it.get("title") or it.get("mediaTitle") or "",
                "product_type": it.get("productType") or "",
                "industry":     it.get("industry") or "",
                "accident_type":it.get("accidentType") or "",
                "url":          it.get("url") or it.get("mediaUrl") or "",
                "raw_json":     it,
            })
        if rows:
            sb.table("kosha_safety_materials").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS:
            break

    _log("safety_materials", "success", total_upserted)
    return {"target": "safety_materials", "upserted": total_upserted}


async def _collect_construction_accidents(since_year: int = 2024) -> dict:
    """건설업 중대재해 수집"""
    sb = get_supabase()
    total_upserted = 0

    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("constDsstr01/getconstDsstr01",
                                   {"pageNo": page, "numOfRows": MAX_ROWS})
        items = KoshaAPI.items(resp)
        if not items:
            break

        rows = []
        for i, it in enumerate(items):
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
        if len(items) < MAX_ROWS:
            break

    _log("construction_accidents", "success", total_upserted)
    return {"target": "construction_accidents", "upserted": total_upserted}


async def _collect_safety_light() -> dict:
    """건설현장 안전 신호등 수집 (실시간성 높음 — 테이블 다시 쓰기)"""
    sb = get_supabase()
    total_upserted = 0
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
                "id":       rid,
                "site_nm":  it.get("siteNm") or it.get("siteName") or "",
                "sido":     it.get("sido") or "",
                "sigungu":  it.get("sigungu") or "",
                "signal":   it.get("signal") or it.get("signalColor") or "",
                "guide_dt": it.get("guideDt") or it.get("inspDate") or "",
                "guide_org":it.get("guideOrg") or it.get("orgName") or "",
                "raw_json": it,
            })
        if len(items) < MAX_ROWS:
            break

    # 신호등은 실시간 데이터 — 전체 교체
    if rows_all:
        sb.table("kosha_construction_safety_light").delete().neq("id", "__never__").execute()
        sb.table("kosha_construction_safety_light").upsert(rows_all, on_conflict="id").execute()
        total_upserted = len(rows_all)

    _log("construction_safety_light", "success", total_upserted)
    return {"target": "construction_safety_light", "upserted": total_upserted}


async def _collect_risk_assessment() -> dict:
    """위험성평가 인정사업장 수집"""
    sb = get_supabase()
    total_upserted = 0

    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("riskAssmt/getRiskAssmtAccdtInfo",
                                   {"pageNo": page, "numOfRows": MAX_ROWS})
        items = KoshaAPI.items(resp)
        if not items:
            break

        rows = []
        for i, it in enumerate(items):
            rid = str(it.get("id") or it.get("seq") or f"ra_{page}_{i}")
            rows.append({
                "id":           rid,
                "company_nm":   it.get("companyNm") or it.get("siteNm") or it.get("bizNm") or "",
                "sido":         it.get("sido") or "",
                "cert_date":    it.get("certDate") or it.get("acptDt") or "",
                "expiry_date":  it.get("expiryDate") or it.get("vlddDt") or "",
                "industry":     it.get("industry") or "",
                "labor_office": it.get("laborOffice") or it.get("labor_office") or "",
                "raw_json":     it,
            })
        if rows:
            sb.table("kosha_risk_assessment").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS:
            break

    _log("risk_assessment", "success", total_upserted)
    return {"target": "risk_assessment", "upserted": total_upserted}


async def _collect_guide() -> dict:
    """KOSHA GUIDE 수집"""
    sb = get_supabase()
    total_upserted = 0

    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get("koshaguide/getKoshaGuide",
                                   {"pageNo": page, "numOfRows": MAX_ROWS,
                                    "returnType": "json"})
        items = KoshaAPI.items(resp)
        if not items:
            break

        rows = []
        for i, it in enumerate(items):
            rid = str(it.get("guideId") or it.get("guideNo") or f"guide_{page}_{i}")
            rows.append({
                "id":           rid,
                "guide_no":     it.get("guideNo") or it.get("guide_no") or "",
                "guide_title":  it.get("guideTitle") or it.get("guideName") or it.get("title") or "",
                "category":     (it.get("category") or it.get("guideCategory") or "").upper(),
                "guide_url":    it.get("guideUrl") or it.get("url") or "",
                "regist_date":  it.get("registDate") or it.get("regDt") or "",
                "raw_json":     it,
            })
        if rows:
            sb.table("kosha_guide").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS:
            break

    _log("guide", "success", total_upserted)
    return {"target": "guide", "upserted": total_upserted}


# ──────────────────────────────────────────────────────────
COLLECTOR_MAP = {
    "accident-cases":           _collect_accident_cases,
    "safety-materials":         _collect_safety_materials,
    "construction-accidents":   _collect_construction_accidents,
    "construction-safety-light":_collect_safety_light,
    "risk-assessment":          _collect_risk_assessment,
    "guide":                    _collect_guide,
}


@router.post("/run")
async def collect_all(
    background_tasks: BackgroundTasks,
    target: Optional[str] = Query(None, description="특정 대상만 (생략 시 전체)"),
    since_year: int = Query(2024, description="수집 시작 연도"),
    background: bool = Query(False, description="True시 백그라운드 실행")
):
    """
    KOSHA 전체 데이터 수집. pg_cron 및 수동 실행 모두 지원.
    """
    targets = [target] if target and target in COLLECTOR_MAP else list(COLLECTOR_MAP.keys())

    if background:
        async def run():
            for t in targets:
                fn = COLLECTOR_MAP[t]
                try:
                    if t in ("construction-safety-light", "risk-assessment", "guide", "safety-materials"):
                        await fn()
                    else:
                        await fn(since_year)
                except Exception as e:
                    _log(t, "fail", 0, str(e)[:300])
        background_tasks.add_task(run)
        return {"status": "queued", "targets": targets}

    # 동기 실행
    results = []
    for t in targets:
        fn = COLLECTOR_MAP[t]
        try:
            if t in ("construction-safety-light", "risk-assessment", "guide", "safety-materials"):
                r = await fn()
            else:
                r = await fn(since_year)
            results.append(r)
        except Exception as e:
            _log(t, "fail", 0, str(e)[:300])
            results.append({"target": t, "error": str(e)[:200]})

    return {"status": "done", "results": results}


@router.post("/accident-cases")
async def collect_accident(since_year: int = Query(2024)):
    return await _collect_accident_cases(since_year)

@router.post("/safety-materials")
async def collect_materials():
    return await _collect_safety_materials()

@router.post("/construction-accidents")
async def collect_const_acc(since_year: int = Query(2024)):
    return await _collect_construction_accidents(since_year)

@router.post("/construction-safety-light")
async def collect_signal():
    return await _collect_safety_light()

@router.post("/risk-assessment")
async def collect_risk():
    return await _collect_risk_assessment()

@router.post("/guide")
async def collect_guide():
    return await _collect_guide()


@router.get("/status")
def collect_status(limit: int = Query(30, ge=1, le=100)):
    """KOSHA 수집 로그 조회"""
    sb = get_supabase()
    logs = (sb.table("kosha_collect_log")
              .select("*")
              .order("collected_at", desc=True)
              .limit(limit)
              .execute())
    counts = {}
    for tbl, dbname in [
        ("accident-cases",           "kosha_accident_cases"),
        ("safety-materials",         "kosha_safety_materials"),
        ("construction-accidents",   "kosha_construction_accidents"),
        ("construction-safety-light","kosha_construction_safety_light"),
        ("risk-assessment",          "kosha_risk_assessment"),
        ("guide",                    "kosha_guide"),
    ]:
        try:
            r = sb.table(dbname).select("id", count="exact").execute()
            counts[tbl] = r.count or 0
        except Exception:
            counts[tbl] = -1

    return {"status": "success", "db_counts": counts, "recent_logs": logs.data or []}
