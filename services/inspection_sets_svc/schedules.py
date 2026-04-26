from __future__ import annotations

from datetime import date

from db.supabase_client import get_supabase
from services.inspection_sets_helpers import _build_next_schedule_row
from .law_engine import run_generate_law_engine


def generate_schedules_all() -> dict:
    supabase = get_supabase()
    factories = supabase.table("factories").select("id").eq("is_active", True).execute().data or []
    total_created = total_skipped_d = total_skipped_c = processed = 0
    results = []
    for fac in factories:
        factory_id = fac["id"]
        r = run_generate_law_engine(factory_id, supabase)
        if r["total_sets"] == 0:
            continue
        processed += 1
        total_created += r["created"]
        total_skipped_d += r["skipped_dup"]
        total_skipped_c += r["skipped_no_condition"]
        results.append({"factory_id": factory_id, "total_sets": r["total_sets"], "created": r["created"], "skipped_dup": r["skipped_dup"], "skipped_no_condition": r["skipped_no_condition"]})
    return {"status": "success", "message": f"공장 {processed}개 처리 — LAW_ENGINE 스케줄 총 {total_created}건 생성", "data": {"total_factories": len(factories), "processed": processed, "total_created": total_created, "total_skipped_duplicate": total_skipped_d, "total_skipped_no_condition": total_skipped_c, "results": results}}


def generate_schedules_for_factory(factory_id: str, mode: str, force: bool) -> dict:
    supabase = get_supabase()
    if mode == "law_engine":
        r = run_generate_law_engine(factory_id, supabase)
        return {"status": "success", "message": f"{r['total_sets']}개 세트 처리 — LAW_ENGINE 스케줄 {r['created']}건 생성", "data": {"factory_id": factory_id, "mode": "law_engine", "total_sets": r["total_sets"], "created": r["created"], "skipped_duplicate": r["skipped_dup"], "skipped_no_condition": r["skipped_no_condition"]}}
    sets = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_value, cycle_unit, inspection_set_name, "
        "inspection_category, source, schedule_anchor_date, next_planned_date"
    ).eq("factory_id", factory_id).eq("anchor_confirmed", True).eq("is_active", True).execute().data or []
    if not sets:
        return {"status": "success", "message": "생성할 점검세트가 없습니다 (기준일 미설정 또는 없음)", "data": {"factory_id": factory_id, "mode": "anchor", "total": 0, "created": 0, "skipped": 0}}
    created = skipped = 0
    results = []
    for iset in sets:
        set_id = iset["id"]
        name = iset.get("inspection_set_name") or ""
        anchor_str = iset.get("schedule_anchor_date")
        if not anchor_str:
            skipped += 1
            results.append({"id": set_id, "name": name, "status": "skipped", "reason": "기준일 없음"})
            continue
        existing = supabase.table("work_schedules").select("id").eq("inspection_set_id", set_id).eq("status_code", "SCHEDULED").limit(1).execute()
        if existing.data and not force:
            skipped += 1
            results.append({"id": set_id, "name": name, "status": "skipped", "reason": "이미 스케줄 존재"})
            continue
        try:
            anchor = date.fromisoformat(anchor_str)
            row, planned = _build_next_schedule_row(iset, anchor)
            if force and existing.data:
                supabase.table("work_schedules").delete().eq("inspection_set_id", set_id).eq("status_code", "SCHEDULED").execute()
            r = supabase.table("work_schedules").insert(row).execute()
            created += len(r.data or [])
            results.append({"id": set_id, "name": name, "status": "created", "planned_date": planned.isoformat()})
        except Exception as e:
            results.append({"id": set_id, "name": name, "status": "error", "reason": str(e)})
    return {"status": "success", "message": f"{len(sets)}개 처리 — 생성 {created}건, 스킵 {skipped}건", "data": {"factory_id": factory_id, "mode": "anchor", "total": len(sets), "created": created, "skipped": skipped, "results": results}}
