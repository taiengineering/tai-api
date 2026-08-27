"""OBJ-01 DEBT-W3-02 — SAFE result initial-batch idempotency service.

POST /inspection/result/{inspection_id}/items 를 원자적 RPC
(fn_record_safe_inspection_result_batch) 1회로 변환하는 순수 서비스 계층.
결과 batch 의 논리 identity 는 inspection_id 이며, RPC 가 parent lock 하에
CREATED / REPLAY / RESULT_INITIAL_BATCH_CONFLICT 를 결정한다.

FORBIDDEN: safety_inspection_results 직접 write, base UPDATE/DELETE, receipt/
idempotency_key 발명. 동시성/멱등은 RPC 의 parent FOR UPDATE + 기존 batch 비교가
소유한다. result_code 는 여기서 canonical 로 정규화해 RPC 에 넘긴다.
"""
from __future__ import annotations

from typing import Any, List

from services.status_vocab import normalize_inspection_result_write

RPC_NAME = "fn_record_safe_inspection_result_batch"

NOT_FOUND_ERROR_CODES = frozenset({"INSPECTION_NOT_FOUND"})
CONFLICT_ERROR_CODES = frozenset({"RESULT_INITIAL_BATCH_CONFLICT"})
EMPTY_ERROR_CODES = frozenset({"EMPTY_RESULTS"})


class SafeResultBatchError(Exception):
    """SAFE 결과 batch 서비스/RPC 계약 위반 typed 에러."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    @property
    def is_not_found(self) -> bool:
        return self.code in NOT_FOUND_ERROR_CODES

    @property
    def is_conflict(self) -> bool:
        return self.code in CONFLICT_ERROR_CODES

    @property
    def is_empty(self) -> bool:
        return self.code in EMPTY_ERROR_CODES


def record_safe_result_batch(supabase, *, inspection_id: str, results: List[dict]) -> dict:
    """SAFE 결과 batch 를 원자적 RPC 1회로 기록/replay 하고 mode/count 를 돌려준다.

    반환 : {"mode": "CREATED"|"REPLAY", "count": N, "data": {...}}
    실패 : SafeResultBatchError(code, detail)
    """
    if not inspection_id:
        raise SafeResultBatchError("INVALID_RESULT_INPUT", "inspection_id required")
    if not results:
        raise SafeResultBatchError("EMPTY_RESULTS", "results required")

    # W3 canonical shape 로 정규화 (result → canonical result_code)
    norm = [{
        "inspection_set_item_id": r.get("inspection_set_item_id"),
        "result_code": normalize_inspection_result_write(r.get("result", "NA")),
        "note": r.get("note", "") or "",
        "photo_url": r.get("photo_url"),
    } for r in results]

    resp = supabase.rpc(RPC_NAME, {
        "p_inspection_id": str(inspection_id),
        "p_results": norm,
    }).execute()
    result = getattr(resp, "data", resp)

    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        raise SafeResultBatchError("RPC_RESULT_MALFORMED", repr(result))

    if not result.get("ok", False):
        raise SafeResultBatchError(result.get("error", "UNKNOWN_RPC_ERROR"),
                                   str(result.get("detail", "")))

    return {"mode": result.get("mode"), "count": int(result.get("count", 0)),
            "data": result.get("data")}
