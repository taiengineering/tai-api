"""
건설안전 관리 라우터 — v2.2.3
=====================================
v2.2.3 (2026-04-16):
  ① 동기화: main v2.2.2 (FS-05) 내용 dev 반영
     - SiteCreate/SitePatch에 latitude, longitude(WGS84, Optional[float]) 필드 추가
     - DB migration 'add_construction_sites_coordinates' 이미 적용됨
     - 대시보드 날씨 위젯이 construction_sites.latitude/longitude 직접 사용
     - 주소→좌표 변환(/juso/coord) 결과를 최초 1회 저장, 반복 변환 제거
  ② SB-01 BUG-FIX #3: _auto_diagnose_and_schedule() rule coverage 통일
     - inspection_required 만 → inspection_required + action_required 둘 다
     - generate-schedules 엔드포인트와 동일한 커버리지 (177건 수준)
  ③ SB-02: 모든 print() → utils.logger (get_logger) 교체
     - silent fail 패턴 유지하되 Fly.io 로그에서 [ERROR] grep 감지 가능

v2.2.2 (2026-04-16 main, FS-05 핫픽스):
  FS-05: SiteCreate/SitePatch latitude/longitude 추가

v2.2.1 (2026-04-16):
  BUG-FIX #1: _create_factory_for_site() construction_type 매핑
  BUG-FIX #2 (DB): inspection_sets UNIQUE scope (factory_id, code)

v2.2.0 (2026-04-16):
  BE-1: inspection_sets 자동 생성 (호출 위치 2곳)
  BE-3: contract_amount 단위 명확화
  BE-4: GET /kcsc/processes?search=

v2.1.0 (2026-04-09):
  POST /sites/{site_id}/diagnose, /generate-schedules, 점검 FCM 알림

v2.0.0 (2026-04-07):
  POST /sites: factories 자동 생성 + 자동 진단/일정
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime, date, timezone
import httpx

from db.supabase_client import get_supabase
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["건설안전"])

VERSION = "2.2.3"

FCM_URL = "https://fcm.googleapis.com/fcm/send"

# v2.2.1 BUG-FIX #1: site_type → construction_type 매핑
# factories.construction_type CHECK 제약: '건축' | '토목' | '공통' | '기타'
CONSTRUCTION_TYPE_MAP: Dict[str, str] = {
    "BUILDING":  "건축",
    "CIVIL":     "토목",
    "SPECIALTY": "공통",
}


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
# v2.2.1: BUG-FIX #1 construction_type 매핑
# ──────────────────────────────────────────────

def _create_factory_for_site(supabase, site: dict) -> Optional[str]:
    try:
        contract_eok = float(site.get("contract_amount") or 0)
        site_type_raw = (site.get("site_type") or "BUILDING").upper()
        construction_type_label = CONSTRUCTION_TYPE_MAP.get(site_type_raw, "건축")

        factory_data = {
            "name":                      site.get("site_name", ""),
            "company_id":                site.get("company_id"),
            "site_type":                 "CONSTRUCTION",
            "sector":                    "CONSTRUCTION",
            "construction_amount":       contract_eok * 100_000_000,
            "employee_count":            site.get("direct_workers") or site.get("total_workers") or 0,
            "subcontractor_worker_count": site.get("subcon_workers") or 0,
            "construction_type":         construction_type_label,
            "site_address":              site.get("site_address"),
            "status_code":               "ACTIVE",
            "is_active":                 True,
            "created_at":                _now_iso(),
            "updated_at":                _now_iso(),
        }
        res = supabase.table("factories").insert(factory_data).execute()
        if res.data:
            factory_id = res.data[0]["id"]
            supabase.table("construction_sites").update({
                "factory_id": factory_id,
                "updated_at": _now_iso(),
            }).eq("id", site["id"]).execute()
            return factory_id
    except Exception as e:
        log.error("[CONSTRUCTION] factories 자동생성 실패 (무시): %s", e, exc_info=True)
    return None


# ──────────────────────────────────────────────
# v2.0.0: 내부 진단 실행 함수
# ──────────────────────────────────────────────

def _run_diagnosis(supabase, factory_id: str, site: dict) -> dict:
    """
    CONSTRUCTION sector 법령진단 실행.
    반환: applicable_count / diagnosis_id / result_data / by_obligation_type / applicable_rules
    """
    contract_eok = float(site.get("contract_amount") or 0)
    direct = int(site.get("direct_workers") or 0)
    subcon = int(site.get("subcon_workers") or 0)
    site_type_raw = site.get("site_type") or "BUILDING"

    from routers.legal_engine import (
        _input_to_facility_context,
        _evaluate_facility_conditions_db,
        _classify_rules_db,
        format_rule_result_db,
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

    triggered: Dict[str, List] = {
        "appointment": [], "inspection": [], "notify": [],
        "report": [], "action": [], "not_applicable": []
    }
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

    diagnosis_id = save_res.data[0]["id"] if save_res.data else None

    if diagnosis_id:
        supabase.table("construction_sites").update({
            "diagnosis_step1_id":         diagnosis_id,
            "last_diagnosis_at":          _now_iso(),
            "diagnosis_applicable_count": total_applicable,
            "updated_at":                 _now_iso(),
        }).eq("factory_id", factory_id).execute()

    return {
        "applicable_count":  total_applicable,
        "diagnosis_id":      diagnosis_id,
        "result_data":       result_data,
        "by_obligation_type": result_data["summary"],
        "applicable_rules":  applicable,
    }


# ──────────────────────────────────────────────
# v2.0.0: 내부 스케줄 생성 함수
# ──────────────────────────────────────────────

def _run_generate_schedules(supabase, factory_id: str, inspection_rules: list, company_id: Optional[str]) -> dict:
    existing = supabase.table("work_schedules").select("rule_code") \
        .eq("factory_id", factory_id).eq("source_type", "LEGAL").eq("status_code", "PENDING").execute()
    existing_codes = {r["rule_code"] for r in (existing.data or []) if r.get("rule_code")}

    today_str = date.today().isoformat()
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
        sched_res = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
        created += len(sched_res.data or [])

    skipped = len(inspection_rules) - len(rows)
    return {"created": created, "skipped": skipped, "total_rules": len(inspection_rules)}


def _auto_diagnose_and_schedule(supabase, factory_id: str, site: dict) -> dict:
    """
    v2.0.0: 현장 등록 시 자동 진단 + 스케줄 생성.
    v2.2.3 SB-01 BUG-FIX #3: inspection + action 모두 스케줄화 (이전: inspection만).
    실패 시 logger.error 기록 후 무시 (현장 등록 자체는 성공 처리).
    """
    result = {"diagnosis": None, "schedules": None}
    try:
        diag = _run_diagnosis(supabase, factory_id, site)
        result["diagnosis"] = {"applicable_count": diag["applicable_count"]}

        company_res = supabase.table("factories").select("company_id").eq("id", factory_id).single().execute()
        company_id = company_res.data.get("company_id") if company_res.data else None

        # SB-01 BUG-FIX #3: inspection + action 둘 다
        inspection_rules = diag["result_data"].get("inspection_required") or []
        action_rules     = diag["result_data"].get("action_required") or []
        all_rules = inspection_rules + action_rules
        sched = _run_generate_schedules(supabase, factory_id, all_rules, company_id)
        result["schedules"] = sched

        # v2.2.0 BE-1: inspection_sets 자동생성 [호출 위치 1]
        try:
            from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis
            auto_create_inspection_sets_from_diagnosis(
                supabase, factory_id, company_id,
                diag.get("applicable_rules") or [],
            )
        except Exception as e:
            log.error("[AUTO_INSPECT_SETS] 현장등록 자동생성 실패 (무시): %s", e, exc_info=True)

    except Exception as e:
        log.error("[CONSTRUCTION] 자동진단/일정생성 실패 (무시): %s", e, exc_info=True)
    return result


# ──────────────────────────────────────────────
# v2.1.0: FCM 알림 헬퍼
# ──────────────────────────────────────────────

async def _send_fcm_inspection_alert(supabase, site_id: str, inspection_id: str, defect_count: int):
    import os
    fcm_server_key = os.getenv("FCM_SERVER_KEY", "")
    if not fcm_server_key:
        return
    try:
        site_res = supabase.table("construction_sites").select("site_name, manager_id").eq("id", site_id).limit(1).execute()
        if not site_res.data:
            return
        site = site_res.data[0]
        manager_id = site.get("manager_id")
        if not manager_id:
            return
        user_res = supabase.table("users").select("fcm_token, name").eq("id", manager_id).limit(1).execute()
        if not user_res.data or not user_res.data[0].get("fcm_token"):
            return
        fcm_token = user_res.data[0]["fcm_token"]
        site_name = site.get("site_name", "현장")
        payload = {
            "to": fcm_token,
            "notification": {
                "title": f"⚠️ [{site_name}] 점검 이상 발생",
                "body":  f"이상 항목 {defect_count}건 감지. 즉시 확인이 필요합니다.",
                "sound": "default",
            },
            "data": {
                "type":          "INSPECTION_FAIL",
                "site_id":       site_id,
                "inspection_id": inspection_id,
                "defect_count":  str(defect_count),
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                FCM_URL, json=payload,
                headers={"Authorization": f"key={fcm_server_key}", "Content-Type": "application/json"},
            )
    except Exception as e:
        log.warning("[FCM] 점검 알림 발송 실패 (무시): %s", e)


# ══════════════════════════════════════════════
# Pydantic 모델
# ══════════════════════════════════════════════

class SiteCreate(BaseModel):
    company_id: str
    site_name: str
    site_code: Optional[str] = None
    site_type: str = "BUILDING"
    contract_amount: Optional[float] = Field(
        None,
        description="공사 도급금액. 단위: 억원(1억=100,000,000원). "
                    "예) 150억원 공사 → 150 입력. "
                    "원화(원) 단위 입력 시 안전관리자 선임 의무 판정 오류 발생.",
    )
    total_workers: Optional[int] = 0
    direct_workers: Optional[int] = 0
    subcon_workers: Optional[int] = 0
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    # v2.2.3 (FS-05): 날씨 위젯용 WGS84 좌표 (선택)
    # /juso/coord 변환 결과를 최초 1회 저장하여 반복 변환 제거
    latitude: Optional[float] = Field(None, description="WGS84 위도 (예: 37.5665)")
    longitude: Optional[float] = Field(None, description="WGS84 경도 (예: 126.9780)")
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
    # v2.2.3 (FS-05): 날씨 위젯용 WGS84 좌표 (선택)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
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
    """현장 등록 + factories 자동생성 + 법령진단 자동실행 + 일정/inspection_sets 자동생성"""
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

        res = supabase.table("construction_sites").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        site = res.data[0]

        factory_id = _create_factory_for_site(supabase, site)

        auto_result = {}
        if factory_id:
            auto_result = _auto_diagnose_and_schedule(supabase, factory_id, site)

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
                "fail": sum(1 for i in insps if i.get("overall_result") in ("FAIL", "ISSUE")),
            },
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ② 건설 법령진단 (독립 엔드포인트)
# ══════════════════════════════════════════════

@router.post("/sites/{site_id}/diagnose")
async def diagnose_site(site_id: str):
    """
    건설현장 법령진단 독립 실행.
    v2.2.0 BE-1: 진단 완료 후 inspection_sets 자동 생성 [호출 위치 2]
    """
    supabase = get_supabase()
    try:
        site_res = supabase.table("construction_sites").select("*").eq("id", site_id).eq("is_active", True).limit(1).execute()
        if not site_res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        site = site_res.data[0]

        factory_id = site.get("factory_id")
        if not factory_id:
            factory_id = _create_factory_for_site(supabase, site)
            if not factory_id:
                raise HTTPException(status_code=500, detail="factory 연결 실패")

        diag = _run_diagnosis(supabase, factory_id, site)

        try:
            from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis
            company_res = supabase.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
            company_id = company_res.data[0].get("company_id") if company_res.data else None
            auto_create_inspection_sets_from_diagnosis(
                supabase, factory_id, company_id,
                diag.get("applicable_rules") or [],
            )
        except Exception as e:
            log.error("[AUTO_INSPECT_SETS] diagnose_site 자동생성 실패 (무시): %s", e, exc_info=True)

        return {
            "status": "success",
            "data": {
                "site_id":            site_id,
                "factory_id":         factory_id,
                "applicable_rules":   diag["applicable_count"],
                "diagnosis_id":       diag["diagnosis_id"],
                "by_obligation_type": diag["by_obligation_type"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ③ 작업일정 자동 생성 (독립 엔드포인트)
# ══════════════════════════════════════════════

@router.post("/sites/{site_id}/generate-schedules")
async def generate_schedules(site_id: str):
    supabase = get_supabase()
    try:
        site_res = supabase.table("construction_sites").select("factory_id, company_id").eq("id", site_id).eq("is_active", True).limit(1).execute()
        if not site_res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        site = site_res.data[0]
        factory_id = site.get("factory_id")
        company_id = site.get("company_id")

        if not factory_id:
            raise HTTPException(status_code=400, detail="법령진단을 먼저 실행하세요 (factory_id 없음)")

        diag_res = supabase.table("factory_diagnosis_results") \
            .select("result_data") \
            .eq("factory_id", factory_id) \
            .eq("sector", "CONSTRUCTION") \
            .eq("is_latest", True) \
            .limit(1).execute()

        if not diag_res.data:
            raise HTTPException(status_code=400, detail="법령진단을 먼저 실행하세요")

        result_data = diag_res.data[0].get("result_data") or {}
        inspection_rules = result_data.get("inspection_required") or []
        action_rules     = result_data.get("action_required") or []
        all_rules = inspection_rules + action_rules

        sched = _run_generate_schedules(supabase, factory_id, all_rules, company_id)

        return {
            "status": "success",
            "data": {
                "site_id":     site_id,
                "factory_id":  factory_id,
                "created":     sched["created"],
                "skipped":     sched["skipped"],
                "total_rules": sched["total_rules"],
                "message":     f"{sched['created']}건 일정 생성, {sched['skipped']}건 중복 스킵",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ④ 공정 (Processes)
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
# ⑤ KCSC 마스터 (BE-4)
# ══════════════════════════════════════════════

@router.get("/kcsc/processes")
async def list_kcsc_processes(
    search: Optional[str] = Query(None, description="공정명 검색 (부분일치). 예) 굴착"),
    construction_type: Optional[str] = Query(None, description="BUILDING / CIVIL / COMMON"),
    work_type_code: Optional[str] = Query(None, description="작업 유형 코드. 예) EXCAVATION"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    """BE-4: KCSC 공정 마스터 검색 API"""
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
# ⑥ 위험작업 / PTW (Works)
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
# ⑦ 작업자 (Workers)
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
# ⑧ 안전점검 (Inspections)
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
    """점검 저장 시 이상(FAIL/ISSUE) 감지 → 안전관리자 FCM 자동 발송"""
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id

        checklist = data.get("checklist_items") or []
        if isinstance(checklist, list):
            bad_items = [item for item in checklist if isinstance(item, dict) and item.get("result") in ("bad", "fail", "이상", "FAIL")]
            defect_count = len(bad_items)
            data["defect_count"] = defect_count
            if "overall_result" not in data or not data["overall_result"]:
                data["overall_result"] = "ISSUE" if defect_count > 0 else "PASS"

        if "inspection_date" in data and isinstance(data["inspection_date"], datetime):
            data["inspection_date"] = data["inspection_date"].isoformat()
        if "corrective_deadline" in data and isinstance(data["corrective_deadline"], date):
            data["corrective_deadline"] = data["corrective_deadline"].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()

        res = supabase.table("construction_inspections").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")

        inspection = res.data[0]

        if data.get("overall_result") in ("FAIL", "ISSUE") and data.get("defect_count", 0) > 0:
            await _send_fcm_inspection_alert(
                supabase,
                site_id=site_id,
                inspection_id=inspection["id"],
                defect_count=data.get("defect_count", 1),
            )

        return {"status": "success", "data": inspection}
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
# ⑨ 안전관리자 선임 의무 판정 엔진
# ══════════════════════════════════════════════

@router.post("/engine/safety-manager")
async def engine_safety_manager(body: SafetyManagerBody):
    result = calc_safety_manager(body.site_type, body.contract_amount, body.total_workers)
    return {"status": "success", "data": result}
