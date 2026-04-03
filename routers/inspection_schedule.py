"""
일정관리 API — inspection_sets 기준일·주기 관리
작업지시서: TAI_작업지시서_일정관리_백엔드_20260403.md

prefix: /inspection-schedule

Endpoints
---------
GET   /inspection-schedule/rules                       마스터 룰 목록 (INSPECT)
GET   /inspection-schedule/rules/{rule_id}/factories   룰별 시설 생성현황
POST  /inspection-schedule/generate                    선택 룰+시설 → inspection_sets 일괄생성
GET   /inspection-schedule/sets/summary-by-rule        룰 커버리지 요약 카드
GET   /inspection-schedule/summary
GET   /inspection-schedule/sets
GET   /inspection-schedule/sets/{id}
PATCH /inspection-schedule/sets/{id}
POST  /inspection-schedule/sets/{id}/confirm-anchor

※ tai-api는 asyncpg `get_db` 대신 Supabase(`get_supabase`)를 사용한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.inspection_sets import _calc_next_date
from routers.legal_engine import CYCLE_CODE_MAP, INSPECTION_CYCLE_UNIT_MAP, get_sector_groups

router = APIRouter(prefix="/inspection-schedule", tags=["inspection-schedule"])

# 목록 정렬 시 한 번에 가져올 최대 행 수 (메모리 정렬)
_MAX_LIST_FETCH = 10000


def _to_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val)[:10]
    return date.fromisoformat(s)


def _serialize_patch_row(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, date) and not isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ── Pydantic 스키마 ────────────────────────────────────────────────────────────


class InspectionSetPatch(BaseModel):
    cycle_unit: Optional[str] = None
    cycle_value: Optional[int] = None
    schedule_anchor_date: Optional[date] = None
    cycle_base_type: Optional[str] = None
    cycle_weekday: Optional[int] = None
    cycle_month_day: Optional[int] = None
    is_month_end: Optional[bool] = None
    holiday_process_type: Optional[str] = None
    description: Optional[str] = None
    schedule_end_date: Optional[date] = None
    custom_cycle_value: Optional[int] = None
    custom_cycle_unit: Optional[str] = None
    custom_description: Optional[str] = None


class ConfirmAnchorBody(BaseModel):
    anchor_date: date


class GenerateScheduleSetsBody(BaseModel):
    rule_id: str = Field(..., description="master_building_legal_rules.rule_id")
    factory_ids: List[str] = Field(default_factory=list)


def _cycle_label_from_master(m: dict) -> str:
    code = str(m.get("inspection_cycle_unit_code") or "")
    if code in INSPECTION_CYCLE_UNIT_MAP:
        return INSPECTION_CYCLE_UNIT_MAP[code]
    unit_std = (m.get("cycle_unit_std") or "").lower()
    umap = {"year": "년", "month": "개월", "day": "일", "week": "주"}
    cv = int(m.get("inspection_cycle_value") or 1)
    return f"{umap.get(unit_std, unit_std or '주기')} {cv}"


def _build_insert_row_from_master(m: dict, company_id: Optional[str], factory_id: str) -> dict:
    """legal_engine.create_inspection_sets_from_legal 와 동일 단일 룰 행 생성."""
    law_name = m.get("law_name") or ""
    law_article = m.get("law_article") or ""
    cycle_unit_code = str(m.get("inspection_cycle_unit_code") or "")
    if cycle_unit_code in CYCLE_CODE_MAP:
        cycle_unit, cycle_value = CYCLE_CODE_MAP[cycle_unit_code]
    else:
        cycle_unit_std = (m.get("cycle_unit_std") or "").lower()
        UNIT_STD_MAP = {"year": "year", "month": "month", "day": "day", "week": "week"}
        cycle_unit = UNIT_STD_MAP.get(cycle_unit_std, "year")
        cycle_value = int(m.get("inspection_cycle_value") or 1)
    _unit_label = "년" if cycle_unit == "year" else "개월"
    return {
        "company_id": company_id,
        "factory_id": factory_id,
        "inspection_set_name": f"{law_name} 점검",
        "inspection_set_code": m.get("rule_id"),
        "legal_rule_id": m.get("rule_id"),
        "law_name": law_name,
        "law_article": law_article,
        "cycle_unit": cycle_unit,
        "cycle_value": cycle_value,
        "cycle_base_type": m.get("cycle_base_type") or "LAST_INSPECTION",
        "cycle_base_guide": m.get("cycle_base_guide")
        or (f"마지막 점검일로부터 {cycle_value}{_unit_label}마다"),
        "description": (m.get("inspection_required") or "")[:2000],
        "source": "LEGAL_ENGINE",
        "is_active": True,
        "anchor_confirmed": False,
        "status_code": "PENDING_ANCHOR",
    }


# ── GET /inspection-schedule/rules (INSPECT 마스터 룰) ────────────────────────


@router.get("/rules")
def list_inspect_master_rules(
    sector: Optional[str] = Query(
        None,
        description="BUILDING | MANUFACTURING | CONSTRUCTION | SPECIAL_FACILITY ... — 해당 섹터군 룰만",
    ),
):
    """obligation_type=INSPECT 인 마스터 룰 목록 (일정 생성 탭 좌측)."""
    supabase = get_supabase()
    res = (
        supabase.table("master_building_legal_rules")
        .select(
            "rule_id, law_name, law_article, sector, "
            "inspection_cycle_value, inspection_cycle_unit_code, cycle_unit_std, "
            "cycle_base_type, cycle_base_guide, inspection_required"
        )
        .eq("is_active", True)
        .eq("obligation_type", "INSPECT")
        .execute()
    )
    rows = list(res.data or [])
    if sector:
        groups = set(get_sector_groups(sector.strip().upper()))
        rows = [r for r in rows if (r.get("sector") or "") in groups]

    items = []
    for r in rows:
        items.append(
            {
                **r,
                "cycle_label": _cycle_label_from_master(r),
            }
        )
    items.sort(key=lambda x: ((x.get("law_name") or ""), (x.get("law_article") or ""), (x.get("rule_id") or "")))
    return {"status": "success", "data": {"items": items, "total": len(items)}}


# ── GET /inspection-schedule/rules/{rule_id}/factories ──────────────────────


@router.get("/rules/{rule_id}/factories")
def list_factories_schedule_status_for_rule(
    rule_id: str,
    site_type: Optional[str] = Query(None, description="시설 site_type 필터 (예: INDUSTRY)"),
):
    """룰별 시설 목록 + 해당 룰에 대한 inspection_sets 존재 여부."""
    supabase = get_supabase()
    mres = (
        supabase.table("master_building_legal_rules")
        .select("rule_id")
        .eq("rule_id", rule_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not mres.data:
        raise HTTPException(status_code=404, detail="마스터 룰을 찾을 수 없습니다.")

    fq = supabase.table("factories").select("id, factory_name, site_type, company_id").eq("is_active", True)
    if site_type:
        fq = fq.eq("site_type", site_type)
    fres = fq.order("factory_name").limit(8000).execute()
    facs = fres.data or []

    sets_res = (
        supabase.table("inspection_sets")
        .select("id, factory_id, status_code")
        .eq("legal_rule_id", rule_id)
        .eq("is_active", True)
        .execute()
    )
    by_fac = {str(s["factory_id"]): s for s in (sets_res.data or [])}

    items = []
    for f in facs:
        fid = str(f["id"])
        row = by_fac.get(fid)
        if not row:
            items.append(
                {
                    "factory_id": fid,
                    "factory_name": f.get("factory_name") or f.get("name") or "-",
                    "site_type": f.get("site_type") or "-",
                    "inspection_set_id": None,
                    "schedule_status": "none",
                    "status_label": "미생성",
                }
            )
        else:
            st = row.get("status_code") or ""
            items.append(
                {
                    "factory_id": fid,
                    "factory_name": f.get("factory_name") or f.get("name") or "-",
                    "site_type": f.get("site_type") or "-",
                    "inspection_set_id": row.get("id"),
                    "schedule_status": st,
                    "status_label": "기준일 필요"
                    if st == "PENDING_ANCHOR"
                    else ("활성" if st in ("ACTIVE", "UPCOMING") else st),
                }
            )
    return {"status": "success", "data": {"items": items, "total": len(items)}}


# ── POST /inspection-schedule/generate ────────────────────────────────────────


@router.post("/generate")
def generate_inspection_sets_for_rule(body: GenerateScheduleSetsBody):
    """선택 룰 + 시설 → LEGAL_ENGINE inspection_sets 일괄 생성 (미존재 시만)."""
    supabase = get_supabase()
    rule_id = (body.rule_id or "").strip()
    if not rule_id:
        raise HTTPException(status_code=422, detail="rule_id가 필요합니다.")
    ids = [str(x).strip() for x in (body.factory_ids or []) if str(x).strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="factory_ids가 비었습니다.")

    mres = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("rule_id", rule_id)
        .eq("is_active", True)
        .eq("obligation_type", "INSPECT")
        .limit(1)
        .execute()
    )
    if not mres.data:
        raise HTTPException(status_code=404, detail="INSPECT 마스터 룰을 찾을 수 없습니다.")
    master = mres.data[0]

    existing = (
        supabase.table("inspection_sets")
        .select("factory_id")
        .eq("legal_rule_id", rule_id)
        .eq("source", "LEGAL_ENGINE")
        .eq("is_active", True)
        .in_("factory_id", ids)
        .execute()
    )
    have = {str(r["factory_id"]) for r in (existing.data or [])}

    insert_rows: List[dict] = []
    skipped = 0
    for fid in ids:
        if fid in have:
            skipped += 1
            continue
        fac = (
            supabase.table("factories")
            .select("company_id")
            .eq("id", fid)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not fac.data:
            skipped += 1
            continue
        company_id = fac.data[0].get("company_id")
        insert_rows.append(_build_insert_row_from_master(master, company_id, fid))

    created = 0
    for i in range(0, len(insert_rows), 20):
        chunk = insert_rows[i : i + 20]
        ins = supabase.table("inspection_sets").insert(chunk).execute()
        created += len(ins.data or [])

    return {
        "status": "success",
        "message": f"생성 {created}건, 기존 스킵 {skipped}건",
        "data": {"created": created, "skipped": skipped, "rule_id": rule_id},
    }


# ── GET /inspection-schedule/sets/summary-by-rule ────────────────────────────


@router.get("/sets/summary-by-rule")
def get_sets_summary_by_rule(
    company_id: Optional[str] = Query(None),
):
    """
    상단 요약 카드 — 룰 커버리지.
    INSPECT 마스터 룰 전체 수 vs 실제 inspection_sets 에 사용된 룰 수 비교.
    """
    supabase = get_supabase()

    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("rule_id", count="exact")
        .eq("obligation_type", "INSPECT")
        .eq("is_active", True)
        .execute()
    )
    total_rules = rules_res.count or 0

    q = (
        supabase.table("inspection_sets")
        .select("legal_rule_id, factory_id, status_code")
        .eq("source", "LEGAL_ENGINE")
        .eq("is_active", True)
    )
    if company_id:
        q = q.eq("company_id", company_id)
    sets_res = q.execute()
    sets = sets_res.data or []

    used_rules = {s["legal_rule_id"] for s in sets if s.get("legal_rule_id")}
    covered_factories = {s["factory_id"] for s in sets if s.get("factory_id")}

    pending = sum(1 for s in sets if s.get("status_code") == "PENDING_ANCHOR")
    active = sum(1 for s in sets if s.get("status_code") in ("ACTIVE", "UPCOMING"))

    return {
        "status": "success",
        "data": {
            "total_rules": total_rules,
            "used_rules": len(used_rules),
            "coverage_pct": round(len(used_rules) / total_rules * 100, 1) if total_rules else 0,
            "total_sets": len(sets),
            "pending_anchor": pending,
            "active": active,
            "covered_factories": len(covered_factories),
        },
    }


# ── GET /inspection-schedule/summary ──────────────────────────────────────────


@router.get("/summary")
def get_inspection_schedule_summary(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
):
    """
    상단 요약 카드 집계
      total          전체 수
      pending_anchor 기준일 미확정 (PENDING_ANCHOR)
      active         활성 (ACTIVE / UPCOMING)
      overdue        next_planned_date < today (active 한정)
      upcoming_7d    next_planned_date ≤ today+7 (active 한정)
    """
    supabase = get_supabase()
    today = date.today()
    today_plus_7 = today + timedelta(days=7)

    q = supabase.table("inspection_sets").select(
        "id, status_code, next_planned_date, source", count="exact"
    ).eq("is_active", True)
    if factory_id:
        q = q.eq("factory_id", factory_id)
    if company_id:
        q = q.eq("company_id", company_id)

    res = q.execute()
    rows = res.data or []

    total = len(rows)
    pending_anchor = sum(1 for r in rows if r.get("status_code") == "PENDING_ANCHOR")
    active_codes = ("ACTIVE", "UPCOMING")
    active = sum(1 for r in rows if r.get("status_code") in active_codes)

    overdue = 0
    upcoming_7d = 0
    for r in rows:
        st = r.get("status_code") or ""
        if st not in active_codes:
            continue
        npd = _to_date(r.get("next_planned_date"))
        if npd is None:
            continue
        if npd < today:
            overdue += 1
        if today <= npd <= today_plus_7:
            upcoming_7d += 1

    legal_engine = sum(1 for r in rows if (r.get("source") or "") == "LEGAL_ENGINE")

    return {
        "status": "success",
        "data": {
            "total": total,
            "pending_anchor": pending_anchor,
            "active": active,
            "legal_engine": legal_engine,
            "overdue": overdue,
            "upcoming_7d": upcoming_7d,
        },
    }


# ── GET /inspection-schedule/sets ─────────────────────────────────────────────


def _enrich_factory_names(supabase, rows: list) -> None:
    ids = list({str(r["factory_id"]) for r in rows if r.get("factory_id")})
    if not ids:
        for r in rows:
            r["factory_name"] = "-"
        return
    fr = supabase.table("factories").select("id, factory_name").in_("id", ids).execute()
    mp = {str(f["id"]): f.get("factory_name") or "-" for f in (fr.data or [])}
    for r in rows:
        r["factory_name"] = mp.get(str(r.get("factory_id")), "-")


@router.get("/sets")
def list_inspection_sets(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None, description="PENDING_ANCHOR / ACTIVE / UPCOMING"),
    active_only: bool = Query(False, description="ACTIVE + UPCOMING 만"),
    keyword: Optional[str] = Query(None),
    factory_keyword: Optional[str] = Query(None, description="시설명 부분 검색"),
    source: Optional[str] = Query(None, description="LEGAL_ENGINE / MANUAL 등"),
    cycle_unit: Optional[str] = Query(None, description="year, half_year, quarter, month, week, day"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """목록 조회 — PENDING_ANCHOR 우선, next_planned_date ASC (메모리 정렬)."""
    supabase = get_supabase()
    q = supabase.table("inspection_sets").select(
        "id, inspection_set_name, inspection_set_code, "
        "inspection_category, cycle_unit, cycle_value, cycle_base_type, cycle_base_guide, "
        "schedule_anchor_date, schedule_end_date, next_planned_date, last_inspection_date, "
        "status_code, anchor_confirmed, "
        "law_name, law_article, legal_rule_id, source, "
        "factory_id, company_id, created_at, updated_at",
        count="exact",
    ).eq("is_active", True)

    if factory_id:
        q = q.eq("factory_id", factory_id)
    if company_id:
        q = q.eq("company_id", company_id)
    if status_code and not active_only:
        q = q.eq("status_code", status_code)
    if source:
        q = q.eq("source", source)
    if cycle_unit:
        q = q.eq("cycle_unit", cycle_unit)
    if keyword:
        q = q.ilike("inspection_set_name", f"%{keyword}%")

    res = q.limit(_MAX_LIST_FETCH).execute()
    rows = list(res.data or [])
    if active_only:
        rows = [r for r in rows if (r.get("status_code") or "") in ("ACTIVE", "UPCOMING")]

    _enrich_factory_names(supabase, rows)

    if factory_keyword:
        fk = factory_keyword.lower().strip()
        rows = [r for r in rows if fk in (str(r.get("factory_name") or "").lower())]

    total = len(rows)

    def _sort_key(r: dict):
        pend = 0 if r.get("status_code") == "PENDING_ANCHOR" else 1
        npd = r.get("next_planned_date")
        npd_key = "9999-12-31" if npd is None else (str(npd)[:10] if not isinstance(npd, str) else npd[:10])
        created = r.get("created_at") or ""
        return (pend, npd_key, created)

    rows.sort(key=_sort_key)
    offset = (page - 1) * size
    page_rows = rows[offset : offset + size]

    today = date.today()
    items = []
    for r in page_rows:
        npd = _to_date(r.get("next_planned_date"))
        days_until = (npd - today).days if npd else None
        items.append(
            {
                **r,
                "days_until_next": days_until,
                "is_overdue": days_until is not None and days_until < 0,
            }
        )

    return {
        "status": "success",
        "data": {"items": items, "total": total, "page": page, "size": size},
    }


# ── GET /inspection-schedule/sets/{id} ────────────────────────────────────────


@router.get("/sets/{set_id}")
def get_inspection_set(set_id: str):
    """단건 — 수정 모달용 전체 필드 + 시설명."""
    supabase = get_supabase()
    res = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("id", set_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="inspection_set을 찾을 수 없습니다.")
    data = dict(res.data[0])

    fac_res = (
        supabase.table("factories")
        .select("factory_name, factory_code")
        .eq("id", data.get("factory_id"))
        .limit(1)
        .execute()
    )
    if fac_res.data:
        data["factory_name"] = fac_res.data[0].get("factory_name")
        data["factory_code"] = fac_res.data[0].get("factory_code")

    npd = _to_date(data.get("next_planned_date"))
    data["days_until_next"] = (npd - date.today()).days if npd else None
    data["is_overdue"] = data["days_until_next"] is not None and data["days_until_next"] < 0
    return {"status": "success", "data": data}


# ── PATCH /inspection-schedule/sets/{id} ──────────────────────────────────────


@router.patch("/sets/{set_id}")
def patch_inspection_set(set_id: str, body: InspectionSetPatch):
    """
    주기·기준일 수정 → next_planned_date 자동 재계산

    cycle_unit / cycle_value / schedule_anchor_date 변경 시 재계산 실행
    """
    supabase = get_supabase()
    cur_res = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("id", set_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not cur_res.data:
        raise HTTPException(status_code=404, detail="inspection_set을 찾을 수 없습니다.")
    cur = cur_res.data[0]

    allowed = {
        "cycle_unit",
        "cycle_value",
        "cycle_base_type",
        "cycle_weekday",
        "cycle_month_day",
        "is_month_end",
        "holiday_process_type",
        "description",
        "schedule_anchor_date",
        "schedule_end_date",
        "custom_cycle_value",
        "custom_cycle_unit",
        "custom_description",
    }
    raw = body.model_dump(exclude_unset=True)
    updates = {k: v for k, v in raw.items() if k in allowed}

    if not updates:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    if any(k in updates for k in ("cycle_unit", "cycle_value", "schedule_anchor_date")):
        anchor = updates.get("schedule_anchor_date")
        if anchor is not None:
            anchor = _to_date(anchor)
        else:
            anchor = _to_date(cur.get("schedule_anchor_date"))
        c_unit = updates.get("cycle_unit") or cur.get("cycle_unit")
        c_val = updates.get("cycle_value")
        if c_val is None:
            c_val = cur.get("cycle_value")
        try:
            c_val = int(c_val) if c_val is not None else None
        except (TypeError, ValueError):
            c_val = None
        if anchor and c_unit and c_val is not None:
            updates["next_planned_date"] = _calc_next_date(anchor, str(c_unit), c_val).isoformat()

    payload = _serialize_patch_row(updates)
    supabase.table("inspection_sets").update(payload).eq("id", set_id).execute()

    updated = (
        supabase.table("inspection_sets").select("*").eq("id", set_id).limit(1).execute()
    )
    if not updated.data:
        raise HTTPException(status_code=500, detail="갱신 후 조회 실패")
    return {"status": "success", "data": updated.data[0]}


# ── POST /inspection-schedule/sets/{id}/confirm-anchor ───────────────────────


@router.post("/sets/{set_id}/confirm-anchor")
def confirm_anchor(set_id: str, body: ConfirmAnchorBody):
    """
    기준일 확정 → status ACTIVE 전환

    1. schedule_anchor_date = body.anchor_date
    2. anchor_confirmed = true
    3. next_planned_date 재계산
    4. status_code = 'ACTIVE'
    """
    supabase = get_supabase()
    cur_res = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("id", set_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not cur_res.data:
        raise HTTPException(status_code=404, detail="inspection_set을 찾을 수 없습니다.")
    cur = cur_res.data[0]

    anchor = body.anchor_date
    cu = cur.get("cycle_unit")
    cv = cur.get("cycle_value")
    try:
        cv_int = int(cv) if cv is not None else None
    except (TypeError, ValueError):
        cv_int = None

    next_date = None
    if cu and cv_int is not None:
        next_date = _calc_next_date(anchor, str(cu), cv_int)

    payload = {
        "schedule_anchor_date": anchor.isoformat(),
        "anchor_confirmed": True,
        "next_planned_date": next_date.isoformat() if next_date else None,
        "status_code": "ACTIVE",
    }
    supabase.table("inspection_sets").update(payload).eq("id", set_id).execute()

    updated = (
        supabase.table("inspection_sets").select("*").eq("id", set_id).limit(1).execute()
    )
    if not updated.data:
        raise HTTPException(status_code=500, detail="갱신 후 조회 실패")
    row = updated.data[0]
    return {
        "status": "success",
        "message": f"기준일({anchor}) 확정 완료. 다음 점검일: {next_date}",
        "data": row,
    }
