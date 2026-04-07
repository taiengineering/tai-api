"""
건설안전 관리 라우터 — v2.0.0
=====================================
v2.0.0 (2026-04-07 현장소장 온보딩 Phase 1):
  - POST /sites: factories 테이블 자동 생성 (sector='CONSTRUCTION') + construction_sites.factory_id 업데이트
  - POST /sites: 현장 생성 후 diagnose/step1 자동 실행 + generate_schedules 자동 트리거
  - user_role '025 현장소장' DB 추가 (migration)
  - construction_sites.factory_id 컬럼 추가 (migration)

v1.1.0:
  - GET /kcsc/works 전체 위험작업 조회 엔드포인트 추가 (is_hazardous 필터)
  - GET /kcsc/processes 정렬 버그 수정 (process_code → kcs_code)
  - GET /kcsc/works/{process_id} is_active 필터 추가
v1.0.0: 신규 생성
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from datetime import datetime, date, timezone

from db.supabase_client import get_supabase

router = APIRouter(tags=["건설안전"])

VERSION = "2.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ptw_number(site_id: str, supabase) -> str:
    """CS-{YYYY}-{5자리 순번} 자동채번"""
    year = datetime.now().year
    res = supabase.table("construction_works") \
        .select("id", count="exact") \
        .eq("site_id", site_id) \
        .execute()
    seq = (res.count or 0) + 1
    return f"CS-{year}-{seq:05d}"


# ──────────────────────────────────────────────
# 안전관리자 선임 의무 판정 엔진
# ──────────────────────────────────────────────

def calc_safety_manager(site_type: str, contract_amount: float, total_workers: int) -> Dict[str, Any]:
    """
    산안법 시행령 제16조 기준
    - 건축(BUILDING): 도급금액 >= 150억 → 선임 의무
    - 토목(CIVIL):    도급금액 >= 120억 → 선임 의무
    - 상시 근로자(하도급 포함) >= 50명 → 선임 의무 (도급금액 무관)
    """
    required = False
    count = 0
    reasons = []

    if site_type == "BUILDING" and contract_amount >= 150:
        required = True
        count = max(1, int(contract_amount // 150))
        reasons.append(f"건축 도급금액 {contract_amount}억 ≥ 150억 (시행령 제16조①1호가목)")
    elif site_type == "CIVIL" and contract_amount >= 120:
        required = True
        count = max(1, int(contract_amount // 120))
        reasons.append(f"토목 도급금액 {contract_amount}억 ≥ 120억 (시행령 제16조①1호나목)")

    if total_workers >= 50:
        required = True
        count = max(count, 1)
        reasons.append(f"상시 근로자(하도급 포함) {total_workers}명 ≥ 50명 (시행령 제16조③)")

    return {
        "required": required,
        "count": count,
        "reasons": reasons,
        "site_type": site_type,
        "contract_amount": contract_amount,
        "total_workers": total_workers,
    }


# ──────────────────────────────────────────────
# v2.0.0: factories 자동생성 헬퍼
# ──────────────────────────────────────────────

def _create_factory_for_site(supabase, site: dict) -> Optional[str]:
    """
    construction_sites → factories 자동연결
    sector='CONSTRUCTION', site_type='CONSTRUCTION' factory 생성 후 factory_id 반환.
    실패 시 None 반환 (현장 등록 자체는 롤백하지 않음).
    """
    try:
        contract_eok = float(site.get("contract_amount") or 0)
        # factories 컬럼: name, company_id, site_type, sector, construction_amount,
        #   employee_count, construction_type, subcontractor_worker_count, status_code,
        #   site_address, is_active, created_at, updated_at
        factory_data = {
            "name":                      site.get("site_name", ""),
            "company_id":                site.get("company_id"),
            "site_type":                 "CONSTRUCTION",
            "sector":                    "CONSTRUCTION",
            "construction_amount":       contract_eok * 100_000_000,  # 억원 → 원
            "employee_count":            site.get("direct_workers") or site.get("total_workers") or 0,
            "subcontractor_worker_count": site.get("subcon_workers") or 0,
            "construction_type":         site.get("site_type") or "건축",  # BUILDING/CIVIL → 건축/토목
            "site_address":              site.get("site_address"),
            "status_code":               "ACTIVE",
            "is_active":                 True,
            "created_at":                _now_iso(),
            "updated_at":                _now_iso(),
        }
        res = supabase.table("factories").insert(factory_data).execute()
        if res.data:
            factory_id = res.data[0]["id"]
            # construction_sites.factory_id 업데이트
            supabase.table("construction_sites").update({
                "factory_id": factory_id,
                "updated_at": _now_iso(),
            }).eq("id", site["id"]).execute()
            return factory_id
    except Exception as e:
        print(f"[CONSTRUCTION] factories 자동생성 실패 (무시): {e}")
    return None


def _auto_diagnose_and_schedule(supabase, factory_id: str, site: dict) -> dict:
    """
    v2.0.0: CONSTRUCTION sector → diagnose/step1 자동실행 + generate_schedules 트리거.
    실패해도 현장 생성 결과에 영향 없음.
    """
    result = {"diagnosis": None, "schedules": None}
    try:
        contract_eok = float(site.get("contract_amount") or 0)
        direct = int(site.get("direct_workers") or 0)
        subcon = int(site.get("subcon_workers") or 0)
        site_type_raw = site.get("site_type") or "BUILDING"

        # diagnose/step1 내부 로직 직접 실행 (HTTP 자기호출 대신 import)
        from routers.legal_engine import (
            _input_to_facility_context,
            _evaluate_facility_conditions_db,
            _classify_rules_db,
            format_rule_result_db,
            _resolve_obligation_type,
            _get_construction_summary,
            get_sector_groups,
            ENGINE_VERSION,
        )
        sector_raw = "CONSTRUCTION"
        sector_groups = get_sector_groups(sector_raw)
        rules_res = supabase.table("master_building_legal_rules").select("*") \
            .eq("is_active", True).in_("sector", sector_groups).eq("diagnosis_stage", 1).execute()
        all_rules = rules_res.data or []

        inp = {
            "contract_amount_eok": contract_eok,
            "direct_workers":      direct,
            "subcon_workers":      subcon,
            "construction_type":   site_type_raw,
        }
        facility_ctx = _input_to_facility_context(sector_raw, inp)
        evaluated_at = datetime.now().isoformat()
        applicable, not_applicable = _evaluate_facility_conditions_db(facility_ctx, all_rules, sector_raw)

        triggered: Dict[str, List] = {"appointment": [], "inspection": [], "notify": [], "report": [], "action": [], "not_applicable": []}
        _classify_rules_db(applicable, triggered)
        for r in not_applicable:
            triggered["not_applicable"].append(format_rule_result_db(r))

        total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
        result_data = {
            "factory_id": factory_id, "sector": sector_raw, "sector_groups": sector_groups,
            "step": 1, "engine_version": ENGINE_VERSION, "evaluated_at": evaluated_at,
            "facility_context": facility_ctx,
            "appointment_required": triggered["appointment"],
            "inspection_required":  triggered["inspection"],
            "action_required":      triggered["action"],
            "report_required":      triggered["report"] + triggered["notify"],
            "applicable_count":     total_applicable,
            "construction_summary": _get_construction_summary(facility_ctx),
            "summary": {
                "total": total_applicable,
                "appointment": len(triggered["appointment"]),
                "inspection":  len(triggered["inspection"]),
                "action":      len(triggered["action"]),
                "report":      len(triggered["report"]),
                "notify":      len(triggered["notify"]),
            },
        }

        # factory_diagnosis_results 저장
        try:
            supabase.table("factory_diagnosis_results").update({"is_latest": False}) \
                .eq("factory_id", factory_id).eq("sector", sector_raw).eq("is_latest", True).execute()
        except Exception:
            pass
        save_res = supabase.table("factory_diagnosis_results").insert({
            "factory_id":      factory_id,
            "sector":          sector_raw,
            "diagnosis_stage": 1,
            "input_data":      inp,
            "result_data":     result_data,
            "rule_count":      total_applicable,
            "is_latest":       True,
        }).execute()

        result["diagnosis"] = {"applicable_count": total_applicable}

        # construction_sites 진단 결과 연결
        if save_res.data:
            diag_id = save_res.data[0]["id"]
            supabase.table("construction_sites").update({
                "diagnosis_step1_id":        diag_id,
                "last_diagnosis_at":         _now_iso(),
                "diagnosis_applicable_count": total_applicable,
                "updated_at":                _now_iso(),
            }).eq("factory_id", factory_id).execute()

        # generate_schedules 자동 트리거
        from routers.legal_engine_patch import generate_schedules_from_diagnosis
        # FastAPI Request 없이 직접 supabase 활용하여 내부 로직 재현
        inspection_rules = result_data.get("inspection_required") or []
        existing = supabase.table("work_schedules").select("rule_code") \
            .eq("factory_id", factory_id).eq("source_type", "LEGAL").eq("status_code", "PENDING").execute()
        existing_codes = {r["rule_code"] for r in (existing.data or []) if r.get("rule_code")}
        today_str = date.today().isoformat()
        company_id_fac = supabase.table("factories").select("company_id").eq("id", factory_id).single().execute()
        company_id = company_id_fac.data.get("company_id") if company_id_fac.data else None
        rows = []
        for rule in inspection_rules:
            rule_id = (rule.get("rule_id") or rule.get("rule_code") or "").strip()
            if not rule_id or rule_id in existing_codes:
                continue
            rows.append({
                "factory_id":      factory_id,
                "company_id":      company_id,
                "source_type":     "LEGAL",
                "rule_code":       rule_id,
                "description":     (rule.get("obligation_summary") or rule.get("description") or "").strip(),
                "obligation_type": rule.get("obligation_type") or "INSPECT",
                "law_name":        rule.get("law_name") or "",
                "law_article":     rule.get("law_article") or "",
                "form_code":       rule.get("form_code") or None,
                "planned_date":    today_str,
                "status_code":     "PENDING",
                "active_yn":       True,
            })
            existing_codes.add(rule_id)
        created = 0
        for i in range(0, len(rows), 20):
            sched_res = supabase.table("work_schedules").insert(rows[i:i+20]).execute()
            created += len(sched_res.data or [])
        result["schedules"] = {"created": created, "total_rules": len(inspection_rules)}

    except Exception as e:
        print(f"[CONSTRUCTION] 자동진단/일정생성 실패 (무시): {e}")

    return result


# ══════════════════════════════════════════════
# Pydantic 모델
# ══════════════════════════════════════════════

class SiteCreate(BaseModel):
    company_id: str
    site_name: str
    site_code: Optional[str] = None
    site_type: str = "BUILDING"
    contract_amount: Optional[float] = None
    total_workers: Optional[int] = 0
    direct_workers: Optional[int] = 0
    subcon_workers: Optional[int] = 0
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    manager_id: Optional[str] = None
    status_code: Optional[str] = "PLANNED"
    notes: Optional[str] = None


class SitePatch(BaseModel):
    site_name: Optional[str] = None
    site_type: Optional[str] = None
    contract_amount: Optional[float] = None
    total_workers: Optional[int] = None
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    manager_id: Optional[str] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class ProcessCreate(BaseModel):
    process_master_id: Optional[str] = None
    kcsc_process_id: Optional[str] = None
    work_type_code: Optional[str] = None
    work_type_label: Optional[str] = None
    process_name: str
    construction_type: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    worker_count: Optional[int] = 0
    is_high_risk: Optional[bool] = False
    sort_order: Optional[int] = 0
    notes: Optional[str] = None


class ProcessPatch(BaseModel):
    process_name: Optional[str] = None
    kcsc_process_id: Optional[str] = None
    work_type_code: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    progress_rate: Optional[int] = None
    worker_count: Optional[int] = None
    is_high_risk: Optional[bool] = None
    status_code: Optional[str] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class WorkCreate(BaseModel):
    process_id: Optional[str] = None
    work_master_id: Optional[str] = None
    work_name: str
    work_date: date
    work_time_start: Optional[str] = None
    work_time_end: Optional[str] = None
    work_location: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    special_work_type: Optional[str] = None
    hazard_codes: Optional[str] = None
    ppe_required: Optional[str] = None
    worker_count: Optional[int] = 0
    notes: Optional[str] = None


class WorkPatch(BaseModel):
    work_name: Optional[str] = None
    work_date: Optional[date] = None
    work_time_start: Optional[str] = None
    work_time_end: Optional[str] = None
    work_location: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    special_work_type: Optional[str] = None
    hazard_codes: Optional[str] = None
    ppe_required: Optional[str] = None
    worker_count: Optional[int] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class PtwPatch(BaseModel):
    ptw_status: str
    ptw_approved_by: Optional[str] = None


class WorkerCreate(BaseModel):
    user_id: Optional[str] = None
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_type: Optional[str] = "SUBCON"
    subcontractor_id: Optional[str] = None
    role_code: Optional[str] = None
    join_date: Optional[date] = None
    certification_codes: Optional[str] = None
    safety_edu_date: Optional[date] = None
    safety_edu_hours: Optional[int] = 0
    notes: Optional[str] = None


class WorkerPatch(BaseModel):
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_type: Optional[str] = None
    subcontractor_id: Optional[str] = None
    role_code: Optional[str] = None
    join_date: Optional[date] = None
    leave_date: Optional[date] = None
    certification_codes: Optional[str] = None
    health_check_date: Optional[date] = None
    health_check_result: Optional[str] = None
    safety_edu_date: Optional[date] = None
    safety_edu_hours: Optional[int] = None
    notes: Optional[str] = None


class EntryPatch(BaseModel):
    entry_status: str


class InspectionCreate(BaseModel):
    work_id: Optional[str] = None
    process_id: Optional[str] = None
    inspection_date: Optional[datetime] = None
    inspector_id: Optional[str] = None
    inspection_type: Optional[str] = "BEFORE_WORK"
    checklist_items: Optional[Any] = None
    overall_result: Optional[str] = None
    defect_count: Optional[int] = 0
    defect_items: Optional[Any] = None
    corrective_action: Optional[str] = None
    corrective_deadline: Optional[date] = None
    photo_urls: Optional[List[str]] = None
    notes: Optional[str] = None


class InspectionPatch(BaseModel):
    inspection_type: Optional[str] = None
    checklist_items: Optional[Any] = None
    overall_result: Optional[str] = None
    defect_count: Optional[int] = None
    defect_items: Optional[Any] = None
    corrective_action: Optional[str] = None
    corrective_deadline: Optional[date] = None
    photo_urls: Optional[List[str]] = None
    notes: Optional[str] = None


class CorrectivePatch(BaseModel):
    corrective_status: str
    corrective_action: Optional[str] = None


class SafetyManagerBody(BaseModel):
    site_type: str
    contract_amount: float
    total_workers: int


# ══════════════════════════════════════════════
# ① 건설현장 (Sites)
# ══════════════════════════════════════════════

@router.get("/sites")
async def list_sites(
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    site_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_sites").select("*", count="exact").eq("is_active", True)
        if company_id:   q = q.eq("company_id", company_id)
        if status_code:  q = q.eq("status_code", status_code)
        if site_type:    q = q.eq("site_type", site_type)
        if search:       q = q.ilike("site_name", f"%{search}%")
        q = q.order("created_at", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
            "total_pages": ((res.count or 0) + size - 1) // size if res.count else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites")
async def create_site(body: SiteCreate):
    """
    v2.0.0: 현장 등록 + factories 자동생성(sector=CONSTRUCTION) + 법령진단 자동실행 + 일정 자동생성
    """
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        for key in ("start_date", "end_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        if body.contract_amount is not None:
            sm = calc_safety_manager(
                body.site_type,
                float(body.contract_amount),
                body.total_workers or 0,
            )
            data["safety_manager_required"] = sm["required"]
            data["safety_manager_count"] = sm["count"]
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()

        # construction_sites INSERT
        res = supabase.table("construction_sites").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        site = res.data[0]

        # v2.0.0: factories 자동생성 + factory_id 업데이트
        factory_id = _create_factory_for_site(supabase, site)

        # v2.0.0: CONSTRUCTION 법령진단 + 일정 자동생성
        auto_result = {}
        if factory_id:
            auto_result = _auto_diagnose_and_schedule(supabase, factory_id, site)

        # 최신 site 데이터 재조회 (factory_id 반영)
        updated = supabase.table("construction_sites").select("*").eq("id", site["id"]).single().execute()
        final_site = updated.data if updated.data else site

        return {
            "status": "success",
            "data": final_site,
            "auto": {
                "factory_id": factory_id,
                "diagnosis":  auto_result.get("diagnosis"),
                "schedules":  auto_result.get("schedules"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sites/{site_id}")
async def get_site(site_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_sites").select("*").eq("id", site_id).eq("is_active", True).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/sites/{site_id}")
async def update_site(site_id: str, body: SitePatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        for key in ("start_date", "end_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        if "contract_amount" in data or "total_workers" in data or "site_type" in data:
            site_res = supabase.table("construction_sites").select("site_type,contract_amount,total_workers").eq("id", site_id).limit(1).execute()
            if site_res.data:
                cur = site_res.data[0]
                sm = calc_safety_manager(
                    data.get("site_type", cur.get("site_type", "BUILDING")),
                    float(data.get("contract_amount", cur.get("contract_amount") or 0)),
                    int(data.get("total_workers", cur.get("total_workers") or 0)),
                )
                data["safety_manager_required"] = sm["required"]
                data["safety_manager_count"] = sm["count"]
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_sites").update(data).eq("id", site_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_sites").update({"is_active": False, "updated_at": _now_iso()}).eq("id", site_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/stats")
async def get_site_stats(site_id: str):
    supabase = get_supabase()
    try:
        site_res = supabase.table("construction_sites").select("*").eq("id", site_id).limit(1).execute()
        if not site_res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        site = site_res.data[0]
        proc_res   = supabase.table("construction_site_processes").select("id,status_code", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        work_res   = supabase.table("construction_works").select("id,status_code,ptw_status", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        worker_res = supabase.table("construction_workers").select("id,worker_type,entry_status", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        insp_res   = supabase.table("construction_inspections").select("id,overall_result", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        procs = proc_res.data or []; works = work_res.data or []
        workers = worker_res.data or []; insps = insp_res.data or []
        return {"status": "success", "data": {
            "site_id": site_id, "site_name": site.get("site_name"),
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
                "fail": sum(1 for i in insps if i.get("overall_result") == "FAIL"),
            },
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ② 공정 (Processes)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/processes")
async def list_processes(
    site_id: str,
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_site_processes").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if status_code:
            q = q.eq("status_code", status_code)
        q = q.order("sort_order").order("created_at").range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/processes")
async def create_process(site_id: str, body: ProcessCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        for key in ("planned_start", "planned_end"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_site_processes").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processes/{process_id}")
async def get_process(process_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_site_processes").select("*").eq("id", process_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/processes/{process_id}")
async def update_process(process_id: str, body: ProcessPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        for key in ("planned_start", "planned_end", "actual_start", "actual_end"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_site_processes").update(data).eq("id", process_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/processes/{process_id}")
async def delete_process(process_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_site_processes").update({"is_active": False, "updated_at": _now_iso()}).eq("id", process_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ③ KCSC 마스터
# ══════════════════════════════════════════════

@router.get("/kcsc/processes")
async def list_kcsc_processes(
    search: Optional[str] = Query(None),
    construction_type: Optional[str] = Query(None),
    work_type_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("kcsc_process_master").select("*", count="exact").eq("is_active", True)
        if search:             q = q.ilike("process_name", f"%{search}%")
        if construction_type:  q = q.eq("construction_type", construction_type)
        if work_type_code:     q = q.eq("work_type_code", work_type_code)
        q = q.order("kcs_code").range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kcsc/works")
async def list_kcsc_works_all(
    is_hazardous: Optional[bool] = Query(None),
    work_type_code: Optional[str] = Query(None),
    hazard_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=300),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("kcsc_work_master").select(
            "id, title, is_hazardous, hazard_type, safety_standard, "
            "is_work_item, equipment_type_codes, work_type_code, process_id",
            count="exact"
        ).eq("is_active", True)
        if is_hazardous is not None: q = q.eq("is_hazardous", is_hazardous)
        if work_type_code:           q = q.eq("work_type_code", work_type_code)
        if hazard_type:              q = q.ilike("hazard_type", f"%{hazard_type}%")
        if search:                   q = q.ilike("title", f"%{search}%")
        q = q.order("sort_order").order("title").range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kcsc/works/{process_id}")
async def list_kcsc_works_by_process(process_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("kcsc_work_master").select("*") \
            .eq("process_id", process_id).eq("is_active", True).order("sort_order").execute()
        return {"status": "success", "data": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ④ 위험작업 / PTW (Works)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/works")
async def list_works(
    site_id: str,
    status_code: Optional[str] = Query(None),
    ptw_status: Optional[str] = Query(None),
    work_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_works").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if status_code: q = q.eq("status_code", status_code)
        if ptw_status:  q = q.eq("ptw_status", ptw_status)
        if work_date:   q = q.eq("work_date", work_date)
        q = q.order("work_date", desc=True).order("created_at", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/works")
async def create_work(site_id: str, body: WorkCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        if "work_date" in data and isinstance(data["work_date"], date):
            data["work_date"] = data["work_date"].isoformat()
        data["ptw_number"] = _ptw_number(site_id, supabase)
        data["ptw_status"] = "DRAFT"
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_works").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/works/{work_id}")
async def get_work(work_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_works").select("*").eq("id", work_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/works/{work_id}")
async def update_work(work_id: str, body: WorkPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        if "work_date" in data and isinstance(data["work_date"], date):
            data["work_date"] = data["work_date"].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_works").update(data).eq("id", work_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/works/{work_id}/ptw")
async def update_ptw(work_id: str, body: PtwPatch):
    supabase = get_supabase()
    allowed = {"APPROVED", "REJECTED", "CLOSED"}
    if body.ptw_status not in allowed:
        raise HTTPException(status_code=400, detail=f"ptw_status는 {allowed} 중 하나여야 합니다.")
    data: Dict[str, Any] = {"ptw_status": body.ptw_status, "updated_at": _now_iso()}
    if body.ptw_status == "APPROVED":
        data["ptw_approved_by"] = body.ptw_approved_by
        data["ptw_approved_at"] = _now_iso()
    res = supabase.table("construction_works").update(data).eq("id", work_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/works/{work_id}")
async def delete_work(work_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_works").update({"is_active": False, "updated_at": _now_iso()}).eq("id", work_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ⑤ 작업자 (Workers)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/workers")
async def list_workers(
    site_id: str,
    worker_type: Optional[str] = Query(None),
    entry_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_workers").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if worker_type:  q = q.eq("worker_type", worker_type)
        if entry_status: q = q.eq("entry_status", entry_status)
        if search:       q = q.ilike("worker_name", f"%{search}%")
        q = q.order("created_at", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/workers")
async def create_worker(site_id: str, body: WorkerCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        for key in ("join_date", "safety_edu_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_workers").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workers/{worker_id}")
async def get_worker(worker_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_workers").select("*").eq("id", worker_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/workers/{worker_id}")
async def update_worker(worker_id: str, body: WorkerPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        for key in ("join_date", "leave_date", "health_check_date", "safety_edu_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_workers").update(data).eq("id", worker_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/workers/{worker_id}/entry")
async def update_entry(worker_id: str, body: EntryPatch):
    supabase = get_supabase()
    allowed = {"IN", "OUT", "OFFSITE"}
    if body.entry_status not in allowed:
        raise HTTPException(status_code=400, detail=f"entry_status는 {allowed} 중 하나여야 합니다.")
    data: Dict[str, Any] = {"entry_status": body.entry_status, "updated_at": _now_iso()}
    if body.entry_status == "IN":
        data["last_entry_at"] = _now_iso()
    res = supabase.table("construction_workers").update(data).eq("id", worker_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/workers/{worker_id}")
async def delete_worker(worker_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_workers").update({"is_active": False, "updated_at": _now_iso()}).eq("id", worker_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ⑥ 안전점검 (Inspections)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/inspections")
async def list_inspections(
    site_id: str,
    inspection_type: Optional[str] = Query(None),
    overall_result: Optional[str] = Query(None),
    corrective_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_inspections").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if inspection_type:   q = q.eq("inspection_type", inspection_type)
        if overall_result:    q = q.eq("overall_result", overall_result)
        if corrective_status: q = q.eq("corrective_status", corrective_status)
        q = q.order("inspection_date", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/inspections")
async def create_inspection(site_id: str, body: InspectionCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        if "inspection_date" in data and isinstance(data["inspection_date"], datetime):
            data["inspection_date"] = data["inspection_date"].isoformat()
        if "corrective_deadline" in data and isinstance(data["corrective_deadline"], date):
            data["corrective_deadline"] = data["corrective_deadline"].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_inspections").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspections/{inspection_id}")
async def get_inspection(inspection_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_inspections").select("*").eq("id", inspection_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/inspections/{inspection_id}")
async def update_inspection(inspection_id: str, body: InspectionPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        if "corrective_deadline" in data and isinstance(data["corrective_deadline"], date):
            data["corrective_deadline"] = data["corrective_deadline"].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_inspections").update(data).eq("id", inspection_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/inspections/{inspection_id}/corrective")
async def update_corrective(inspection_id: str, body: CorrectivePatch):
    supabase = get_supabase()
    allowed = {"IN_PROGRESS", "DONE"}
    if body.corrective_status not in allowed:
        raise HTTPException(status_code=400, detail=f"corrective_status는 {allowed} 중 하나여야 합니다.")
    data: Dict[str, Any] = {"corrective_status": body.corrective_status, "updated_at": _now_iso()}
    if body.corrective_action:
        data["corrective_action"] = body.corrective_action
    res = supabase.table("construction_inspections").update(data).eq("id", inspection_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/inspections/{inspection_id}")
async def delete_inspection(inspection_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_inspections").update({"is_active": False, "updated_at": _now_iso()}).eq("id", inspection_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ⑦ 안전관리자 선임 의무 판정 엔진
# ══════════════════════════════════════════════

@router.post("/engine/safety-manager")
async def engine_safety_manager(body: SafetyManagerBody):
    result = calc_safety_manager(body.site_type, body.contract_amount, body.total_workers)
    return {"status": "success", "data": result}
