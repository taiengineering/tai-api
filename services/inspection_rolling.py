"""OBJ-04 ROLLING-02 — SAFE 완료 rolling 다음 회차 helper (멱등).
/complete 와 W3 all-NORMAL auto-complete 가 공유. 멱등 근거:
결정적 next_date + uq_work_schedules_new_set_planned_factory + ON CONFLICT DO NOTHING
(ignore_duplicates=True) → same-anchor/replay/concurrent 물리 INSERT 0..1.
completion_anchor 는 caller 가 freeze 한 최초 완료일(REPLAY 마다 today 재계산 금지).
next_planned_date 는 뒤로 되돌리지 않는다(late replay backward regression 방지).
금지: DDL, OBJ-01 base/journal, W3 result identity, full cross-object txn.
※ _add_cycle 은 routers/inspection_checklist.py 의 동명 함수와 byte-동일하게 유지(서비스→라우터 import 금지, 순환 회피 위해 복제).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

from dateutil.relativedelta import relativedelta

from services.status_vocab import ws_write_scheduled

CONFLICT_KEY = "inspection_set_id,planned_date,factory_id"


def _add_cycle(base: date, cycle_unit: str, cycle_value: int) -> date:
    """base + cycle → 다음 날짜."""
    unit = cycle_unit.lower()
    if unit == "day":        return base + timedelta(days=cycle_value)
    if unit == "week":       return base + timedelta(weeks=cycle_value)
    if unit in ("month", "quarter", "half_year"):
        months = cycle_value if unit == "month" else (3 if unit == "quarter" else 6)
        return base + relativedelta(months=months)
    # year / 기타
    try:    return base + relativedelta(years=cycle_value)
    except: return base + relativedelta(years=1)


def ensure_next_rolling_schedule(supabase: Any, work_schedule_id: str, completion_anchor) -> Dict[str, Any]:
    """멱등 rolling. 반환 {created, next_planned_date, skipped}."""
    ws = supabase.table("work_schedules").select(
        "id, factory_id, inspection_set_id, planned_date, company_id"
    ).eq("id", work_schedule_id).limit(1).execute()
    if not ws.data:
        return {"created": False, "next_planned_date": None, "skipped": True}

    row = ws.data[0]
    inspection_set_id = row.get("inspection_set_id")
    factory_id = row.get("factory_id")
    source_planned = row.get("planned_date")
    if not inspection_set_id:                      # rolling 대상 아님(기존 의미 보존)
        return {"created": False, "next_planned_date": None, "skipped": True}

    iset = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_unit, cycle_value, inspection_set_name, "
        "inspection_category, source, schedule_end_date, next_planned_date"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not iset.data:
        return {"created": False, "next_planned_date": None, "skipped": True}

    s = iset.data[0]
    cycle_unit = (s.get("cycle_unit") or "year").lower()
    cycle_value = int(s.get("cycle_value") or 1)
    anchor = completion_anchor if isinstance(completion_anchor, date) \
        else date.fromisoformat(str(completion_anchor)[:10])
    next_date = _add_cycle(anchor, cycle_unit, cycle_value)

    end_str = s.get("schedule_end_date")           # §7 범위 초과면 INSERT 0
    if end_str and next_date > date.fromisoformat(str(end_str)[:10]):
        return {"created": False, "next_planned_date": None, "skipped": True}

    company_res = supabase.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
    company_id = company_res.data[0].get("company_id") if company_res.data else s.get("company_id")
    source_type = "LEGAL" if s.get("source") == "LEGAL_ENGINE" else "MANUAL"
    row_ins = {                                    # §4 row shape verbatim(기존 inline 과 동일 필드)
        "inspection_set_id": inspection_set_id,
        "company_id":        company_id,
        "factory_id":        factory_id,
        "planned_date":      next_date.isoformat(),
        "start_date":        next_date.isoformat(),
        "end_date":          next_date.isoformat(),
        "status_code":       ws_write_scheduled(),
        "source_type":       source_type,
        "obligation_type":   s.get("inspection_category") or "GENERAL",
        "summary":           s.get("inspection_set_name") or "",
        "active_yn":         True,
        "assigned_user_id":  None,
    }
    # §5 DO NOTHING 필수(merge 금지 — replay 가 배정/시작된 다음 회차를 덮으면 안 됨)
    ins = supabase.table("work_schedules").upsert(
        row_ins, on_conflict=CONFLICT_KEY, ignore_duplicates=True,
    ).execute()
    created = bool(ins.data)

    # §6 next_planned_date backward regression 방지
    cur = s.get("next_planned_date")
    set_next = False
    if cur is None:
        set_next = True
    else:
        cur_d = date.fromisoformat(str(cur)[:10])
        src_d = date.fromisoformat(str(source_planned)[:10]) if source_planned else None
        if src_d is not None and cur_d <= src_d:   # 아직 현재/과거 회차 → 전진 허용
            set_next = True
        # cur_d > src_d → 이미 더 미래 → overwrite 금지
    if set_next and str(cur)[:10] != next_date.isoformat():
        supabase.table("inspection_sets").update(
            {"next_planned_date": next_date.isoformat()}
        ).eq("id", inspection_set_id).execute()

    return {"created": created, "next_planned_date": next_date.isoformat(), "skipped": False}
