"""WO-DUAL-CST-STEP2-IMPLEMENT-001 GATE-1 — SAFE CONSTRUCTION 공식 LEG 진입.

경로: assemble_construction_marketing_contract(SAFE 자산 READ) -> canonical27
      -> consumer override(RUNTIME20, non-null) -> DiagnoseStep1Body(sector="CONSTRUCTION", input=values)
      -> run_leg_diagnosis(공식 Runtime Delegate: build_facility -> /rtm/evaluate -> full_result).

산업 GATE-4A(run_safe_industrial_leg)와 대칭. canonical denominator 27 불변.
override allowlist = RUNTIME_INPUT_FIELDS(20). subcontractor_count 는 override 대상 아님
(CANONICAL_UNRESOLVED, LEG passthrough 아님 — VERIFIER CORRECTION).
DB WRITE 0(READ-ONLY LEG diagnosis). factory 생성 side effect 0.
"""
from __future__ import annotations
from typing import Any, Dict

from services.safe_construction_canonical_assembler import (
    assemble_construction_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION,
    RUNTIME_INPUT_FIELDS,
)
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.leg_diagnosis_svc import run_leg_diagnosis


class ConstructionSiteBridgeError(Exception):
    """site 에 factory_id 연결이 없을 때(진단 중 factory 생성 금지 — fail-closed)."""


# SAFE 화면에서 진단 시 명시 가능한 canonical override field(RUNTIME20).
#   assembler 가 값을 만들지 않는 위험작업/규제/has_subcontractor 축(20).
#   subcontractor_count 는 포함하지 않는다(정본 컬럼 없음 · LEG passthrough 아님).
# WO-E2E-OBJ01-SEM003-DIVING-FAMILY-FASTLANE-IMPLEMENT-001:
#   SEM-003 5 stable diving subtype/supply booleans are consumer overrides
#   (SafeConstructionConsumerInput) but are NOT in the audit-frozen
#   RUNTIME_INPUT_FIELDS/TARGET_FIELDS canonical 27. Extend the override
#   allowlist so they merge into `values` and flow through _LEG_INPUT_FIELDS
#   filter to LEG runtime. Assembler contract remains at 27 unchanged.
SEM003_DIVING_OVERRIDE_FIELDS = (
    "has_scuba_diving",
    "has_surface_supplied_diving",
    "supplies_air_to_diver_from_air_compressor",
    "supplies_breathing_gas_to_diver_from_cylinder",
    # PATCH-1: existing LEG numeric input for Art.531 boundary (≥10 kgf/cm²).
    # Not re-added to _LEG_INPUT_FIELDS (already exists). Consumer-only override.
    "breathing_gas_cylinder_pressure_kgf_cm2",
    # WO-E2E-OBJ01-DIVING-COVERAGE-BACKLOG-FASTLANE-IMPLEMENT-001:
    # 3 new stable inputs for Art.547③/⑥ (surface-supplied specific).
    "diving_depth_m",
    "diving_surface_ascent_restricted",
    "diving_decompression_stop_required",
)
# WO-E2E-OBJ01-HIGH-PRESSURE-COMMON-COVERAGE-INTEGRATED-IMPLEMENT-001:
# HP-common override axis is separate from SEM-003 Diving so that
# has_pressure_adjustment_chamber does NOT get cleared when has_diving!=true
# (기압조절실 = 고압작업자 OR 잠수작업자 공통 설비). 4 of the 5 keys
# already exist in LEG _LEG_INPUT_FIELDS from prior WOs; only has_caisson_work
# is new to the transport allowlist (215→216). Total SEM-003 override count
# stays at 8; HP-common adds 5; SAFE_CST_OVERRIDE_FIELDS = 20 + 8 + 5 = 33.
HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS = (
    "has_high_pressure_work",
    "has_pressure_adjustment_chamber",
    "has_air_compressor",
    "supplies_air_to_high_pressure_workroom_or_airlock",
    "has_caisson_work",
)
SAFE_CST_OVERRIDE_FIELDS = (
    tuple(RUNTIME_INPUT_FIELDS)
    + SEM003_DIVING_OVERRIDE_FIELDS
    + HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS
)


def run_safe_construction_leg(supabase, site_id: str, consumer_input) -> Dict[str, Any]:
    """SAFE CONSTRUCTION 공식 LEG 진단. full_result 반환(저장/결제/factory 생성 없음)."""
    # A. asset canonical (assembler, READ ONLY) — site↔factory bridge 포함.
    contract = assemble_construction_marketing_contract(supabase, site_id)
    factory_id = contract.get("factory_id")
    if not factory_id:
        # 진단 실행이 factory 를 생성하지 않는다 → fail-closed.
        raise ConstructionSiteBridgeError("현장과 시설 연결이 완료되지 않았습니다.")

    values: Dict[str, Any] = dict(contract["values"])           # 정확히 27
    unresolved = set(contract.get("unresolved_fields") or [])
    provenance: Dict[str, Any] = dict(contract.get("provenance") or {})

    # B. consumer override — RUNTIME20 만, non-null(None=미override, false/0=override).
    if hasattr(consumer_input, "model_dump"):
        overrides = consumer_input.model_dump(exclude_none=True)
    else:
        overrides = {k: v for k, v in dict(consumer_input or {}).items() if v is not None}
    for f in SAFE_CST_OVERRIDE_FIELDS:
        if f in overrides:
            values[f] = overrides[f]
            provenance[f] = {"mode": "CONSUMER_OVERRIDE", "source": "safe.construction-diagnosis"}
            unresolved.discard(f)

    # C. WO-010 STEP-2C : canonical27 final-cut 제거. TARGET_FIELDS / RUNTIME_INPUT_FIELDS 는
    #    assembler 의 source contract 로 계속 import(unresolved_fields 반환용) — 계약 파일 delta 0.
    #    source_facts 는 상한 없이 전량 전달하고 build_saas_leg_step1 이 _LEG_INPUT_FIELDS(103) 로
    #    필터한다. R8 축 등 source 에 값이 있으면 배선 상한 없이 build_facility 에 도달.
    #    construction_type synthetic 은 SaaS 에서 새로 만들지 않음 — source 있으면 전달, 없으면 ABSENT.
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        # WO-OBS009-MATERIAL-CANONICAL-RUNTIME-WIRING-PATCH-001: Common Material canonical
        # adapter fed via factory_id. READ FAILURE != EMPTY SOURCE — MaterialSourceLoadError
        # propagates fail-closed and LEG is NOT called on material read failure.
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
    )

    # D. 공식 Runtime Delegate 1회 (direct evaluate_rtm / master_building_legal_rules / v510 미사용).
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": CONTRACT_VERSION,
        "unresolved_fields": sorted(unresolved),
        "factory_id": factory_id,
    }
