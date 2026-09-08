"""services/saas_diagnosis_result_persistence.py

WO-SAAS-INDUSTRIAL-C10-CANONICAL-WIRING-001 / STEP 4B-4C.

SaaS official LEG 결과(full_result)를 C-10(anonymous_diagnosis_results)에 **최소 저장**한다.
파이프라인 정의서(full_result → C-10 → C-11 canonical) 정합 복원용.

- 소비자 run_diagnosis() 저장 경로는 수정/재사용하지 않는다(별도 최소 insert).
- consumer auth/결제/면책/tier/free-count 필드는 **생성하지 않는다**(ci_hash/auth_log_id/disclaimer_log_id/payment_ref 미생성).
- source_type='saas'. public_token 은 생성하되 SaaS API response 로 절대 노출하지 않는다(호출부 계약).
- 법령결과 보정/변환/fallback 0. full_result 는 그대로 저장(EXACT). 입력 mutation 0.
- fail-close: factory_id/company_id 비어있거나 full_result/obligations_raw 타입 불량이면 ValueError.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

from services.time import now_kst, serialize_external_utc


class SaasPersistError(ValueError):
    """C-10 SaaS persist 입력 검증 실패(fail-close)."""


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
        "created_at": serialize_external_utc(now_kst()),
    }
    ins = supabase.table("anonymous_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise SaasPersistError("C-10 저장 실패")
    created = ins.data[0]
    return {"diagnosis_id": str(created.get("id") or ""), "public_token": public_token}


__all__ = ["persist_saas_full_result", "SaasPersistError"]
