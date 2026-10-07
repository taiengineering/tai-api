"""WO-DUAL-CST-STEP2-IMPLEMENT-001 GATE-1 — SAFE CONSTRUCTION 공식 LEG 진입.

경로: assemble_construction_marketing_contract(SAFE 자산 READ) -> canonical27
      -> consumer override(RUNTIME20, non-null) -> CST process projection(SEM-P0-01A-R4)
      -> DiagnoseStep1Body(sector="CONSTRUCTION", input=values)
      -> run_leg_diagnosis(공식 Runtime Delegate: build_facility -> /rtm/evaluate -> full_result).

산업 GATE-4A(run_safe_industrial_leg)와 대칭. canonical denominator 27 불변.
override allowlist = RUNTIME_INPUT_FIELDS(20). subcontractor_count 는 override 대상 아님
(CANONICAL_UNRESOLVED, LEG passthrough 아님 — VERIFIER CORRECTION).
DB WRITE 0(READ-ONLY LEG diagnosis). factory 생성 side effect 0.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from services.safe_construction_canonical_assembler import (
    assemble_construction_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION,
    RUNTIME_INPUT_FIELDS,
)
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.leg_diagnosis_svc import run_leg_diagnosis
from services.cst_process_projector import project_cst_process_codes, project_cst_work_codes


class ConstructionSiteBridgeError(Exception):
    """site 에 factory_id 연결이 없을 때(진단 중 factory 생성 금지 — fail-closed)."""


class ConstructionProcessSourceLoadError(RuntimeError):
    """CST process source DB/query failure. Must not be treated as empty source."""

    code = "CST_PROCESS_SOURCE_UNAVAILABLE"

    def __init__(self, message: str, *, site_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.site_id = site_id


class ConstructionWorkSourceLoadError(RuntimeError):
    """CST work source DB/query failure. Must not be treated as empty source."""

    code = "CST_WORK_SOURCE_UNAVAILABLE"

    def __init__(self, message: str, *, site_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.site_id = site_id


def _load_site_process_work_type_codes(supabase, site_id: str) -> List[str]:
    """Read active kcsc_process_master.work_type_code values for the site.

    Fail-closed: raises ConstructionProcessSourceLoadError on any DB failure.
    Returns [] when the site has no active process rows (valid empty case).
    """
    if supabase is None:
        raise ConstructionProcessSourceLoadError(
            "CST process source client missing", site_id=site_id
        )
    try:
        _proc_res = (
            supabase.table("construction_site_processes")
            .select("kcsc_process_id")
            .eq("site_id", site_id)
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        raise ConstructionProcessSourceLoadError(
            f"construction_site_processes 조회 실패: {exc}", site_id=site_id
        ) from exc
    _proc_data = getattr(_proc_res, "data", None)
    if not isinstance(_proc_data, list):
        raise ConstructionProcessSourceLoadError(
            "construction_site_processes 응답 형식 오류", site_id=site_id
        )
    proc_rows: list = _proc_data

    process_ids = [r["kcsc_process_id"] for r in proc_rows if r.get("kcsc_process_id")]
    if not process_ids:
        return []

    try:
        _master_res = (
            supabase.table("kcsc_process_master")
            .select("work_type_code")
            .in_("id", process_ids)
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        raise ConstructionProcessSourceLoadError(
            f"kcsc_process_master 조회 실패: {exc}", site_id=site_id
        ) from exc
    _master_data = getattr(_master_res, "data", None)
    if not isinstance(_master_data, list):
        raise ConstructionProcessSourceLoadError(
            "kcsc_process_master 응답 형식 오류", site_id=site_id
        )
    master_rows: list = _master_data

    return [r["work_type_code"] for r in master_rows if r.get("work_type_code")]


def _load_site_work_type_codes(supabase, site_id: str) -> List[str]:
    """Read active kcsc_work_master.work_type_code values for the site.

    Fail-closed: raises ConstructionWorkSourceLoadError on any DB failure.
    Returns [] when the site has no active work rows (valid empty case).
    """
    if supabase is None:
        raise ConstructionWorkSourceLoadError(
            "CST work source client missing", site_id=site_id
        )
    try:
        _work_res = (
            supabase.table("construction_works")
            .select("work_master_id")
            .eq("site_id", site_id)
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        raise ConstructionWorkSourceLoadError(
            f"construction_works 조회 실패: {exc}", site_id=site_id
        ) from exc
    _work_data = getattr(_work_res, "data", None)
    if not isinstance(_work_data, list):
        raise ConstructionWorkSourceLoadError(
            "construction_works 응답 형식 오류", site_id=site_id
        )
    work_rows: list = _work_data

    work_master_ids = [r["work_master_id"] for r in work_rows if r.get("work_master_id")]
    if not work_master_ids:
        return []

    try:
        _master_res = (
            supabase.table("kcsc_work_master")
            .select("work_type_code")
            .in_("id", work_master_ids)
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        raise ConstructionWorkSourceLoadError(
            f"kcsc_work_master 조회 실패: {exc}", site_id=site_id
        ) from exc
    _master_data = getattr(_master_res, "data", None)
    if not isinstance(_master_data, list):
        raise ConstructionWorkSourceLoadError(
            "kcsc_work_master 응답 형식 오류", site_id=site_id
        )
    master_rows: list = _master_data

    return [r["work_type_code"] for r in master_rows if r.get("work_type_code")]


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


def run_safe_construction_leg(
    supabase,
    site_id: str,
    consumer_input,
    subcontract_legal_event_id: Optional[str] = None,
) -> Dict[str, Any]:
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

    # B-prime. CST process projection (SEM-P0-01A-R4 — performs_confined_space_work,
    #   performs_electrical_work). READ-ONLY. DB failure raises ConstructionProcessSourceLoadError
    #   (fail-closed — LEG is NOT called on source read failure).
    cst_codes = _load_site_process_work_type_codes(supabase, site_id)
    cst_facts = project_cst_process_codes(cst_codes)
    for field, val in cst_facts.items():
        values[field] = val
        provenance[field] = {"mode": "CST_PROCESS_PROJECTION", "source": "kcsc_process_master"}
        unresolved.discard(field)

    # B-prime-prime. CST work projection (BLK-009 — has_blasting).
    #   READ-ONLY. DB failure raises ConstructionWorkSourceLoadError
    #   (fail-closed — LEG is NOT called on source read failure).
    work_codes = _load_site_work_type_codes(supabase, site_id)
    work_facts = project_cst_work_codes(work_codes)
    for field, val in work_facts.items():
        values[field] = val
        provenance[field] = {"mode": "CST_WORK_PROJECTION", "source": "kcsc_work_master"}
        unresolved.discard(field)

    # B-prime-prime-prime. Subcontract legal event facts (S02-L2, EXISTING_SOURCE_FACT)
    if subcontract_legal_event_id:
        from services.subcontract_legal_event_source.store import get_event
        from services.subcontract_legal_event_source.canonical_adapter import (
            project_confirmed_event, get_event_provenance
        )
        try:
            event_row = get_event(supabase, subcontract_legal_event_id)
            # Identity check: event must belong to same site
            if str(event_row.get("site_id", "")) != str(site_id):
                # Wrong site — fail-closed: do not merge
                pass
            else:
                event_facts = project_confirmed_event(event_row)
                if event_facts:
                    prov = get_event_provenance(event_row)
                    for field, val in event_facts.items():
                        values[field] = val
                        provenance[field] = prov
                        unresolved.discard(field)
        except Exception:
            # DB error = fail-closed (do not silently ignore with empty)
            raise

    # C. WO-010 STEP-2C : canonical27 final-cut 제거. TARGET_FIELDS / RUNTIME_INPUT_FIELDS 는
    #    assembler 의 source contract 로 계속 import(unresolved_fields 반환용) — 계약 파일 delta 0.
    #    source_facts 는 상한 없이 전량 전달하고 build_saas_leg_step1 이 _LEG_INPUT_FIELDS(103) 로
    #    필터한다. R8 축 등 source 에 값이 있으면 배선 상한 없이 build_facility 에 도달.
    #    construction_type synthetic 은 SaaS 에서 새로 만들지 않음 — source 있으면 전달, 없으면 ABSENT.
    from services.work_source.store import load_work_rows_optional
    from services.material_source.store import load_factory_material_rows_optional
    from services.equipment_source.store import load_equipment_rows_optional
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION",
        source_facts=values,
        factory_id=factory_id,
        work_rows=load_work_rows_optional(supabase, factory_id),
        # WO-OBS009-MATERIAL-CANONICAL-RUNTIME-WIRING-PATCH-001: Common Material canonical
        # adapter fed via factory_id. READ FAILURE != EMPTY SOURCE — MaterialSourceLoadError
        # propagates fail-closed and LEG is NOT called on material read failure.
        material_rows=load_factory_material_rows_optional(supabase, factory_id),
        # WO-EQUIPMENT-A2-REMAINING-CONSUMER-PARITY-IMPLEMENT-001:
        # Equipment A2 shared seam — same reader/projector as MANUFACTURING (PR #450).
        # READ FAILURE != EMPTY SOURCE — EquipmentSourceLoadError propagates fail-closed.
        equipment_rows=load_equipment_rows_optional(supabase, factory_id),
    )

    # D. 공식 Runtime Delegate 1회 (direct evaluate_rtm / master_building_legal_rules / v510 미사용).
    full_result = run_leg_diagnosis(step1)

    return {
        "full_result": full_result,
        "contract_version": CONTRACT_VERSION,
        "unresolved_fields": sorted(unresolved),
        "factory_id": factory_id,
    }
