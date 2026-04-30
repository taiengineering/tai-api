"""
KOSHA 데이터 수집 — DB 저장 + 크론 갱신
prefix: /kosha-collect

v1.4.0 (2026-04-30):
  [FIX] KoshaAPI.items() — KOSHA API가 {"items":{"item":[...]}} 구조로 반환하는 문제 해결
  [FIX] safety-materials 필드명 변경 대응 (MED_SJ_NM, MED_URL, MED_COMPY_DY)
  [FIX] accident-cases callApiId 구조 변경 대응

v1.3.1: _log() 잘못된 키워드인자 버그 수정
v1.3.0: 포털 문서 기반 callApiId 추가
"""
from __future__ import annotations
import os, logging, httpx, json, hashlib
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
MAX_PAGES = 100
INIT_DATE = "2024-01-01"


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
                    for items_el in root.findall(".//items"):
                        for item_el in items_el:
                            item = {c.tag: c.text or "" for c in item_el}
                            if item:
                                items.append(item)
                    return {"body": {
                        "items": items,
                        "totalCount": int(root.findtext(".//totalCount") or 0)
                    }}
        except Exception as e:
            log.error("[KOSHA] %s 호출 실패: %s", path, e)
            return {"body": {"items": [], "totalCount": 0}}

    @staticmethod
    def items(resp: dict) -> list:
        """v1.4.0: KOSHA API가 {"items":{"item":[...]}} 구조로 반환하는 경우 처리"""
        body = resp.get("body") or resp.get("data") or {}
        if isinstance(body, dict):
            it = body.get("items", [])
            if isinstance(it, list):
                return it
            if isinstance(it, dict):
                # {"item": [...]} 또는 {"item": {...}} 패턴
                inner = it.get("item", [])
                if isinstance(inner, list):
                    return inner
                if isinstance(inner, dict):
                    return [inner]  # 단일 객체
                return []
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
            "rows_upserted": rows,
            "error_msg": err or None,
        }).execute()
    except Exception:
        pass


def _get_last_collected(target: str) -> Optional[str]:
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
            return r.data[0]["collected_at"][:10]
    except Exception:
        pass
    return INIT_DATE


def _parse_date(val: str) -> Optional[str]:
    if not val: return None
    v = str(val).strip().replace("/", "-")
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return v[:10] if len(v) >= 10 else v


def _after_since(date_str: str, since_date: str) -> bool:
    d = _parse_date(date_str)
    if not d: return True
    return d >= since_date


def _make_id(prefix: str, *parts) -> str:
    """URL 등으로부터 안정적인 ID 생성"""
    raw = "|".join(str(p) for p in parts if p)
    if raw:
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


# ─────────────────────────────────────────────────────
# 수집함수
# ─────────────────────────────────────────────────────

async def _collect_accident_cases(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    """
    국내재해사례 게시판 조회서비스
    data.go.kr에서 활용신청 필요 (APICODE_ERROR 90 발생 시)
    """
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        params = {
            "pageNo": page, "numOfRows": MAX_ROWS
        }
        resp  = await KoshaAPI.get("disaster_api02/getdisaster_api02", params)
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            # 필드명이 대문자로 변경되었을 수 있으므로 둘 다 체크
            dt = str(it.get("regDt") or it.get("REG_DT") or it.get("writeDate") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("boardNo") or it.get("BOARD_NO") or it.get("bbsNo") or _make_id("ac", page, i))
            rows.append({
                "id": rid,
                "title": it.get("title") or it.get("TITLE") or it.get("bbsTitle") or it.get("BBS_TITLE") or "",
                "business": it.get("business") or it.get("BUSINESS") or "",
                "content": it.get("content") or it.get("CONTENT") or it.get("bbsContent") or "",
                "board_no": rid,
                "reg_dt": dt,
                "file_url": it.get("fileUrl") or it.get("FILE_URL") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_accident_cases").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS: break
    _log("accident_cases", "success", total_upserted)
    return {"target": "accident_cases", "since": since, "upserted": total_upserted}


async def _collect_safety_materials(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    """
    v1.4.0: 필드명 변경 대응
    기존: mediaId, title, productType, industry, accidentType, url
    변경: MED_SJ_NM(제목), MED_URL(URL), MED_COMPY_DY(등록일)
    callApiId=1030
    """
    sb = get_supabase()
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "selectMediaList01/getselectMediaList01",
            {"callApiId": "1030", "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        rows = []
        for i, it in enumerate(items):
            # 새 필드명 (MED_*) + 기존 필드명 모두 체크
            title = it.get("MED_SJ_NM") or it.get("title") or it.get("mediaTitle") or ""
            url   = it.get("MED_URL") or it.get("url") or it.get("mediaUrl") or ""
            reg_dt = it.get("MED_COMPY_DY") or it.get("regDt") or ""
            rid = it.get("mediaId") or it.get("MED_SEQ") or _make_id("mat", url, title)
            rows.append({
                "id": str(rid),
                "title": title,
                "product_type": it.get("productType") or it.get("MED_CL_NM") or "",
                "industry": it.get("industry") or "",
                "accident_type": it.get("accidentType") or "",
                "url": url,
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_safety_materials").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if len(items) < MAX_ROWS: break
    _log("safety_materials", "success", total_upserted)
    return {"target": "safety_materials", "upserted": total_upserted}


async def _collect_construction_accidents(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    """callApiId=1010"""
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "constDsstr01/getconstDsstr01",
            {"callApiId": "1010", "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("occurrenceDate") or it.get("dsstrDt") or it.get("DSSTR_DT") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("id") or it.get("seq") or it.get("SEQ") or _make_id("ca", page, i))
            rows.append({
                "id": rid,
                "accident_type": it.get("accidentType") or it.get("dsstrKnd") or it.get("DSSTR_KND") or "",
                "work_type": it.get("workType") or it.get("workKnd") or it.get("WORK_KND") or "",
                "causative": it.get("causative") or it.get("crtrFtr") or it.get("CRTR_FTR") or "",
                "occurrence_date": dt,
                "accident_summary": it.get("accidentSummary") or it.get("dsstrOutl") or it.get("DSSTR_OUTL") or "",
                "risk_reduction": it.get("riskReduction") or it.get("rskRdcMsr") or it.get("RSK_RDC_MSR") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_construction_accidents").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS: break
    _log("construction_accidents", "success", total_upserted)
    return {"target": "construction_accidents", "since": since, "upserted": total_upserted}


async def _collect_safety_light(full_refresh: bool = True) -> dict:
    """constplan/getconstplan + callApiId=1020"""
    sb = get_supabase()
    rows_all: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "constplan/getconstplan",
            {"callApiId": "1020", "pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        for i, it in enumerate(items):
            rid = str(it.get("id") or it.get("siteId") or it.get("SITE_ID") or it.get("sno") or _make_id("sl", page, i))
            rows_all.append({
                "id": rid,
                "site_nm": it.get("siteNm") or it.get("SITE_NM") or it.get("siteName") or "",
                "sido": it.get("sido") or it.get("SIDO") or "",
                "sigungu": it.get("sigungu") or it.get("SIGUNGU") or "",
                "signal": it.get("signal") or it.get("SIGNAL") or it.get("signalColor") or "",
                "guide_dt": it.get("guideDt") or it.get("GUIDE_DT") or it.get("inspDate") or "",
                "guide_org": it.get("guideOrg") or it.get("GUIDE_ORG") or it.get("orgName") or "",
                "raw_json": it,
            })
        if len(items) < MAX_ROWS: break
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
        resp  = await KoshaAPI.get(
            "riskAssmt/getRiskAssmtAccdtInfo",
            {"pageNo": page, "numOfRows": MAX_ROWS}
        )
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
            dt = str(it.get("certDate") or it.get("acptDt") or it.get("ACPT_DT") or "")
            if dt and not _after_since(dt, since):
                stop_early = True
                continue
            rid = str(it.get("id") or it.get("seq") or it.get("SEQ") or _make_id("ra", page, i))
            rows.append({
                "id": rid,
                "company_nm": it.get("companyNm") or it.get("COMPANY_NM") or it.get("siteNm") or "",
                "sido": it.get("sido") or it.get("SIDO") or "",
                "cert_date": dt,
                "expiry_date": it.get("expiryDate") or it.get("vlddDt") or it.get("VLDD_DT") or "",
                "industry": it.get("industry") or it.get("INDUSTRY") or "",
                "labor_office": it.get("laborOffice") or it.get("LABOR_OFFICE") or "",
                "raw_json": it,
            })
        if rows:
            sb.table("kosha_risk_assessment").upsert(rows, on_conflict="id").execute()
            total_upserted += len(rows)
        if stop_early or len(items) < MAX_ROWS: break
    _log("risk_assessment", "success", total_upserted)
    return {"target": "risk_assessment", "since": since, "upserted": total_upserted}


async def _collect_guide(full_refresh: bool = False) -> dict:
    """
    KOSHA GUIDE API 폐기 확인.
    대체: 안전보건법령 스마트검색(srch/smartSearch)으로 KOSHA GUIDE 질의 수집.
    """
    sb = get_supabase()
    total_upserted = 0
    keywords = ["KOSHA GUIDE", "안전보건기술지침"]
    for kw in keywords:
        for page in range(1, 20):
            resp = await KoshaAPI.get(
                "srch/smartSearch",
                {"keyword": kw, "pageNo": page, "numOfRows": MAX_ROWS, "returnType": "json"}
            )
            items = KoshaAPI.items(resp)
            if not items: break
            rows = []
            for i, it in enumerate(items):
                rid = str(it.get("guideNo") or it.get("docNo") or it.get("id") or _make_id("guide", kw, page, i))
                rows.append({
                    "id": rid,
                    "guide_no": it.get("guideNo") or it.get("docNo") or "",
                    "guide_title": it.get("title") or it.get("guideTitle") or "",
                    "category": (it.get("category") or "").upper(),
                    "guide_url": it.get("url") or it.get("fileUrl") or "",
                    "regist_date": it.get("regDt") or it.get("date") or "",
                    "raw_json": it,
                })
            if rows:
                sb.table("kosha_guide").upsert(rows, on_conflict="id").execute()
                total_upserted += len(rows)
            if len(items) < MAX_ROWS: break
    _log("guide", "success", total_upserted)
    return {"target": "guide", "upserted": total_upserted}


# ─────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────

@router.post("/run")
async def collect_all(
    background_tasks: BackgroundTasks,
    target:       Optional[str] = Query(None),
    since_date:   str  = Query(INIT_DATE),
    full_refresh: bool = Query(False),
    background:   bool = Query(False),
):
    targets = [target] if target else [
        "accident-cases", "safety-materials", "construction-accidents",
        "construction-safety-light", "risk-assessment", "guide"
    ]

    async def run_all():
        for t in targets:
            try:
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
    if target == "accident-cases":            return await _collect_accident_cases(since_date, full_refresh)
    elif target == "safety-materials":        return await _collect_safety_materials(since_date, full_refresh)
    elif target == "construction-accidents":  return await _collect_construction_accidents(since_date, full_refresh)
    elif target == "construction-safety-light": return await _collect_safety_light()
    elif target == "risk-assessment":         return await _collect_risk_assessment(since_date, full_refresh)
    elif target == "guide":                   return await _collect_guide(full_refresh)
    raise ValueError(f"Unknown target: {target}")


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
    return {"status": "success",
            "db_counts": counts, "recent_logs": logs.data or []}
