"""WO-010 STEP-2A: unified LEG input contract core tests.

services.canonical.leg_input_contract.build_unified_leg_input 의 계약 검증.
T10(파일 delta 게이트) 는 pytest 밖의 git diff 게이트로 확인 — 이 파일 안 assert 대상 아님.
"""
from __future__ import annotations

import ast
import inspect

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from services.canonical import leg_input_contract as core
from services.canonical.leg_input_contract import build_unified_leg_input


PATCH2A_15_AXES = (
    "scaffold_height_m",
    "grinding_wheel_diameter_cm",
    "breathing_gas_cylinder_pressure_kgf_cm2",
    "structure_height_m",
    "object_drop_height_m",
    "construction_machine_weight_ton",
    "hazmat_designated_quantity_multiple",
    "rotor_peripheral_speed_m_s",
    "rotor_shaft_weight_ton",
    "same_site_construction_count",
    "diving_worker_count",
    "has_structure",
    "has_object_drop",
    "has_construction_machine",
    "has_high_speed_rotor",
)


def test_T1_vocabulary_len_and_distinct():
    """T1: len(_LEG_INPUT_FIELDS) == 103 && distinct == 103 (실측)."""
    assert len(_LEG_INPUT_FIELDS) == 103
    assert len(set(_LEG_INPUT_FIELDS)) == 103


def test_T2_no_second_vocabulary():
    """T2: NO SECOND VOCABULARY — _LEG_INPUT_FIELDS import 재사용 + 대형 리터럴 부재."""
    src = inspect.getsource(core)
    assert "_LEG_INPUT_FIELDS" in src, "must reference _LEG_INPUT_FIELDS"
    assert "from clients.leg_runtime_client import _LEG_INPUT_FIELDS" in src, (
        "must import _LEG_INPUT_FIELDS from clients.leg_runtime_client (single SoT)"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            str_elts = [
                e for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            assert len(str_elts) < 50, (
                "second vocabulary literal detected (>=50 str elements); "
                "must reuse _LEG_INPUT_FIELDS via import."
            )


def test_T3_value_preservation_false_and_zero_kept():
    """T3: VALUE PRESERVATION — false/0/원문 verbatim 보존."""
    facts = {
        "worker_count": "51",
        "total_floor_area": 11860.03,
        "has_scaffold": False,
        "diving_worker_count": 0,
    }
    body = build_unified_leg_input(sector="INDUSTRIAL", source_facts=facts)
    assert body.input == facts


def test_T4_unknown_absence_none_blank_whitespace():
    """T4: UNKNOWN — None/빈문자열/공백문자열 축은 input 키 부재."""
    facts = {
        "worker_count": None,
        "total_floor_area": "",
        "building_use_type": "   ",
        "has_scaffold": True,
    }
    body = build_unified_leg_input(sector="INDUSTRIAL", source_facts=facts)
    assert "worker_count" not in body.input
    assert "total_floor_area" not in body.input
    assert "building_use_type" not in body.input
    assert body.input.get("has_scaffold") is True


def test_T5_synthetic_ban_and_subset_of_allowlist():
    """T5: SYNTHETIC BAN — 400/1.0/"건축" 미생성 + input.keys ⊆ _LEG_INPUT_FIELDS."""
    facts = {"worker_count": 10, "has_scaffold": True}
    body = build_unified_leg_input(sector="CONSTRUCTION", source_facts=facts)
    assert "floor_area" not in body.input
    assert "contract_amount_eok" not in body.input
    assert "construction_type" not in body.input
    assert set(body.input.keys()).issubset(set(_LEG_INPUT_FIELDS))


def test_T6_same_facts_sector_label_independent():
    """T6: SAME FACTS — sector 라벨만 바꿔도 input dict 동일."""
    facts = {"worker_count": 10, "total_floor_area": 100.0, "has_scaffold": True}
    body_b = build_unified_leg_input(sector="BUILDING", source_facts=facts)
    body_i = build_unified_leg_input(sector="INDUSTRIAL", source_facts=facts)
    body_c = build_unified_leg_input(sector="CONSTRUCTION", source_facts=facts)
    assert body_b.input == body_i.input == body_c.input


def test_T7_sector_policy_delegated_to_build_facility():
    """T7: SECTOR POLICY — N1 gate 는 build_facility(무변경) 재사용."""
    facts = {"floor_count": 5, "worker_count": 10}
    sb = build_unified_leg_input(sector="BUILDING", source_facts=facts)
    assert "floor_count" in build_facility(sb)
    sb_i = build_unified_leg_input(sector="INDUSTRIAL", source_facts=facts)
    assert "floor_count" not in build_facility(sb_i)
    sb_c = build_unified_leg_input(sector="CONSTRUCTION", source_facts={"floor_count": 5})
    assert "floor_count" not in build_facility(sb_c)


def test_T8_patch2a_15_axes_accepted():
    """T8: PATCH-2A 15축 모두 input 수용."""
    facts = {
        "scaffold_height_m": 1.2,
        "grinding_wheel_diameter_cm": 20,
        "breathing_gas_cylinder_pressure_kgf_cm2": 100,
        "structure_height_m": 10.0,
        "object_drop_height_m": 3.0,
        "construction_machine_weight_ton": 5.5,
        "hazmat_designated_quantity_multiple": 2.0,
        "rotor_peripheral_speed_m_s": 40.0,
        "rotor_shaft_weight_ton": 1.0,
        "same_site_construction_count": 3,
        "diving_worker_count": 2,
        "has_structure": True,
        "has_object_drop": True,
        "has_construction_machine": True,
        "has_high_speed_rotor": True,
    }
    body = build_unified_leg_input(sector="CONSTRUCTION", source_facts=facts)
    for axis in PATCH2A_15_AXES:
        assert axis in body.input, "PATCH-2A axis {} missing".format(axis)
    assert sum(1 for k in body.input if k in PATCH2A_15_AXES) == 15


def test_T9_tai_api_only_no_leg_repo_import():
    """T9: tai-api only — 코어 모듈이 leg repo(leg_pipeline/leg_repository) 를 import 하지 않음."""
    src = inspect.getsource(core)
    assert "leg_pipeline" not in src
    assert "leg_repository" not in src
