"""WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 STEP5 — CONSTRUCTION canonical 27 → LEG handoff 검증.

실제 clients.leg_runtime_client.build_facility 를 사용하고 evaluate_rtm 만 monkeypatch 한다.
자체 fake build_facility 로 통과시키지 않는다(WO §20).
"""
import inspect

import pytest

from clients import leg_runtime_client
import services.safe_construction_leg_handoff as H


CANON_C5 = ["work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
            "has_manual_heavy_handling", "manual_handling_weight_kg"]
E15 = ["worker_count", "has_excavation", "has_demolition", "has_tower_crane",
       "has_confined_space", "has_asbestos_demo", "has_blasting", "has_diving",
       "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
       "has_water_tank", "is_energy_intensive", "is_multi_use"]


def _contract(values, unresolved=None):
    return {
        "contract_version": "MKT_CST_PAID_CONTRACT_V1",
        "sector": "CONSTRUCTION",
        "site_id": "site-1",
        "values": dict(values),
        "unresolved_fields": list(unresolved or []),
        "provenance": {},
    }


class _Spy:
    def __init__(self, ret):
        self.calls = []
        self.ret = ret

    def __call__(self, facility, **kw):
        self.calls.append(facility)
        return self.ret


def _patch_eval(monkeypatch, ret=None):
    spy = _Spy(ret if ret is not None else {"status": "OK", "obligations": []})
    monkeypatch.setattr(leg_runtime_client, "evaluate_rtm", spy)
    return spy


# H5-01 values only source
def test_H5_01_values_only_source():
    fac = H.build_construction_leg_facility(_contract({"construction_type": "건축"}))
    assert fac.get("construction_type") == "건축"


# H5-02 sector CONSTRUCTION
def test_H5_02_sector_construction():
    assert H.SECTOR == "CONSTRUCTION"
    a = H._CanonicalStep1Adapter({"x": 1})
    assert a.sector == "CONSTRUCTION"


# H5-03 uses existing build_facility (not faked)
def test_H5_03_uses_existing_build_facility():
    vals = {"construction_type": "토목", "has_subcontractor": True}
    fac = H.build_construction_leg_facility(_contract(vals))
    # 동일 함수 재사용 증명: 실제 build_facility 를 동일 adapter 로 호출한 결과와 일치
    expected = leg_runtime_client.build_facility(H._CanonicalStep1Adapter(vals))
    assert fac == expected
    # handoff 소스가 leg_runtime_client 를 import 해 사용
    assert "leg_runtime_client" in inspect.getsource(H)


# H5-04 no new allowlist  H5-05 no new alias  H5-06 no new default
def test_H5_04_05_06_no_new_allowlist_alias_default():
    src = inspect.getsource(H)
    # 자체 allowlist/alias 표를 "정의(할당)"하지 않음 (docstring 언급은 허용).
    assert "_LEG_INPUT_FIELDS = " not in src         # 자체 allowlist 정의 없음
    assert "_LEG_CODE_TO_CONSUMER = " not in src     # 자체 alias 표 정의 없음
    assert "_FIELD_MAP = " not in src
    # facility 는 오직 build_facility allowlist 키만 → canonical-only 키(process_list 등) 미포함
    fac = H.build_construction_leg_facility(_contract({
        "construction_type": "건축", "process_list": [{"name": "x", "hazard_codes": []}],
        "subcontractor": [{"company_name": "A"}], "subcontractor_count": 3,
        "project_amount": 150, "project_address": "서울",
    }))
    for k in ("process_list", "subcontractor", "subcontractor_count", "project_amount", "project_address"):
        assert k not in fac


# H5-07 construction_type 전달
def test_H5_07_construction_type():
    fac = H.build_construction_leg_facility(_contract({"construction_type": "공통"}))
    assert fac["construction_type"] == "공통"


# H5-08/09 has_subcontractor false/true 보존
def test_H5_08_has_subcontractor_false():
    fac = H.build_construction_leg_facility(_contract({"has_subcontractor": False}))
    assert fac["has_subcontractor"] is False


def test_H5_09_has_subcontractor_true():
    fac = H.build_construction_leg_facility(_contract({"has_subcontractor": True}))
    assert fac["has_subcontractor"] is True


# H5-10 work_height_m=0 보존  H5-11 numeric value 그대로
def test_H5_10_work_height_zero_preserved():
    fac = H.build_construction_leg_facility(_contract({"work_height_m": 0}))
    assert fac["work_height_m"] == 0


def test_H5_11_numeric_value_passthrough():
    fac = H.build_construction_leg_facility(_contract({"work_height_m": 3.5, "manual_handling_weight_kg": 25}))
    assert fac["work_height_m"] == 3.5 and fac["manual_handling_weight_kg"] == 25


# H5-12 canonical None 미전달
def test_H5_12_none_omitted():
    fac = H.build_construction_leg_facility(_contract({"construction_type": None, "work_height_m": None}))
    assert "construction_type" not in fac and "work_height_m" not in fac


# H5-13 E15 None → facility 미포함
def test_H5_13_e15_none_absent():
    vals = {f: None for f in E15}
    vals["construction_type"] = "건축"
    fac = H.build_construction_leg_facility(_contract(vals))
    for f in E15:
        assert f not in fac


# H5-14/15 primitive derivation 0
def test_H5_14_process_list_no_derivation():
    fac = H.build_construction_leg_facility(_contract({
        "process_list": [{"name": "굴착", "hazard_codes": ["추락"]}],
    }))
    assert "process_list" not in fac
    assert "has_excavation" not in fac  # process → E flag 파생 없음


def test_H5_15_subcontractor_no_derivation():
    fac = H.build_construction_leg_facility(_contract({
        "subcontractor": [{"company_name": "A", "work_scope": "철근", "worker_count": 3, "safety_manager": "있음"}],
        "subcontractor_count": 1,
    }))
    assert "subcontractor" not in fac and "subcontractor_count" not in fac


# H5-16 existing CONSTRUCTION chemical sector behavior 재사용
def test_H5_16_construction_chemical_sector_behavior():
    # has_chemical_substance non-null → build_facility(CONSTRUCTION gate)가 exact-name 으로 교정
    fac = H.build_construction_leg_facility(_contract({"has_chemical_substance": True}))
    assert fac.get("has_chemical_substance") is True
    assert "has_chemical" not in fac
    # 동일성: 실제 build_facility 결과와 exact 일치
    expected = leg_runtime_client.build_facility(H._CanonicalStep1Adapter({"has_chemical_substance": True}))
    assert fac == expected


# H5-17 evaluate_rtm 정확히 1회
def test_H5_17_evaluate_called_once(monkeypatch):
    spy = _patch_eval(monkeypatch)
    H.send_construction_canonical_to_leg(_contract({"construction_type": "건축"}))
    assert len(spy.calls) == 1


# H5-18 payload == build output
def test_H5_18_payload_exact(monkeypatch):
    spy = _patch_eval(monkeypatch)
    c = _contract({"construction_type": "건축", "has_subcontractor": True, "work_height_m": 0})
    expected = H.build_construction_leg_facility(c)
    H.send_construction_canonical_to_leg(c)
    assert spy.calls[0] == expected


# H5-19 raw response identity/passthrough
def test_H5_19_raw_passthrough(monkeypatch):
    sentinel = {"status": "OK", "obligations": [{"id": "x"}], "trace_id": "t1"}
    spy = _patch_eval(monkeypatch, ret=sentinel)
    out = H.send_construction_canonical_to_leg(_contract({"construction_type": "건축"}))
    assert out is sentinel  # identity: 가공/필터/정렬 0


# H5-20/21 DB READ/WRITE 0
def test_H5_20_21_no_db():
    src = inspect.getsource(H)
    assert "supabase" not in src.lower()
    assert "get_supabase" not in src
    assert "assemble_construction_marketing_contract" not in src  # assembler 미호출


# H5-22 unresolved present but no gating
def test_H5_22_unresolved_no_gating(monkeypatch):
    spy = _patch_eval(monkeypatch)
    c = _contract({"construction_type": "건축"}, unresolved=["worker_count", "has_excavation", "process_list"])
    out = H.send_construction_canonical_to_leg(c)
    assert len(spy.calls) == 1  # unresolved 존재해도 차단/분기 없음
