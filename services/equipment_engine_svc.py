from __future__ import annotations

from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from services.equipment_helpers import CATEGORY_MAP, DELTA_MAP, _build_schedules_for_repair, _enrich_asset_row, _now_iso


def run_get_equipment_stats(supabase, version: str):
    res = supabase.table("engine_equipment_summary").select(
        "source_facility_category, top_band, needs_review, process_count"
    ).execute()
    rows = res.data or []

    total = len(rows)
    cat_count: dict = {}
    band_count = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
    review_count = 0
    total_mappings = 0

    for row in rows:
        cat = row.get("source_facility_category") or ""
        band = row.get("top_band") or ""
        cat_count[cat] = cat_count.get(cat, 0) + 1
        if band in band_count:
            band_count[band] += 1
        if row.get("needs_review"):
            review_count += 1
        total_mappings += row.get("process_count") or 0

    model_res = supabase.table("equipment_model_master").select("id", count="exact").limit(0).execute()
    asset_total_res = supabase.table("equipment_assets").select("id", count="exact").limit(0).execute()
    asset_no_model_res = (
        supabase.table("equipment_assets").select("id", count="exact").is_("equipment_model_id", "null").limit(0).execute()
    )
    asset_no_insp_res = (
        supabase.table("equipment_assets").select("id", count="exact").is_("last_inspection_date", "null").limit(0).execute()
    )
    legal_target_res = supabase.table("master_legal_inspection_target").select("id", count="exact").limit(0).execute()
    legal_rows = supabase.table("master_legal_inspection_target").select("equipment_name").execute()
    legal_names = [r.get("equipment_name", "") for r in (legal_rows.data or []) if r.get("equipment_name")]
    unmapped_count = 0
    for lname in legal_names:
        chk = supabase.table("equipment_assets").select("id", count="exact").ilike("asset_name", f"%{lname[:6]}%").limit(0).execute()
        if (chk.count or 0) == 0:
            unmapped_count += 1

    return {
        "status": "success",
        "data": {
            "total_mapping_rows": total_mappings,
            "unique_equipment": total,
            "model_master_total": model_res.count or 0,
            "needs_review_count": review_count,
            "band_distribution": band_count,
            "category_distribution": {
                k: {"count": v, "label": CATEGORY_MAP.get(k, k)} for k, v in sorted(cat_count.items(), key=lambda x: -x[1])
            },
            "asset_registered_total": asset_total_res.count or 0,
            "asset_no_model": asset_no_model_res.count or 0,
            "asset_no_inspection": asset_no_insp_res.count or 0,
            "legal_inspection_target_count": legal_target_res.count or 0,
            "legal_inspection_unmapped": unmapped_count,
            "version": version,
        },
    }


def run_list_assets(
    supabase,
    page: int,
    page_size: int,
    search: Optional[str],
    has_model: Optional[bool],
    no_inspection: Optional[bool],
    is_legal_target: Optional[bool],
    equipment_type_code: Optional[str],
):
    def _apply_filters(q):
        if search:
            q = q.ilike("asset_name", f"%{search.strip()}%")
        if has_model is True:
            q = q.not_.is_("equipment_model_id", "null")
        elif has_model is False:
            q = q.is_("equipment_model_id", "null")
        if no_inspection is True:
            q = q.is_("last_inspection_date", "null")
        elif no_inspection is False:
            q = q.not_.is_("last_inspection_date", "null")
        if is_legal_target is not None:
            q = q.eq("is_legal_target", is_legal_target)
        if equipment_type_code:
            q = q.eq("equipment_type_code", equipment_type_code)
        return q

    count_q = _apply_filters(supabase.table("equipment_assets").select("id", count="exact"))
    total = (count_q.limit(0).execute().count) or 0
    offset = (page - 1) * page_size
    data_q = _apply_filters(supabase.table("equipment_assets").select("*"))
    data_q = data_q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    res = data_q.execute()
    items = [_enrich_asset_row(dict(r)) for r in (res.data or [])]
    return {
        "status": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        },
    }


def run_patch_asset(supabase, asset_id: str, body):
    update_data = {}
    if body.last_inspection_date is not None:
        update_data["last_inspection_date"] = body.last_inspection_date.isoformat()
    if body.next_inspection_date is not None:
        update_data["next_inspection_date"] = body.next_inspection_date.isoformat()
    if body.is_legal_target is not None:
        update_data["is_legal_target"] = body.is_legal_target
    if body.is_operating is not None:
        update_data["is_operating"] = body.is_operating
    if body.model_id and not body.equipment_model_id:
        update_data["equipment_model_id"] = body.model_id
    elif body.equipment_model_id:
        update_data["equipment_model_id"] = body.equipment_model_id

    if not update_data:
        raise ValueError("수정할 항목이 없습니다.")

    update_data["updated_at"] = _now_iso()
    res = supabase.table("equipment_assets").update(update_data).eq("id", asset_id).execute()
    if not res.data:
        raise LookupError("자산을 찾을 수 없습니다.")

    asset = res.data[0]
    repair_result = {"schedules_reset": 0, "sets_processed": 0}
    if body.is_operating is True and body.repair_date:
        try:
            repair_date = date.fromisoformat(body.repair_date)
            end_date = repair_date + relativedelta(years=1)
            factory_id = asset.get("factory_id")
            if factory_id:
                sets_res = (
                    supabase.table("inspection_sets")
                    .select("id, factory_id, company_id, cycle_value, cycle_unit, inspection_set_name, inspection_category")
                    .eq("factory_id", factory_id)
                    .eq("source", "MANUAL")
                    .eq("status_code", "ACTIVE")
                    .eq("is_active", True)
                    .execute()
                )
                sets = sets_res.data or []
                total_created = 0
                for iset in sets:
                    try:
                        (
                            supabase.table("work_schedules")
                            .delete()
                            .eq("inspection_set_id", iset["id"])
                            .eq("status_code", "SCHEDULED")
                            .execute()
                        )
                        rows = _build_schedules_for_repair(iset, repair_date, end_date)
                        next_date = repair_date + (
                            DELTA_MAP.get((iset.get("cycle_unit") or "year").lower(), lambda v: relativedelta(years=v))(
                                int(iset.get("cycle_value") or 1)
                            )
                        )
                        (
                            supabase.table("inspection_sets")
                            .update(
                                {
                                    "schedule_anchor_date": repair_date.isoformat(),
                                    "schedule_end_date": end_date.isoformat(),
                                    "next_planned_date": next_date.isoformat(),
                                }
                            )
                            .eq("id", iset["id"])
                            .execute()
                        )
                        for i in range(0, len(rows), 20):
                            r = supabase.table("work_schedules").insert(rows[i : i + 20]).execute()
                            total_created += len(r.data or [])
                    except Exception:
                        pass
                repair_result = {
                    "schedules_reset": total_created,
                    "sets_processed": len(sets),
                    "repair_date": repair_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
        except Exception:
            pass
    return {"status": "success", "data": {**asset, "repair_result": repair_result}}

