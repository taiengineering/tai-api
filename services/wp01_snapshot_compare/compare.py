"""WP01-A Snapshot Compare — 핵심 비교 로직.

현재 facility dict 와 기준 facility dict 를 비교해 변경 여부를 판정한다.
법령판정이 아님 — 데이터 동일성 확인만 수행한다.
DB WRITE 0, LEG EXECUTION 0.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Set

from services.wp01_snapshot_compare.errors import (
    BaselineNotFound,
    BaselineQueryError,
    CollectionError,
)
from services.wp01_snapshot_compare.baseline import load_baseline_facility
from services.wp01_snapshot_compare.collector import (
    collect_current_facility_industrial,
    collect_current_facility_building,
    collect_current_facility_construction,
)


_STATUS_UNCHANGED = "UNCHANGED"
_STATUS_CHANGED = "CHANGED"
_STATUS_BASELINE_REQUIRED = "BASELINE_REQUIRED"
_STATUS_UNRESOLVED = "UNRESOLVED"

_MISSING = object()  # sentinel: 키 자체가 없음(≠ 명시적 null)


def _canonical_hash(facility: Dict[str, Any]) -> str:
    """facility dict 의 정규 SHA-256 해시 (키 정렬, 재귀 정렬)."""
    serialized = json.dumps(facility, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _diff_facilities(
    baseline: Dict[str, Any], current: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """baseline vs current 차이 목록 반환. 키 누락과 명시적 null 구분.

    각 항목:
      field: 필드명
      change_type: ADDED | REMOVED | CHANGED
      baseline_value: baseline 값 (ADDED 시 None — 키 없음)
      current_value: current 값 (REMOVED 시 None — 키 없음)

    ADDED  = current에만 있는 키(baseline 키 없음)
    REMOVED = baseline에만 있는 키(current 키 없음)
    CHANGED = 양쪽 모두 키 있으나 값 다름(null vs 값 포함)
    """
    all_keys: Set[str] = set(baseline.keys()) | set(current.keys())
    diffs = []
    for key in sorted(all_keys):
        b_present = key in baseline
        c_present = key in current
        b_val = baseline[key] if b_present else _MISSING
        c_val = current[key] if c_present else _MISSING

        if b_val is _MISSING and c_val is not _MISSING:
            change_type = "ADDED"
            diffs.append({
                "field": key,
                "change_type": change_type,
                "baseline_value": None,
                "current_value": c_val,
            })
        elif b_val is not _MISSING and c_val is _MISSING:
            change_type = "REMOVED"
            diffs.append({
                "field": key,
                "change_type": change_type,
                "baseline_value": b_val,
                "current_value": None,
            })
        elif b_val is not _MISSING and c_val is not _MISSING and b_val != c_val:
            change_type = "CHANGED"
            diffs.append({
                "field": key,
                "change_type": change_type,
                "baseline_value": b_val,
                "current_value": c_val,
            })
    return diffs


def compare_snapshot(
    supabase: Any,
    *,
    sector: str,
    factory_id: str,
    consumer_input: Any,
    site_id: Optional[str] = None,
    subcontract_legal_event_id: Optional[str] = None,
    subcontractor_id: Optional[str] = None,
    material_inout_event_id: Optional[str] = None,
    occupancy_assessment_id: Optional[str] = None,
    app3_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """섹터별 현재 입력 사실과 최신 C10 스냅샷 비교.

    반환 dict:
      status: UNCHANGED | CHANGED | BASELINE_REQUIRED | UNRESOLVED
      diff: list[{field, change_type, baseline_value, current_value}]
      unresolved_fields: 현재 수집 시 해결되지 않은 필드 목록
      h01_absent_fields: BUILDING 전용, H01 DB write 없이 확인 불가한 필드 목록
      baseline_snapshot_id: C10 기준 스냅샷 id (BASELINE_REQUIRED/UNRESOLVED 시 None)
      baseline_hash: 기준 스냅샷 해시
      current_hash: 현재 facility 해시 (UNRESOLVED 시 None)
      sector: 판정에 사용된 sector 값
    """
    result: Dict[str, Any] = {
        "status": _STATUS_UNRESOLVED,
        "diff": [],
        "unresolved_fields": [],
        "h01_absent_fields": [],
        "baseline_snapshot_id": None,
        "baseline_hash": None,
        "current_hash": None,
        "sector": sector,
    }

    # 0. 유효한 sector 먼저 검증 — 알 수 없는 sector 는 DB 조회 전 즉시 UNRESOLVED
    if sector not in ("INDUSTRIAL", "BUILDING", "CONSTRUCTION"):
        result["status"] = _STATUS_UNRESOLVED
        result["unresolved_reason"] = f"알 수 없는 sector: {sector!r}"
        return result

    # CONSTRUCTION: site_id 없으면 현장 특정 불가 — DB 조회 전 즉시 UNRESOLVED
    if sector == "CONSTRUCTION" and not site_id:
        result["status"] = _STATUS_UNRESOLVED
        result["unresolved_reason"] = "CONSTRUCTION sector requires site_id"
        return result

    # 1. 기준 스냅샷 로드 (sector + status=ACTIVE + [CONSTRUCTION] site_id 필터)
    try:
        baseline_facility, snapshot_id = load_baseline_facility(
            supabase, factory_id, sector, site_id=site_id
        )
    except BaselineNotFound as exc:
        result["status"] = _STATUS_BASELINE_REQUIRED
        result["baseline_reason"] = str(exc)
        return result
    except BaselineQueryError as exc:
        result["status"] = _STATUS_UNRESOLVED
        result["unresolved_reason"] = f"기준 스냅샷 조회 실패: {exc}"
        return result

    result["baseline_snapshot_id"] = snapshot_id
    result["baseline_hash"] = _canonical_hash(baseline_facility)

    # 2. 현재 입력 사실 수집
    current_facility: Optional[Dict[str, Any]] = None
    h01_absent_fields: Set[str] = set()

    try:
        if sector == "INDUSTRIAL":
            current_facility, unresolved = collect_current_facility_industrial(
                supabase, factory_id, consumer_input, app3_projection
            )
            result["unresolved_fields"] = unresolved
        elif sector == "BUILDING":
            current_facility, unresolved, h01_absent_fields = collect_current_facility_building(
                supabase,
                factory_id,
                consumer_input,
                material_inout_event_id=material_inout_event_id,
                occupancy_assessment_id=occupancy_assessment_id,
                app3_projection=app3_projection,
            )
            result["unresolved_fields"] = unresolved
            result["h01_absent_fields"] = sorted(h01_absent_fields)
        elif sector == "CONSTRUCTION":
            if not site_id:
                result["status"] = _STATUS_UNRESOLVED
                result["unresolved_reason"] = "CONSTRUCTION sector requires site_id"
                return result
            current_facility, unresolved, _factory_id = collect_current_facility_construction(
                supabase,
                site_id,
                consumer_input,
                subcontract_legal_event_id=subcontract_legal_event_id,
                subcontractor_id=subcontractor_id,
                app3_projection=app3_projection,
            )
            result["unresolved_fields"] = unresolved
        else:
            result["status"] = _STATUS_UNRESOLVED
            result["unresolved_reason"] = f"알 수 없는 sector: {sector!r}"
            return result
    except CollectionError as exc:
        result["status"] = _STATUS_UNRESOLVED
        result["unresolved_reason"] = str(exc)
        return result

    # BUILDING H01: 원천 확인 불가 필드가 있으면 항상 UNRESOLVED.
    # 필드가 기존 스냅샷에 없어도 현재 값 확인 불가로 정확한 비교 불가.
    if h01_absent_fields:
        result["status"] = _STATUS_UNRESOLVED
        result["unresolved_reason"] = (
            f"H01 인증 필드 확인 불가(DB write 없이): {sorted(h01_absent_fields)}"
        )
        return result

    # 3. 해시 비교 + diff 생성
    current_hash = _canonical_hash(current_facility)
    result["current_hash"] = current_hash

    if current_hash == result["baseline_hash"]:
        result["status"] = _STATUS_UNCHANGED
    else:
        result["status"] = _STATUS_CHANGED
        diffs = _diff_facilities(baseline_facility, current_facility)
        result["diff"] = diffs

    return result
