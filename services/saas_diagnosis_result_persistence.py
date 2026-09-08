"""services/saas_diagnosis_result_persistence.py

WO-SAAS-INDUSTRIAL-C10-CANONICAL-WIRING-001 / STEP 4B-4C (+PATCH-0).

SaaS official LEG 결과(full_result)를 C-10(anonymous_diagnosis_results)에 **최소 저장**하고,
legacy 충돌이 없을 때만 canonical INSPECT materialization 을 수행한다.
파이프라인 정의서(full_result → C-10 → C-11 canonical) 정합 복원용.

- 소비자 run_diagnosis() 저장 경로는 수정/재사용하지 않는다(별도 최소 insert).
- consumer auth/결제/면책/tier/free-count 필드는 생성하지 않는다.
- 최소 row: public_token · input_data · full_result · status · source_type · engine_version
  (created_at 등은 DB 기본값에 맡긴다 — 수동 생성 0, PATCH-0B).
- source_type='saas'. public_token 은 생성하되 SaaS API response 로 노출 금지(호출부 계약).
- 법령결과 보정/변환/fallback 0. full_result EXACT. 입력 mutation 0.
- legacy coexistence guard: 같은 factory 에 active + legal_obligation_atom_id IS NULL(=legacy) row 가
  1건이라도 있으면 canonical writer 실행 0(legacy 수정/비활성/매핑 0). BLOCKED_LEGACY_ROWS.
- writer/guard 실패는 삼키지 않고 log.exception 1회 남긴다(PATCH-0A). C-10 정본은 보존.
- canonical_writer.py 는 수정하지 않고 그대로 호출한다.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

log = logging.getLogger(__name__)


class SaasPersistError(ValueError):
    """C-10 SaaS persist 입력 검증/저장 실패(fail-close)."""


def persist_saas_full_result(
    supabase: Any,
    *,
    factory_id: Any,
    company_id: Any,
    full_result: Any,
) -> Dict[str, str]:
    """SaaS official full_result → anonymous_diagnosis_results 최소 저장.

    반환 {diagnosis_id, public_token}. public_token 은 내부용 — 응답 노출 금지(호출부 책임).
    """
    fid = factory_id.strip() if isinstance(factory_id, str) else factory_id
    cid = company_id.strip() if isinstance(company_id, str) else company_id
    if not fid or not isinstance(fid, str):
        raise SaasPersistError("factory_id required")
    if not cid or not isinstance(cid, str):
        raise SaasPersistError("company_id required")
    if not isinstance(full_result, dict):
        raise SaasPersistError("full_result must be dict")
    obligations_raw = full_result.get("obligations_raw")
    if not isinstance(obligations_raw, list):  # [] 는 정상, 누락/타입불량은 fail-close
        raise SaasPersistError("full_result.obligations_raw must be list")

    public_token = str(uuid.uuid4())
    input_data: Dict[str, Any] = {"factory_id": fid, "company_id": cid}
    sector = full_result.get("sector")
    if sector:  # full_result 에 실재할 때만 그대로 운반(발명 0)
        input_data["sector"] = sector

    row = {
        "public_token": public_token,
        "input_data": input_data,
        "full_result": full_result,          # EXACT — 보정/변환 0
        "status": "ACTIVE",
        "source_type": "saas",
        "engine_version": full_result.get("engine_version"),
    }
    ins = supabase.table("anonymous_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise SaasPersistError("C-10 저장 실패")
    created = ins.data[0]
    return {"diagnosis_id": str(created.get("id") or ""), "public_token": public_token}


def _has_active_legacy_null_atom_rows(supabase: Any, factory_id: str) -> bool:
    """factory 에 active + source=LEGAL_ENGINE + legal_obligation_atom_id IS NULL row 1건이라도 존재? (LIMIT 1)."""
    res = (
        supabase.table("inspection_sets")
        .select("id")
        .eq("factory_id", factory_id)
        .eq("source", "LEGAL_ENGINE")
        .eq("is_active", True)
        .is_("legal_obligation_atom_id", "null")
        .limit(1)
        .execute()
    )
    return bool(res.data)


def materialize_saas_inspection(
    supabase: Any, factory_id: str, company_id: str, full_result: Dict[str, Any]
) -> Dict[str, Any]:
    """legacy coexistence guard 통과 시에만 canonical writer 호출.

    반환 inspection_materialization dict:
      · legacy 존재 → {"status": "BLOCKED_LEGACY_ROWS"} (writer 0)
      · 정상 → {"status": "MATERIALIZED", **counts}
    (writer 예외는 상위 orchestrator 에서 FAILED + log 처리 — 여기선 raise 그대로 전파.)
    """
    if _has_active_legacy_null_atom_rows(supabase, factory_id):
        return {"status": "BLOCKED_LEGACY_ROWS"}
    from services.inspection_sets_svc.canonical_writer import materialize_canonical_inspection_sets
    counts = materialize_canonical_inspection_sets(
        supabase, factory_id, company_id, full_result.get("obligations_raw"),
    )
    return {"status": "MATERIALIZED", **counts}


def run_saas_c10_and_materialize(
    supabase: Any, factory_id: str, company_id: str, full_result: Dict[str, Any]
) -> Dict[str, Any]:
    """C-10 persist → canonical materialization orchestration.

    - C-10 저장 실패 → SaasPersistError 전파(호출부가 HTTP 실패 처리, writer 0).
    - C-10 성공 후 writer/guard 실패 → C-10 보존, inspection_materialization.status='FAILED',
      log.exception 1회(silent swallow 0, PATCH-0A).
    반환 {"diagnosis_id", "inspection_materialization"} (public_token 미포함 — 응답 노출 금지).
    """
    persisted = persist_saas_full_result(
        supabase, factory_id=factory_id, company_id=company_id, full_result=full_result,
    )  # 실패 시 raise → 호출부 HTTP 실패, writer 미실행
    try:
        materialization = materialize_saas_inspection(supabase, factory_id, company_id, full_result)
    except Exception:  # noqa: BLE001 — C-10 정본 보존, consumer projection 실패만 표기(로그 남김)
        log.exception(
            "[SAAS_C10] inspection materialization failed factory_id=%s diagnosis_id=%s",
            factory_id,
            persisted["diagnosis_id"],
        )
        materialization = {"status": "FAILED"}
    return {
        "diagnosis_id": persisted["diagnosis_id"],
        "inspection_materialization": materialization,
    }


__all__ = [
    "persist_saas_full_result",
    "materialize_saas_inspection",
    "run_saas_c10_and_materialize",
    "SaasPersistError",
]
