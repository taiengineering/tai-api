"""services/saas_diagnosis_snapshot_svc.py

WO-DIAGNOSIS-RESULT-SNAPSHOT-INVENTORY-SEPARATION-001.

anonymous_diagnosis_results(source_type='saas') 단건 조회.
- company_id 는 저장된 input_data.company_id 에서 읽는다 (클라이언트 공급 금지).
- 소유권 검사는 _ensure_own_company(stored_company_id) — 클라 factory_id 기반 스코프 0.
- 반환 필드: diagnosis_id / factory_id / sector / engine_version / created_at / full_result.
  public_token / company_id / raw input_data 미포함.
"""
from __future__ import annotations

from typing import Any, Dict


class SnapshotNotFound(LookupError):
    """C-10 snapshot 없음 또는 source_type 불일치."""


class SnapshotContractError(ValueError):
    """저장 row 구조 위반 — input_data.company_id 누락."""


def get_saas_diagnosis_snapshot(
    supabase: Any,
    *,
    diagnosis_id: str,
) -> Dict[str, Any]:
    """diagnosis_id 로 C-10 saas snapshot 단건 조회.

    반환:
        {
            "diagnosis_id": str,
            "factory_id": str,
            "sector": str | None,
            "engine_version": str | None,
            "created_at": str | None,
            "full_result": dict,
            "_stored_company_id": str,   # 호출자가 소유권 검사에 사용
        }

    SnapshotNotFound: row 없음 / source_type != 'saas'.
    SnapshotContractError: input_data.company_id 누락(저장 계약 위반).
    """
    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, input_data, full_result, engine_version, created_at, source_type")
        .eq("id", diagnosis_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise SnapshotNotFound("진단 결과를 찾을 수 없습니다.")

    row = res.data[0]

    if row.get("source_type") != "saas":
        raise SnapshotNotFound("진단 결과를 찾을 수 없습니다.")

    input_data: dict = row.get("input_data") or {}
    stored_company_id: str = input_data.get("company_id") or ""
    if not stored_company_id:
        raise SnapshotContractError("저장된 진단 결과의 회사 정보를 확인할 수 없습니다.")

    full_result: dict = row.get("full_result") or {}

    return {
        "diagnosis_id": str(row.get("id") or diagnosis_id),
        "factory_id": input_data.get("factory_id") or "",
        "sector": input_data.get("sector") or full_result.get("sector") or None,
        "engine_version": row.get("engine_version") or full_result.get("engine_version") or None,
        "created_at": row.get("created_at") or None,
        "full_result": full_result,
        "_stored_company_id": stored_company_id,
    }


__all__ = ["get_saas_diagnosis_snapshot", "SnapshotNotFound", "SnapshotContractError"]
