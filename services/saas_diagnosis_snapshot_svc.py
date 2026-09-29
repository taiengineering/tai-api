"""services/saas_diagnosis_snapshot_svc.py

WO-DIAGNOSIS-RESULT-SNAPSHOT-INVENTORY-SEPARATION-001 + PATCH1.

anonymous_diagnosis_results(source_type='saas') 단건 조회.
- company_id 는 저장된 input_data.company_id 에서 읽는다 (클라이언트 공급 금지).
- 소유권 검사는 _ensure_own_company(stored_company_id) — 클라 factory_id 기반 스코프 0.
- 반환 필드: diagnosis_id / factory_id / sector / engine_version / created_at / full_result.
  public_token / company_id / raw input_data 미포함.

저장 계약 검증(fail-closed):
  input_data = dict, company_id = nonblank, factory_id = nonblank
  full_result = dict, full_result.obligations_raw = list
  위반 시 SnapshotContractError — 빈 dict로 정상 처리 금지.
"""
from __future__ import annotations

from typing import Any, Dict


class SnapshotNotFound(LookupError):
    """C-10 snapshot 없음 또는 source_type 불일치."""


class SnapshotContractError(ValueError):
    """저장 row 구조 위반 — 계약 필드 누락/타입 불량."""


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
    SnapshotContractError: 저장 계약 위반(company_id/factory_id/full_result/obligations_raw).
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

    # ── input_data 계약 검증 ─────────────────────────────────────────
    input_data = row.get("input_data")
    if not isinstance(input_data, dict):
        raise SnapshotContractError("저장된 진단 결과의 입력 정보(input_data)를 확인할 수 없습니다.")

    stored_company_id: str = input_data.get("company_id") or ""
    if not (isinstance(stored_company_id, str) and stored_company_id.strip()):
        raise SnapshotContractError("저장된 진단 결과의 회사 정보를 확인할 수 없습니다.")

    stored_factory_id: str = input_data.get("factory_id") or ""
    if not (isinstance(stored_factory_id, str) and stored_factory_id.strip()):
        raise SnapshotContractError("저장된 진단 결과의 사업장 정보를 확인할 수 없습니다.")

    # ── full_result 계약 검증 ────────────────────────────────────────
    full_result = row.get("full_result")
    if not isinstance(full_result, dict):
        raise SnapshotContractError("저장된 진단 결과(full_result) 구조가 올바르지 않습니다.")

    obligations_raw = full_result.get("obligations_raw")
    if not isinstance(obligations_raw, list):
        raise SnapshotContractError("저장된 진단 결과(obligations_raw) 구조가 올바르지 않습니다.")

    return {
        "diagnosis_id": str(row.get("id") or diagnosis_id),
        "factory_id": stored_factory_id,
        "sector": input_data.get("sector") or full_result.get("sector") or None,
        "engine_version": row.get("engine_version") or full_result.get("engine_version") or None,
        "created_at": row.get("created_at") or None,
        "full_result": full_result,
        "_stored_company_id": stored_company_id,
    }


__all__ = ["get_saas_diagnosis_snapshot", "SnapshotNotFound", "SnapshotContractError"]
