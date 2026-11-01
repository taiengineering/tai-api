"""Admin 문서 디지털화 — Intake + Preflight.

WO-034: OBJ01 파이프라인 [1] Intake Manifest + [2] Preflight Census.
WO-037: [7] Quality — include_quality=true 시 구조 검수 실행.
합성 데이터 전용 (실자료 처리 차단 — GR3-H05 미해소).

권한 계약 (WO-032 FROZEN):
  - role_code == "001" 전용
  - company_id: companies 테이블 실존 확인 (_ensure_own_company() 재사용 금지)
  - 파일 크기: ≤ 52,428,800 bytes → 413
  - 감사: fail-closed (INTAKE_RECEIVED 실패 시 처리 중단)
"""
from __future__ import annotations

import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

import services.audit_svc as audit_svc
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.onboarding_digitization.intake_svc import (
    _SCHEMA_VERSION,
    _verify_company_exists,
    run_intake_preflight,
)
from services.onboarding_digitization.models import IntakePreflightResponse
from services.onboarding_digitization.triage_svc import run_triage
from services.onboarding_digitization.parse_svc import run_parse
from services.onboarding_digitization.map_svc import run_map
from services.onboarding_digitization.quality_svc import run_quality
from services.onboarding_digitization.package_svc import run_package

router = APIRouter(
    prefix="/admin/companies",
    tags=["관리 - 문서 디지털화"],
)


def _require_synthetic_gate() -> None:
    """합성 데이터 전용 실행 경계 — DIGITIZATION_SYNTHETIC_ENABLED=true 필요 (R1-02).

    운영 환경에서 신규 디지털화 API가 실자료 처리 경로를 여는 것을 차단.
    운영 활성화는 별도 Owner 승인 Gate 후 설정.
    """
    if os.getenv("DIGITIZATION_SYNTHETIC_ENABLED", "false").lower() != "true":
        raise HTTPException(
            status_code=503,
            detail="디지털화 API 비활성 — 합성 데이터 환경 아님 (DIGITIZATION_SYNTHETIC_ENABLED=true 필요)",
        )


def _require_role_001(current: dict) -> None:
    if current.get("role_code") != "001":
        raise HTTPException(
            status_code=403,
            detail="디지털화 관리자 권한이 없습니다 (role_code=001 필요)",
        )


def _require_audit(
    action: str,
    entity_type: str,
    actor_id: Optional[str],
    after_data: dict,
) -> str:
    """필수 감사기록 — 실패 시 503 발생 (fail-closed, WO-034 C05)."""
    audit_id = audit_svc.record(
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        after=after_data,
    )
    if audit_id is None:
        raise HTTPException(
            status_code=503,
            detail=f"감사기록 실패 — {action} 처리 중단",
        )
    return audit_id


@router.post("/{company_id}/digitization/intake")
async def intake_preflight(
    company_id: str,
    files: List[UploadFile] = File(...),
    current: dict = Depends(get_current_user),
    include_parse: bool = Query(default=False),
    include_map: bool = Query(default=False),
    include_quality: bool = Query(default=False),
    include_package: bool = Query(default=False),
):
    """파일 접수 및 Preflight 검사.

    [1] Intake Manifest + [2] Preflight Census.
    합성 데이터 전용 — 실고객 파일·운영 DB 쓰기 없음.
    """
    # 0. 합성 데이터 전용 실행 경계 — DB 접근 전 차단 (R2-01: 순서 결함 수정)
    _require_synthetic_gate()

    # 1. role_code == "001" 강제 (031/032/033 포함 비적격 → 403)
    _require_role_001(current)

    # get_supabase()는 gate·role 확인 후 호출 — 비활성 환경에서 DB 클라이언트 오류 방지 (R2-01)
    supabase = get_supabase()

    # 2. company_id 실존 확인 (C01: _ensure_own_company() 재사용 금지)
    _verify_company_exists(company_id, supabase)

    # 3. 빈 파일 목록 방어
    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다")

    actor_id: Optional[str] = current.get("id")

    # source_id 사전 생성 — INTAKE_RECEIVED와 INTAKE_COMPLETE 감사 추적 일치 (R1-05)
    source_id = str(uuid.uuid4())

    # 4. 감사: INTAKE_RECEIVED — fail-closed (처리 시작 전 필수)
    _require_audit(
        action="INTAKE_RECEIVED",
        entity_type="onboarding_digitization",
        actor_id=actor_id,
        after_data={
            "company_id": company_id,
            "source_id": source_id,
            "file_count": len(files),
            "filenames": [f.filename for f in files],
        },
    )

    # 5. Intake + Preflight 실행 (크기 제한 포함 — C02, source_id 전달 — R1-05)
    bundle, report, file_bytes = await run_intake_preflight(
        company_id=company_id,
        actor_id=actor_id or "",
        upload_files=files,
        supabase=supabase,
        source_id=source_id,
    )

    # 6. 감사: INTAKE_COMPLETE — fail-closed (결과 반환 전 필수)
    _require_audit(
        action="INTAKE_COMPLETE",
        entity_type="onboarding_digitization",
        actor_id=actor_id,
        after_data={
            "company_id": company_id,
            "source_id": bundle.source_id,
            "overall_status": report.overall_status,
            "file_count": len(bundle.files),
        },
    )

    # 7. [3] Triage + [4] Parse (include_parse/map/quality/package 시 실행)
    triage_report = None
    parse_report = None
    mapping_report = None
    quality_report = None
    package_result = None
    if include_parse or include_map or include_quality or include_package:
        triage_report = run_triage(
            source_id=bundle.source_id,
            preflight_results=report.file_results,
        )
        parse_report = run_parse(
            source_id=bundle.source_id,
            file_bytes_dict=file_bytes,
            triage_report=triage_report,
        )

    # 8. [5] Map (include_map/quality/package 시 실행)
    if (include_map or include_quality or include_package) and parse_report is not None:
        mapping_report = run_map(
            source_id=bundle.source_id,
            parse_report=parse_report,
        )

    # 9. [7] Quality (include_quality/package 시 실행)
    if (include_quality or include_package) and mapping_report is not None:
        quality_report = run_quality(
            source_bundle=bundle,
            preflight_report=report,
            parse_report=parse_report,
            mapping_report=mapping_report,
        )

    # 10. [8] Package (include_package=true 시 전체 파이프라인 결과 묶음)
    if include_package and triage_report is not None and parse_report is not None and mapping_report is not None:
        package_result = run_package(
            source_bundle=bundle,
            preflight_report=report,
            triage_report=triage_report,
            parse_report=parse_report,
            mapping_report=mapping_report,
            quality_report=quality_report,
        )

    return {
        "status": "success",
        "data": IntakePreflightResponse(
            schema_version=_SCHEMA_VERSION,
            bundle=bundle,
            preflight=report,
            triage=triage_report if not include_package else None,
            # Package 요청 시 중간 단계 응답 미포함 — 패키지에 전부 포함됨
            parsed=parse_report if (include_parse or include_map) and not include_package else None,
            mapped=mapping_report if include_map and not include_package else None,
            quality=quality_report if include_quality and not include_package else None,
            package=package_result,
        ).model_dump(),
    }
