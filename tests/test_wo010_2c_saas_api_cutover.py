"""WO-010 STEP-2C PR-A : SaaS API unified runtime cutover tests.

검증 범위:
  · T1  IND : final-cut(29 assert) 소스 제거 + build_saas_leg_step1 사용 확인
  · T2  IND EXISTING PARITY : OLD(canonical29 → build_facility) vs NEW(unified → build_facility) EXACT
  · T3  IND ACCEPTABLE : source_facts 에 R1 12축 명시 주입 시 build_facility 도달 12/12 (배선 상한 제거)
  · T4  CST EXISTING PARITY : OLD(canonical27 → build_facility) vs NEW(unified → build_facility) EXACT
  · T5  CST ACCEPTABLE : R8 11축 주입 시 도달 11/11 (배선 상한 제거)
  · T6  BLD EXISTING PARITY : OLD vs NEW facility EXACT · elevator None/0/1 · N1 gate 유지
  · T6b BLD ACCEPTABLE : R7 4축(SafeBuildingConsumerInput 통과) 주입 시 도달 4/4
  · T7  SAME FACTS parity : 동일 fact dict → 3 sector adapter 동일 sector 시 facility SAME
  · T8  worker51 3/3 · false/0 보존 · None ABSENT
  · T9  N1 firewall : floor_count 등 IND/CST 미도달
  · T10 계약파일 정적 delta 게이트(import 유지 + 심볼 stable)
  · T11 alias : IND has_chemical_substance→has_chemical / CST rename / BUILDING skip · 신규 alias 0

배선 상한 제거 검증(T3/T5/T6b) 은 GATE-0 정정 반영 : "source 가 실제로 있다" 를 증명하는 것이 아니라
"주입 시 상한이 안 자른다" 만 증명한다. source 없는 축은 여전히 ABSENT/UNRESOLVED 유지 (T8).
"""
from __future__ import annotations

import inspect
from typing import Any, Dict

import pytest

from clients.leg_runtime_client import (
    _BUILDING_N1_FIELDS,
    _LEG_CODE_TO_CONSUMER,
    _LEG_INPUT_FIELDS,
    build_facility,
)
from schemas.legal_engine import DiagnoseStep1Body
from services import safe_industrial_leg_runtime as ind_rt
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.safe_industrial_canonical_assembler import TARGET_FIELDS as IND_TARGET_FIELDS_29
from services.safe_construction_canonical_assembler import (
    TARGET_FIELDS as CST_TARGET_FIELDS_27,
    RUNTIME_INPUT_FIELDS as CST_RUNTIME_INPUT_FIELDS,
)


# ── R1 12 : IND 배선 상한 제거 후 도달 가능 대표 축(PATCH-2A 15 중 CST-only 3 제외) ──
R1_IND_12 = (
    "scaffold_height_m", "grinding_wheel_diameter_cm", "breathing_gas_cylinder_pressure_kgf_cm2",
    "structure_height_m", "object_drop_height_m", "hazmat_designated_quantity_multiple",
    "rotor_peripheral_speed_m_s", "rotor_shaft_weight_ton", "diving_worker_count",
    "has_structure", "has_object_drop", "has_high_speed_rotor",
)
R1_IND_12_VALUES: Dict[str, Any] = {
    "scaffold_height_m": 1.2, "grinding_wheel_diameter_cm": 20,
    "breathing_gas_cylinder_pressure_kgf_cm2": 100, "structure_height_m": 10.0,
    "object_drop_height_m": 3.0, "hazmat_designated_quantity_multiple": 2.0,
    "rotor_peripheral_speed_m_s": 40.0, "rotor_shaft_weight_ton": 1.0,
    "diving_worker_count": 2, "has_structure": True, "has_object_drop": True,
    "has_high_speed_rotor": True,
}

# ── R8 11 : CST 배선 상한 제거 후 도달 가능 대표 축(canonical27/RUNTIME20 밖 + _LEG_INPUT_FIELDS 안) ──
R8_CST_11 = (
    "construction_machine_weight_ton", "same_site_construction_count", "has_construction_machine",
    "scaffold_height_m", "structure_height_m", "object_drop_height_m", "diving_worker_count",
    "has_structure", "has_object_drop", "has_high_speed_rotor", "has_asbestos_demo",
)
R8_CST_11_VALUES: Dict[str, Any] = {
    "construction_machine_weight_ton": 5.5, "same_site_construction_count": 3,
    "has_construction_machine": True, "scaffold_height_m": 1.2, "structure_height_m": 10.0,
    "object_drop_height_m": 3.0, "diving_worker_count": 2, "has_structure": True,
    "has_object_drop": True, "has_high_speed_rotor": True, "has_asbestos_demo": True,
}

# ── R7 4 : BLD 배선 상한 제거 후 도달 가능 대표 축(SafeBuildingConsumerInput 통과 + _LEG_INPUT_FIELDS 안) ──
R7_BLD_4 = (
    "building_height_m", "cantilever_projection_m", "has_flat_plate_structure",
    "is_collapse_risk_land",
)
R7_BLD_4_VALUES: Dict[str, Any] = {
    "building_height_m": 65.0, "cantilever_projection_m": 1.5,
    "has_flat_plate_structure": True, "is_collapse_risk_land": False,
}


def _facility_diff(old, new):
    o_k, n_k = set(old), set(new)
    added = n_k - o_k
    removed = o_k - n_k
    changed = {k for k in (o_k & n_k) if old[k] != new[k]}
    return added, removed, changed


# ─────────────────────────────────────────────────────────────────────────
# T1: IND final-cut(29 assert) 소스 제거 + build_saas_leg_step1 배선
# ─────────────────────────────────────────────────────────────────────────
def test_T1_ind_runtime_uses_unified_adapter():
    src = inspect.getsource(ind_rt)
    assert "assert len(values) == 29" not in src, "canonical29 final-cut 잔존 (assert 문)"
    assert "build_saas_leg_step1" in src, "build_saas_leg_step1 배선 없음"
    assert (
        "from services.canonical.saas_leg_source_adapter import build_saas_leg_step1" in src
    ), "adapter import 부재"
    # DiagnoseStep1Body 직접 구성이 사라졌는지 (import 도 제거)
    assert "from schemas.legal_engine import DiagnoseStep1Body" not in src, (
        "DiagnoseStep1Body import 잔존 — adapter 경유로 대체됐어야 한다"
    )


def test_T1b_cst_runtime_uses_unified_adapter():
    from services import safe_construction_leg_runtime as cst_rt
    src = inspect.getsource(cst_rt)
    assert "assert len(values) == 27" not in src
    assert "build_saas_leg_step1" in src
    assert (
        "from services.canonical.saas_leg_source_adapter import build_saas_leg_step1" in src
    )


def test_T1c_bld_runtime_uses_unified_adapter():
    from services import safe_building_leg_runtime as bld_rt
    src = inspect.getsource(bld_rt)
    assert "build_saas_leg_step1" in src
    assert (
        "from services.canonical.saas_leg_source_adapter import build_saas_leg_step1" in src
    )


# ─────────────────────────────────────────────────────────────────────────
# T2: IND EXISTING PARITY (OLD 29-cut vs NEW unified) — facility EXACT
# ─────────────────────────────────────────────────────────────────────────
def _ind_asset_values_29(**over):
    """canonical29 EXACT dict — None 슬롯 포함."""
    values = {f: None for f in IND_TARGET_FIELDS_29}
    values.update({
        "worker_count": 51,
        "total_floor_area": 11860.03,
        "ksic_major": "24",
        "building_use_type": "제조업",
        "has_chemical_substance": True,
        "has_boiler": False,
        "has_safety_manager": True,
        "gas_capacity_kg": 0,        # 0 보존
        "has_high_pressure_gas": False,
    })
    values.update(over)
    return values


def test_T2_ind_existing_parity():
    values = _ind_asset_values_29()
    # OLD : 원 계약(canonical29 body.input 통째로) → build_facility
    old_step1 = DiagnoseStep1Body(factory_id="F1", sector="INDUSTRIAL", input=dict(values))
    old = build_facility(old_step1)
    # NEW : STEP-2C unified adapter → build_facility
    new_step1 = build_saas_leg_step1(sector="INDUSTRIAL", source_facts=dict(values), factory_id="F1")
    new = build_facility(new_step1)
    added, removed, changed = _facility_diff(old, new)
    assert removed == set() and changed == set(), (
        "IND EXISTING PARITY 위반. added={} removed={} changed={}".format(added, removed, changed)
    )
    # ADDED 는 원 IND 경로에서 안 잡히던 축이 새로 도달 가능해진 것 : has_chemical alias 승격 등.
    #   기존 도달축(removed=0, changed=0) 은 EXACT 유지 확인.


# ─────────────────────────────────────────────────────────────────────────
# T3: IND ACCEPTABLE — R1 12축 명시 주입 시 12/12 도달 (배선 상한 제거)
# ─────────────────────────────────────────────────────────────────────────
def test_T3_ind_r1_12_axes_reach_facility():
    # 상한(29) 이 있었다면 R1 축들은 canonical29 밖이라 절단됐을 것.
    # STEP-2C 는 상한 제거로 주입 시 build_facility 도달을 허용한다.
    values = _ind_asset_values_29(**R1_IND_12_VALUES)
    step1 = build_saas_leg_step1(sector="INDUSTRIAL", source_facts=values, factory_id="F1")
    fac = build_facility(step1)
    missing = [a for a in R1_IND_12 if a not in fac]
    assert not missing, "IND R1 12축 미도달 : {}".format(missing)
    for a in R1_IND_12:
        assert fac[a] == R1_IND_12_VALUES[a], "{} 값 EXACT 아님".format(a)


# ─────────────────────────────────────────────────────────────────────────
# T4: CST EXISTING PARITY
# ─────────────────────────────────────────────────────────────────────────
def _cst_values_27(**over):
    values = {f: None for f in CST_TARGET_FIELDS_27}
    values.update({
        "has_excavation": True,
        "has_scaffold": False,
        "has_chemical_substance": True,
        "worker_count": 20,
    })
    values.update(over)
    return values


def test_T4_cst_existing_parity():
    values = _cst_values_27()
    # OLD : canonical27 body.input 통째로 → build_facility(sector="CONSTRUCTION")
    old_step1 = DiagnoseStep1Body(factory_id="F1", sector="CONSTRUCTION", input=dict(values))
    old = build_facility(old_step1)
    # NEW : STEP-2C unified adapter → build_facility
    new_step1 = build_saas_leg_step1(sector="CONSTRUCTION", source_facts=dict(values), factory_id="F1")
    new = build_facility(new_step1)
    added, removed, changed = _facility_diff(old, new)
    assert removed == set() and changed == set(), (
        "CST EXISTING PARITY 위반. added={} removed={} changed={}".format(added, removed, changed)
    )


# ─────────────────────────────────────────────────────────────────────────
# T5: CST ACCEPTABLE — R8 11축 주입 시 도달 11/11
# ─────────────────────────────────────────────────────────────────────────
def test_T5_cst_r8_11_axes_reach_facility():
    values = _cst_values_27(**R8_CST_11_VALUES)
    step1 = build_saas_leg_step1(sector="CONSTRUCTION", source_facts=values, factory_id="F1")
    fac = build_facility(step1)
    missing = [a for a in R8_CST_11 if a not in fac]
    assert not missing, "CST R8 11축 미도달 : {}".format(missing)
    for a in R8_CST_11:
        assert fac[a] == R8_CST_11_VALUES[a], "{} 값 EXACT 아님".format(a)


# ─────────────────────────────────────────────────────────────────────────
# T6: BLD EXISTING PARITY
# ─────────────────────────────────────────────────────────────────────────
def _bld_values(**over):
    """OWNED_EXACT 3 + SafeBuildingConsumerInput 대표값."""
    values = {
        "floor_count": 12,
        "has_boiler": False,
        "is_multi_use": True,
        "worker_count": 51,
        "total_floor_area": 11860.03,
        "building_use_type": "업무시설",
        "has_chemical_substance": True,
    }
    values.update(over)
    return values


def test_T6_bld_existing_parity():
    values = _bld_values()
    old_step1 = DiagnoseStep1Body(factory_id="F1", sector="BUILDING", input=dict(values))
    old = build_facility(old_step1)
    new_step1 = build_saas_leg_step1(sector="BUILDING", source_facts=dict(values), factory_id="F1")
    new = build_facility(new_step1)
    added, removed, changed = _facility_diff(old, new)
    assert removed == set() and changed == set(), (
        "BLD EXISTING PARITY 위반. added={} removed={} changed={}".format(added, removed, changed)
    )
    # BLD 는 alias 승격 스킵 규약이라 has_chemical 신규 생성 없어야 함.
    assert "has_chemical" not in new, "BUILDING alias 승격 스킵 규약 위반 (has_chemical 신규)"


@pytest.mark.parametrize("elev,expected", [
    (None, None), (0, False), (1, True), (3, True),
])
def test_T6b_bld_elevator_derived(elev, expected):
    """elevator_count derived : None→ABSENT / 0→false / 1→true (cutover 전후 EXACT)."""
    values = _bld_values()
    if elev is not None:
        values["elevator_count"] = elev
    step1 = build_saas_leg_step1(sector="BUILDING", source_facts=values, factory_id="F1")
    fac = build_facility(step1)
    if expected is None:
        assert "has_building_elevator" not in fac
    else:
        assert fac.get("has_building_elevator") is expected


def test_T6c_bld_r7_4_axes_reach_facility():
    """R7 4축 주입(SafeBuildingConsumerInput schema 를 통과하는 대표축) 시 build_facility 4/4 도달."""
    values = _bld_values(**R7_BLD_4_VALUES)
    step1 = build_saas_leg_step1(sector="BUILDING", source_facts=values, factory_id="F1")
    fac = build_facility(step1)
    missing = [a for a in R7_BLD_4 if a not in fac]
    assert not missing, "BLD R7 4축 미도달 : {}".format(missing)
    for a in R7_BLD_4:
        assert fac[a] == R7_BLD_4_VALUES[a]


# ─────────────────────────────────────────────────────────────────────────
# T7: SAME FACTS parity — 동일 fact dict, 동일 sector → facility SAME
# ─────────────────────────────────────────────────────────────────────────
def test_T7_same_facts_same_sector_produces_same_facility():
    facts = {"worker_count": 10, "has_scaffold": True, "scaffold_height_m": 1.5}
    fac_ind_1 = build_facility(build_saas_leg_step1(sector="INDUSTRIAL", source_facts=dict(facts)))
    fac_ind_2 = build_facility(build_saas_leg_step1(sector="INDUSTRIAL", source_facts=dict(facts)))
    assert fac_ind_1 == fac_ind_2

    fac_cst_1 = build_facility(build_saas_leg_step1(sector="CONSTRUCTION", source_facts=dict(facts)))
    fac_cst_2 = build_facility(build_saas_leg_step1(sector="CONSTRUCTION", source_facts=dict(facts)))
    assert fac_cst_1 == fac_cst_2

    fac_bld_1 = build_facility(build_saas_leg_step1(sector="BUILDING", source_facts=dict(facts)))
    fac_bld_2 = build_facility(build_saas_leg_step1(sector="BUILDING", source_facts=dict(facts)))
    assert fac_bld_1 == fac_bld_2


# ─────────────────────────────────────────────────────────────────────────
# T8: worker51 3/3 + false/0 보존 + None ABSENT
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sector", ["INDUSTRIAL", "CONSTRUCTION", "BUILDING"])
def test_T8_worker51_3sectors(sector):
    step1 = build_saas_leg_step1(sector=sector, source_facts={"worker_count": 51}, factory_id="F1")
    fac = build_facility(step1)
    assert fac.get("worker_count") == 51, "{} worker51 미도달".format(sector)


def test_T8_zero_false_absent_contract():
    facts = {"worker_count": 0, "has_boiler": False, "gas_capacity_kg": 0, "has_scaffold": False}
    step1 = build_saas_leg_step1(sector="INDUSTRIAL", source_facts=facts, factory_id="F1")
    fac = build_facility(step1)
    assert fac.get("worker_count") == 0
    assert fac.get("has_boiler") is False
    assert fac.get("gas_capacity_kg") == 0
    assert fac.get("has_scaffold") is False
    # 미제공은 발명되지 않는다
    assert "has_press" not in fac
    assert "has_conveyor" not in fac
    assert "has_emergency_gen" not in fac


def test_T8_none_absent():
    facts = {"worker_count": 51, "has_scaffold": None, "total_floor_area": None}
    step1 = build_saas_leg_step1(sector="INDUSTRIAL", source_facts=facts, factory_id="F1")
    fac = build_facility(step1)
    assert fac.get("worker_count") == 51
    assert "has_scaffold" not in fac
    assert "total_floor_area" not in fac


# ─────────────────────────────────────────────────────────────────────────
# T9: N1 firewall — floor_count 등 IND/CST 미도달
# ─────────────────────────────────────────────────────────────────────────
def test_T9_n1_firewall_ind_cst():
    facts = {
        "worker_count": 10,
        "floor_count": 7,
        "building_height_m": 21.0,
        "cantilever_projection_m": 1.5,
        "has_flat_plate_structure": True,
    }
    for sector in ("INDUSTRIAL", "CONSTRUCTION"):
        step1 = build_saas_leg_step1(sector=sector, source_facts=dict(facts), factory_id="F1")
        fac = build_facility(step1)
        for k in ("floor_count", "building_height_m", "cantilever_projection_m", "has_flat_plate_structure"):
            assert k not in fac, "{} N1 firewall 파괴 : {} 유입".format(sector, k)


def test_T9_n1_reach_bld():
    """BLD 는 N1 축 도달 허용."""
    facts = {
        "worker_count": 10, "floor_count": 7, "building_height_m": 21.0,
        "cantilever_projection_m": 1.5, "has_flat_plate_structure": True,
    }
    step1 = build_saas_leg_step1(sector="BUILDING", source_facts=dict(facts), factory_id="F1")
    fac = build_facility(step1)
    for k in ("floor_count", "building_height_m", "cantilever_projection_m", "has_flat_plate_structure"):
        assert fac.get(k) == facts[k], "BLD N1 축 {} 미도달".format(k)


# ─────────────────────────────────────────────────────────────────────────
# T10: 계약 파일 정적 delta 게이트 (import 유지 + 심볼 stable)
# ─────────────────────────────────────────────────────────────────────────
def test_T10_contract_files_still_importable_and_stable():
    from clients import leg_runtime_client as m_leg
    from services.canonical import leg_input_contract as m_core
    from services.canonical import industrial_www as m_iw
    from services import safe_industrial_canonical_assembler as m_ind_asm
    from services import safe_construction_canonical_assembler as m_cst_asm
    import schemas.legal_engine as m_sch

    assert len(m_leg._LEG_INPUT_FIELDS) == 103
    assert len(m_leg._BUILDING_N1_FIELDS) == 32
    assert m_leg._LEG_CODE_TO_CONSUMER == {
        "has_chemical": "has_chemical_substance",
        "has_high_place_work": "has_high_work",
    }
    assert hasattr(m_core, "build_unified_leg_input")
    assert hasattr(m_iw, "build_industrial_www_step1")
    assert len(m_ind_asm.TARGET_FIELDS) == 29
    assert len(m_cst_asm.TARGET_FIELDS) == 27
    assert len(m_cst_asm.RUNTIME_INPUT_FIELDS) == 20
    assert hasattr(m_sch, "DiagnoseStep1Body")
    assert hasattr(m_sch, "SafeIndustrialConsumerInput")
    assert hasattr(m_sch, "SafeConstructionConsumerInput")
    assert hasattr(m_sch, "SafeBuildingConsumerInput")


# ─────────────────────────────────────────────────────────────────────────
# T11: alias — IND/CST/BLD alias regression + 신규 alias 0
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("hcs", [True, False])
def test_T11_ind_chemical_alias(hcs):
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL", source_facts={"worker_count": 10, "has_chemical_substance": hcs},
    )
    fac = build_facility(step1)
    assert fac.get("has_chemical") is hcs
    assert "has_chemical_substance" not in fac   # IND rename 없음


@pytest.mark.parametrize("hcs", [True, False])
def test_T11_cst_chemical_rename(hcs):
    step1 = build_saas_leg_step1(
        sector="CONSTRUCTION", source_facts={"worker_count": 10, "has_chemical_substance": hcs},
    )
    fac = build_facility(step1)
    assert fac.get("has_chemical_substance") is hcs
    assert "has_chemical" not in fac   # CST rename 후 has_chemical 잔존 금지


@pytest.mark.parametrize("hcs", [True, False])
def test_T11_bld_chemical_exact_key(hcs):
    """BLD : has_chemical_substance 는 patch-A exact-key 로 반영. has_chemical 승격 없음."""
    step1 = build_saas_leg_step1(
        sector="BUILDING", source_facts={"worker_count": 10, "has_chemical_substance": hcs},
    )
    fac = build_facility(step1)
    assert fac.get("has_chemical_substance") is hcs
    assert "has_chemical" not in fac, "BLD alias 승격 스킵 규약 위반"


def test_T11_no_new_alias_registered():
    assert _LEG_CODE_TO_CONSUMER == {
        "has_chemical": "has_chemical_substance",
        "has_high_place_work": "has_high_work",
    }
