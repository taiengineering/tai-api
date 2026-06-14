"""
legal_adapter_test — 어댑터 경로 테스트 라우터 (임시, 검증 후 제거).

POST /admin/legal-adapter-run  body={factory_id}
  → factory 입력 표준화 → 어댑터 → 표준 계약 목록 (요약 + 상위 표본)
X-Internal-Secret 보호. 기존 진단 경로 무수정.
"""
from __future__ import annotations

import os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from schemas.legal_engine import DiagnoseStep1Body
from services.legal_rules import normalize_sector_db
from services.legal_engine_adapter_run import run_adapter_diagnosis

router = APIRouter()

_SECTOR_FROM_FACTORY = {
    "INDUSTRY": "INDUSTRIAL", "MANUFACTURING": "INDUSTRIAL", "INDUSTRIAL": "INDUSTRIAL",
    "BUILDING": "BUILDING", "CONSTRUCTION": "CONSTRUCTION", "SPECIAL_FACILITY": "BUILDING",
}


class AdapterRunBody(BaseModel):
    factory_id: str


def _factory_to_step1_body(factory: dict) -> DiagnoseStep1Body:
    raw = str(factory.get("sector") or "INDUSTRY").upper()
    input_sector = _SECTOR_FROM_FACTORY.get(raw, "INDUSTRIAL")
    sector = normalize_sector_db(input_sector)
    engine_sector = "MANUFACTURING" if sector == "INDUSTRIAL" else sector
    workers = int(factory.get("employee_count") or 0)
    inp = {"factory_id": str(factory.get("id") or ""), "anonymous_flow": True}
    if engine_sector == "CONSTRUCTION":
        return DiagnoseStep1Body(
            factory_id=str(factory.get("id") or ""), sector=engine_sector, input=inp,
            construction_type=factory.get("construction_type") or "건축",
            contract_amount_eok=float(factory.get("construction_amount") or 0.0) / 1e8 or 1.0,
            direct_workers=workers, subcon_workers=int(factory.get("subcontractor_worker_count") or 0),
        )
    if engine_sector == "BUILDING":
        return DiagnoseStep1Body(
            factory_id=str(factory.get("id") or ""), sector=engine_sector, input=inp,
            building_use_type=factory.get("main_purpose_name") or factory.get("building_use_code") or "사무실",
            floor_area=float(factory.get("building_area") or 0.0) or 400.0,
            total_floor_area=float(factory.get("building_area") or 0.0) or 400.0,
            worker_count=workers, employee_count=workers,
            floor_count=int(factory.get("floor_count") or 5),
        )
    return DiagnoseStep1Body(
        factory_id=str(factory.get("id") or ""), sector=engine_sector, input=inp,
        worker_count=workers, employee_count=workers,
        floor_area=float(factory.get("building_area") or 0.0) or 400.0,
        total_floor_area=float(factory.get("building_area") or 0.0) or 400.0,
        ksic_major=factory.get("ksic_code") or "",
    )


@router.post("/admin/legal-adapter-run")
def legal_adapter_run(
    body: AdapterRunBody,
    x_internal_secret: str = Header(None, alias="X-Internal-Secret"),
):
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")
    sb = get_supabase()
    fac = sb.table("factories").select("*").eq("id", body.factory_id.strip()).limit(1).execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="factory not found")
    step1 = _factory_to_step1_body(fac.data[0])
    try:
        result = run_adapter_diagnosis(sb, step1)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"adapter run failed: {exc}")
    # 요약 + 상위 표본(전체는 큼)
    return {
        "adapter": result["adapter"],
        "sector": result["sector"],
        "counts": result["counts"],
        "facility_base_actor": result["facility_base"]["actor"],
        "sample_contexts": result["contexts"][:15],
    }
