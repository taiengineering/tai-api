"""온보딩 체크리스트 상태 API — 섹터별 세팅 진행률 조회.

v1.0.0  2026-05-26  신규 생성
"""
from fastapi import APIRouter, Query
from uuid import UUID
from db.supabase_client import get_supabase

router = APIRouter(prefix="/onboarding", tags=["온보딩"])


@router.get("/status")
async def get_onboarding_status(
    company_id: UUID = Query(...),
    sector: str = Query("INDUSTRIAL", description="INDUSTRIAL|FACILITY|CONSTRUCTION"),
):
    sb = get_supabase()
    cid = str(company_id)

    if sector == "CONSTRUCTION":
        steps = await _construction_steps(sb, cid)
    elif sector == "FACILITY":
        steps = await _facility_steps(sb, cid)
    else:
        steps = await _industrial_steps(sb, cid)

    done = sum(1 for s in steps if s["done"])
    return {
        "status": "success",
        "data": {
            "sector": sector,
            "steps": steps,
            "done_count": done,
            "total_count": len(steps),
            "complete": done == len(steps),
        },
    }


async def _industrial_steps(sb, cid: str):
    fac = sb.table("factories").select("id", count="exact").eq("company_id", cid).eq("is_active", True).execute()
    fac_ids = [r["id"] for r in (fac.data or [])]

    proc_count = 0
    equip_count = 0
    iset_count = 0
    iitem_count = 0
    if fac_ids:
        for fid in fac_ids[:10]:
            p = sb.table("factory_process").select("id", count="exact").eq("factory_id", fid).execute()
            proc_count += (p.count or 0)
            e = sb.table("equipment_assets").select("id", count="exact").eq("factory_id", fid).execute()
            equip_count += (e.count or 0)
        iset = sb.table("inspection_sets").select("id", count="exact").eq("company_id", cid).execute()
        iset_count = iset.count or 0
        if iset_count > 0:
            iitem = sb.table("inspection_set_items").select("id", count="exact").in_("set_id", [r["id"] for r in (iset.data or [])[:20]]).execute()
            iitem_count = iitem.count or 0

    return [
        {"key": "facility", "label": "사업장·시설 등록", "desc": "관리할 사업장과 시설을 등록하세요.", "href": "factory-list.html", "done": (fac.count or 0) > 0, "count": fac.count or 0},
        {"key": "process", "label": "공정 등록", "desc": "시설의 제조·작업 공정을 등록하세요.", "href": "process-manage.html", "done": proc_count > 0, "count": proc_count},
        {"key": "equipment", "label": "설비 등록", "desc": "관리 대상 설비·기계를 등록하세요.", "href": "my-equipment.html", "done": equip_count > 0, "count": equip_count},
        {"key": "inspection_anchor", "label": "점검항목 관리", "desc": "법정·자체 점검항목을 설정하세요.", "href": "inspection-anchor.html", "done": iset_count > 0, "count": iset_count},
        {"key": "inspection_issue", "label": "점검항목 발행", "desc": "점검항목을 발행하여 일정을 시작하세요.", "href": "my-inspection.html", "done": iitem_count > 0, "count": iitem_count},
    ]


async def _facility_steps(sb, cid: str):
    fac = sb.table("factories").select("id", count="exact").eq("company_id", cid).eq("is_active", True).execute()
    fac_ids = [r["id"] for r in (fac.data or [])]

    equip_count = 0
    iset_count = 0
    iitem_count = 0
    if fac_ids:
        for fid in fac_ids[:10]:
            e = sb.table("equipment_assets").select("id", count="exact").eq("factory_id", fid).execute()
            equip_count += (e.count or 0)
        iset = sb.table("inspection_sets").select("id", count="exact").eq("company_id", cid).execute()
        iset_count = iset.count or 0
        if iset_count > 0:
            iitem = sb.table("inspection_set_items").select("id", count="exact").in_("set_id", [r["id"] for r in (iset.data or [])[:20]]).execute()
            iitem_count = iitem.count or 0

    return [
        {"key": "facility", "label": "사업장·시설 등록", "desc": "관리할 건물·시설을 등록하세요.", "href": "factory-list.html", "done": (fac.count or 0) > 0, "count": fac.count or 0},
        {"key": "equipment", "label": "설비 등록", "desc": "관리 대상 설비를 등록하세요.", "href": "my-equipment.html", "done": equip_count > 0, "count": equip_count},
        {"key": "inspection_anchor", "label": "점검항목 관리", "desc": "법정·자체 점검항목을 설정하세요.", "href": "inspection-anchor.html", "done": iset_count > 0, "count": iset_count},
        {"key": "inspection_issue", "label": "점검항목 발행", "desc": "점검항목을 발행하여 일정을 시작하세요.", "href": "my-inspection.html", "done": iitem_count > 0, "count": iitem_count},
    ]


async def _construction_steps(sb, cid: str):
    sites = sb.table("construction_sites").select("id", count="exact").eq("company_id", cid).eq("is_active", True).execute()
    site_ids = [r["id"] for r in (sites.data or [])]

    proc_count = 0
    work_count = 0
    iset_count = 0
    cinsp_count = 0
    if site_ids:
        for sid in site_ids[:10]:
            p = sb.table("construction_site_processes").select("id", count="exact").eq("site_id", sid).execute()
            proc_count += (p.count or 0)
            w = sb.table("construction_works").select("id", count="exact").eq("site_id", sid).execute()
            work_count += (w.count or 0)
            ci = sb.table("construction_inspections").select("id", count="exact").eq("site_id", sid).execute()
            cinsp_count += (ci.count or 0)
        iset = sb.table("inspection_sets").select("id", count="exact").eq("company_id", cid).execute()
        iset_count = iset.count or 0

    return [
        {"key": "site", "label": "사업장·공사장 등록", "desc": "관리할 건설현장을 등록하세요.", "href": "construction-site-list.html", "done": (sites.count or 0) > 0, "count": sites.count or 0},
        {"key": "process", "label": "공정 등록", "desc": "현장의 공정을 등록하세요.", "href": "construction-process-list.html", "done": proc_count > 0, "count": proc_count},
        {"key": "work", "label": "작업 등록", "desc": "공정별 작업을 등록하세요.", "href": "construction-work-list.html", "done": work_count > 0, "count": work_count},
        {"key": "inspection_anchor", "label": "점검항목 관리", "desc": "점검항목을 설정하세요.", "href": "construction-inspection-anchor.html", "done": iset_count > 0, "count": iset_count},
        {"key": "inspection_issue", "label": "점검항목 발행", "desc": "점검을 발행하여 안전관리를 시작하세요.", "href": "construction-inspection-list.html", "done": cinsp_count > 0, "count": cinsp_count},
    ]
