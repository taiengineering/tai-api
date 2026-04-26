from __future__ import annotations

from services.inspection_sets_helpers import _build_law_engine_row, _meets_4_conditions


def run_generate_law_engine(factory_id: str, supabase) -> dict:
    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, schedule_anchor_date, cycle_unit, cycle_value, "
        "assignee_user_id, description, legal_rule_code, legal_rule_id, "
        "law_name, law_article, inspection_category"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()
    all_sets = sets_res.data or []
    if not all_sets:
        return {"total_sets": 0, "created": 0, "skipped_dup": 0, "skipped_no_condition": 0}
    existing_res = supabase.table("work_schedules").select("inspection_set_id") \
        .eq("factory_id", factory_id).eq("source_type", "LAW_ENGINE").eq("status_code", "PENDING").execute()
    existing_ids = {r["inspection_set_id"] for r in (existing_res.data or []) if r.get("inspection_set_id")}
    rows, skipped_dup, skipped_no_cond = [], 0, 0
    for iset in all_sets:
        set_id = iset["id"]
        if set_id in existing_ids:
            skipped_dup += 1
            continue
        if not _meets_4_conditions(iset):
            skipped_no_cond += 1
            continue
        rows.append(_build_law_engine_row(iset))
        existing_ids.add(set_id)
    created = 0
    for i in range(0, len(rows), 20):
        res = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
        created += len(res.data or [])
    return {"total_sets": len(all_sets), "created": created, "skipped_dup": skipped_dup, "skipped_no_condition": skipped_no_cond}
