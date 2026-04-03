"""
일정관리 API — inspection_sets 기준일·주기 관리
작업지시서: TAI_작업지시서_일정관리_백엔드_20260403.md

prefix: /inspection-schedule

Endpoints
---------
GET   /inspection-schedule/summary
GET   /inspection-schedule/sets
GET   /inspection-schedule/sets/{id}
PATCH /inspection-schedule/sets/{id}
POST  /inspection-schedule/sets/{id}/confirm-anchor

※ tai-api는 asyncpg `get_db` 대신 Supabase(`get_supabase`)를 사용한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.inspection_sets import _calc_next_date

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
    cycle_weekday: Optional[int] = None
    cycle_month_day: Optional[int] = None
    is_month_end: Optional[bool] = None
    holiday_process_type: Optional[str] = None
    description: Optional[str] = None
    custom_cycle_value: Optional[int] = None
    custom_cycle_unit: Optional[str] = None
    custom_description: Optional[str] = None


class ConfirmAnchorBody(BaseModel):
    anchor_date: date


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
        "id, status_code, next_planned_date", count="exact"
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

    return {
        "status": "success",
        "data": {
            "total": total,
            "pending_anchor": pending_anchor,
            "active": active,
            "overdue": overdue,
            "upcoming_7d": upcoming_7d,
        },
    }


# ── GET /inspection-schedule/sets ─────────────────────────────────────────────


@router.get("/sets")
def list_inspection_sets(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None, description="PENDING_ANCHOR / ACTIVE / UPCOMING"),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """목록 조회 — PENDING_ANCHOR 우선, next_planned_date ASC (메모리 정렬)."""
    supabase = get_supabase()
    q = supabase.table("inspection_sets").select(
        "id, inspection_set_name, inspection_set_code, "
        "inspection_category, cycle_unit, cycle_value, "
        "schedule_anchor_date, next_planned_date, last_inspection_date, "
        "status_code, anchor_confirmed, "
        "law_name, law_article, legal_rule_id, source, "
        "factory_id, company_id, created_at, updated_at",
        count="exact",
    ).eq("is_active", True)

    if factory_id:
        q = q.eq("factory_id", factory_id)
    if company_id:
        q = q.eq("company_id", company_id)
    if status_code:
        q = q.eq("status_code", status_code)
    if keyword:
        q = q.ilike("inspection_set_name", f"%{keyword}%")

    res = q.limit(_MAX_LIST_FETCH).execute()
    rows = list(res.data or [])
    total = res.count if res.count is not None else len(rows)

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
        "cycle_weekday",
        "cycle_month_day",
        "is_month_end",
        "holiday_process_type",
        "description",
        "schedule_anchor_date",
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
