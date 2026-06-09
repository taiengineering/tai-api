"""Factory-based Engine Test Harness — 검증 전용.

UI 무료진단(/diagnosis/run)과 동일 엔진(run_step1_via_compiler)을 타되,
본인인증·면책·결제·횟수제한 없이 factories 테이블에 등록된 실제 사업장으로
진단을 실행하고, 결과를 anonymous_diagnosis_results에 public_token과 함께
저장하여 기존 결과페이지(paid-diagnosis-result.html)를 그대로 재사용한다.

엔진 판정 로직/역회전/Compiler/룰데이터는 일절 수정하지 않는다 (GPT 영역 read-only).
입력 매핑은 services.diagnosis_integrated_svc.run_diagnosis의 step1_body 생성
로직을 그대로 차용하여 UI 경로와 동일한 입력→엔진 경로를 보장한다.

목록은 검증 전용으로 등록한 사업장(status_code='TEST_HARNESS')만 노출한다.
기존 실데이터/임시진단(ACTIVE, ANON_TEMP, DEMO 등)은 섞이지 않는다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from schemas.legal_engine import DiagnoseStep1Body
from services.diagnosis_integrated_svc import run_step1_via_compiler
from services.diagnosis_helpers import _build_partial
from services.legal_rules import normalize_sector_db

router = APIRouter(prefix="/diagnosis", tags=["진단검증하니스"])

VERSION = "1.1.0"
ENGINE_VERSION = "v3.0-compiler-core-factory-test"
TTL_DAYS = 30

# 검증 하니스 전용 사업장 식별자. 이 status_code만 목록에 노출한다.
TEST_HARNESS_STATUS = "TEST_HARNESS"

# factories.sector 값 → 진단 입력 sector (입력표준 INDUSTRIAL)
_SECTOR_FROM_FACTORY = {
    "INDUSTRY": "INDUSTRIAL",
    "MANUFACTURING": "INDUSTRIAL",
    "INDUSTRIAL": "INDUSTRIAL",
    "BUILDING": "BUILDING",
    "CONSTRUCTION": "CONSTRUCTION",
    "SPECIAL_FACILITY": "BUILDING",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FactoryTestRunBody(BaseModel):
    factory_id: str = Field(..., description="factories.id")


def _factory_to_step1_body(factory: Dict[str, Any]) -> DiagnoseStep1Body:
    """factories 행 → DiagnoseStep1Body.

    run_diagnosis(diagnosis_integrated_svc)의 step1_body 생성 규칙을 그대로 따른다.
    """
    raw_sector = str(factory.get("sector") or factory.get("site_type") or "INDUSTRY").upper()
    input_sector = _SECTOR_FROM_FACTORY.get(raw_sector, "INDUSTRIAL")
    sector = normalize_sector_db(input_sector)
    engine_sector = "MANUFACTURING" if sector == "INDUSTRIAL" else sector

    workers = int(factory.get("employee_count") or 0)
    floor_area = float(factory.get("building_area") or 0.0) or 400.0
    total_floor_area = floor_area
    contract_eok = float(factory.get("construction_amount") or 0.0) / 100_000_000.0 or 1.0

    inp: Dict[str, Any] = {
        "region": factory.get("address_sido") or "",
        "anonymous_flow": True,
        "factory_test": True,
        "factory_id": str(factory.get("id") or ""),
    }
    if factory.get("company_id"):
        inp["company_id"] = str(factory["company_id"])

    if engine_sector == "CONSTRUCTION":
        return DiagnoseStep1Body(
            factory_id=str(factory.get("id") or ""),
            sector=engine_sector,
            input=inp,
            construction_type=factory.get("construction_type") or "건축",
            contract_amount_eok=float(contract_eok),
            direct_workers=workers,
            subcon_workers=int(factory.get("subcontractor_worker_count") or 0),
        )
    if engine_sector == "BUILDING":
        return DiagnoseStep1Body(
            factory_id=str(factory.get("id") or ""),
            sector=engine_sector,
            input=inp,
            building_use_type=(
                factory.get("main_purpose_name")
                or factory.get("building_use_code")
                or "사무실"
            ),
            floor_area=float(floor_area),
            total_floor_area=float(total_floor_area),
            worker_count=workers,
            employee_count=workers,
            floor_count=int(factory.get("floor_count") or 5),
            electric_capacity=factory.get("electrical_capacity_kw"),
            elevator_count=factory.get("elevator_count"),
            has_high_pressure_gas=factory.get("has_high_pressure_gas"),
            has_hazardous_material=factory.get("is_hazardous_material"),
            has_boiler=factory.get("has_boiler"),
        )
    # MANUFACTURING (입력표준 INDUSTRIAL)
    return DiagnoseStep1Body(
        factory_id=str(factory.get("id") or ""),
        sector=engine_sector,
        input=inp,
        worker_count=workers,
        employee_count=workers,
        floor_area=float(floor_area),
        total_floor_area=float(total_floor_area),
        ksic_major=factory.get("ksic_code") or "",
        electric_capacity=factory.get("electrical_capacity_kw"),
        has_boiler=factory.get("has_boiler"),
        has_hazardous_material=factory.get("is_hazardous_material"),
        has_high_pressure_gas=factory.get("has_high_pressure_gas"),
        has_chemical_substance=factory.get("has_chemical_substance"),
    )


@router.get("/factory-test-cases")
def list_factory_test_cases(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
):
    """검증 하니스용 factories 목록 (카드 표시용).

    status_code='TEST_HARNESS'인 검증 전용 사업장만, 최신 등록순으로 노출한다.
    """
    supabase = get_supabase()
    offset = (page - 1) * size
    q = (
        supabase.table("factories")
        .select(
            "id, name, sector, employee_count, building_area, floor_count, "
            "construction_amount, construction_type, subcontractor_worker_count, "
            "ksic_code, main_purpose_name, building_use_code, "
            "is_hazardous_material, has_high_pressure_gas, has_chemical_substance, "
            "has_boiler, electrical_capacity_kw, elevator_count, "
            "last_diagnosis_at, legal_applicable_count",
            count="exact",
        )
        .eq("status_code", TEST_HARNESS_STATUS)
        .order("created_at", desc=True)
        .range(offset, offset + size - 1)
    )
    res = q.execute()
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page": page,
            "size": size,
            "total_pages": -(-(res.count or 0) // size) if res.count else 0,
        },
    }


@router.post("/factory-test-run")
def factory_test_run(body: FactoryTestRunBody):
    """factory_id로 진단 실행 → anonymous_diagnosis_results 저장 → public_token 반환.

    결과는 기존 결과페이지(paid-diagnosis-result.html?token=public_token)로 확인.
    """
    supabase = get_supabase()
    fid = body.factory_id.strip()
    if not fid:
        raise HTTPException(status_code=422, detail="factory_id가 필요합니다.")

    fac_res = (
        supabase.table("factories").select("*").eq("id", fid).limit(1).execute()
    )
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="사업장(factory)을 찾을 수 없습니다.")
    factory = fac_res.data[0]

    step1_body = _factory_to_step1_body(factory)

    try:
        eng = run_step1_via_compiler(supabase, step1_body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if eng.get("status") != "success":
        raise HTTPException(status_code=500, detail="진단 실행에 실패했습니다.")

    full_result = eng["data"]
    # 결과페이지가 company_name을 input_data/full_result에서 읽으므로 주입
    full_result.setdefault("company_name", factory.get("name") or "사업장")

    public_token = str(uuid.uuid4())
    sector = str(full_result.get("sector") or "").upper()
    tier_code = {
        "INDUSTRIAL": "INDUSTRY_FREE",
        "MANUFACTURING": "INDUSTRY_FREE",
        "BUILDING": "BUILDING_FREE",
        "CONSTRUCTION": "CONSTRUCTION_FREE",
    }.get(sector, "INDUSTRY_FREE")

    row = {
        "public_token": public_token,
        "input_data": {
            "sector": sector,
            "tier_code": tier_code,
            "company_name": factory.get("name") or "사업장",
            "factory_id": fid,
            "worker_count": int(factory.get("employee_count") or 0),
            "floor_area": float(factory.get("building_area") or 0.0),
        },
        "partial_result": _build_partial(full_result),
        "full_result": full_result,
        "expires_at": (_now() + timedelta(days=TTL_DAYS)).isoformat(),
        "status": "ACTIVE",
        "source_type": "factory_test",
        "engine_version": ENGINE_VERSION,
        "tier_code": tier_code,
        "paid_amount": 0,
    }
    ins = supabase.table("anonymous_diagnosis_results").insert(row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="결과 저장에 실패했습니다.")

    summary = full_result.get("summary") or {}
    return {
        "status": "success",
        "public_token": public_token,
        "factory_id": fid,
        "company_name": factory.get("name") or "사업장",
        "sector": sector,
        "applicable_count": full_result.get("applicable_count") or summary.get("total") or 0,
        "risk_level": full_result.get("risk_level") or "MEDIUM",
        "result_page": f"/paid-diagnosis-result.html?token={public_token}",
        "result": full_result,
    }
