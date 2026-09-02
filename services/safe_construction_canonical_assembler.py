"""WO-DUAL-CST-STEP2-IMPLEMENT-001 GATE-1 — SAFE CONSTRUCTION canonical assembler.

SAFE 건설 자산(construction_sites)을 READ-ONLY 로 읽어 Marketing CONSTRUCTION
유료 계약(MKT_CST_PAID_CONTRACT_V1, exact27)으로 조립한다.

원칙 (WO-DUAL-CST-STEP1-CONTRACT-AUDIT-001 FROZEN):
  - SAFE EXACT SOURCE 6 만 현장 원값에서 채운다(단위변환만 허용, 어휘/위험작업 추론 금지).
  - RUNTIME_INPUT 13 은 assembler 가 값을 만들지 않는다 → None + unresolved.
    진단 요청의 consumer override(명시값)로만 해소된다.
  - special_work_type / hazard_type / process_name / work_name = LEG boolean derivation 금지
    (DERIVATION=0, audit CONFIRMED: 자유텍스트 → LEG 축 결정론적 매핑 없음).
  - NOT_CONSUMED 8 은 canonical key 로 유지하되 LEG 억지 투입/alias/의미변환 금지.
  - false/0/[] 보존, NULL != false/0/"".
  - contract_amount = 억(eok) 단위(construction_svc 관례) → project_amount 변환 없이 그대로.
  - DB WRITE 0. 새 법적 의미 생성 0.
"""
from __future__ import annotations

from typing import Any, Dict, List

CONTRACT_VERSION = "MKT_CST_PAID_CONTRACT_V1"
SECTOR = "CONSTRUCTION"

# frozen exact27 (audit DB 실측 순서 — diagnosis_input_fields sector=CONSTRUCTION tier=PAID)
TARGET_FIELDS = [
    "project_amount", "worker_count", "construction_type", "project_address",
    "has_subcontractor", "subcontractor_count", "process_list",
    "has_excavation", "has_demolition", "work_height_m",
    "has_truck_loading_unloading", "has_tower_crane", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    "has_confined_space", "has_asbestos_demo", "has_blasting", "has_diving",
    "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
    "has_water_tank", "is_energy_intensive", "is_multi_use", "subcontractor",
]

# SAFE EXACT SOURCE 6 — construction_sites 원값에서 확보(단위변환만).
#   target -> construction_sites column. (has_subcontractor/subcontractor_count 은 아래 특례)
_EXACT_DIRECT = {
    "worker_count": "total_workers",        # 전체/동시 투입 인원 = total_workers(direct 아님)
    "construction_type": "site_type",       # 공사 유형
    "project_address": "site_address",      # 현장 주소
    "project_amount": "contract_amount",    # 총 공사금액(억 단위, 변환 없음)
}

# RUNTIME_INPUT 13 — SAFE 자산에 표준코드 없음 → assembler None + unresolved.
#   consumer override(명시값)로만 해소. audit 확정 목록 그대로 freeze(추가/삭제 금지).
RUNTIME_INPUT_FIELDS = (
    "has_excavation", "has_demolition", "has_tower_crane",
    "has_confined_space", "has_asbestos_demo", "has_blasting", "has_diving",
    "work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    "has_chemical_substance",
    # VERIFIER CORRECTION: has_subcontractor 는 subcon_workers>0 자동유도 금지(DERIVABLE=0),
    #   LEG passthrough 대상 → RUNTIME_INPUT(사용자 명시 boolean 만). RUNTIME13 -> RUNTIME14.
    "has_subcontractor",
)

# 규제대상/기타 — LEG consumed 이나 SAFE 자산 직접 컬럼 없음 → RUNTIME_INPUT 성격(override 대상).
_REGULATORY_RUNTIME = (
    "has_asbestos", "has_gas", "has_high_pressure_gas",
    "has_water_tank", "is_energy_intensive", "is_multi_use",
)

# NOT_CONSUMED / composite table — canonical 유지, LEG 억지 투입 금지. assembler None + unresolved.
_NOT_CONSUMED_OR_TABLE = (
    "process_list", "subcontractor",   # table 형(RAW envelope), LEG 미소비
)


def _rows(res) -> List[dict]:
    return list(getattr(res, "data", None) or [])


def assemble_construction_marketing_contract(supabase, site_id: str) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    provenance: Dict[str, Dict[str, Any]] = {}
    unresolved: set = set()

    def _resolve(field, value, mode, source):
        values[field] = value
        provenance[field] = {"mode": mode, "source": source}

    def _unresolved(field, source):
        values[field] = None
        provenance[field] = {"mode": "UNRESOLVED", "source": source}
        unresolved.add(field)

    # ── construction_sites (single row) ──
    site_res = (
        supabase.table("construction_sites")
        .select("*").eq("id", site_id).limit(1).execute()
    )
    site_rows = _rows(site_res)
    site = site_rows[0] if site_rows else {}
    factory_id = site.get("factory_id")   # site↔factory bridge (없으면 runtime fail-closed)

    # ── SAFE EXACT SOURCE 6 ──
    # 4 direct: column 존재 시 원값(None/0/"" 보존). 단위변환 없음(contract_amount 이미 억).
    for field, col in _EXACT_DIRECT.items():
        if col not in site:
            _unresolved(field, f"construction_sites.{col}(source column unavailable)")
        else:
            v = site.get(col)
            _resolve(field, v, "DIRECT", f"construction_sites.{col}")

    # subcontractor_count (VERIFIER CORRECTION): 하도급 "업체 수" 정본 컬럼 없음.
    #   construction_workers distinct count 유도 = derivation 금지(DERIVABLE=0).
    #   subcon_workers(근로자 수)로 대체도 의미 상이라 금지.
    #   CANONICAL_UNRESOLVED 유지 + RUNTIME_INPUT 아님(LEG passthrough 대상 아님 → 강제 질문 안 함).
    #   construction_workers 조회 없음.
    _unresolved("subcontractor_count",
                "CANONICAL_UNRESOLVED(하도급 업체 수 정본 컬럼 없음 — 유도 금지, LEG runtime 아님)")
    # has_subcontractor 는 아래 RUNTIME_INPUT_FIELDS 루프에서 unresolved 처리(자동유도 금지).

    # ── RUNTIME_INPUT 14(위험작업+has_subcontractor) + 규제 = None + unresolved (override 대상) ──
    for f in RUNTIME_INPUT_FIELDS:
        _unresolved(f, "RUNTIME_INPUT(SAFE 자산 표준코드 없음 — 진단 시 사용자 확인)")
    for f in _REGULATORY_RUNTIME:
        _unresolved(f, "RUNTIME_INPUT(규제대상 — SAFE 직접 컬럼 없음, 진단 시 확인)")

    # ── NOT_CONSUMED table(process_list/subcontractor) = None + unresolved (LEG 미투입) ──
    for f in _NOT_CONSUMED_OR_TABLE:
        _unresolved(f, "NOT_CONSUMED(table/RAW envelope — LEG 미소비, canonical 유지)")

    # ── 27 정합성(안전망) ──
    for f in TARGET_FIELDS:
        if f not in values:
            _unresolved(f, "MISSING")

    return {
        "contract_version": CONTRACT_VERSION,
        "sector": SECTOR,
        "factory_id": factory_id,
        "values": {f: values[f] for f in TARGET_FIELDS},   # 정확히 27, 순서 고정
        "unresolved_fields": sorted(unresolved),
        "provenance": provenance,
    }
