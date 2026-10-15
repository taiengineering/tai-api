"""WP01-A Baseline 로더 — C10 최신 SaaS 스냅샷에서 facility_used 추출.

DB WRITE 0, LEG EXECUTION 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from services.wp01_snapshot_compare.errors import BaselineNotFound, BaselineQueryError


def load_baseline_facility(
    supabase: Any,
    factory_id: str,
    sector: str,
    *,
    site_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """C10(anonymous_diagnosis_results)에서 최신 확정 스냅샷의 facility_used 반환.

    반환: (facility_used_dict, snapshot_id).

    선택 조건:
      - source_type = 'saas'
      - status = 'ACTIVE'  (EXPIRED/CLAIMED 제외)
      - input_data->>'factory_id' = factory_id
      - input_data->>'sector' = sector  (섹터 혼입 차단)
      - [CONSTRUCTION only] input_data->>'site_id' = site_id  (현장 격리)
      - created_at DESC, LIMIT 1

    CONSTRUCTION 격리:
      site_id 가 제공되지 않으면 기준 현장을 특정할 수 없으므로 BaselineNotFound.
      기존 C10 행에 input_data.site_id 가 없으면 필터 불일치 → 행 없음 → BaselineNotFound.
      (persist_saas_full_result 가 site_id 를 저장하기 시작한 이후 행만 유효.)

    오류 구분:
      - DB/권한/연결 오류 → BaselineQueryError  → 호출부에서 UNRESOLVED
      - 행 없음(진단 이력 없음) → BaselineNotFound  → 호출부에서 BASELINE_REQUIRED
      - 행 있으나 facility_used 결함 → BaselineNotFound  → 호출부에서 BASELINE_REQUIRED
    """
    if not factory_id or not isinstance(factory_id, str):
        raise BaselineQueryError("factory_id 누락 또는 타입 오류", factory_id=factory_id)
    if not sector or not isinstance(sector, str):
        raise BaselineQueryError("sector 누락 또는 타입 오류", factory_id=factory_id)

    # CONSTRUCTION: site_id 없이는 현장 격리 불가 → BASELINE_REQUIRED
    if sector == "CONSTRUCTION" and not site_id:
        raise BaselineNotFound(
            "CONSTRUCTION 기준 스냅샷은 site_id 없이 조회할 수 없습니다.",
            factory_id=factory_id,
        )

    try:
        q = (
            supabase.table("anonymous_diagnosis_results")
            .select("id,full_result,created_at")
            .eq("source_type", "saas")
            .eq("status", "ACTIVE")
            .eq("input_data->>factory_id", factory_id)
            .eq("input_data->>sector", sector)
        )
        if site_id:
            # CONSTRUCTION 현장 격리: 다른 현장의 기준 스냅샷 혼입 차단
            q = q.eq("input_data->>site_id", site_id)
        res = q.order("created_at", desc=True).limit(1).execute()
    except Exception as exc:
        raise BaselineQueryError(
            f"C10 기준 스냅샷 조회 실패: {type(exc).__name__}", factory_id=factory_id
        ) from exc

    rows = getattr(res, "data", None)
    if rows is None:
        raise BaselineQueryError(
            "C10 응답 형식 오류(data=None)", factory_id=factory_id
        )
    if not rows:
        raise BaselineNotFound(
            f"기준 스냅샷 없음(source_type=saas, status=ACTIVE, sector={sector!r})",
            factory_id=factory_id,
        )

    row = rows[0]
    snapshot_id: str = str(row.get("id") or "")

    full_result: Optional[Any] = row.get("full_result")
    if not isinstance(full_result, dict):
        raise BaselineNotFound(
            "C10 full_result 형식 오류 — 구형 또는 손상된 스냅샷",
            factory_id=factory_id,
        )

    facility_used: Optional[Any] = full_result.get("facility_used")
    if not isinstance(facility_used, dict):
        raise BaselineNotFound(
            "C10 full_result.facility_used 없음 — LEG 미실행 또는 구형 스냅샷",
            factory_id=factory_id,
        )

    return facility_used, snapshot_id
