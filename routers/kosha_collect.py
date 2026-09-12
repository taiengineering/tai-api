"""
KOSHA 데이터 수집 — DB 저장 + 크론 갱신
prefix: /kosha-collect

v1.8.0 (2026-09-13):
  [OBJ-KG] _collect_guide() → services.kosha_guide_sync full-set atomic current.
        callApiId=1050 고정(주입 불가). dry_run 지원. page-by-page current 제거.
        라이브 probe에서 Railway kr_get 경로로 GUIDE JSON 확인.
        과거 Cafe24-only 주석은 인프라 추정이므로 재고정하지 않는다.

v1.7.0 (2026-08-10):
  [FIX] _collect_guide() 신 KOSHA GUIDE 전용 API 전환 — kosha_guide 0건 해소.
        폐기된 srch/smartSearch 키워드 우회 → getKoshaGuide(koshaguide) 전용 API.
        callApiId=1050 필수. 응답 body.items.item[] (techGdlnNm/No/OfancYmd/fileDownloadUrl).

v1.6.0 (2026-05-02):
  [FIX] MAX_PAGES 100→500 (10,000건 한도 해제)
  [ADD] _collect_safety_materials()에 start_page 파라미터 추가
  [ADD] /run 엔드포인트에 start_page 쿼리 파라미터 추가 (이어받기 가능)

v1.5.0 (2026-04-30):
  [ADD] _classify_material() — 제목 기반 자동 카테고리/업종 분류
  [ADD] _collect_safety_materials()에 수집 시 category/sector 자동 적용

v1.4.0: KoshaAPI.items() 파싱 + 필드명 변경 대응
v1.3.1: _log() 버그 수정
v1.3.0: callApiId 추가
"""
from __future__ import annotations
import os, logging, httpx, json, hashlib, re, asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query, BackgroundTasks
from typing import Optional
from db.supabase_client import get_supabase
from services.kr_public_api import kr_get
from services.kosha_safety_material_sync import (
    kosha_service_key as _get_service_key,
    make_id as _make_id,
    media_list_params,
    sync_safety_materials,
    SupabaseSnapshotStore,
)
from services.kosha_safety_material_enrichment import dry_run_plan, run_one_batch
from services.kosha_safety_materials.enrichment import snapshot_precondition
from services.kosha_safety_materials.writer import SupabaseStore as EnrichmentStore
from services.kosha_guide_sync import sync_kosha_guides

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/kosha-collect", tags=["KOSHA데이터수집"])

BASE      = "https://apis.data.go.kr/B552468"
MAX_ROWS  = 100
MAX_PAGES = 500   # v1.6.0: 100→500 (10,000건 한도 해제. 실 totalCount 기반으로 자동 중단됨)
INIT_DATE = "2024-01-01"


def _parse_kosha_text(text: str) -> dict:
    """KOSHA 응답 텍스트 → dict. JSON 우선, 실패 시 XML 파싱(기존 동작 유지)."""
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


class KoshaAPI:
    @staticmethod
    async def get(path: str, params: dict) -> dict:
        params["serviceKey"] = _get_service_key()
        url = f"{BASE}/{path}"
        try:
            status, text = await asyncio.to_thread(kr_get, url, params=params, timeout=30)
            return _parse_kosha_text(text)
        except Exception as e:
            log.error("[KOSHA] %s 호출 실패: %s", path, e)
            return {"body": {"items": [], "totalCount": 0}}

    @staticmethod
    def items(resp: dict) -> list:
        body = resp.get("body") or resp.get("data") or {}
        if isinstance(body, dict):
            it = body.get("items", [])
            if isinstance(it, list):
                return it
            if isinstance(it, dict):
                inner = it.get("item", [])
                if isinstance(inner, list):
                    return inner
                if isinstance(inner, dict):
                    return [inner]
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


# ─────────────────────────────────────────────────────
# 수집함수
# ─────────────────────────────────────────────────────

async def _collect_accident_cases(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        params = {"callApiId": "1040", "pageNo": page, "numOfRows": MAX_ROWS}
        resp  = await KoshaAPI.get("disaster_api02/getdisaster_api02", params)
        items = KoshaAPI.items(resp)
        if not items: break
        rows, stop_early = [], False
        for i, it in enumerate(items):
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


async def _fetch_safety_materials_page(page_no: int):
    params = media_list_params(page_no, MAX_ROWS)
    resp = await KoshaAPI.get("selectMediaList01/getselectMediaList01", params)
    return KoshaAPI.items(resp), KoshaAPI.total(resp)


async def _collect_safety_materials(
    since_date: str = INIT_DATE,
    full_refresh: bool = False,
    start_page: int = 1,
    dry_run: bool = True,
) -> dict:
    """Current snapshot sync. start_page must be 1. Default dry_run=True (no DML).

    Historical start_page continuation is not a valid current snapshot.
    """
    del since_date, full_refresh  # snapshot is always a full official set
    store = SupabaseSnapshotStore()
    result = await sync_safety_materials(
        fetch_page=_fetch_safety_materials_page,
        store=store,
        dry_run=dry_run,
        start_page=start_page,
        max_pages=MAX_PAGES,
    )
    inserted = int(result.get("catalog_dml") or 0)
    status = result.get("status")
    if status in ("COMPLETED", "SNAPSHOT_NO_CHANGE", "DRY_RUN"):
        _log("safety_materials", "success", inserted)
    else:
        _log("safety_materials", "fail", inserted, str(result.get("failure_reason") or status)[:300])
    return {"target": "safety_materials", "start_page": start_page, "upserted": inserted, **result}


def _collect_safety_material_details(dry_run: bool = True, batch_size: int = 100) -> dict:
    """One batch of current-membership detail enrichment. Default dry_run=True."""
    store = EnrichmentStore()
    if dry_run:
        plan = dry_run_plan(store, batch_size=batch_size)
        _log("safety_material_details", "success", 0)
        return {"target": "safety_material_details", **plan}
    pre = snapshot_precondition(store)
    result = run_one_batch(
        store,
        run_snapshot_id=pre["snapshot"]["id"],
        batch_size=batch_size,
        dry_run=False,
    )
    inserted = int(result.get("new_detail_rows") or 0)
    status = result.get("status")
    if status in ("BATCH_OK", "FULL_SWEEP_COMPLETE"):
        _log("safety_material_details", "success", inserted)
    else:
        _log("safety_material_details", "fail", inserted, str(result.get("stop_reason") or status)[:300])
    return {"target": "safety_material_details", **result}


async def _collect_construction_accidents(since_date: str = INIT_DATE, full_refresh: bool = False) -> dict:
    sb = get_supabase()
    since = INIT_DATE if full_refresh else since_date
    total_upserted = 0
    for page in range(1, MAX_PAGES + 1):
        resp  = await KoshaAPI.get(
            "constDsstr01/getconstDsstr01",
            {"callApiId": "1050", "pageNo": page, "numOfRows": MAX_ROWS}
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


async def _collect_guide(full_refresh: bool = False, dry_run: bool = True) -> dict:
    """GUIDE Source Adapter wrapper. Catalog table is kosha_guide.

    Current promotion is latest COMPLETED snapshot membership, not page-by-page
    upsert. callApiId is fixed at 1050 inside kosha_guide_sync (not injectable).
    Missing techGdlnNo is REJECT — no fallback id generation.
    """
    del full_refresh
    from dataclasses import asdict
    result = await asyncio.to_thread(sync_kosha_guides, dry_run=dry_run)
    payload = asdict(result)
    upserted = int(result.catalog_upserted or 0)
    payload["upserted"] = upserted
    if result.status in ("COMPLETED", "SNAPSHOT_NO_CHANGE", "DRY_RUN"):
        _log("guide", "success", upserted)
    else:
        _log("guide", "fail", upserted, str(result.failure_reason or result.status)[:300])
    return payload


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
    start_page:   int  = Query(1, ge=1, description="safety-materials 이어받기용 시작 페이지 (snapshot path는 1만 유효)"),
    dry_run:      bool = Query(True, description="safety-materials / guide: True면 업무 DML 0"),
    batch_size:   int  = Query(100, ge=1, le=200, description="safety-material-details 한 호출당 건수"),
):
    targets = [target] if target else [
        "accident-cases", "safety-materials", "construction-accidents",
        "construction-safety-light", "risk-assessment", "guide"
    ]

    async def run_all():
        for t in targets:
            try:
                since = since_date if full_refresh else _get_last_collected(t)
                await _dispatch(t, since, full_refresh, start_page, dry_run, batch_size)
            except Exception as e:
                _log(t, "fail", 0, str(e)[:300])

    if background:
        background_tasks.add_task(run_all)
        return {"status": "queued", "targets": targets,
                "since_date": since_date, "full_refresh": full_refresh,
                "start_page": start_page, "dry_run": dry_run}

    results = []
    for t in targets:
        try:
            since = since_date if full_refresh else _get_last_collected(t)
            r = await _dispatch(t, since, full_refresh, start_page, dry_run, batch_size)
            results.append(r)
        except Exception as e:
            _log(t, "fail", 0, str(e)[:300])
            results.append({"target": t, "error": str(e)[:200]})
    return {"status": "done", "results": results}


async def _dispatch(target: str, since_date: str, full_refresh: bool, start_page: int = 1, dry_run: bool = True, batch_size: int = 100):
    if target == "accident-cases":            return await _collect_accident_cases(since_date, full_refresh)
    elif target == "safety-materials":        return await _collect_safety_materials(since_date, full_refresh, start_page, dry_run)
    elif target == "safety-material-details": return _collect_safety_material_details(dry_run, batch_size)
    elif target == "construction-accidents":  return await _collect_construction_accidents(since_date, full_refresh)
    elif target == "construction-safety-light": return await _collect_safety_light()
    elif target == "risk-assessment":         return await _collect_risk_assessment(since_date, full_refresh)
    elif target == "guide":                   return await _collect_guide(full_refresh, dry_run)
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
