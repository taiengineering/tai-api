# routers/price_setting.py — 가격 설정 관리 API
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_supabase

router = APIRouter(prefix="/price-setting", tags=["가격 설정"])


# ── Pydantic 모델 ────────────────────────────────────────────

class SaasPlanUpdate(BaseModel):
    monthly_base_fee: Optional[int] = None
    annual_base_fee: Optional[int] = None
    annual_discount_rate: Optional[float] = None
    max_facilities: Optional[int] = None
    max_users: Optional[int] = None
    included_users: Optional[int] = None
    monthly_reports_include: Optional[int] = None
    storage_period_month: Optional[int] = None
    extra_facility_fee: Optional[int] = None
    extra_user_fee: Optional[int] = None
    extra_user_fee_v2: Optional[int] = None
    extra_report_fee: Optional[int] = None
    api_integration_fee: Optional[int] = None
    max_sites: Optional[int] = None
    storage_history_month: Optional[int] = None
    annual_free_months: Optional[int] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    badge_color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    include_law_alert: Optional[bool] = None
    include_api: Optional[bool] = None
    include_api_v2: Optional[bool] = None
    include_unlimited_storage: Optional[bool] = None
    include_task_assign: Optional[bool] = None
    include_group_mgmt: Optional[bool] = None
    include_miss_alert: Optional[bool] = None
    include_safety_content: Optional[str] = None
    include_dashboard: Optional[str] = None
    updated_by: Optional[str] = None


class DiagnosisReportUpdate(BaseModel):
    basic_fee: Optional[int] = None
    process_fee: Optional[int] = None
    equipment_fee: Optional[int] = None
    total_report_fee: Optional[int] = None
    facility_type_name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class RepairBrokerageUpdate(BaseModel):
    repair_type_name: Optional[str] = None
    amount_from: Optional[int] = None
    amount_to: Optional[int] = None
    commission_rate: Optional[float] = None
    commission_fixed: Optional[int] = None
    commission_type: Optional[str] = None
    urgent_type: Optional[str] = None
    urgent_surcharge_rate: Optional[float] = None
    warranty_period_month: Optional[int] = None
    vendor_monthly_fee: Optional[int] = None
    is_active: Optional[bool] = None


class SafetyManagementUpdate(BaseModel):
    plan_name: Optional[str] = None
    worker_count_from: Optional[int] = None
    worker_count_to: Optional[int] = None
    risk_grade_code: Optional[str] = None
    visit_count_per_month: Optional[int] = None
    hours_per_visit: Optional[int] = None
    base_monthly_fee: Optional[int] = None
    contract_period_month: Optional[int] = None
    long_term_discount_rate: Optional[float] = None
    include_safety_manager: Optional[bool] = None
    include_fire_manager: Optional[bool] = None
    include_elec_manager: Optional[bool] = None
    include_document: Optional[bool] = None
    include_education: Optional[bool] = None
    emergency_call_fee: Optional[int] = None
    document_fee_per_report: Optional[int] = None
    education_fee_per_hour: Optional[int] = None
    is_active: Optional[bool] = None


class ConsultingUpdate(BaseModel):
    service_name: Optional[str] = None
    consulting_type_code: Optional[str] = None
    facility_area_from: Optional[int] = None
    facility_area_to: Optional[int] = None
    staff_grade_code: Optional[str] = None
    staff_count: Optional[int] = None
    work_days: Optional[int] = None
    base_fee: Optional[int] = None
    report_type_code: Optional[str] = None
    report_fee: Optional[int] = None
    include_redesign: Optional[bool] = None
    include_recheck: Optional[bool] = None
    urgent_surcharge_rate: Optional[float] = None
    urgent_days_threshold: Optional[int] = None
    is_active: Optional[bool] = None


# ── 변경 로그 기록 ────────────────────────────────────────────

def _log_changes(sb, table_name: str, record_id: str, old: dict, new: dict, changed_by: str = None):
    """변경된 필드만 price_change_log에 기록"""
    logs = []
    for field, new_val in new.items():
        old_val = old.get(field)
        if str(old_val) != str(new_val):
            logs.append({
                "table_name": table_name,
                "record_id": record_id,
                "field_name": field,
                "old_value": str(old_val) if old_val is not None else None,
                "new_value": str(new_val) if new_val is not None else None,
                "changed_by": changed_by,
            })
    if logs:
        sb.table("price_change_log").insert(logs).execute()
    return len(logs)


# ── SaaS 요금제 ──────────────────────────────────────────────

@router.get("/saas-plans")
def list_saas_plans():
    sb = get_supabase()
    res = sb.table("price_saas_plan").select("*").order("sort_order").execute()
    return {"status": "success", "data": res.data}


@router.get("/saas-plans/{plan_id}")
def get_saas_plan(plan_id: str):
    sb = get_supabase()
    res = sb.table("price_saas_plan").select("*").eq("id", plan_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


@router.patch("/saas-plans/{plan_id}")
def update_saas_plan(plan_id: str, body: SaasPlanUpdate):
    sb = get_supabase()

    # 기존 데이터 조회
    old_res = sb.table("price_saas_plan").select("*").eq("id", plan_id).single().execute()
    if not old_res.data:
        raise HTTPException(status_code=404, detail="요금제를 찾을 수 없습니다")

    # None이 아닌 필드만 업데이트
    update_data = {k: v for k, v in body.dict().items() if v is not None and k != "updated_by"}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    update_data["updated_at"] = datetime.now().isoformat()
    if body.updated_by:
        update_data["updated_by"] = body.updated_by

    # 변경 로그 기록
    changed = _log_changes(sb, "price_saas_plan", plan_id, old_res.data, update_data, body.updated_by)

    # 업데이트
    res = sb.table("price_saas_plan").update(update_data).eq("id", plan_id).execute()
    return {
        "status": "success",
        "data": res.data[0] if res.data else None,
        "changes_logged": changed,
    }


# ── 진단 보고서 가격 ─────────────────────────────────────────

@router.get("/diagnosis-reports")
def list_diagnosis_reports():
    sb = get_supabase()
    res = sb.table("price_diagnosis_report").select("*").order("sort_order").execute()
    return {"status": "success", "data": res.data}


@router.patch("/diagnosis-reports/{report_id}")
def update_diagnosis_report(report_id: str, body: DiagnosisReportUpdate):
    sb = get_supabase()

    old_res = sb.table("price_diagnosis_report").select("*").eq("id", report_id).single().execute()
    if not old_res.data:
        raise HTTPException(status_code=404, detail="보고서 가격을 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    update_data["updated_at"] = datetime.now().isoformat()

    changed = _log_changes(sb, "price_diagnosis_report", report_id, old_res.data, update_data)

    res = sb.table("price_diagnosis_report").update(update_data).eq("id", report_id).execute()
    return {
        "status": "success",
        "data": res.data[0] if res.data else None,
        "changes_logged": changed,
    }


# ── 변경 이력 ─────────────────────────────────────────────────

@router.get("/change-logs")
def list_change_logs(
    table_name: str = None,
    record_id: str = None,
    page: int = 1,
    page_size: int = 50,
):
    sb = get_supabase()
    q = sb.table("price_change_log").select("*")
    if table_name:
        q = q.eq("table_name", table_name)
    if record_id:
        q = q.eq("record_id", record_id)

    offset = (page - 1) * page_size
    res = q.order("changed_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": res.data}


# ── 수리중개 수수료 ──────────────────────────────────────────

@router.get("/repair-brokerage")
def list_repair_brokerage():
    sb = get_supabase()
    res = sb.table("price_repair_brokerage").select("*").order("repair_type_code").execute()
    return {"status": "success", "data": res.data}


@router.patch("/repair-brokerage/{item_id}")
def update_repair_brokerage(item_id: str, body: RepairBrokerageUpdate):
    sb = get_supabase()
    old_res = sb.table("price_repair_brokerage").select("*").eq("id", item_id).single().execute()
    if not old_res.data:
        raise HTTPException(status_code=404, detail="수리중개 요금을 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")
    update_data["updated_at"] = datetime.now().isoformat()

    changed = _log_changes(sb, "price_repair_brokerage", item_id, old_res.data, update_data)
    res = sb.table("price_repair_brokerage").update(update_data).eq("id", item_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None, "changes_logged": changed}


# ── 안전관리 대행 ─────────────────────────────────────────────

@router.get("/safety-management")
def list_safety_management():
    sb = get_supabase()
    res = sb.table("price_safety_management").select("*").order("worker_count_from").execute()
    return {"status": "success", "data": res.data}


@router.patch("/safety-management/{item_id}")
def update_safety_management(item_id: str, body: SafetyManagementUpdate):
    sb = get_supabase()
    old_res = sb.table("price_safety_management").select("*").eq("id", item_id).single().execute()
    if not old_res.data:
        raise HTTPException(status_code=404, detail="안전관리 요금을 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")
    update_data["updated_at"] = datetime.now().isoformat()

    changed = _log_changes(sb, "price_safety_management", item_id, old_res.data, update_data)
    res = sb.table("price_safety_management").update(update_data).eq("id", item_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None, "changes_logged": changed}


# ── 컨설팅 ────────────────────────────────────────────────────

@router.get("/consulting")
def list_consulting():
    sb = get_supabase()
    res = sb.table("price_consulting").select("*").order("consulting_type_code").execute()
    return {"status": "success", "data": res.data}


@router.patch("/consulting/{item_id}")
def update_consulting(item_id: str, body: ConsultingUpdate):
    sb = get_supabase()
    old_res = sb.table("price_consulting").select("*").eq("id", item_id).single().execute()
    if not old_res.data:
        raise HTTPException(status_code=404, detail="컨설팅 요금을 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")
    update_data["updated_at"] = datetime.now().isoformat()

    changed = _log_changes(sb, "price_consulting", item_id, old_res.data, update_data)
    res = sb.table("price_consulting").update(update_data).eq("id", item_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None, "changes_logged": changed}
