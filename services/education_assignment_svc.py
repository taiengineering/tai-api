"""교육 발령 만료 처리 core — §82 Phase A.

HTTP `POST /education/assignments/expire` 와 scheduler DIRECT handler 가
동일 함수를 호출한다. cron_job_master.endpoint_url cutover 는 Phase C.
"""
from __future__ import annotations

from datetime import date, datetime, timezone


def expire_overdue_education_assignments(sb) -> dict:
    """PENDING 이고 due_date < today 인 발령을 OVERDUE 로 갱신.

    반환: {"updated": int, "date": "YYYY-MM-DD"}
    """
    today = date.today().isoformat()
    res = (
        sb.table("education_assignment")
        .update({
            "status_code": "OVERDUE",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("status_code", "PENDING")
        .lt("due_date", today)
        .execute()
    )
    return {"updated": len(res.data or []), "date": today}
