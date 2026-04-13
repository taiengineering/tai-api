"""
worker_home.py — v1.0.0
작업자 전용 홈 API (오늘의 할일 + QR 스캔 → 점검세트)

2026-04-13 신규 생성

API:
  GET  /worker/today                   오늘의 할일 (배정된 점검/TBM/교육) 한 번에 반환
  GET  /worker/qr-check/{equipment_id} QR 스캔 → 해당 설비 점검세트 + 항목 반환
"""
import logging
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/worker", tags=["worker_home"])

VERSION = "1.0.0"


def _today() -> str:
    return date.today().isoformat()


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
