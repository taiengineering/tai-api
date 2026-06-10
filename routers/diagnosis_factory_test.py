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

추가: GET /diagnosis/factory-test-verify/{token}
  진단 결과의 각 법령이 sector에 맞는지 law_sector_mapping과 실시간 대조하여
  OK/UNMAPPED/MISMATCH로 분류한다(진단 성공 여부와 별개의 sector 적합성 검증).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from schemas.legal_engine import DiagnoseStep1Body
from services.diagnosis_integrated_svc import run_step1_via_compiler
from services.diagnosis_helpers import _build_partial
from services.legal_rules import normalize_sector_db

router = APIRouter(prefix="/diagnosis", tags=["진단검증하니스"])

VERSION = "1.2.0"
ENGINE_VERSION = "v3.0-compiler-core-factory-test"
TTL_DAYS = 30

# 검증 하니스 전용 사업장 식별자. 이 status_code만 목록에 노출한다.
TEST_HARNESS_STATUS = "TEST_HARNESS"

# factories.sector 값 → 진단 입력 sector (입력표준 INDUSTRIAL)
#
# ※ SPECIAL_FACILITY → BUILDING 매핑은 "의도적 보류(dormant)"이며 버그가 아니다.
#    SPECIAL_FACILITY(병원·학교 등 특수시설)는 원래 정식 서비스 섹터였으나,
#    해당 분야는 관련 법령이 지나치게 분산되어 있어 현재 법령엔진 기술로는
#    진단 정확도가 충분히 나오지 않는다. 그래서 서비스 노출만 감춰둔 상태다.
#    (데이터는 살아있음: constants.sectors.VALID_SECTORS에 SPECIAL_FACILITY 포함,
#     law_sector_mapping에 SPECIAL_FACILITY 전용 법령 113건 보존)
#    엔진 기술이 발전하면 되살릴 섹터이므로, 이 줄을 함부로
#    "SPECIAL_FACILITY → SPECIAL_FACILITY"로 고치지 말 것. 지금 살리면 아직
#    정확도가 안 나오는 섹터를 강제로 노출하는 셈이 된다. 부활 시점은
#    법령엔진 정확도 확보 후 별도 결정한다.
_SECTOR_FROM_FACTORY = {
    "INDUSTRY": "INDUSTRIAL",
    "MANUFACTURING": "INDUSTRIAL",
    "INDUSTRIAL": "INDUSTRIAL",
    "BUILDING": "BUILDING",
    "CONSTRUCTION": "CONSTRUCTION",
    "SPECIAL_FACILITY": "BUILDING",  # 의도적 보류 — 위 주석 참조. 건드리지 말 것.
}

# 엔진 내부 표준(MANUFACTURING) → law_sector_mapping 표준(INDUSTRIAL) 환원.
# anonymous_factory_service._mapping_sector_key와 동일 규칙(검증도 같은 기준으로 대조).
_ENGINE_TO_MAPPING_SECTOR = {"MANUFACTURING": "INDUSTRIAL"}


def _mapping_sector_key(sector_value: str) -> str:
    s = (sector_value or "").strip().upper()
    return _ENGINE_TO_MAPPING_SECTOR.get(s, s)


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


@router.get("/factory-test-verify/{token}")
def factory_test_verify(token: str):
    """진단 결과의 sector 적합성 검증.

    저장된 진단 결과의 각 법령을 law_sector_mapping과 실시간 대조하여 분류한다.
    진단 '성공 여부'와는 별개로, 나온 법령이 해당 sector에 맞는지를 본다.

    판정:
      - OK        : law_sector_mapping에 매핑되어 있고 해당 sector를 포함     → 적합
      - MISMATCH  : 매핑되어 있으나 해당 sector를 포함하지 않음(타 sector 전용) → 누수(버그)
      - UNMAPPED  : law_sector_mapping에 매핑이 없음                          → 검토 필요

    sector_health:
      - FAIL : MISMATCH > 0 (입구 필터가 막았어야 할 법령이 새어 들어옴)
      - WARN : MISMATCH = 0 이고 UNMAPPED > 0 (가지고 온 미매핑 법령 검토 필요)
      - PASS : MISMATCH = 0, UNMAPPED = 0
    """
    supabase = get_supabase()
    tok = (token or "").strip()
    if not tok:
        raise HTTPException(status_code=422, detail="token이 필요합니다.")

    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("public_token, full_result")
        .eq("public_token", tok)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")

    full_result = res.data[0].get("full_result") or {}
    result_sector = str(full_result.get("sector") or "").upper()
    sector_key = _mapping_sector_key(result_sector)

    rules = full_result.get("rules_table") or []
    # 결과의 고유 법령명 수집(법령별 적용 건수도 같이)
    law_counts: Dict[str, int] = {}
    for r in rules:
        ln = (r.get("law_name") or "").strip()
        if ln:
            law_counts[ln] = law_counts.get(ln, 0) + 1
    law_names = list(law_counts.keys())

    # law_sector_mapping 일괄 조회(law_name 매칭; 366건 전부 law_name 고유)
    mapping: Dict[str, List[str]] = {}
    CHUNK = 100
    for i in range(0, len(law_names), CHUNK):
        chunk = law_names[i : i + CHUNK]
        try:
            m = (
                supabase.table("law_sector_mapping")
                .select("law_name, sectors")
                .in_("law_name", chunk)
                .execute()
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"law_sector_mapping 조회 실패: {exc}")
        for row in m.data or []:
            nm = (row.get("law_name") or "").strip()
            secs = [str(s).strip().upper() for s in (row.get("sectors") or []) if s]
            if nm:
                mapping[nm] = secs

    ok: List[Dict[str, Any]] = []
    mismatch: List[Dict[str, Any]] = []
    unmapped: List[Dict[str, Any]] = []
    for ln in law_names:
        cnt = law_counts[ln]
        secs = mapping.get(ln)
        if secs is None:
            unmapped.append({"law_name": ln, "count": cnt})
        elif sector_key in secs:
            ok.append({"law_name": ln, "count": cnt, "sectors": secs})
        else:
            mismatch.append({"law_name": ln, "count": cnt, "sectors": secs})

    if mismatch:
        health = "FAIL"
    elif unmapped:
        health = "WARN"
    else:
        health = "PASS"

    # 정렬: 건수 많은 순(검토 우선순위)
    mismatch.sort(key=lambda x: x["count"], reverse=True)
    unmapped.sort(key=lambda x: x["count"], reverse=True)

    return {
        "status": "success",
        "public_token": tok,
        "result_sector": result_sector,
        "mapping_sector_key": sector_key,
        "sector_health": health,
        "summary": {
            "total_laws": len(law_names),
            "ok": len(ok),
            "mismatch": len(mismatch),
            "unmapped": len(unmapped),
            "total_rules": len(rules),
        },
        "mismatch_laws": mismatch,
        "unmapped_laws": unmapped,
    }
