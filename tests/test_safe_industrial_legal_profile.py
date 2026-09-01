"""WO-SAFE-LEGAL-IND-IMPLEMENT-001 STEP 3 (STEP3-PATCH-1) — facility supplemental persistence tests.

Service-level + contract-body-level + real router access-gate + route/import regression.
No production DB (FakeSupabase). P05 imports the REAL router helper _ensure_profile_factory_access
and monkeypatches only the shared dependency _ensure_factory_own (company_scope is not modified by
this WO and cannot run standalone). P23 imports the real routers.factories / routers.factory_legal_diagnosis
and asserts route preservation + no collision.
"""
import copy
import importlib
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.factory_legal_diagnosis as fld_router
from routers.factory_legal_diagnosis import _ensure_profile_factory_access

from services.safe_industrial_legal_profile_svc import (
    CONTRACT_VERSION, FACILITY_SUPPLEMENTAL_FIELDS, SERVER_MANAGED_FIELDS,
    LegalDiagnosisProfileBody,
    validate_profile, build_upsert_row, empty_profile_representation, to_response,
    get_profile, upsert_profile, load_marketing_vocab,
)

# -- Marketing vocabulary fixture (mirrors diagnosis_input_fields INDUSTRIAL) --
VOCAB = {
    "business_activity_types": {"리모델링 수행", "배출시설 운영"},
    "hazardous_work_environments": {"고열작업(실내)", "화재·폭발 위험장소"},
    "building_qualifications": {"의무관리대상 공동주택"},
    "regulated_facility_types": {"제조소등(위험물시설)", "배출시설/방지시설"},
    "material_category": {"인화성 액체/가스", "위험물"},
    "material_handling_modes": {"취급", "저장", "운반", "주입"},
}

DIF_ROWS = [
    {"field_code": "business_activity_types", "field_type": "multi_select",
     "input_options": ["리모델링 수행", "배출시설 운영"]},
    {"field_code": "hazardous_work_environments", "field_type": "multi_select",
     "input_options": ["고열작업(실내)", "화재·폭발 위험장소"]},
    {"field_code": "building_qualifications", "field_type": "multi_select",
     "input_options": ["의무관리대상 공동주택"]},
    {"field_code": "regulated_facility_types", "field_type": "multi_select",
     "input_options": ["제조소등(위험물시설)", "배출시설/방지시설"]},
    {"field_code": "material_profile", "field_type": "table", "input_options": {"columns": [
        {"key": "material_category", "options": ["인화성 액체/가스", "위험물"]},
        {"key": "handling_modes", "options": ["취급", "저장", "운반", "주입"]},
    ]}},
    {"field_code": "worker_count", "field_type": "number", "input_options": None},  # noise
]


# -- FakeSupabase (minimal chain: select/eq/limit/execute, upsert/execute) --
class _Result:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, table): self.t = table; self._f = {}
    def select(self, *a, **k): return self
    def eq(self, col, val): self._f[col] = val; return self
    def limit(self, n): return self
    def execute(self):
        if self.t.name == "diagnosis_input_fields":
            return _Result(list(self.t.store))
        rows = [r for r in self.t.store if all(r.get(c) == v for c, v in self._f.items())]
        return _Result(copy.deepcopy(rows))


class _Table:
    def __init__(self, name, store, counters): self.name = name; self.store = store; self.counters = counters
    def select(self, *a, **k): return _Query(self)
    def eq(self, *a, **k): q = _Query(self); return q.eq(*a, **k)
    def upsert(self, row, on_conflict=None):
        self.counters["writes"] += 1
        key = row.get(on_conflict or "factory_id")
        for i, r in enumerate(self.store):
            if r.get(on_conflict or "factory_id") == key:
                self.store[i] = {**r, **row}
                self._pending = _Result([copy.deepcopy(self.store[i])]); return self
        self.store.append(copy.deepcopy(row))
        self._pending = _Result([copy.deepcopy(row)]); return self
    def execute(self):
        return getattr(self, "_pending", _Result([]))


class FakeSupabase:
    def __init__(self, profiles=None, dif=None, factories=None):
        self.stores = {
            "factory_legal_diagnosis_profile": list(profiles or []),
            "diagnosis_input_fields": list(dif or DIF_ROWS),
            "factories": list(factories or []),
        }
        self.counters = {"writes": 0}
    def table(self, name):
        self.stores.setdefault(name, [])
        return _Table(name, self.stores[name], self.counters)


def _base_body(**over):
    b = {f: None for f in FACILITY_SUPPLEMENTAL_FIELDS}
    b.update(over)
    return b


def _cur(company_id="C1", role_code="010"):
    return {"company_id": company_id, "role_code": role_code}


# -- P01 / P02 / P22 GET --
def test_P01_get_existing_profile():
    row = {"factory_id": "F1", "contract_version": CONTRACT_VERSION,
           "work_height_m": 2.5, "has_truck_loading_unloading": False,
           "business_activity_types": [], "updated_at": "2026-09-01T16:00:00"}
    sb = FakeSupabase(profiles=[row])
    out = get_profile(sb, "F1")
    assert out["profile_exists"] is True
    assert out["factory_id"] == "F1"
    assert out["work_height_m"] == 2.5
    assert out["has_truck_loading_unloading"] is False
    assert out["business_activity_types"] == []
    assert set(FACILITY_SUPPLEMENTAL_FIELDS).issubset(out.keys())
    assert "company_id" not in out


def test_P02_P22_get_missing_no_mutation():
    sb = FakeSupabase(profiles=[])
    out = get_profile(sb, "F404")
    assert out["profile_exists"] is False
    assert all(out[f] is None for f in FACILITY_SUPPLEMENTAL_FIELDS)
    assert sb.counters["writes"] == 0  # P02/P22: GET never mutates


# -- P03 / P04 upsert cardinality --
def test_P03_put_creates_one_row():
    sb = FakeSupabase(profiles=[])
    cleaned = validate_profile(_base_body(work_height_m=3.0), VOCAB)
    upsert_profile(sb, "F1", cleaned)
    assert len(sb.stores["factory_legal_diagnosis_profile"]) == 1
    assert sb.counters["writes"] == 1


def test_P04_second_put_updates_same_row():
    sb = FakeSupabase(profiles=[])
    upsert_profile(sb, "F1", validate_profile(_base_body(work_height_m=3.0), VOCAB))
    upsert_profile(sb, "F1", validate_profile(_base_body(work_height_m=5.0), VOCAB))
    rows = sb.stores["factory_legal_diagnosis_profile"]
    assert len(rows) == 1               # row 증가 0
    assert rows[0]["work_height_m"] == 5.0


# -- P05-A~E factory existence + ownership gate (REAL router helper) --
def test_P05A_own_factory_access_pass(monkeypatch):
    sb = FakeSupabase(factories=[{"id": "F1", "company_id": "C1"}])
    monkeypatch.setattr(fld_router, "_ensure_factory_own", lambda s, f, c: None)  # own → pass
    _ensure_profile_factory_access(sb, "F1", _cur())   # no raise
    assert sb.counters["writes"] == 0


def test_P05B_foreign_factory_404(monkeypatch):
    sb = FakeSupabase(factories=[{"id": "F1", "company_id": "C1"}])
    def own(s, f, c): raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(fld_router, "_ensure_factory_own", own)
    with pytest.raises(HTTPException) as ei:
        _ensure_profile_factory_access(sb, "F1", _cur(company_id="C2"))
    assert ei.value.status_code == 404


def test_P05C_missing_factory_normal_user_404(monkeypatch):
    sb = FakeSupabase(factories=[])   # F404 absent
    called = {"n": 0}
    def own(s, f, c): called["n"] += 1
    monkeypatch.setattr(fld_router, "_ensure_factory_own", own)
    with pytest.raises(HTTPException) as ei:
        _ensure_profile_factory_access(sb, "F404", _cur())
    assert ei.value.status_code == 404
    assert called["n"] == 0            # existence check fires BEFORE ownership


def test_P05D_missing_factory_ALL_admin_404(monkeypatch):
    """★ regression: ALL 관리자여도 존재하지 않는 factory 는 404 (ownership 우회 방지)."""
    sb = FakeSupabase(factories=[])
    monkeypatch.setattr(fld_router, "_ensure_factory_own", lambda s, f, c: None)  # admin would bypass
    with pytest.raises(HTTPException) as ei:
        _ensure_profile_factory_access(sb, "F404", _cur(role_code="001"))
    assert ei.value.status_code == 404


def test_P05E_ownership_failure_no_db(monkeypatch):
    sb = FakeSupabase(factories=[{"id": "F1", "company_id": "C1"}])
    def own(s, f, c): raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(fld_router, "_ensure_factory_own", own)
    with pytest.raises(HTTPException):
        _ensure_profile_factory_access(sb, "F1", _cur(company_id="C2"))
    assert sb.counters["writes"] == 0  # blocked before any profile read/write


# -- P06 / P07 server-managed override rejection --
def test_P06_client_company_id_not_persisted():
    cleaned = validate_profile(_base_body(total_floor_area=100.0), VOCAB)
    row = build_upsert_row("F1", {**cleaned, "company_id": "HACK"})
    assert "company_id" not in row
    assert row["factory_id"] == "F1"


def test_P07_contract_version_server_fixed():
    cleaned = validate_profile(_base_body(), VOCAB)
    row = build_upsert_row("F1", {**cleaned, "contract_version": "HACK_V9"})
    assert row["contract_version"] == CONTRACT_VERSION


def test_P06_P07_body_extra_forbidden():
    for bad in ("company_id", "contract_version", "factory_id", "created_at", "updated_at", "id"):
        with pytest.raises(ValidationError):
            LegalDiagnosisProfileBody(**{bad: "x"})
    ok = LegalDiagnosisProfileBody(work_height_m=1.0, business_activity_types=[])
    assert ok.dict()["work_height_m"] == 1.0
    assert ok.dict()["business_activity_types"] == []


# -- P08~P11 NULL / [] / false / 0 preserved (not merged) --
def test_P08_null_preserved():
    cleaned = validate_profile(_base_body(work_height_m=None, business_activity_types=None), VOCAB)
    assert cleaned["work_height_m"] is None
    assert cleaned["business_activity_types"] is None
    row = build_upsert_row("F1", cleaned)
    assert row["work_height_m"] is None and row["business_activity_types"] is None


def test_P09_empty_list_preserved_distinct_from_null():
    cleaned = validate_profile(_base_body(business_activity_types=[], hazardous_work_environments=None), VOCAB)
    assert cleaned["business_activity_types"] == []
    assert cleaned["hazardous_work_environments"] is None
    assert cleaned["business_activity_types"] != cleaned["hazardous_work_environments"]


def test_P10_false_preserved():
    cleaned = validate_profile(_base_body(has_truck_loading_unloading=False), VOCAB)
    assert cleaned["has_truck_loading_unloading"] is False
    assert build_upsert_row("F1", cleaned)["has_truck_loading_unloading"] is False


def test_P11_zero_preserved():
    cleaned = validate_profile(_base_body(work_height_m=0, manual_handling_weight_kg=0.0), VOCAB)
    assert cleaned["work_height_m"] == 0
    assert cleaned["manual_handling_weight_kg"] == 0.0


# -- P12 numeric --
def test_P12_negative_numeric_rejected():
    for f in ("work_height_m", "truck_loading_height_m", "manual_handling_weight_kg", "total_floor_area"):
        with pytest.raises(HTTPException) as ei:
            validate_profile(_base_body(**{f: -1}), VOCAB)
        assert ei.value.status_code == 422


# -- P13~P16 vocabulary arrays --
@pytest.mark.parametrize("field", [
    "business_activity_types", "hazardous_work_environments",
    "building_qualifications", "regulated_facility_types",
])
def test_P13_P16_invalid_vocab_rejected(field):
    with pytest.raises(HTTPException) as ei:
        validate_profile(_base_body(**{field: ["___INVALID___"]}), VOCAB)
    assert ei.value.status_code == 422


def test_vocab_valid_accepted():
    cleaned = validate_profile(_base_body(
        business_activity_types=["리모델링 수행"],
        regulated_facility_types=["제조소등(위험물시설)", "배출시설/방지시설"],
    ), VOCAB)
    assert cleaned["business_activity_types"] == ["리모델링 수행"]


# -- P17~P20 material_profile --
def test_P17_material_category_invalid_rejected():
    with pytest.raises(HTTPException) as ei:
        validate_profile(_base_body(material_profile=[{"material_category": "___NOPE___"}]), VOCAB)
    assert ei.value.status_code == 422


def test_P18_material_handling_mode_invalid_rejected():
    with pytest.raises(HTTPException) as ei:
        validate_profile(_base_body(material_profile=[
            {"material_category": "위험물", "handling_modes": ["취급", "___NOPE___"]}]), VOCAB)
    assert ei.value.status_code == 422


def test_P19_material_extra_key_rejected():
    with pytest.raises(HTTPException) as ei:
        validate_profile(_base_body(material_profile=[
            {"material_category": "위험물", "handling_modes": ["취급"], "danger": 9}]), VOCAB)
    assert ei.value.status_code == 422


def test_P20_material_empty_list_preserved():
    cleaned = validate_profile(_base_body(material_profile=[]), VOCAB)
    assert cleaned["material_profile"] == []
    ok = validate_profile(_base_body(material_profile=[
        {"material_category": "위험물", "handling_modes": ["취급", "저장"]}]), VOCAB)
    assert ok["material_profile"][0]["material_category"] == "위험물"


# -- P21 ksic_list multi --
def test_P21_ksic_list_multi_preserved():
    cleaned = validate_profile(_base_body(ksic_list=["C", "D", "F"]), VOCAB)
    assert cleaned["ksic_list"] == ["C", "D", "F"]
    with pytest.raises(HTTPException):
        validate_profile(_base_body(ksic_list=[1, 2]), VOCAB)


# -- P23 route/import regression (real modules) --
def test_P23_router_import_and_route_regression():
    fac = importlib.import_module("routers.factories")
    fld = importlib.import_module("routers.factory_legal_diagnosis")
    fac_pairs = {(m, r.path) for r in fac.router.routes for m in getattr(r, "methods", set())}
    fld_pairs = {(m, r.path) for r in fld.router.routes for m in getattr(r, "methods", set())}
    fac_paths = {r.path for r in fac.router.routes}
    assert "/factories/{factory_id}" in fac_paths
    assert "/factories/{factory_id}/contacts" in fac_paths
    assert "/factories/{factory_id}/legal" in fac_paths
    assert ("GET", "/factories/{factory_id}/legal-diagnosis/profile") in fld_pairs
    assert ("PUT", "/factories/{factory_id}/legal-diagnosis/profile") in fld_pairs
    assert fac_pairs.isdisjoint(fld_pairs)


# -- load_marketing_vocab from DB source (SoT reuse, no hardcode) --
def test_load_marketing_vocab_from_db_source():
    sb = FakeSupabase()
    v = load_marketing_vocab(sb)
    assert "리모델링 수행" in v["business_activity_types"]
    assert "위험물" in v["material_category"]
    assert "취급" in v["material_handling_modes"]


# -- contract shape guards --
def test_allowlist_is_exactly_12():
    assert len(FACILITY_SUPPLEMENTAL_FIELDS) == 12
    assert len(set(FACILITY_SUPPLEMENTAL_FIELDS)) == 12


def test_server_managed_not_in_allowlist():
    assert set(SERVER_MANAGED_FIELDS).isdisjoint(set(FACILITY_SUPPLEMENTAL_FIELDS))


def test_empty_representation_shape():
    d = empty_profile_representation("F1")
    assert d["profile_exists"] is False and d["contract_version"] == CONTRACT_VERSION
    assert all(d[f] is None for f in FACILITY_SUPPLEMENTAL_FIELDS)
    assert "company_id" not in d
