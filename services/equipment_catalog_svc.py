from __future__ import annotations

from services.equipment_helpers import CATEGORY_MAP, _now_iso


def run_list_equipment_master(supabase, search, category, top_band, needs_review, page: int, page_size: int):
    count_q = supabase.table("engine_equipment_summary").select("facility_name_std", count="exact")
    if category:
        count_q = count_q.eq("source_facility_category", category)
    if top_band:
        count_q = count_q.eq("top_band", top_band)
    if needs_review is not None:
        count_q = count_q.eq("needs_review", needs_review)
    if search:
        count_q = count_q.ilike("facility_name_std", f"%{search}%")
    total = (count_q.limit(0).execute().count) or 0

    offset = (page - 1) * page_size
    data_q = supabase.table("engine_equipment_summary").select("*")
    if category:
        data_q = data_q.eq("source_facility_category", category)
    if top_band:
        data_q = data_q.eq("top_band", top_band)
    if needs_review is not None:
        data_q = data_q.eq("needs_review", needs_review)
    if search:
        data_q = data_q.ilike("facility_name_std", f"%{search}%")
    data_q = data_q.order("process_count", desc=True).range(offset, offset + page_size - 1)
    res = data_q.execute()

    rows = res.data or []
    for row in rows:
        row["category_label"] = CATEGORY_MAP.get(row.get("source_facility_category") or "", "")

    return {
        "status": "success",
        "data": {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        },
    }


def run_refresh_engine_equipment(supabase):
    supabase.rpc("refresh_engine_equipment_summary").execute()
    return {"status": "success", "message": "MV가 갱신됐습니다.", "data": {"refreshed_at": _now_iso()}}


def run_get_equipment_detail(supabase, facility_name: str):
    res = (
        supabase.table("process_equipment_map")
        .select(
            "id, process_id, process_path, process_lv1, process_lv2, process_lv3, process_lv4, "
            "industry_code_full, industry_name_full, match_band, match_score, source_type, "
            "needs_review, source_facility_category, category_path, equipment_role"
        )
        .eq("facility_name_std", facility_name)
        .order("match_band")
        .limit(500)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise LookupError("설비를 찾을 수 없습니다.")
    industry_set: dict = {}
    band_dist = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
    for row in rows:
        ind = row.get("industry_code_full", "")
        if ind:
            industry_set[ind] = row.get("industry_name_full", ind)
        b = row.get("match_band", "")
        if b in band_dist:
            band_dist[b] += 1
    first = rows[0]
    return {
        "status": "success",
        "data": {
            "facility_name_std": facility_name,
            "source_facility_category": first.get("source_facility_category") or "",
            "category_label": CATEGORY_MAP.get(first.get("source_facility_category") or "", ""),
            "category_path": first.get("category_path") or "",
            "equipment_role": first.get("equipment_role") or "",
            "total_mappings": len(rows),
            "industry_count": len(industry_set),
            "band_distribution": band_dist,
            "processes": rows[:100],
        },
    }


def run_update_equipment_master(supabase, facility_name: str, body: dict):
    allowed = {"source_facility_category", "category_path", "needs_review", "equipment_role"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise ValueError("수정할 항목이 없습니다.")
    res = supabase.table("process_equipment_map").update(update_data).eq("facility_name_std", facility_name).execute()
    return {
        "status": "success",
        "message": f"{len(res.data or [])}건 업데이트됐습니다.",
        "data": {"facility_name_std": facility_name, **update_data},
    }


def run_bulk_approve_review(supabase, body: dict):
    names = body.get("facility_names", [])
    if not names:
        raise ValueError("facility_names가 필요합니다.")
    res = supabase.table("process_equipment_map").update({"needs_review": False}).in_("facility_name_std", names).execute()
    return {
        "status": "success",
        "message": f"{len(res.data or [])}건 승인됐습니다.",
        "data": {"approved_count": len(res.data or [])},
    }


def run_list_equipment_models(supabase, search, equipment_std, manufacturer, source_type, page: int, page_size: int):
    offset = (page - 1) * page_size
    q = supabase.table("equipment_model_master").select(
        "id, manufacturer, model_name, equipment_std, primary_equipment_std, "
        "model_year, expected_life_years, maintenance_cycle_months, risk_score, "
        "criticality_score, source_type, cert_match_status, country_of_origin, equipment_lv2",
        count="exact",
    )
    if equipment_std:
        q = q.eq("equipment_std", equipment_std)
    if manufacturer:
        q = q.ilike("manufacturer", f"%{manufacturer}%")
    if source_type:
        q = q.eq("source_type", source_type)
    if search:
        q = q.or_(f"model_name.ilike.%{search}%,manufacturer.ilike.%{search}%,equipment_std.ilike.%{search}%")
    q = q.order("equipment_std").order("manufacturer").range(offset, offset + page_size - 1)
    res = q.execute()
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page": page,
            "page_size": page_size,
            "total_pages": ((res.count or 0) + page_size - 1) // page_size,
        },
    }


def run_get_model_detail(supabase, model_id: str):
    res = supabase.table("equipment_model_master").select("*").eq("id", model_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise LookupError("모델을 찾을 수 없습니다.")
    return {"status": "success", "data": rows[0]}


def run_update_model(supabase, model_id: str, body: dict):
    allowed = {
        "manufacturer",
        "model_name",
        "equipment_std",
        "model_year",
        "expected_life_years",
        "maintenance_cycle_months",
        "risk_score",
        "criticality_score",
        "source_type",
        "country_of_origin",
        "equipment_lv2",
    }
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise ValueError("수정할 항목이 없습니다.")
    res = supabase.table("equipment_model_master").update(update_data).eq("id", model_id).execute()
    if not res.data:
        raise LookupError("모델을 찾을 수 없습니다.")
    return {"status": "success", "message": "모델이 수정됐습니다.", "data": res.data[0]}
