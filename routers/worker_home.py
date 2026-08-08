"""
worker_home.py — v1.1.0
작업자 전용 홈 API (오늘의 할일 + QR 스캔 → 점검세트 + 홈 지표 요약)

2026-04-13 신규 생성
2026-08-08 v1.1.0: GET /worker/summary 추가 (홈 지표 서버 기준 집계)

API:
  GET  /worker/today                   오늘의 할일 (배정된 점검/TBM/교육) 한 번에 반환
  GET  /worker/qr-check/{equipment_id} QR 스캔 → 해당 설비 점검세트 + 항목 반환
  GET  /worker/summary                 홈 상단 지표 3종 (점검완료/TBM서명/미처리이상)
"""
import logging
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/worker", tags=["worker_home"])

VERSION = "1.1.0"


def _today() -> str:
    return date.today().isoformat()


def _clean_phone(phone: str) -> str:
    return (phone or "").replace("-", "").replace(" ", "")


def _phone_variants(phone: str) -> list:
    """users.phone 은 하이픈 유무가 섞여 있어 양쪽 형식을 모두 시도한다.
    (worker_check.py 와 동일 관례)
    """
    clean = _clean_phone(phone)
    if not clean:
        return []
    out = [clean]
    if len(clean) == 11:
        out.append(f"{clean[:3]}-{clean[3:7]}-{clean[7:]}")
    return out


# ─────────────────────────────────────────────────────────────
# GET /worker/today
# ─────────────────────────────────────────────────────────────

@router.get("/today")
def get_today_tasks(
    user_id:    Optional[str] = Query(None, description="작업자 user UUID"),
    factory_id: Optional[str] = Query(None, description="시설 ID (TBM/교육 조회용)"),
    company_id: Optional[str] = Query(None, description="회사 ID"),
):
    """
    작업자 오늘의 할일.

    반환 구조:
    {
      "date": "2026-04-13",
      "tasks": {
        "inspections": [...],   # 배정된 점검 일정
        "tbm":         [...],   # 오늘의 TBM
        "education":   [...],   # 오늘 교육 일정
      },
      "summary": { "total": N, "pending": N, "completed": N }
    }
    """
    supabase = get_supabase()
    today = _today()

    tasks = {"inspections": [], "tbm": [], "education": []}

    # ── 1. 배정된 점검 일정 ──────────────────────────────────
    # work_assignments에서 오늘 날짜 + assigned_user_id 기준
    if user_id:
        wa_q = supabase.table("work_assignments") \
            .select("id, schedule_id, asset_id, status_code, inspection_set_id, scheduled_date") \
            .eq("assigned_user_id", user_id) \
            .eq("scheduled_date", today) \
            .neq("status_code", "CANCELLED")
        wa_res = wa_q.execute()

        for wa in (wa_res.data or []):
            item = {
                "assignment_id": wa["id"],
                "schedule_id":   wa["schedule_id"],
                "asset_id":      wa.get("asset_id"),
                "status_code":   wa.get("status_code", "PENDING"),
                "scheduled_date": wa.get("scheduled_date"),
                "type": "inspection",
            }
            # 점검세트명 조회
            if wa.get("inspection_set_id"):
                is_res = supabase.table("inspection_sets") \
                    .select("inspection_set_name, cycle_unit, cycle_value") \
                    .eq("id", wa["inspection_set_id"]) \
                    .limit(1).execute()
                if is_res.data:
                    item["inspection_set_name"] = is_res.data[0].get("inspection_set_name", "")
                    item["cycle_unit"]          = is_res.data[0].get("cycle_unit", "")

            # 업무일정 정보 보강
            if wa.get("schedule_id"):
                ws_res = supabase.table("work_schedules") \
                    .select("description, law_name, obligation_type") \
                    .eq("id", wa["schedule_id"]) \
                    .limit(1).execute()
                if ws_res.data:
                    item["description"]     = ws_res.data[0].get("description", "")
                    item["law_name"]        = ws_res.data[0].get("law_name", "")
                    item["obligation_type"] = ws_res.data[0].get("obligation_type", "")

            tasks["inspections"].append(item)

    # ── 2. 오늘의 TBM ──────────────────────────────────────
    if factory_id or company_id:
        tbm_q = supabase.table("tbm_meetings") \
            .select("id, meeting_title, work_date, work_location, conductor_name, status_code") \
            .eq("work_date", today) \
            .neq("status_code", "CANCELLED")
        if factory_id: tbm_q = tbm_q.eq("factory_id", factory_id)
        if company_id: tbm_q = tbm_q.eq("company_id", company_id)
        tbm_res = tbm_q.order("created_at", desc=False).limit(10).execute()

        for tbm in (tbm_res.data or []):
            tasks["tbm"].append({
                "tbm_id":         tbm["id"],
                "title":          tbm.get("meeting_title", "TBM"),
                "work_date":      tbm.get("work_date"),
                "work_location":  tbm.get("work_location", ""),
                "conductor_name": tbm.get("conductor_name", ""),
                "status_code":    tbm.get("status_code", "DRAFT"),
                "type":           "tbm",
            })

    # ── 3. 오늘 교육 일정 ──────────────────────────────────
    # education_sessions 테이블 기준 (company_id / 오늘 날짜)
    if company_id or factory_id:
        try:
            edu_q = supabase.table("education_sessions") \
                .select("id, session_name, scheduled_date, status_code, location, instructor_name") \
                .eq("scheduled_date", today)
            if company_id: edu_q = edu_q.eq("company_id", company_id)
            edu_res = edu_q.order("created_at", desc=False).limit(10).execute()

            for edu in (edu_res.data or []):
                tasks["education"].append({
                    "session_id":      edu["id"],
                    "session_name":    edu.get("session_name", "교육"),
                    "scheduled_date":  edu.get("scheduled_date"),
                    "status_code":     edu.get("status_code", "SCHEDULED"),
                    "location":        edu.get("location", ""),
                    "instructor_name": edu.get("instructor_name", ""),
                    "type":            "education",
                })
        except Exception:
            pass  # 테이블 없을 경우 무시

    # ── 집계 ──────────────────────────────────────────────
    all_tasks = tasks["inspections"] + tasks["tbm"] + tasks["education"]
    total     = len(all_tasks)
    completed = sum(1 for t in all_tasks if t.get("status_code") in ("COMPLETED", "DONE"))
    pending   = total - completed

    return {
        "status": "success",
        "data": {
            "date":    today,
            "tasks":   tasks,
            "summary": {
                "total":     total,
                "pending":   pending,
                "completed": completed,
            },
        },
    }


# ─────────────────────────────────────────────────────────────
# GET /worker/summary
# 작업자앱 홈 상단 지표 3종 — 서버가 소유한 사실로 집계한다.
#
# 종전에는 프론트가 localStorage(tai_activities)를 세었다. 그 구조는
#   - 관리자가 조치를 완료해도 미처리 이상 카운트가 줄지 않고
#   - 최근 10건 제한에 걸려 그 이상은 누락되며
#   - 판정이 title 문자열 매칭이라 i18n 언어 전환 시 0 이 되는
# 문제가 있었다. 상태의 소유자인 서버가 계산해 내려준다.
# ─────────────────────────────────────────────────────────────

@router.get("/summary")
def get_worker_summary(
    phone: str = Query(..., description="작업자 전화번호"),
    factory_id: Optional[str] = Query(None, description="TBM 조회 범위"),
    company_id: Optional[str] = Query(None, description="TBM 조회 범위"),
):
    """
    홈 상단 지표 3종.

    반환 구조:
    {
      "today_checks": 2,        # 오늘 완료한 점검 건수
      "tbm_signed":   true,     # 오늘 TBM 에 내가 서명했는지 (오늘 TBM 없으면 null)
      "open_issues":  3,        # 내가 신고한 건 중 미처리(RECEIVED) 건수
    }

    각 지표는 독립적으로 집계하며 실패 시 null 을 반환한다.
    프론트가 0 과 구분해 '미확인'으로 표시할 수 있어야 하기 때문이다 —
    조회 실패를 0 으로 내리면 작업자가 미처리 신고가 없다고 오인할 수 있다.
    """
    supabase = get_supabase()
    today = _today()
    variants = _phone_variants(phone)

    today_checks = None
    tbm_signed = None
    open_issues = None

    # ── 1. 오늘 완료한 점검 ────────────────────────────────
    # safety_inspections.inspection_date 는 timestamp 이므로 당일 범위로 필터한다.
    try:
        inspector_id = None
        for v in variants:
            u = supabase.table("users").select("id").eq("phone", v).limit(1).execute()
            if u.data:
                inspector_id = u.data[0]["id"]
                break
        if not inspector_id and variants:
            w = supabase.table("worker_registry").select("id").eq("phone", variants[0]).limit(1).execute()
            if w.data:
                inspector_id = w.data[0]["id"]

        if inspector_id:
            r = supabase.table("safety_inspections") \
                .select("id", count="exact") \
                .eq("inspector_id", inspector_id) \
                .gte("inspection_date", f"{today}T00:00:00") \
                .lte("inspection_date", f"{today}T23:59:59") \
                .execute()
            today_checks = r.count or 0
        else:
            # 작업자를 특정하지 못하면 0 건이 맞다(기록 주체가 없으므로).
            today_checks = 0
    except Exception as e:
        log.error(f"[WorkerSummary] today_checks 집계 실패 phone={phone}: {e}")

    # ── 2. 오늘 TBM 서명 여부 ──────────────────────────────
    # tbm_attendees.phone 이 존재해 전화번호로 직접 조회할 수 있다.
    try:
        tbm_q = supabase.table("tbm_meetings").select("id") \
            .eq("work_date", today).neq("status_code", "CANCELLED")
        if factory_id: tbm_q = tbm_q.eq("factory_id", factory_id)
        if company_id: tbm_q = tbm_q.eq("company_id", company_id)
        tbm_res = tbm_q.limit(20).execute()
        tbm_ids = [t["id"] for t in (tbm_res.data or [])]

        if not tbm_ids:
            # 오늘 TBM 자체가 없으면 '미완료'가 아니라 '해당 없음'이다.
            tbm_signed = None
        else:
            att = supabase.table("tbm_attendees") \
                .select("sign_status, phone") \
                .in_("meeting_id", tbm_ids) \
                .in_("phone", variants) \
                .execute()
            rows = att.data or []
            if not rows:
                # 명단에 없으면 서명 대상이 아니다.
                tbm_signed = None
            else:
                tbm_signed = any((r.get("sign_status") or "").upper() == "SIGNED" for r in rows)
    except Exception as e:
        log.error(f"[WorkerSummary] tbm_signed 집계 실패 phone={phone}: {e}")

    # ── 3. 미처리 이상 신고 ────────────────────────────────
    # 관리자가 조치를 확인(CONFIRMED)하면 자연히 줄어든다.
    try:
        r = supabase.table("safety_reports") \
            .select("id", count="exact") \
            .in_("phone", variants) \
            .eq("status", "RECEIVED") \
            .execute()
        open_issues = r.count or 0
    except Exception as e:
        log.error(f"[WorkerSummary] open_issues 집계 실패 phone={phone}: {e}")

    return {
        "status": "success",
        "data": {
            "date":         today,
            "today_checks": today_checks,
            "tbm_signed":   tbm_signed,
            "open_issues":  open_issues,
        },
    }


# ─────────────────────────────────────────────────────────────
# GET /worker/qr-check/{equipment_id}
# QR 스캔 → 설비 ID로 점검세트 + 항목 반환
# ─────────────────────────────────────────────────────────────

@router.get("/qr-check/{equipment_id}")
def get_qr_inspection(equipment_id: str):
    """
    QR 스캔 후 설비 ID로 해당 설비의 점검세트와 항목을 반환.

    반환 구조:
    {
      "equipment": { id, name, ... },
      "inspection_sets": [
        {
          "inspection_set_id": ...,
          "inspection_set_name": ...,
          "items": [ { item_seq, item_name, is_required, description }, ... ]
        }
      ]
    }
    """
    supabase = get_supabase()

    # 1. 설비 정보 조회 (equipment_assets 테이블)
    eq_res = supabase.table("equipment_assets") \
        .select("id, name, asset_code, factory_id, company_id, status_code") \
        .eq("id", equipment_id) \
        .limit(1).execute()

    if not eq_res.data:
        raise HTTPException(status_code=404, detail="설비를 찾을 수 없습니다.")

    equipment = eq_res.data[0]
    factory_id = equipment.get("factory_id")

    # 2. 해당 설비에 연결된 inspection_sets 조회
    #    equipment_set_id → equipment_assets.id 또는
    #    inspection_sets.factory_id + equipment_set_id 기반
    sets_data = []

    # equipment_assets.id로 매핑된 inspection_sets
    is_res = supabase.table("inspection_sets") \
        .select("id, inspection_set_name, cycle_unit, cycle_value, description") \
        .eq("equipment_set_id", equipment_id) \
        .execute()

    # factory_id 기반 전체 세트도 포함 (설비별 매핑 없을 때)
    if not is_res.data and factory_id:
        is_res = supabase.table("inspection_sets") \
            .select("id, inspection_set_name, cycle_unit, cycle_value, description") \
            .eq("factory_id", factory_id) \
            .limit(20).execute()

    for iset in (is_res.data or []):
        set_id = iset["id"]

        # 3. 점검 항목 조회
        items_res = supabase.table("inspection_set_items") \
            .select("item_seq, item_name, is_required, description") \
            .eq("inspection_set_id", set_id) \
            .eq("is_active", True) \
            .order("item_seq").execute()

        sets_data.append({
            "inspection_set_id":   set_id,
            "inspection_set_name": iset.get("inspection_set_name", ""),
            "cycle_unit":          iset.get("cycle_unit", ""),
            "cycle_value":         iset.get("cycle_value"),
            "description":         iset.get("description", ""),
            "items":               items_res.data or [],
        })

    return {
        "status": "success",
        "data": {
            "equipment":      equipment,
            "inspection_sets": sets_data,
            "total_sets":     len(sets_data),
        },
    }
