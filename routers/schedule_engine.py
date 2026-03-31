"""
법정점검 일정 생성 엔진 — v1.1.0
v1.1.0: BUG-3 수정
  - anchor_confirmed 체크 → ANCHOR_NOT_SET 반환
  - 과거 날짜도 OVERDUE 상태로 생성
  - 중복 체크 유지
"""
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase
from datetime import date, datetime, timedelta
import traceback

router = APIRouter(prefix="/schedule-engine", tags=["schedule_engine"])


def add_cycle(base_date: date, cycle_unit: str, cycle_value: int) -> date:
    if cycle_unit == "day":
        return base_date + timedelta(days=cycle_value)
    if cycle_unit == "week":
        return base_date + timedelta(weeks=cycle_value)
    if cycle_unit == "month":
        month = base_date.month - 1 + cycle_value
        year  = base_date.year + month // 12
        month = month % 12 + 1
        day   = min(base_date.day, 28)
        return date(year, month, day)
    if cycle_unit == "year":
        try:
            return date(base_date.year + cycle_value, base_date.month, base_date.day)
        except ValueError:
            return date(base_date.year + cycle_value, base_date.month, 28)
    return base_date


@router.get("/test")
def test():
    return {"message": "schedule engine alive"}


@router.post("/generate/{inspection_set_id}")
def generate_schedule(inspection_set_id: str):
    """
    단건 일정 생성.
    - anchor_confirmed=False → ANCHOR_NOT_SET 오류 반환
    - next_planned_date = anchor + cycle
    - 과거 날짜 → OVERDUE 상태로 생성
    - 중복 방지
    """
    try:
        supabase = get_supabase()

        iset_res = (
            supabase.table("inspection_sets")
            .select("*")
            .eq("id", inspection_set_id)
            .limit(1)
            .execute()
        )
        if not iset_res.data:
            return {"success": False, "message": "inspection_set not found"}

        s = iset_res.data[0]

        # ── BUG-3: anchor 없으면 명확한 오류 반환 ──
        if not s.get("schedule_anchor_date") or not s.get("anchor_confirmed"):
            return {
                "success":           False,
                "reason":            "ANCHOR_NOT_SET",
                "message":           "기준일이 설정되지 않았습니다. 기준일을 먼저 입력해주세요.",
                "inspection_set_id": inspection_set_id,
                "created_count":     0,
            }

        cycle_unit  = s.get("cycle_unit") or "year"
        cycle_value = int(s.get("cycle_value") or 1)
        anchor      = date.fromisoformat(str(s["schedule_anchor_date"]))

        # next_planned_date = anchor + 주기
        planned_date     = add_cycle(anchor, cycle_unit, cycle_value)
        planned_date_str = planned_date.isoformat()

        # 중복 체크
        existing = (
            supabase.table("work_schedules")
            .select("id")
            .eq("inspection_set_id", inspection_set_id)
            .eq("planned_date", planned_date_str)
            .execute()
        )
        if existing.data:
            return {
                "success":           True,
                "inspection_set_id": inspection_set_id,
                "created_count":     0,
                "message":           "이미 동일한 일정이 존재합니다.",
                "planned_date":      planned_date_str,
            }

        # ── BUG-3: 과거 날짜도 OVERDUE 상태로 생성 ──
        status_code = "OVERDUE" if planned_date < date.today() else "planned"

        insert_payload = {
            "company_id":        s.get("company_id"),
            "factory_id":        s.get("factory_id"),
            "inspection_set_id": inspection_set_id,
            "planned_date":      planned_date_str,
            "status_code":       status_code,
            "description":       f"{s.get('inspection_set_name', '')} 자동생성",
        }
        res = supabase.table("work_schedules").insert(insert_payload).execute()
        created = res.data or []

        # inspection_sets next_planned_date 업데이트
        supabase.table("inspection_sets").update({
            "next_planned_date": planned_date_str,
        }).eq("id", inspection_set_id).execute()

        return {
            "success":           True,
            "inspection_set_id": inspection_set_id,
            "created_count":     len(created),
            "created_rows":      created,
            "planned_date":      planned_date_str,
            "status":            status_code,
        }

    except Exception as e:
        return {
            "success":     False,
            "error_type":  type(e).__name__,
            "error_repr":  repr(e),
            "traceback":   traceback.format_exc(),
        }
