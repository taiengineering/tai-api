# WO-FE-CST-GAP-IMPL-001 PHASE B CORRECTION-01 — CONSTRUCTION 11 coverage fact materialization test
# frontend 처럼 body.input(nested) 로만 값을 보내는 경로에서 CONSTRUCTION 11 fact 가 canonical→facility
# 로 materialize 되는지, false 가 보존되는지, top-level explicit 이 우선하는지, sector firewall 을 검증한다.
# (production run_diagnosis CODE-C1 로직 + build_facility 를 실제 호출하여 관측)
from clients.leg_runtime_client import build_facility, _LEG_CODE_TO_CONSUMER
from services.canonical.materialization import canonical_applicability

CST11 = ["has_tower_crane", "has_subcontractor", "has_excavation", "has_demolition",
         "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
         "has_water_tank", "is_energy_intensive", "is_multi_use"]
_REV = {v: k for k, v in _LEG_CODE_TO_CONSUMER.items()}
_C11 = set(CST11)
# DiagnosisRunBody model_fields: top-level has_* 가 None 으로 이미 존재(frontend 는 input 안에만 전송)
_TOP_NONE = {"has_gas": None, "has_high_pressure_gas": None, "is_multi_use": None,
             "has_chemical": None, "has_chemical_substance": None, "has_asbestos": None,
             "has_subcontractor": None, "has_excavation": None, "has_demolition": None,
             "has_water_tank": None, "is_energy_intensive": None, "has_tower_crane": None}


def _cst_inp(raw_input, sector="CONSTRUCTION", top=None):
    # production run_diagnosis CODE-C1 (CORRECTION-01) 재현: is-None precedence + 11 explicit target
    _available = dict(_TOP_NONE if top is None else top)
    _available["input"] = raw_input
    _available["form_data"] = None
    if sector == "CONSTRUCTION" and isinstance(raw_input, dict):
        for k, v in raw_input.items():
            if k not in _C11:
                continue
            t = _REV.get(k, k)
            if _available.get(t) is None:
                _available[t] = v
    inp = {"region": "", "anonymous_flow": True, "tier_code": "T"}
    for c, val in canonical_applicability(_available).items():
        inp.setdefault(c, val)
    return inp


class _S:
    def __init__(self, inp, sector):
        self._i = inp
        self._s = sector
    input = property(lambda s: s._i)
    sector = property(lambda s: s._s)
    def __getattr__(self, k):
        return None


def test_t1_11_raw_true_materialization():
    fac = build_facility(_S(_cst_inp({c: True for c in CST11}), "CONSTRUCTION"))
    assert all(fac.get(c) is True for c in CST11)


def test_t2_11_raw_false_preservation():
    fac = build_facility(_S(_cst_inp({c: False for c in CST11}), "CONSTRUCTION"))
    assert all(fac.get(c) is False for c in CST11)


def test_t3_has_gas_nested_only():
    assert build_facility(_S(_cst_inp({"has_gas": True}), "CONSTRUCTION")).get("has_gas") is True


def test_t4_has_high_pressure_gas_nested_only():
    assert build_facility(_S(_cst_inp({"has_high_pressure_gas": True}), "CONSTRUCTION")).get("has_high_pressure_gas") is True


def test_t5_is_multi_use_nested_only():
    assert build_facility(_S(_cst_inp({"is_multi_use": True}), "CONSTRUCTION")).get("is_multi_use") is True


def test_t6_chemical_nested_only_final_exact_name():
    fac = build_facility(_S(_cst_inp({"has_chemical_substance": True}), "CONSTRUCTION"))
    assert fac.get("has_chemical_substance") is True and "has_chemical" not in fac


def test_t7_explicit_top_level_false_precedence():
    top = dict(_TOP_NONE); top["has_gas"] = False
    inp = _cst_inp({"has_gas": True}, "CONSTRUCTION", top=top)
    assert inp.get("has_gas") is False  # top-level explicit False > nested True


def test_t8_industrial_raw_unchanged():
    ind = _cst_inp({"has_gas": True, "has_chemical_substance": True}, "MANUFACTURING")
    assert "has_gas" not in ind and "has_chemical_substance" not in ind and "has_chemical" not in ind
    faci = build_facility(_S({"has_chemical": True}, "MANUFACTURING"))
    assert faci.get("has_chemical") is True and "has_chemical_substance" not in faci


def test_t9_building_raw_unchanged():
    assert "has_gas" not in _cst_inp({"has_gas": True}, "BUILDING")


def test_t10_non_target_construction_not_opened():
    inp = _cst_inp({"has_welding": True, "has_forklift": True}, "CONSTRUCTION")
    assert "has_welding" not in inp and "has_forklift" not in inp
