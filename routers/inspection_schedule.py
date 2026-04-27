"""
일정관리 API — inspection_sets 기준일·주기 관리
prefix: /inspection-schedule

v1.1 (2026-04-03):
  anchor_type (FIXED_ANNUAL/HISTORICAL/EVENT) 필드·필터 추가
  /sets API에 anchor_type 포함, confirm-anchor에 anchor_type PATCH 지원
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from services.inspection_sets_helpers import next_planned_from as _calc_next_date  # ★ 서비스 분리 후 경로 변경
from services.legal_format import CYCLE_CODE_MAP, INSPECTION_CYCLE_UNIT_MAP
from services.legal_helpers import get_sector_groups

router = APIRouter(prefix="/inspection-schedule", tags=["inspection-schedule"])
_MAX_LIST_FETCH = 10000


def _to_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val)[:10])


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


# ── Pydantic 스키마 ──────────────────────────────────────────────────────────

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
    anchor_type: Optional[str] = None           # FIXED_ANNUAL / HISTORICAL / EVENT


class ConfirmAnchorBody(BaseModel):
    anchor_date: Optional[date] = None            # 없으면 기준일 없이 활성화(이벤트 등)
    anchor_type: Optional[str] = None           # 확정 시 유형도 함께 저장 가능


class GenerateScheduleSetsBody(BaseModel):
    rule_id: str = Field(...)
    factory_ids: List[str] = Field(default_factory=list)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

ANCHOR_TYPE_LABEL = {
    "FIXED_ANNUAL": "🗓 년초고정",
    "HISTORICAL":   "📋 이력일",
    "EVENT":        "⚡ 이벤트",
}

def _cycle_label_from_master(m: dict) -> str:
    """cycle_unit_std 기반 라벨 생성 (unit_code fallback)."""
    unit_std = (m.get("cycle_unit_std") or "").lower()
    val = int(m.get("inspection_cycle_value") or 0)

    # cycle_unit_std 없으면 unit_code에서 역산
    if not unit_std:
        code = str(m.get("inspection_cycle_unit_code") or "")
        _CODE_TO_UNIT = {
            "001": "day", "002": "week", "003": "month",
            "004": "quarter", "005": "half_year", "006": "year",
            "007": "year", "008": "year", "009": "year",
            "010": "year", "011": "year", "012": "year", "013": "year",
        }
        unit_std = _CODE_TO_UNIT.get(code, "")

    if not val:
        return ""

    _SHORT = {
        "year": "연 1회", "half_year": "반기 1회", "quarter": "분기 1회",
        "month": "월 1회", "week": "주 1회", "day": "매일",
    }
    if val == 1:
        return _SHORT.get(unit_std, f"1{unit_std}")
    if unit_std == "year":
        return f"{val}년마다"
    base = _SHORT.get(unit_std, unit_std)
    return base.replace("1회", f"{val}회")


def _build_insert_row(m: dict, company_id: Optional[str], factory_id: str) -> dict:
    law_name = m.get("law_name") or ""
    law_article = m.get("law_article") or ""
    # cycle_unit_std 우선, unit_code fallback
    unit_std = (m.get("cycle_unit_std") or "").lower()
    if unit_std:
        _STD_MAP = {"year": "year", "half_year": "month", "quarter": "month", "month": "month", "week": "week", "day": "day"}
        _STD_VAL = {"half_year": 6, "quarter": 3}
        cycle_unit = _STD_MAP.get(unit_std, "year")
        cycle_value = _STD_VAL.get(unit_std, int(m.get("inspection_cycle_value") or 1))
    else:
        code = str(m.get("inspection_cycle_unit_code") or "")
        if code in CYCLE_CODE_MAP:
            cycle_unit, cycle_value = CYCLE_CODE_MAP[code]
        else:
            cycle_unit = "year"
            cycle_value = int(m.get("inspection_cycle_value") or 1)
    _lbl = "년" if cycle_unit == "year" else "개월"
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
        or (f"마지막 점검일로부터 {cycle_value}{_lbl}마다"),
        "description": (str(m.get("obligation_summary") or m.get("inspection_required") or ""))[:2000],
        "source": "LEGAL_ENGINE",
        "is_active": True,
        "anchor_confirmed": False,
        "status_code": "PENDING_ANCHOR",
    }


def _enrich_factory_names(supabase, rows: list) -> None:
    ids = list({str(r["factory_id"]) for r in rows if r.get("factory_id")})
    if not ids:
        for r in rows:
            r["factory_name"] = "-"
        return
    fr = supabase.table("factories").select("id, name").in_("id", ids).execute()
    mp = {str(f["id"]): f.get("name") or "-" for f in (fr.data or [])}
    for r in rows:
        r["factory_name"] = mp.get(str(r.get("factory_id")), "-")


# ── GET /inspection-schedule/rules ───────────────────────────────────────────

@router.get("/rules")
def list_inspect_master_rules(sector: Optional[str] = Query(None)):
    supabase = get_supabase()
    res = (
        supabase.table("master_building_legal_rules")
        .select(
            "rule_id, law_name, law_article, sector, obligation_summary, "
            "inspection_cycle_value, inspection_cycle_unit_code, cycle_unit_std, "
            "condition_code, condition_value, condition_operator_code"
        )
        .eq("is_active", True)
        .eq("obligation_type", "INSPECT")
        .not_.in_("sector", ["SPECIAL_FACILITY", "SPECIAL"])
        .execute()
    )
    rows = list(res.data or [])
    if sector:
        groups = set(get_sector_groups(sector.strip().upper()))
        rows = [r for r in rows if (r.get("sector") or "") in groups]

    sets_res = (
        supabase.table("inspection_sets")
        .select("legal_rule_id, status_code")
        .eq("is_active", True)
        .eq("source", "LEGAL_ENGINE")
        .execute()
    )
    converted: dict = {}
    for s in (sets_res.data or []):
        rid = s.get("legal_rule_id") or ""
        converted.setdefault(rid, []).append(s.get("status_code") or "")

    items = []
    for r in rows:
        rid = r.get("rule_id") or ""
        statuses = converted.get(rid, [])
        active_cnt = sum(1 for s in statuses if s in ("ACTIVE", "UPCOMING"))
        items.append({
            **r,
            "cycle_label": _cycle_label_from_master(r),
            "converted_count": len(statuses),
            "active_count": active_cnt,
        })

    items.sort(key=lambda x: (x.get("law_name") or "", x.get("rule_id") or ""))
    return {"status": "success", "data": {"items": items, "total": len(items)}}


# ── GET /inspection-schedule/rules/{rule_id}/factories ───────────────────────

@router.get("/rules/{rule_id}/factories")
def list_factories_for_rule(rule_id: str, site_type: Optional[str] = Query(None)):
    supabase = get_supabase()
    mres = (
        supabase.table("master_building_legal_rules")
        .select("rule_id, law_name, law_article, sector, obligation_summary, "
                "inspection_cycle_value, inspection_cycle_unit_code, condition_code, condition_value")
        .eq("rule_id", rule_id).eq("is_active", True).limit(1).execute()
    )
    if not mres.data:
        raise HTTPException(status_code=404, detail="마스터 룰을 찾을 수 없습니다.")
    master = mres.data[0]

    fq = supabase.table("factories").select("id, name, sector, company_id")
    if site_type:
        fq = fq.eq("sector", site_type)
    facs = fq.order("name").limit(8000).execute().data or []

    sets_res = (
        supabase.table("inspection_sets")
        .select("id, factory_id, status_code, anchor_confirmed, next_planned_date")
        .eq("legal_rule_id", rule_id).eq("is_active", True).execute()
    )
    by_fac = {str(s["factory_id"]): s for s in (sets_res.data or [])}

    STATUS_LABEL = {
        "PENDING_ANCHOR": "기준일 필요", "ACTIVE": "활성",
        "UPCOMING": "일정예정", "OVERDUE": "연체", "INACTIVE": "비활성",
    }
    items = []
    for f in facs:
        fid = str(f["id"])
        row = by_fac.get(fid)
        if not row:
            items.append({"factory_id": fid, "factory_name": f.get("name") or "-",
                          "sector": f.get("sector") or "-", "inspection_set_id": None,
                          "status_code": "none", "status_label": "미생성", "next_planned_date": None})
        else:
            st = row.get("status_code") or ""
            items.append({"factory_id": fid, "factory_name": f.get("name") or "-",
                          "sector": f.get("sector") or "-", "inspection_set_id": row.get("id"),
                          "status_code": st, "status_label": STATUS_LABEL.get(st, st),
                          "next_planned_date": row.get("next_planned_date")})

    return {"status": "success", "data": {
        "rule": {**master, "cycle_label": _cycle_label_from_master(master)},
        "items": items, "total": len(items),
        "generated": len(by_fac), "not_generated": len(facs) - len(by_fac),
    }}


# ── POST /inspection-schedule/generate ───────────────────────────────────────

@router.post("/generate")
def generate_inspection_sets(body: GenerateScheduleSetsBody):
    supabase = get_supabase()
    rule_id = (body.rule_id or "").strip()
    if not rule_id:
        raise HTTPException(status_code=422, detail="rule_id 필수")
    ids = [str(x).strip() for x in (body.factory_ids or []) if str(x).strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="factory_ids 필수")

    mres = (
        supabase.table("master_building_legal_rules").select("*")
        .eq("rule_id", rule_id).eq("is_active", True).eq("obligation_type", "INSPECT")
        .limit(1).execute()
    )
    if not mres.data:
        raise HTTPException(status_code=404, detail="INSPECT 마스터 룰 없음")
    master = mres.data[0]

    existing = (
        supabase.table("inspection_sets").select("factory_id")
        .eq("legal_rule_id", rule_id).eq("source", "LEGAL_ENGINE").eq("is_active", True)
        .in_("factory_id", ids).execute()
    )
    have = {str(r["factory_id"]) for r in (existing.data or [])}

    insert_rows: List[dict] = []
    skipped = 0
    for fid in ids:
        if fid in have:
            skipped += 1
            continue
        fac = supabase.table("factories").select("company_id").eq("id", fid).limit(1).execute()
        if not fac.data:
            skipped += 1
            continue
        insert_rows.append(_build_insert_row(master, fac.data[0].get("company_id"), fid))

    created = 0
    for i in range(0, len(insert_rows), 20):
        res = supabase.table("inspection_sets").insert(insert_rows[i:i + 20]).execute()
        created += len(res.data or [])

    return {"status": "success", "message": f"생성 {created}건, 스킵 {skipped}건",
            "data": {"created": created, "skipped": skipped, "rule_id": rule_id}}


# ── GET /inspection-schedule/sets/summary-by-rule ────────────────────────────

@router.get("/sets/summary-by-rule")
def get_sets_summary_by_rule():
    supabase = get_supabase()
    total_rules = (
        supabase.table("master_building_legal_rules")
        .select("rule_id", count="exact")
        .eq("obligation_type", "INSPECT").eq("is_active", True)
        .not_.in_("sector", ["SPECIAL_FACILITY", "SPECIAL"]).execute()
    ).count or 0

    sets = (
        supabase.table("inspection_sets")
        .select("legal_rule_id, factory_id, status_code, anchor_type")
        .eq("source", "LEGAL_ENGINE").eq("is_active", True).execute()
    ).data or []

    used_rules = {s["legal_rule_id"] for s in sets if s.get("legal_rule_id")}
    pending = sum(1 for s in sets if s.get("status_code") == "PENDING_ANCHOR")
    active = sum(1 for s in sets if s.get("status_code") in ("ACTIVE", "UPCOMING"))

    by_type = {"FIXED_ANNUAL": 0, "HISTORICAL": 0, "EVENT": 0, "unknown": 0}
    for s in sets:
        t = s.get("anchor_type") or "unknown"
        by_type[t] = by_type.get(t, 0) + 1

    return {"status": "success", "data": {
        "total_rules": total_rules,
        "converted_rules": len(used_rules),
        "not_converted_rules": total_rules - len(used_rules),
        "total_sets": len(sets),
        "pending_anchor": pending,
        "active": active,
        "by_anchor_type": by_type,
    }}


# ── GET /inspection-schedule/summary ─────────────────────────────────────────

@router.get("/summary")
def get_summary(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
):
    supabase = get_supabase()
    today = date.today()
    q = supabase.table("inspection_sets").select(
        "status_code, next_planned_date, source"
    ).eq("is_active", True)
    if factory_id: q = q.eq("factory_id", factory_id)
    if company_id: q = q.eq("company_id", company_id)
    rows = q.execute().data or []
    pending = sum(1 for r in rows if r.get("status_code") == "PENDING_ANCHOR")
    active = sum(1 for r in rows if r.get("status_code") in ("ACTIVE", "UPCOMING"))
    overdue = sum(1 for r in rows
                  if r.get("status_code") in ("ACTIVE", "UPCOMING")
                  and _to_date(r.get("next_planned_date")) is not None
                  and _to_date(r.get("next_planned_date")) < today)
    return {"status": "success", "data": {
        "total": len(rows), "pending_anchor": pending,
        "active": active, "overdue": overdue, "upcoming_7d": 0,
    }}


# ── GET /inspection-schedule/sets ────────────────────────────────────────────

@router.get("/sets")
def list_inspection_sets(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    cycle_unit: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    factory_keyword: Optional[str] = Query(None),
    anchor_type: Optional[str] = Query(None),
    anchor_type_confidence: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("inspection_sets").select(
        "id, inspection_set_name, inspection_set_code, inspection_category, "
        "cycle_unit, cycle_value, cycle_base_type, cycle_base_guide, "
        "schedule_anchor_date, schedule_end_date, next_planned_date, last_inspection_date, "
        "status_code, anchor_confirmed, law_name, law_article, legal_rule_id, "
        "anchor_type, anchor_type_confidence, anchor_type_reason, "
        "source, factory_id, company_id, created_at, updated_at"
    ).eq("is_active", True)

    if factory_id: q = q.eq("factory_id", factory_id)
    if company_id: q = q.eq("company_id", company_id)
    if status_code: q = q.eq("status_code", status_code)
    if source: q = q.eq("source", source)
    if cycle_unit: q = q.eq("cycle_unit", cycle_unit)
    if keyword: q = q.ilike("inspection_set_name", f"%{keyword}%")
    if anchor_type: q = q.eq("anchor_type", anchor_type)
    if anchor_type_confidence is not None:
        q = q.lte("anchor_type_confidence", anchor_type_confidence)

    rows = list(q.limit(_MAX_LIST_FETCH).execute().data or [])
    _enrich_factory_names(supabase, rows)

    if factory_keyword:
        fk = factory_keyword.lower()
        rows = [r for r in rows if fk in str(r.get("factory_name") or "").lower()]

    today = date.today()

    def _sort_key(r):
        pend = 0 if r.get("status_code") == "PENDING_ANCHOR" else 1
        npd = r.get("next_planned_date")
        return (pend, str(npd)[:10] if npd else "9999-12-31", r.get("created_at") or "")

    rows.sort(key=_sort_key)
    total = len(rows)
    offset = (page - 1) * size
    items = []
    for r in rows[offset: offset + size]:
        npd = _to_date(r.get("next_planned_date"))
        days = (npd - today).days if npd else None
        r["anchor_type_label"] = ANCHOR_TYPE_LABEL.get(r.get("anchor_type") or "", "미분류")
        items.append({**r, "days_until_next": days, "is_overdue": days is not None and days < 0})

    return {"status": "success", "data": {"items": items, "total": total, "page": page, "size": size}}


# ── GET /inspection-schedule/sets/{id} ───────────────────────────────────────

@router.get("/sets/{set_id}")
def get_inspection_set(set_id: str):
    supabase = get_supabase()
    res = (
        supabase.table("inspection_sets").select("*")
        .eq("id", set_id).eq("is_active", True).limit(1).execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="inspection_set 없음")
    data = dict(res.data[0])
    fac = supabase.table("factories").select("name").eq("id", data.get("factory_id")).limit(1).execute()
    data["factory_name"] = fac.data[0].get("name") if fac.data else "-"
    data["anchor_type_label"] = ANCHOR_TYPE_LABEL.get(data.get("anchor_type") or "", "미분류")
    npd = _to_date(data.get("next_planned_date"))
    data["days_until_next"] = (npd - date.today()).days if npd else None
    data["is_overdue"] = data["days_until_next"] is not None and data["days_until_next"] < 0
    return {"status": "success", "data": data}


# ── PATCH /inspection-schedule/sets/{id} ─────────────────────────────────────

@router.patch("/sets/{set_id}")
def patch_inspection_set(set_id: str, body: InspectionSetPatch):
    supabase = get_supabase()
    cur = (
        supabase.table("inspection_sets").select("*")
        .eq("id", set_id).eq("is_active", True).limit(1).execute()
    )
    if not cur.data:
        raise HTTPException(status_code=404, detail="inspection_set 없음")
    cur = cur.data[0]

    allowed = {
        "cycle_unit", "cycle_value", "cycle_base_type", "cycle_weekday",
        "cycle_month_day", "is_month_end", "holiday_process_type", "description",
        "schedule_anchor_date", "schedule_end_date",
        "custom_cycle_value", "custom_cycle_unit", "custom_description",
        "anchor_type",
    }
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="변경할 필드 없음")

    if any(k in updates for k in ("cycle_unit", "cycle_value", "schedule_anchor_date", "anchor_type")):
        if "schedule_anchor_date" in updates:
            anchor = _to_date(updates["schedule_anchor_date"])
        else:
            anchor = _to_date(cur.get("schedule_anchor_date"))
        at_eff = updates["anchor_type"] if "anchor_type" in updates else cur.get("anchor_type")
        c_unit = updates.get("cycle_unit") or cur.get("cycle_unit")
        c_val = int(updates.get("cycle_value") or cur.get("cycle_value") or 1)
        if at_eff == "EVENT" and anchor is None:
            updates["next_planned_date"] = None
        elif anchor and c_unit and c_val:
            updates["next_planned_date"] = _calc_next_date(anchor, str(c_unit), c_val).isoformat()
        elif "schedule_anchor_date" in updates and updates.get("schedule_anchor_date") is None:
            updates["next_planned_date"] = None

    supabase.table("inspection_sets").update(_serialize_patch_row(updates)).eq("id", set_id).execute()
    updated = supabase.table("inspection_sets").select("*").eq("id", set_id).limit(1).execute()
    if not updated.data:
        raise HTTPException(status_code=500, detail="갱신 후 조회 실패")
    return {"status": "success", "data": updated.data[0]}


# ── POST /inspection-schedule/sets/{id}/confirm-anchor ───────────────────────

@router.post("/sets/{set_id}/confirm-anchor")
def confirm_anchor(set_id: str, body: ConfirmAnchorBody):
    supabase = get_supabase()
    cur = (
        supabase.table("inspection_sets").select("cycle_unit, cycle_value")
        .eq("id", set_id).eq("is_active", True).limit(1).execute()
    )
    if not cur.data:
        raise HTTPException(status_code=404, detail="inspection_set 없음")
    cur = cur.data[0]

    anchor = body.anchor_date
    cu = cur.get("cycle_unit")
    cv = int(cur.get("cycle_value") or 1)

    if anchor is None:
        patch = {
            "schedule_anchor_date": None,
            "anchor_confirmed": True,
            "next_planned_date": None,
            "status_code": "ACTIVE",
            "anchor_type_confidence": 100,
        }
    else:
        next_date = _calc_next_date(anchor, str(cu), cv) if cu else None
        patch = {
            "schedule_anchor_date": anchor.isoformat(),
            "anchor_confirmed": True,
            "next_planned_date": next_date.isoformat() if next_date else None,
            "status_code": "ACTIVE",
            "anchor_type_confidence": 100,
        }
    if body.anchor_type:
        patch["anchor_type"] = body.anchor_type

    supabase.table("inspection_sets").update(patch).eq("id", set_id).execute()
    row = supabase.table("inspection_sets").select("*").eq("id", set_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=500, detail="갱신 후 조회 실패")
    if anchor is None:
        msg = "활성화되었습니다. (기준일 미설정)"
    elif "next_date" in dir() and next_date:
        msg = f"기준일 확정 완료. 다음 점검일: {next_date}"
    else:
        msg = "활성화되었습니다."
    return {"status": "success", "message": msg, "data": row.data[0]}
