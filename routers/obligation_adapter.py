"""Obligation Adapter API — v1.0.0 (WO-OBLIGATION-ADAPTER-IMPL-001)

B안 어댑터 라우터 (HTTP only).

흐름:
  GET /obligation-adapter/{factory_id}
    1. V4 evaluate() 호출 (routers.applicability_api.evaluate)
    2. applicability_conditions 조회 → conditions_by_id 조립
    3. obligation_adapter_service.build_obligations_from_v4() 호출
    4. result_data.obligations 호환 JSON 반환

원칙:
  - V4 불변 (evaluate 재사용, 수정 안 함)
  - 정제레이어 불변
  - 라우터는 HTTP만 (변환 로직은 서비스에)
  - 새 판단/법령/threshold 생성 금지
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from routers.applicability_api import evaluate as v4_evaluate
from services.obligation_adapter_service import build_obligations_from_v4

router = APIRouter(
    prefix="/obligation-adapter",
    tags=["Obligation Adapter (B안)"],
)


@router.get("/{factory_id}")
def adapt_obligations(factory_id: str):
    """V4 verdict → result_data.obligations 변환.

    V4 evaluate()를 그대로 호출한 뒤,
    MATCH된 condition을 obligation 문장으로 변환해 반환.
    """
    # 1. V4 평가 (불변 재사용)
    v4_result = v4_evaluate(factory_id=factory_id, save=False)

    # 2. condition 레코드 조회 → {id: row}
    supabase = get_supabase()
    cond_res = (
        supabase.table("applicability_conditions")
        .select("id, law_name, appendix_no, action_type, action_text, "
                "industry_name, required_count, sector, status")
        .eq("status", "ACTIVE")
        .execute()
    )
    conditions_by_id = {str(c["id"]): c for c in (cond_res.data or [])}

    # 3. 변환 (서비스 레이어)
    result = build_obligations_from_v4(v4_result, conditions_by_id)

    return {
        "status": "success",
        "factory_id": factory_id,
        "verdict": result["verdict"],
        "obligation_count": result["obligation_count"],
        "obligations": result["obligations"],
        "source": result["source"],
    }
