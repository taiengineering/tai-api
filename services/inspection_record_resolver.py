"""OBJ-01 INSPECTION RECORD — Effective Record Resolver wrapper (STEP-1A).

이 모듈은 DB 정본 resolver(fn_resolve_inspection_record)를 호출해 현재 유효
레코드를 반환한다. Python 측 folding 로직은 존재하지 않는다 —
folding 의 단일 정본은 DB resolver 이다.

READ-ONLY: 어떤 write 도 하지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, List

# resolver 측 fail-closed 코드 (DB 가 반환)
RESOLVER_ERRORS = frozenset({
    "INSPECTION_NOT_FOUND",
    "LEGACY_STATUS_UNRESOLVED",
    "RESULT_CODE_UNRESOLVED",
    "JOURNAL_REVISION_GAP",
})


class InspectionRecordError(Exception):
    """resolver/command domain 예외. code 보유. HTTP 매핑은 router 책임."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _extract_data(resp: Any) -> Any:
    data = getattr(resp, "data", None)
    if data is None and isinstance(resp, dict):
        data = resp.get("data")
    return data


def resolve_inspection_record(inspection_id: str, supabase: Any = None) -> Dict[str, Any]:
    """현재 유효 점검 레코드를 반환. fail-closed 코드는 InspectionRecordError 로 raise."""
    if supabase is None:
        from db.supabase_client import get_supabase  # lazy import

        supabase = get_supabase()

    resp = supabase.rpc(
        "fn_resolve_inspection_record", {"p_inspection_id": inspection_id}
    ).execute()
    data = _extract_data(resp)

    if not isinstance(data, dict):
        raise InspectionRecordError("RESOLVER_MALFORMED_RESPONSE", str(type(data)))
    if "error" in data:
        raise InspectionRecordError(data.get("error"), data.get("detail") or "")
    return data


def list_effective_inspection_records_by_inspector(
    inspector_id: str, limit: int, supabase: Any = None
) -> List[Dict[str, Any]]:
    """inspector 의 현재 유효 점검 레코드 리스트를 반환 (N+1 방지 DB 어댑터 경유).

    이 wrapper 는 오직 RPC 호출 / 응답 shape 검증 / domain error 변환 / list 반환만 한다.
    Python 에서 folding·candidate union·current-state 계산을 하지 않는다.
    """
    if supabase is None:
        from db.supabase_client import get_supabase  # lazy import

        supabase = get_supabase()

    resp = supabase.rpc(
        "fn_list_effective_inspection_records_by_inspector",
        {"p_inspector_id": str(inspector_id), "p_limit": int(limit)},
    ).execute()
    data = _extract_data(resp)

    if isinstance(data, dict) and "error" in data:
        raise InspectionRecordError(data.get("error"), data.get("detail") or "")
    if not isinstance(data, list):
        raise InspectionRecordError("EFFECTIVE_LIST_MALFORMED_RESPONSE", str(type(data)))
    return data
