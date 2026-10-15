"""WP01-A Baseline 로더 — C10 최신 SaaS 스냅샷에서 facility_used 추출.

DB WRITE 0, LEG EXECUTION 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.wp01_snapshot_compare.errors import BaselineNotFound


def load_baseline_facility(supabase: Any, factory_id: str) -> Dict[str, Any]:
    """C10(anonymous_diagnosis_results)에서 최신 source_type='saas' 행의 facility_used 반환.

    full_result.facility_used 가 없거나 행 자체가 없으면 BaselineNotFound 를 올린다.
    source_type='saas' rows 만 대상(paid_diag / site_free 등 비SaaS 제외).
    """
    if not factory_id or not isinstance(factory_id, str):
        raise BaselineNotFound("factory_id 누락", factory_id=factory_id)

    try:
        res = (
            supabase.table("anonymous_diagnosis_results")
            .select("id,full_result,created_at")
            .eq("source_type", "saas")
            .eq("input_data->>factory_id", factory_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise BaselineNotFound(
            f"C10 기준 스냅샷 조회 실패: {exc}", factory_id=factory_id
        ) from exc

    rows = getattr(res, "data", None) or []
    if not rows:
        raise BaselineNotFound(
            "기준 스냅샷 없음(source_type=saas 행 0건)", factory_id=factory_id
        )

    full_result: Optional[Any] = rows[0].get("full_result")
    if not isinstance(full_result, dict):
        raise BaselineNotFound(
            "C10 full_result 형식 오류", factory_id=factory_id
        )

    facility_used: Optional[Any] = full_result.get("facility_used")
    if not isinstance(facility_used, dict):
        raise BaselineNotFound(
            "C10 full_result.facility_used 없음 — 구형 스냅샷이거나 LEG 미실행", factory_id=factory_id
        )

    return facility_used
