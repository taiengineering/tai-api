"""WO-E2E-OBJ-SEM-001-IMPLEMENT-REV1-PATCH1 — subcontractor_work_types source expansion tests (A~L).

expansion 은 has_subcontractor=true + non-empty valid-enum array 일 때만 domain boolean 생성.
absent/empty/unknown/malformed/parent-false → 둘 다 ABSENT (법적 "해당없음" 확정 금지).
"""
import copy
import pytest

from services.canonical.subcontractor_source_expansion import expand_subcontractor_work_types


def _has(r):
    return ("has_fire_facility_subcontract" in r, "has_ict_subcontract" in r)


def test_a_key_absent_both_absent():
    r = expand_subcontractor_work_types({"has_subcontractor": True, "worker_count": 10})
    assert _has(r) == (False, False)


def test_b_parent_false_stale_array_both_absent():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": False, "subcontractor_work_types": ["FIRE_FACILITY"]})
    assert _has(r) == (False, False)


def test_c_empty_array_both_absent():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": []})
    assert _has(r) == (False, False)


def test_d_malformed_scalar_both_absent():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": "FIRE_FACILITY"})
    assert _has(r) == (False, False)


def test_e_unknown_token_both_absent():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY", "INVALID_X"]})
    assert _has(r) == (False, False)


def test_f_general_only_fire_false_ict_false():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": ["GENERAL_CONSTRUCTION"]})
    assert r["has_fire_facility_subcontract"] is False
    assert r["has_ict_subcontract"] is False


def test_g_fire_true_ict_false():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY"]})
    assert r["has_fire_facility_subcontract"] is True
    assert r["has_ict_subcontract"] is False


def test_h_ict_false_true():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": ["ICT"]})
    assert r["has_fire_facility_subcontract"] is False
    assert r["has_ict_subcontract"] is True


def test_i_fire_ict_both_true():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY", "ICT"]})
    assert r["has_fire_facility_subcontract"] is True
    assert r["has_ict_subcontract"] is True


def test_j_other_false_false():
    r = expand_subcontractor_work_types(
        {"has_subcontractor": True, "subcontractor_work_types": ["OTHER"]})
    assert r["has_fire_facility_subcontract"] is False
    assert r["has_ict_subcontract"] is False


def test_k_input_mutation_zero():
    src = {"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY"]}
    snap = copy.deepcopy(src)
    expand_subcontractor_work_types(src)
    assert src == snap  # 원본 mutation 0


def test_l_reaches_unified_leg_input_as_two_bools():
    """build_unified_leg_input 까지 2 bool exact 도달 (expansion → LEG vocabulary allowlist 통과)."""
    from services.canonical.leg_input_contract import build_unified_leg_input
    body = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": True,
                      "subcontractor_work_types": ["FIRE_FACILITY", "ICT"]},
    )
    inp = body.input
    assert inp.get("has_fire_facility_subcontract") is True
    assert inp.get("has_ict_subcontract") is True
    # work_types 자체는 LEG vocabulary 가 아니므로 unified 에 없음
    assert "subcontractor_work_types" not in inp


def test_l2_absent_case_no_domain_keys_in_unified():
    """empty array → domain key 미도달 (LEG 에 fire/ict 안 감)."""
    from services.canonical.leg_input_contract import build_unified_leg_input
    body = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": True, "subcontractor_work_types": []},
    )
    assert "has_fire_facility_subcontract" not in body.input
    assert "has_ict_subcontract" not in body.input
