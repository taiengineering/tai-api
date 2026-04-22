from services.construction_helpers import calc_safety_manager
from services.construction_svc import normalize_date_fields, run_list_query


def list_sites(supabase, company_id, status_code, site_type, search, page, size):
    data = run_list_query(
        supabase,
        "construction_sites",
        {
            "is_active": True,
            "company_id": company_id,
            "status_code": status_code,
            "site_type": site_type,
            "site_name__ilike": f"%{search}%" if search else None,
        },
        page,
        size,
        [("created_at", True)],
    )
    total = data.get("total", 0)
    data["total_pages"] = (total + size - 1) // size if total else 0
    return data


def build_site_create_payload(body, now_iso_fn):
    data = body.model_dump(exclude_none=True)
    data = normalize_date_fields(data, ("start_date", "end_date"))
    if body.contract_amount is not None:
        sm = calc_safety_manager(body.site_type, float(body.contract_amount), body.total_workers or 0)
        data["safety_manager_required"] = sm["required"]
        data["safety_manager_count"] = sm["count"]
    data["created_at"] = now_iso_fn()
    data["updated_at"] = now_iso_fn()
    return data


def build_site_update_payload(body, current_site, now_iso_fn):
    data = body.model_dump(exclude_none=True)
    if not data:
        return data
    data = normalize_date_fields(data, ("start_date", "end_date"))
    if "contract_amount" in data or "total_workers" in data or "site_type" in data:
        sm = calc_safety_manager(
            data.get("site_type", current_site.get("site_type", "BUILDING")),
            float(data.get("contract_amount", current_site.get("contract_amount") or 0)),
            int(data.get("total_workers", current_site.get("total_workers") or 0)),
        )
        data["safety_manager_required"] = sm["required"]
        data["safety_manager_count"] = sm["count"]
    data["updated_at"] = now_iso_fn()
    return data


def build_site_stats(site_id: str, site: dict, procs: list, works: list, workers: list, insps: list):
    return {
        "site_id": site_id,
        "site_name": site.get("site_name"),
        "safety_manager_required": site.get("safety_manager_required"),
        "safety_manager_count": site.get("safety_manager_count"),
        "factory_id": site.get("factory_id"),
        "processes": {
            "total": len(procs),
            "in_progress": sum(1 for p in procs if p.get("status_code") == "IN_PROGRESS"),
            "done": sum(1 for p in procs if p.get("status_code") == "DONE"),
        },
        "works": {
            "total": len(works),
            "scheduled": sum(1 for w in works if w.get("status_code") == "SCHEDULED"),
            "in_progress": sum(1 for w in works if w.get("status_code") == "IN_PROGRESS"),
            "ptw_pending": sum(1 for w in works if w.get("ptw_status") == "DRAFT"),
            "ptw_approved": sum(1 for w in works if w.get("ptw_status") == "APPROVED"),
        },
        "workers": {
            "total": len(workers),
            "direct": sum(1 for w in workers if w.get("worker_type") == "DIRECT"),
            "subcon": sum(1 for w in workers if w.get("worker_type") == "SUBCON"),
            "on_site": sum(1 for w in workers if w.get("entry_status") == "IN"),
        },
        "inspections": {
            "total": len(insps),
            "pass": sum(1 for i in insps if i.get("overall_result") == "PASS"),
            "fail": sum(1 for i in insps if i.get("overall_result") in ("FAIL", "ISSUE")),
        },
    }


def run_diagnose_site(supabase, site_id: str, create_factory_fn, run_diagnosis_fn):
    site_res = supabase.table("construction_sites").select("*").eq("id", site_id).eq("is_active", True).limit(1).execute()
    if not site_res.data:
        raise LookupError("현장을 찾을 수 없습니다.")
    site = site_res.data[0]

    factory_id = site.get("factory_id")
    if not factory_id:
        factory_id = create_factory_fn(supabase, site)
        if not factory_id:
            raise RuntimeError("factory 연결 실패")

    diag = run_diagnosis_fn(supabase, factory_id, site)
    return site, factory_id, diag


def run_generate_site_schedules(supabase, site_id: str, run_generate_schedules_fn):
    site_res = (
        supabase.table("construction_sites")
        .select("factory_id, company_id")
        .eq("id", site_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not site_res.data:
        raise LookupError("현장을 찾을 수 없습니다.")
    site = site_res.data[0]
    factory_id = site.get("factory_id")
    company_id = site.get("company_id")
    if not factory_id:
        raise ValueError("법령진단을 먼저 실행하세요 (factory_id 없음)")

    diag_res = (
        supabase.table("factory_diagnosis_results")
        .select("result_data")
        .eq("factory_id", factory_id)
        .eq("sector", "CONSTRUCTION")
        .eq("is_latest", True)
        .limit(1)
        .execute()
    )
    if not diag_res.data:
        raise ValueError("법령진단을 먼저 실행하세요")

    result_data = diag_res.data[0].get("result_data") or {}
    inspection_rules = result_data.get("inspection_required") or []
    action_rules = result_data.get("action_required") or []
    sched = run_generate_schedules_fn(supabase, factory_id, inspection_rules + action_rules, company_id)
    return factory_id, sched
