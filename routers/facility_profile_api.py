"""WO-V4-PHASE1-001: FacilityProfile API

Phase 1 전용 엔드포인트.

금지:
  Check Engine / Track A / Track B 연결 금지
  ApplicabilityCondition 생성 금지
  Registry 구현 금지
  factories 쪼럼 수정 금지
  value 필드에 UNKNOWN 문자열/0/false 저장 금지
"""
from __future__ import annotations

import json
from typing import Dict, Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.facility_profile_service import build_facility_profile, profile_to_db_row

router = APIRouter(
    prefix="/facility-profiles",
    tags=["Phase1 FacilityProfile"],
)


class FacilityProfileResponse(BaseModel):
    factory_id: str
    profile_id: str
    profile_version: int
    sector: str
    ksic_code: str | None
    workforce: Dict[str, Any]
    building: Dict[str, Any]
    metrics: Dict[str, Any]
    provenance: Dict[str, Any]
    profile_snapshot: Dict[str, Any]


@router.post("/{factory_id}", response_model=FacilityProfileResponse)
def create_facility_profile(
    factory_id: str,
):
    """factories row → FacilityProfile 생성 + 저장.

    Phase 1 목표: 입력 손실 0%. Track A/B 연결 없음.
    """
    supabase = get_supabase()

    # factories 로드 (Source of Record 읽기 전용)
    res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    row = res.data

    # FacilityProfile 생성
    profile = build_facility_profile(row)

    # 기존 버전 확인 (최신 버전에 +1)
    existing = (
        supabase.table("facility_profiles")
        .select("profile_version")
        .eq("factory_id", factory_id)
        .order("profile_version", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        profile["profile_version"] = existing.data[0]["profile_version"] + 1

    # DB 저장
    db_row = profile_to_db_row(profile)
    insert_res = (
        supabase.table("facility_profiles")
        .insert(db_row)
        .execute()
    )
    saved = insert_res.data[0]

    return FacilityProfileResponse(
        factory_id=factory_id,
        profile_id=str(saved["id"]),
        profile_version=saved["profile_version"],
        sector=profile["sector"],
        ksic_code=profile.get("ksic_code"),
        workforce=profile["workforce"],
        building=profile["building"],
        metrics=profile["metrics"],
        provenance=profile["provenance"],
        profile_snapshot=profile,
    )


@router.get("/{factory_id}", response_model=FacilityProfileResponse)
def get_facility_profile(
    factory_id: str,
    version: int = Query(None, description="버전 번호 (없으면 최신)"),
):
    """FacilityProfile 복원 (Round Trip 검증용)."""
    supabase = get_supabase()

    query = (
        supabase.table("facility_profiles")
        .select("*")
        .eq("factory_id", factory_id)
    )
    if version:
        query = query.eq("profile_version", version)
    else:
        query = query.order("profile_version", desc=True).limit(1)

    res = query.execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="FacilityProfile을 찾을 수 없습니다")

    saved = res.data[0]
    snapshot = saved["profile_snapshot"]

    return FacilityProfileResponse(
        factory_id=factory_id,
        profile_id=str(saved["id"]),
        profile_version=saved["profile_version"],
        sector=snapshot["sector"],
        ksic_code=snapshot.get("ksic_code"),
        workforce=snapshot["workforce"],
        building=snapshot["building"],
        metrics=snapshot["metrics"],
        provenance=snapshot["provenance"],
        profile_snapshot=snapshot,
    )


@router.get("/{factory_id}/verify", response_model=dict)
def verify_round_trip(
    factory_id: str,
):
    """SC-01~SC-04 Round Trip 검증.

    factories 원본과 FacilityProfile 재로드를 비교하여
    입력 손실률과 UNKNOWN 보존 여부를 반환한다.
    """
    supabase = get_supabase()

    # factories 원본
    fac_res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    row = fac_res.data
    original_profile = build_facility_profile(row)

    # 저장된 최신 프로파일
    prof_res = (
        supabase.table("facility_profiles")
        .select("profile_snapshot")
        .eq("factory_id", factory_id)
        .order("profile_version", desc=True)
        .limit(1)
        .execute()
    )
    if not prof_res.data:
        raise HTTPException(status_code=404, detail="저장된 FacilityProfile이 없습니다. POST 먼저 호출하세요.")

    saved_snapshot = prof_res.data[0]["profile_snapshot"]

    # SC-01: 핵심 필드 비교
    check_fields = [
        ("sector", original_profile.get("sector"), saved_snapshot.get("sector")),
        ("ksic_code", original_profile.get("ksic_code"), saved_snapshot.get("ksic_code")),
    ]
    tri_paths = [
        ("workforce.regular_workers",     original_profile["workforce"]["regular_workers"],     saved_snapshot["workforce"]["regular_workers"]),
        ("workforce.subcontract_workers", original_profile["workforce"]["subcontract_workers"], saved_snapshot["workforce"]["subcontract_workers"]),
        ("workforce.total_workers",       original_profile["workforce"]["total_workers"],       saved_snapshot["workforce"]["total_workers"]),
        ("building.use_code",             original_profile["building"]["use_code"],             saved_snapshot["building"]["use_code"]),
        ("building.floor_area",           original_profile["building"]["floor_area"],           saved_snapshot["building"]["floor_area"]),
        ("building.floor_count",          original_profile["building"]["floor_count"],          saved_snapshot["building"]["floor_count"]),
        ("metrics.construction_amount",   original_profile["metrics"]["construction_amount"],   saved_snapshot["metrics"]["construction_amount"]),
        ("metrics.electrical_kw",         original_profile["metrics"]["electrical_kw"],         saved_snapshot["metrics"]["electrical_kw"]),
        ("metrics.gas_capacity",          original_profile["metrics"]["gas_capacity"],          saved_snapshot["metrics"]["gas_capacity"]),
    ]

    mismatches = []
    unknown_violations = []  # SC-02: UNKNOWN이 0/false로 저장된 경우

    for path, orig, saved in tri_paths:
        if orig != saved:
            mismatches.append({"field": path, "original": orig, "saved": saved})
        # SC-02 검증
        if saved.get("state") == "UNKNOWN":
            if saved.get("value") not in (None,):
                unknown_violations.append({"field": path, "value": saved.get("value")})

    for name, orig_val, saved_val in check_fields:
        if orig_val != saved_val:
            mismatches.append({"field": name, "original": orig_val, "saved": saved_val})

    return {
        "factory_id": factory_id,
        "sc01_input_loss_count": len(mismatches),
        "sc01_pass": len(mismatches) == 0,
        "sc02_unknown_violations": len(unknown_violations),
        "sc02_pass": len(unknown_violations) == 0,
        "sc03_provenance_available": bool(saved_snapshot.get("provenance")),
        "mismatches": mismatches,
        "unknown_violations": unknown_violations,
    }
