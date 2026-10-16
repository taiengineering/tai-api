"""services/saas_diagnosis_result_persistence.py

WO-SAAS-INDUSTRIAL-C10-CANONICAL-WIRING-001 / STEP 4B-4C (+PATCH-0).
WO-E2E2000-WP01-A-C10-FOUNDATION-001 B-2/B-3 보정.

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

B-2: inspection_materialization_status 컬럼 기록.
  INSERT 시 PENDING. 반영 완료 시 MATERIALIZED/BLOCKED_LEGACY_ROWS. 실패 시 FAILED.
  status UPDATE 실패 시 PENDING 유지 — WP01-A 가 해당 행을 기준 스냅샷으로 사용하지 않도록 보장.

B-3: CONSTRUCTION site_id 저장.
  site_id 는 인증·소유권·현장 Scope 검증을 통과한 서버 측 컨텍스트에서만 전달.
  input_data JSONB 에 저장: {"factory_id", "company_id", "sector", [site_id]}.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class SaasPersistError(ValueError):
    """C-10 SaaS persist 입력 검증/저장 실패(fail-close)."""


def persist_saas_full_result(
    supabase: Any,
    *,
    factory_id: Any,
    company_id: Any,
    full_result: Any,
    site_id: Optional[str] = None,
) -> Dict[str, str]:
    """SaaS official full_result → anonymous_diagnosis_results 최소 저장.

    반환 {diagnosis_id, public_token}. public_token 은 내부용 — 응답 노출 금지(호출부 책임).

    B-2: inspection_materialization_status = 'PENDING' 으로 INSERT.
    B-3: site_id 가 제공되면 input_data 에 포함 (CONSTRUCTION 전용, 서버 검증 완료 값만).
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
    if site_id and isinstance(site_id, str) and site_id.strip():
        # B-3: 서버 검증 완료 site_id 만 저장 (CONSTRUCTION 현장 격리용)
        input_data["site_id"] = site_id.strip()

    row = {
        "public_token": public_token,
        "input_data": input_data,
        "full_result": full_result,                          # EXACT — 보정/변환 0
        "status": "ACTIVE",
        "source_type": "saas",
        "engine_version": full_result.get("engine_version"),
        "inspection_materialization_status": "PENDING",      # B-2: 반영 전 기본값
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


def _record_materialization_status(
    supabase: Any,
    diagnosis_id: str,
    factory_id: str,
    mat_status: str,
) -> None:
    """C-10 행의 inspection_materialization_status 를 기록.

    실패·0행·상태불일치 시 row 가 PENDING 으로 유지 → WP01-A 기준 선택 제외(보안 보장).
    0행 수정·상태 불일치 시 WARNING 기록 — 호출부가 응답으로 식별 가능.
    예외 시 log.exception 1회(PATCH-0A). 어떤 경우에도 raise 금지.
    """
    try:
        res = (
            supabase.table("anonymous_diagnosis_results")
            .update({"inspection_materialization_status": mat_status})
            .eq("id", diagnosis_id)
            .execute()
        )
        updated = getattr(res, "data", None)
        if not updated:  # None or [] → 0행 수정
            log.warning(
                "[SAAS_C10] status update 0 rows affected — row stays PENDING "
                "factory_id=%s diagnosis_id=%s mat_status=%s",
                factory_id, diagnosis_id, mat_status,
            )
            return
        actual = updated[0].get("inspection_materialization_status")
        if actual != mat_status:
            log.warning(
                "[SAAS_C10] status update mismatch — stored=%r expected=%r "
                "factory_id=%s diagnosis_id=%s",
                actual, mat_status, factory_id, diagnosis_id,
            )
    except Exception:  # noqa: BLE001
        log.exception(
            "[SAAS_C10] status update failed — row stays PENDING "
            "factory_id=%s diagnosis_id=%s mat_status=%s",
            factory_id, diagnosis_id, mat_status,
        )


def run_saas_c10_and_materialize(
    supabase: Any,
    factory_id: str,
    company_id: str,
    full_result: Dict[str, Any],
    *,
    site_id: Optional[str] = None,
) -> Dict[str, Any]:
    """C-10 persist → canonical materialization orchestration.

    - C-10 저장 실패 → SaasPersistError 전파(호출부가 HTTP 실패 처리, writer 0).
    - C-10 성공 후 writer/guard 실패 → C-10 보존, inspection_materialization.status='FAILED',
      log.exception 1회(silent swallow 0, PATCH-0A).
    - 반영 완료 후 inspection_materialization_status 업데이트(B-2).
      업데이트 실패 시 PENDING 유지 — WP01-A 기준 선택 제외(허위 MATERIALIZED 금지).
    반환 {"diagnosis_id", "inspection_materialization"} (public_token 미포함 — 응답 노출 금지).
    """
    persisted = persist_saas_full_result(
        supabase,
        factory_id=factory_id,
        company_id=company_id,
        full_result=full_result,
        site_id=site_id,
    )  # 실패 시 raise → 호출부 HTTP 실패, writer 미실행
    diagnosis_id = persisted["diagnosis_id"]

    try:
        materialization = materialize_saas_inspection(supabase, factory_id, company_id, full_result)
        mat_status = materialization["status"]  # MATERIALIZED or BLOCKED_LEGACY_ROWS
    except Exception:  # noqa: BLE001
        log.exception(
            "[SAAS_C10] inspection materialization failed factory_id=%s diagnosis_id=%s",
            factory_id, diagnosis_id,
        )
        materialization = {"status": "FAILED"}
        mat_status = "FAILED"

    # B-2: C-10 행에 반영 결과 기록. 실패 시 PENDING 유지(허위 MATERIALIZED 방지).
    _record_materialization_status(supabase, diagnosis_id, factory_id, mat_status)

    return {
        "diagnosis_id": diagnosis_id,
        "inspection_materialization": materialization,
    }


def finalize_saas_leg_result(
    supabase: Any,
    *,
    factory_id: str,
    leg_out: dict,
    site_id: Optional[str] = None,
) -> dict:
    """Official LEG out → C-10 persist + canonical materialization. HTTP 오류변환은 라우터.

    B-3: CONSTRUCTION 현장 격리를 위해 site_id 수락 (서버 검증 완료 값만).
    """
    full_result = leg_out["full_result"]  # STEP A EXACT (transform 0)
    fac = supabase.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
    if not fac.data:
        raise LookupError("사업장을 찾을 수 없습니다.")  # STEP B (domain error)
    company_id = fac.data[0].get("company_id")
    if not (isinstance(company_id, str) and company_id.strip()):
        raise ValueError("company_id required")
    wiring = run_saas_c10_and_materialize(
        supabase, factory_id, company_id, full_result, site_id=site_id
    )  # STEP C
    return {  # STEP D common result
        "status": "success",
        "data": full_result,
        "contract_version": leg_out["contract_version"],
        "unresolved_fields": leg_out["unresolved_fields"],
        "diagnosis_id": wiring["diagnosis_id"],
        "inspection_materialization": wiring["inspection_materialization"],
    }


__all__ = [
    "persist_saas_full_result",
    "materialize_saas_inspection",
    "run_saas_c10_and_materialize",
    "finalize_saas_leg_result",
    "SaasPersistError",
]
