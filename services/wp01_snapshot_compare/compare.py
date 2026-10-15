"""WP01-A Snapshot Compare — 핵심 비교 로직.

현재 facility dict 와 기준 facility dict 를 비교해 변경 여부를 판정한다.
법령판정이 아님 — 데이터 동일성 확인만 수행한다.
DB WRITE 0, LEG EXECUTION 0.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Set

from services.wp01_snapshot_compare.errors import BaselineNotFound, CollectionError
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


def _canonical_hash(facility: Dict[str, Any]) -> str:
    """facility dict 의 정규 SHA-256 해시 (키 정렬, null 값 제외, 재귀 정렬)."""
    serialized = json.dumps(facility, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _diff_facilities(
    baseline: Dict[str, Any], current: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """baseline vs current 차이 목록 반환.

    각 항목: {field, baseline_value, current_value}.
    baseline 에만 있는 필드(삭제)와 current 에만 있는 필드(추가)도 포함.
    """
    all_keys: Set[str] = set(baseline.keys()) | set(current.keys())
    diffs = []
    for key in sorted(all_keys):
        b_val = baseline.get(key)
        c_val = current.get(key)
        if b_val != c_val:
            diffs.append({
                "field": key,
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
      diff: list[{field, baseline_value, current_value}] (CHANGED 일 때만 비어있지 않음)
      unresolved_fields: 현재 수집 시 해결되지 않은 필드 목록
      h01_absent_fields: BUILDING 전용, H01 DB write 없이 확인 불가한 필드 목록
      baseline_hash: 기준 스냅샷 해시 (BASELINE_REQUIRED/UNRESOLVED 시 None)
      current_hash: 현재 facility 해시 (UNRESOLVED 시 None)
      sector: 판정에 사용된 sector 값
    """
    result: Dict[str, Any] = {
        "status": _STATUS_UNRESOLVED,
        "diff": [],
        "unresolved_fields": [],
        "h01_absent_fields": [],
        "baseline_hash": None,
        "current_hash": None,
        "sector": sector,
    }

    # 1. 기준 스냅샷 로드
    try:
        baseline_facility = load_baseline_facility(supabase, factory_id)
    except BaselineNotFound as exc:
        result["status"] = _STATUS_BASELINE_REQUIRED
        result["baseline_reason"] = str(exc)
        return result

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

    # BUILDING H01 absent check — baseline 에 해당 필드 있으면 UNRESOLVED
    if h01_absent_fields:
        h01_in_baseline = h01_absent_fields & set(baseline_facility.keys())
        if h01_in_baseline:
            result["status"] = _STATUS_UNRESOLVED
            result["unresolved_reason"] = (
                f"H01 인증 필드 확인 불가(DB write 없이): {sorted(h01_in_baseline)}"
            )
            return result

    # 3. 해시 비교
    current_hash = _canonical_hash(current_facility)
    result["current_hash"] = current_hash

    if current_hash == result["baseline_hash"]:
        result["status"] = _STATUS_UNCHANGED
    else:
        result["status"] = _STATUS_CHANGED
        result["diff"] = _diff_facilities(baseline_facility, current_facility)

    return result
