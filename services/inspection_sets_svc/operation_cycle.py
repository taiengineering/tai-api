"""services/inspection_sets_svc/operation_cycle.py

WO-SAAS-OPERATION-CYCLE-SETTER-001 / STEP 4B-4D-A (+PATCH-1B).

사용자가 확정한 SaaS **운영주기**(cycle_unit/cycle_value)만 canonical inspection_set row 에 기록한다.
법정주기 해석 endpoint 가 아니다 — 값 변환/제안/일정계산 0. A-GUARDED 유지.

허용 대상:
  source == 'LEGAL_ENGINE' AND legal_obligation_atom_id IS NOT NULL  (= canonical row 만).
  legacy(atom NULL)/MANUAL 은 거부. 기존 legacy cycle 값 완전 불변.

일정 시작 가드 (PATCH-1B, TOCTOU 방지):
  1) 선(先) SELECT guard — 사용자 친화적 오류 메시지용(대상/일정상태 판별).
  2) 최종 UPDATE 에 **동일 상태조건을 WHERE 로 재부여**(conditional atomic update):
     source=LEGAL_ENGINE AND atom NOT NULL AND schedule_anchor_date IS NULL AND
     next_planned_date IS NULL AND anchor_confirmed=false.
     UPDATE 반환 0행 → SELECT 이후 상태가 바뀐 것 → 409 (500 아님).

성공 시:
  cycle_unit / cycle_value 만 UPDATE.
  status_code / anchor_confirmed / schedule_anchor_date / next_planned_date 변경 0. work_schedules write 0.
"""
from __future__ import annotations

from typing import Any, Dict

from db.supabase_client import get_supabase
from schemas.inspection_sets import OperationCycleBody
from .errors import InspectionSetsSvcError

# 서버 스케줄러(inspection_sets_helpers.DELTA_MAP)와 동일한 6 unit 만 허용.
ALLOWED_CYCLE_UNITS = frozenset({"day", "week", "month", "quarter", "half_year", "year"})

_SCHEDULE_STARTED_409 = "이미 기준일/일정이 설정된 점검 세트입니다. 주기를 변경할 수 없습니다."


def set_operation_cycle(inspection_set_id: str, body: OperationCycleBody) -> Dict[str, Any]:
    """canonical row 에 운영주기(cycle_unit/value)만 기록. (ownership 은 라우터 _ensure_set_own 선행)."""
    # value 는 schema(strict int, ge=1)가 1차 검증 — service 는 defense-in-depth.
    unit = (body.cycle_unit or "").strip().lower()
    if unit not in ALLOWED_CYCLE_UNITS:
        raise InspectionSetsSvcError(
            422, "cycle_unit 은 day/week/month/quarter/half_year/year 중 하나여야 합니다."
        )
    value = body.cycle_value
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InspectionSetsSvcError(422, "cycle_value 는 1 이상의 정수여야 합니다.")

    supabase = get_supabase()
    # 1) 선 SELECT — 친화적 오류(대상 아님 vs 일정 시작됨) 판별용
    res = (
        supabase.table("inspection_sets")
        .select(
            "id, source, legal_obligation_atom_id, schedule_anchor_date, "
            "next_planned_date, anchor_confirmed"
        )
        .eq("id", inspection_set_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise InspectionSetsSvcError(404, "점검 세트를 찾을 수 없습니다.")
    row = res.data[0]

    if row.get("source") != "LEGAL_ENGINE":
        raise InspectionSetsSvcError(409, "운영주기 설정은 법령엔진 점검 세트에만 가능합니다.")
    if not (isinstance(row.get("legal_obligation_atom_id"), str) and row["legal_obligation_atom_id"].strip()):
        raise InspectionSetsSvcError(409, "기존(레거시) 점검 세트에는 이 방식으로 주기를 설정할 수 없습니다.")
    if (
        row.get("schedule_anchor_date") is not None
        or row.get("next_planned_date") is not None
        or row.get("anchor_confirmed") is True
    ):
        raise InspectionSetsSvcError(409, _SCHEDULE_STARTED_409)

    # 2) 최종 UPDATE — 동일 상태조건을 WHERE 로 재부여(TOCTOU 방지). 반환 0행 → 409.
    upd = (
        supabase.table("inspection_sets")
        .update({"cycle_unit": unit, "cycle_value": value})  # cycle 만 — status/anchor/next/schedule 무변경
        .eq("id", inspection_set_id)
        .eq("source", "LEGAL_ENGINE")
        .not_.is_("legal_obligation_atom_id", "null")
        .is_("schedule_anchor_date", "null")
        .is_("next_planned_date", "null")
        .eq("anchor_confirmed", False)
        .execute()
    )
    if not upd.data:
        # SELECT 통과했으나 UPDATE 0행 = 그 사이 상태가 바뀜(동시 anchor 저장 등) → 주기 변경 거부.
        raise InspectionSetsSvcError(409, _SCHEDULE_STARTED_409)
    return {
        "status": "success",
        "message": "운영주기가 설정됐습니다.",
        "data": {
            "inspection_set_id": inspection_set_id,
            "cycle_unit": unit,
            "cycle_value": value,
        },
    }


__all__ = ["set_operation_cycle", "ALLOWED_CYCLE_UNITS"]
