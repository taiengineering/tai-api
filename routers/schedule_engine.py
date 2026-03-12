from fastapi import APIRouter
from db.supabase_client import get_supabase
from datetime import date, datetime, timedelta

router = APIRouter(prefix="/schedule-engine", tags=["schedule_engine"])


def add_cycle(base_date: date, cycle_unit: str, cycle_value: int) -> date:
    if cycle_unit == "day":
        return base_date + timedelta(days=cycle_value)
    if cycle_unit == "week":
        return base_date + timedelta(weeks=cycle_value)
    if cycle_unit == "month":
        # 단순 월 계산 버전
        month = base_date.month - 1 + cycle_value
        year = base_date.year + month // 12
        month = month % 12 + 1
        day = min(base_date.day, 28)
        return date(year, month, day)
    if cycle_unit == "year":
        try:
            return date(base_date.year + cycle_value, base_date.month, base_date.day)
        except ValueError:
            return date(base_date.year + cycle_value, base_date.month, 28)

    return base_date


@router.post("/generate/{inspection_set_id}")
def generate_schedule(inspection_set_id: str):
    supabase = get_supabase()

    # 1. 점검세트 조회
    inspection_set_result = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("id", inspection_set_id)
        .limit(1)
        .execute()
    )

    if not inspection_set_result.data:
        return {
            "success": False,
            "message": "inspection_set not found"
        }

    inspection_set = inspection_set_result.data[0]

    schedule_anchor_date = inspection_set.get("schedule_anchor_date")
    cycle_unit = inspection_set.get("cycle_unit")
    cycle_value = inspection_set.get("cycle_value") or 1
    schedule_end_date = inspection_set.get("schedule_end_date")
    next_planned_date = inspection_set.get("next_planned_date")

    if not schedule_anchor_date:
        return {
            "success": False,
            "message": "schedule_anchor_date is required"
        }

    if not cycle_unit:
        return {
            "success": False,
            "message": "cycle_unit is required"
        }

    # 문자열 → date 변환
    if next_planned_date:
        current_date = datetime.strptime(next_planned_date, "%Y-%m-%d").date()
    else:
        current_date = datetime.strptime(schedule_anchor_date, "%Y-%m-%d").date()

    if schedule_end_date:
        end_date = datetime.strptime(schedule_end_date, "%Y-%m-%d").date()
    else:
        end_date = current_date + timedelta(days=90)

    created_rows = []
    loop_guard = 0

    while current_date <= end_date:
        loop_guard += 1
        if loop_guard > 100:
            break

        current_date_str = current_date.isoformat()

        # 2. 중복 체크
        exists_result = (
            supabase.table("work_schedules")
            .select("id")
            .eq("inspection_set_id", inspection_set_id)
            .eq("planned_date", current_date_str)
            .execute()
        )

        if not exists_result.data:
            insert_payload = {
                "company_id": inspection_set.get("company_id"),
                "factory_id": inspection_set.get("factory_id"),
                "inspection_set_id": inspection_set_id,
                "planned_date": current_date_str,
                "status_code": "planned"
            }

            insert_result = (
                supabase.table("work_schedules")
                .insert(insert_payload)
                .execute()
            )

            created_rows.append(insert_result.data)

        # 3. 다음 주기 계산
        current_date = add_cycle(current_date, cycle_unit, cycle_value)

    # 4. next_planned_date 업데이트
    (
        supabase.table("inspection_sets")
        .update({
            "next_planned_date": current_date.isoformat()
        })
        .eq("id", inspection_set_id)
        .execute()
    )

    return {
        "success": True,
        "inspection_set_id": inspection_set_id,
        "created_count": len(created_rows),
        "created_rows": created_rows
    }
