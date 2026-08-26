"""OBJ-01 KNOT-3C1 — SAFE start atomic creator service.

SAFE 점검 시작(POST /inspection/start)을 원자적 생성 RPC
(fn_start_safe_inspection_record) 한 번으로 변환하는 순수 서비스 계층.
work_schedules 상태 변경과 safety_inspections 초기 생성이 RPC 안에서 한
트랜잭션으로 일어나며, 동일 (schedule_id, factory_id) 재호출은 replay(두 번째
생성 0)로 수렴한다.

멱등 key = (work_schedule_id, factory_id). Worker one-shot 처럼 payload 변경
감사를 위한 별도 submission receipt 는 필요 없다(lifecycle-start 성격).

FORBIDDEN: safety_inspections / work_schedules 직접 write, journal/receipt/results
write, MAX(revision) 조회, retry loop. 동시성/멱등은 RPC 의 row lock + replay 가
소유한다.
"""
from __future__ import annotations

from typing import Any, Optional

RPC_NAME = "fn_start_safe_inspection_record"

# 라우터에서 404 로 매핑할 코드
NOT_FOUND_ERROR_CODES = frozenset({"WORK_SCHEDULE_NOT_FOUND"})
# 라우터에서 409 로 매핑할 코드
CARDINALITY_ERROR_CODES = frozenset({"INSPECTION_CARDINALITY_VIOLATION"})


class SafeStartError(Exception):
    """SAFE start 서비스/RPC 계약 위반을 표현하는 typed 에러."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    @property
    def is_not_found(self) -> bool:
        return self.code in NOT_FOUND_ERROR_CODES

    @property
    def is_cardinality(self) -> bool:
        return self.code in CARDINALITY_ERROR_CODES


def start_safe_inspection(
    supabase,
    *,
    schedule_id: str,
    factory_id: str,
    started_at: Any,
    inspector_name: str = "",
) -> dict:
    """SAFE 점검 시작을 원자적 RPC 1회로 실행하고 snapshot 을 돌려준다.

    schedule_id : work_schedules.id (RPC lock 대상, base assignment_id)
    factory_id  : parent work_schedules.factory_id (신뢰된 companion, body 아님)
    반환        : {"data": snapshot, "replayed": bool}
    실패        : SafeStartError(code, detail)
    """
    if not schedule_id:
        raise SafeStartError("INVALID_START_INPUT", "schedule_id required")
    if not factory_id:
        raise SafeStartError("INVALID_START_INPUT", "factory_id required")
    if not started_at:
        raise SafeStartError("START_TIMESTAMP_INVALID", "started_at required")

    params = {
        "p_schedule_id": str(schedule_id),
        "p_factory_id": str(factory_id),
        "p_started_at": started_at,
        "p_inspector_name": inspector_name or "",
    }

    # RPC 정확히 1회. 직접 테이블 쓰기/revision 조회 없음.
    resp = supabase.rpc(RPC_NAME, params).execute()
    result = getattr(resp, "data", resp)

    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        raise SafeStartError("RPC_RESULT_MALFORMED", repr(result))

    if not result.get("ok", False):
        raise SafeStartError(result.get("error", "UNKNOWN_RPC_ERROR"),
                             str(result.get("detail", "")))

    return {"data": result.get("data"), "replayed": bool(result.get("replayed", False))}
