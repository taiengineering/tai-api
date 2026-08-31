"""
법정점검 일정 생성 엔진 — v1.2.0
v1.2.0: 점검주기생성_버그수정
  - anchor_confirmed 엄격 체크 완화
    - next_planned_date 있으면 anchor_confirmed 없어도 생성 가능
    - anchor만 있어도 cycle 계산으로 생성 가능
    - anchor & next_planned_date 모두 없는 경우만 ANCHOR_NOT_SET
  - status_code SCHEDULED (이전: OVERDUE/planned)
  - 중복 방지 유지
v1.1.0: BUG-3 anchor_confirmed 체크 + OVERDUE 상태 생성
"""
from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase
from datetime import date, datetime, timedelta
import traceback
from services.time import business_today

router = APIRouter(prefix="/schedule-engine", tags=["schedule_engine"])


def add_cycle(base_date: date, cycle_unit: str, cycle_value: int) -> date:
    if cycle_unit == "day":
        return base_date + timedelta(days=cycle_value)
    if cycle_unit == "week":
        return base_date + timedelta(weeks=cycle_value)
    if cycle_unit in ("month", "quarter", "half_year"):
        months = cycle_value if cycle_unit == "month" else (3 if cycle_unit == "quarter" else 6)
        month = base_date.month - 1 + months
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
    단건 일정 생성 (v1.2.0)
    - next_planned_date 있으면 바로 사용
    - next_planned_date 없고 anchor 있으면 anchor + cycle로 계산
    - 둘 다 없으면 ANCHOR_NOT_SET 반환
    - 중복 방지 (inspection_set_id + planned_date 체크)
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
        anchor   = s.get("schedule_anchor_date")
        next_date = s.get("next_planned_date")

        # ── next_planned_date 없으면 anchor로 계산 ──
        if not next_date:
            if not anchor:
                return {
                    "success":           False,
                    "reason":            "ANCHOR_NOT_SET",
                    "message":           "기준일(anchor)이 설정되지 않았습니다. 기준일을 먼저 입력해주세요.",
                    "inspection_set_id": inspection_set_id,
                    "created_count":     0,
                }
            # anchor + cycle → next_date 계산
            cycle_unit  = s.get("cycle_unit") or "year"
            cycle_value = int(s.get("cycle_value") or 1)
            anchor_dt   = date.fromisoformat(str(anchor))
            next_date   = add_cycle(anchor_dt, cycle_unit, cycle_value).isoformat()

        planned_date_str = str(next_date)

        # ── 중복 체크 ──
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
                "existing_id":       existing.data[0]["id"],
            }

        # ── 상태 결정 ──
        try:
            planned_dt = date.fromisoformat(planned_date_str)
            status_code = "OVERDUE" if planned_dt < business_today() else "SCHEDULED"
        except Exception:
            status_code = "SCHEDULED"

        insert_payload = {
            "company_id":        s.get("company_id"),
            "factory_id":        s.get("factory_id"),
            "inspection_set_id": inspection_set_id,
            "planned_date":      planned_date_str,
            "start_date":        planned_date_str,
            "repeat_type":       s.get("cycle_unit") or "year",
            "repeat_interval":   s.get("cycle_value") or 1,
            "status_code":       status_code,
            "active_yn":         True,
            "description":       f"{s.get('inspection_set_name', '점검')} — 법정점검 일정",
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
