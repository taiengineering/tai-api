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
  진단 결과의 sector 적합성 역검증. 범용 체크엔진(services.check_engine)을
  '어댑터'로 호출한다. 이 라우터(어댑터)가 법령엔진 데이터(진단결과·
  law_sector_mapping)를 체크엔진 계약(CheckItem)으로 변환하고, 체크엔진이
  반환한 사실(verdict)을 sector_health로 해석한다. 체크엔진 코어는 sector·
  법령을 모른다(오염 격리).
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
from constants.sectors import to_mapping_sector
from services import check_engine

router = APIRouter(prefix="/diagnosis", tags=["진단검증하니스"])

VERSION = "1.3.0"
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

# sector 키 환원은 constants.sectors.to_mapping_sector(표준 단일 정의처)를 인용한다.
# 별도 변환 상수를 이 파일에 두지 않는다 — 표준이 분산되면 입구 필터와 어긋난다.


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


# ─────────────────────────────────────────────────────────────────────────────
# 법령엔진용 어댑터: 진단결과·law_sector_mapping → 체크엔진 계약 → 해석
#  - 오염(sector/법령/테이블/판정)은 전부 이 어댑터에만 둔다.
#  - 체크엔진(services.check_engine)은 sector를 모르는 범용 대조기.
# ─────────────────────────────────────────────────────────────────────────────
def _load_law_values_by_name(
    supabase, law_names: List[str]
) -> Dict[str, List[str]]:
    """결과 법령명 → 그 법령이 룰상 허용하는 sector 목록(values).

    입구 필터와 동일 기준(law_id 경유)으로 law_sector_mapping을 읽는다.
    매핑이 없으면 빈 목록 → 체크엔진이 NO_RULE로 처리.
    """
    CHUNK = 100
    name_to_lawid: Dict[str, str] = {}
    for i in range(0, len(law_names), CHUNK):
        chunk = law_names[i : i + CHUNK]
        lm = (
            supabase.table("law_master")
            .select("id, law_name, is_active")
            .in_("law_name", chunk)
            .eq("is_active", True)
            .execute()
        )
        for row in lm.data or []:
            nm = (row.get("law_name") or "").strip()
            lid = str(row.get("id") or "")
            if nm and lid:
                name_to_lawid[nm] = lid

    lawid_to_sectors: Dict[str, List[str]] = {}
    law_ids = list(dict.fromkeys(name_to_lawid.values()))
    for i in range(0, len(law_ids), CHUNK):
        chunk = law_ids[i : i + CHUNK]
        m = (
            supabase.table("law_sector_mapping")
            .select("law_id, sectors")
            .in_("law_id", chunk)
            .execute()
        )
        for row in m.data or []:
            lid = str(row.get("law_id") or "")
            secs = [str(s).strip().upper() for s in (row.get("sectors") or []) if s]
            if lid:
                lawid_to_sectors[lid] = secs

    out: Dict[str, List[str]] = {}
    for nm in law_names:
        lid = name_to_lawid.get(nm)
        out[nm] = lawid_to_sectors.get(lid, []) if lid else []
    return out


@router.get("/factory-test-verify/{token}")
def factory_test_verify(token: str):
    """진단 결과의 sector 적합성 역검증 (범용 체크엔진 + 법령엔진 어댑터).

    흐름:
      1) 저장된 진단결과에서 고유 법령명을 모은다.
      2) 어댑터가 각 법령의 '허용 sector 목록'을 law_sector_mapping에서 읽어
         체크엔진 계약(CheckItem)으로 만든다.
      3) 체크엔진이 expected(진단 sector)와 대조해 사실(verdict)을 낸다.
      4) 어댑터가 verdict를 결과 형식·sector_health로 해석한다.

    verdict 의미(체크엔진):
      - MATCH    → 적합(OK)        : 이 법은 이 sector에서 나올 수 있다.
      - MISMATCH → 누수(MISMATCH)  : 이 법은 이 sector에서 나오면 안 되는데 나옴.
      - NO_RULE  → 미매핑(UNMAPPED): 룰이 없어 판단 보류(가지고 감).
    sector_health(어댑터 해석):
      - FAIL : MISMATCH > 0 / WARN : NO_RULE > 0 / PASS : 둘 다 0
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
    expected = to_mapping_sector(result_sector)  # 표준 인용(입구 필터와 동일)

    rules = full_result.get("rules_table") or []
    law_counts: Dict[str, int] = {}
    for r in rules:
        ln = (r.get("law_name") or "").strip()
        if ln:
            law_counts[ln] = law_counts.get(ln, 0) + 1
    law_names = list(law_counts.keys())

    # 어댑터: 법령 → 허용 sector 목록(values)
    try:
        law_values = _load_law_values_by_name(supabase, law_names)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"룰 조회 실패: {exc}")

    # 계약 변환 → 체크엔진 호출(역검증)
    items = [check_engine.CheckItem(id=nm, values=law_values.get(nm, [])) for nm in law_names]
    results = check_engine.check(items, expected)
    counts = check_engine.tally(results)

    # 어댑터 해석: verdict → 결과 형식
    ok: List[Dict[str, Any]] = []
    mismatch: List[Dict[str, Any]] = []
    unmapped: List[Dict[str, Any]] = []
    for r in results:
        cnt = law_counts.get(r.id, 0)
        if r.verdict == check_engine.VERDICT_MATCH:
            ok.append({"law_name": r.id, "count": cnt, "sectors": list(r.values)})
        elif r.verdict == check_engine.VERDICT_MISMATCH:
            mismatch.append({"law_name": r.id, "count": cnt, "sectors": list(r.values)})
        else:  # NO_RULE
            unmapped.append({"law_name": r.id, "count": cnt})

    if counts.get(check_engine.VERDICT_MISMATCH, 0) > 0:
        health = "FAIL"
    elif counts.get(check_engine.VERDICT_NO_RULE, 0) > 0:
        health = "WARN"
    else:
        health = "PASS"

    mismatch.sort(key=lambda x: x["count"], reverse=True)
    unmapped.sort(key=lambda x: x["count"], reverse=True)

    return {
        "status": "success",
        "public_token": tok,
        "result_sector": result_sector,
        "mapping_sector_key": expected,
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
