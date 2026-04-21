def list_kcsc_processes(supabase, search, construction_type, work_type_code, page, size):
    offset = (page - 1) * size
    q = supabase.table("kcsc_process_master").select("*", count="exact").eq("is_active", True)
    if search:
        q = q.ilike("process_name", f"%{search}%")
    if construction_type:
        q = q.eq("construction_type", construction_type)
    if work_type_code:
        q = q.eq("work_type_code", work_type_code)
    res = q.order("kcs_code").range(offset, offset + size - 1).execute()
    return {"items": res.data or [], "total": res.count or 0, "page": page, "size": size}


def list_kcsc_works_all(supabase, is_hazardous, work_type_code, hazard_type, search, page, size):
    offset = (page - 1) * size
    q = supabase.table("kcsc_work_master").select(
        "id, title, is_hazardous, hazard_type, safety_standard, "
        "is_work_item, equipment_type_codes, work_type_code, process_id",
        count="exact",
    ).eq("is_active", True)
    if is_hazardous is not None:
        q = q.eq("is_hazardous", is_hazardous)
    if work_type_code:
        q = q.eq("work_type_code", work_type_code)
    if hazard_type:
        q = q.ilike("hazard_type", f"%{hazard_type}%")
    if search:
        q = q.ilike("title", f"%{search}%")
    res = q.order("sort_order").order("title").range(offset, offset + size - 1).execute()
    return {"items": res.data or [], "total": res.count or 0, "page": page, "size": size}


def list_kcsc_works_by_process(supabase, process_id: str):
    res = (
        supabase.table("kcsc_work_master")
        .select("*")
        .eq("process_id", process_id)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []
