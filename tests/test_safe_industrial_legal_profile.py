"""WO-SAFE-LEGAL-IND-IMPLEMENT-001-R2 STEP3 — backend profile persistence tests (R2 contract).

Service-level + contract-body-level + real router access-gate. No production DB (FakeSupabase).
R2: 13-field profile (total_floor_area removed; building_use_type_override/main_structure_override added),
sparse partial-merge (omitted 보존 / explicit NULL clear), unknown field -> 422 (pydantic extra=forbid).
"""
import copy
import importlib
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.factory_legal_diagnosis as fld_router
from routers.factory_legal_diagnosis import _ensure_profile_factory_access

from services.safe_industrial_legal_profile_svc import (
    CONTRACT_VERSION, FACILITY_SUPPLEMENTAL_FIELDS, SERVER_MANAGED_FIELDS, OVERRIDE_FIELDS,
    LegalDiagnosisProfileBody,
    validate_profile, build_upsert_row, empty_profile_representation, to_response,
    get_profile, upsert_profile, load_marketing_vocab,
)

VOCAB = {
    "business_activity_types": {"리모델링 수행", "배출시설 운영"},
    "hazardous_work_environments": {"고열작업(실내)", "화재·폭발 위험장소"},
    "building_qualifications": {"의무관리대상 공동주택"},
    "regulated_facility_types": {"제조소등(위험물시설)", "배출시설/방지시설"},
    "material_category": {"인화성 액체/가스", "위험물"},
    "material_handling_modes": {"취급", "저장", "운반", "주입"},
}
DIF_ROWS = [
    {"field_code": "business_activity_types", "field_type": "multi_select", "input_options": ["리모델링 수행", "배출시설 운영"]},
    {"field_code": "hazardous_work_environments", "field_type": "multi_select", "input_options": ["고열작업(실내)", "화재·폭발 위험장소"]},
    {"field_code": "building_qualifications", "field_type": "multi_select", "input_options": ["의무관리대상 공동주택"]},
    {"field_code": "regulated_facility_types", "field_type": "multi_select", "input_options": ["제조소등(위험물시설)", "배출시설/방지시설"]},
    {"field_code": "material_profile", "field_type": "table", "input_options": {"columns": [
        {"key": "material_category", "options": ["인화성 액체/가스", "위험물"]},
        {"key": "handling_modes", "options": ["취급", "저장", "운반", "주입"]}]}},
]


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


def _cur(company_id="C1", role_code="010"):
    return {"company_id": company_id, "role_code": role_code}


# T3-01 exact profile field set = 13
def test_T3_01_profile_field_set_13():
    assert len(FACILITY_SUPPLEMENTAL_FIELDS) == 13
    assert len(set(FACILITY_SUPPLEMENTAL_FIELDS)) == 13
    assert set(LegalDiagnosisProfileBody.model_fields.keys()) == set(FACILITY_SUPPLEMENTAL_FIELDS)


# T3-02 total_floor_area absent from empty representation (+ not a field)
def test_T3_02_total_floor_area_absent_empty():
    d = empty_profile_representation("F1")
    assert "total_floor_area" not in d
    assert "total_floor_area" not in FACILITY_SUPPLEMENTAL_FIELDS
    assert d["profile_exists"] is False and d["contract_version"] == CONTRACT_VERSION
    assert all(d[f] is None for f in FACILITY_SUPPLEMENTAL_FIELDS)


# T3-03 total_floor_area input = 422 (pydantic extra=forbid)
def test_T3_03_total_floor_area_input_422():
    with pytest.raises(ValidationError):
        LegalDiagnosisProfileBody(**{"total_floor_area": 100.0})


# T3-04 / T3-05 override save/restore
def test_T3_04_building_use_type_override_save_restore():
    sb = FakeSupabase(profiles=[])
    cleaned = validate_profile({"building_use_type_override": "공장"}, VOCAB)
    out = upsert_profile(sb, "F1", cleaned)
    assert out["building_use_type_override"] == "공장"
    assert get_profile(sb, "F1")["building_use_type_override"] == "공장"


def test_T3_05_main_structure_override_save_restore():
    sb = FakeSupabase(profiles=[])
    cleaned = validate_profile({"main_structure_override": "RC"}, VOCAB)
    out = upsert_profile(sb, "F1", cleaned)
    assert out["main_structure_override"] == "RC"


# T3-06 override NULL accepted
def test_T3_06_override_null_accepted():
    cleaned = validate_profile({"building_use_type_override": None, "main_structure_override": None}, VOCAB)
    assert cleaned["building_use_type_override"] is None
    assert cleaned["main_structure_override"] is None


# T3-07 override non-string rejected (StrictStr at body + validate_profile)
def test_T3_07_override_non_string_rejected():
    for bad in (123, True, ["x"], {"a": 1}):
        with pytest.raises(ValidationError):
            LegalDiagnosisProfileBody(building_use_type_override=bad)
    with pytest.raises(HTTPException) as ei:
        validate_profile({"main_structure_override": 5}, VOCAB)
    assert ei.value.status_code == 422


# T3-08 NULL array preserved / T3-09 [] preserved (distinct)
def test_T3_08_09_null_and_empty_array_preserved():
    c = validate_profile({"business_activity_types": None, "hazardous_work_environments": []}, VOCAB)
    assert c["business_activity_types"] is None            # 미확인
    assert c["hazardous_work_environments"] == []          # 명시적 없음
    assert c["business_activity_types"] != c["hazardous_work_environments"]


# T3-10 false preserved
def test_T3_10_false_preserved():
    c = validate_profile({"has_truck_loading_unloading": False}, VOCAB)
    assert c["has_truck_loading_unloading"] is False
    assert build_upsert_row("F1", {**{f: None for f in FACILITY_SUPPLEMENTAL_FIELDS}, **c})["has_truck_loading_unloading"] is False


# T3-11 numeric 0 preserved
def test_T3_11_zero_preserved():
    c = validate_profile({"work_height_m": 0, "manual_handling_weight_kg": 0.0}, VOCAB)
    assert c["work_height_m"] == 0 and c["manual_handling_weight_kg"] == 0.0


# T3-12 omitted field preserves existing value  (sparse merge; A/B/C -> update only B)
def test_T3_12_omitted_preserves_existing():
    existing = {"factory_id": "F1", "contract_version": CONTRACT_VERSION,
                "work_height_m": 3.0, "ksic_list": ["A"], "has_manual_heavy_handling": True}
    sb = FakeSupabase(profiles=[existing])
    cleaned = validate_profile({"work_height_m": 5.0}, VOCAB)   # provided-only (B)
    out = upsert_profile(sb, "F1", cleaned)
    assert out["work_height_m"] == 5.0            # B changed
    assert out["ksic_list"] == ["A"]              # A preserved
    assert out["has_manual_heavy_handling"] is True  # C preserved
    assert len(sb.stores["factory_legal_diagnosis_profile"]) == 1  # row 증가 0


# T3-13 explicit NULL clears existing value
def test_T3_13_explicit_null_clears():
    existing = {"factory_id": "F1", "contract_version": CONTRACT_VERSION, "work_height_m": 5.0, "ksic_list": ["A"]}
    sb = FakeSupabase(profiles=[existing])
    cleaned = validate_profile({"work_height_m": None}, VOCAB)  # explicit null (present)
    out = upsert_profile(sb, "F1", cleaned)
    assert out["work_height_m"] is None           # cleared
    assert out["ksic_list"] == ["A"]              # untouched


# T3-12/13 router contract: exclude_unset distinguishes omitted vs explicit-null
def test_T3_12b_router_exclude_unset_distinguishes():
    omitted = LegalDiagnosisProfileBody(**{"work_height_m": 5.0}).dict(exclude_unset=True)
    assert omitted == {"work_height_m": 5.0}       # ksic_list 등 omitted 제외
    explicit = LegalDiagnosisProfileBody(**{"work_height_m": None}).dict(exclude_unset=True)
    assert explicit == {"work_height_m": None}     # explicit null 포함


# T3-14 unknown field = 422
def test_T3_14_unknown_field_422():
    with pytest.raises(ValidationError):
        LegalDiagnosisProfileBody(**{"__nope__": 1})


# T3-15 company_id absent from profile persistence
def test_T3_15_company_id_absent():
    row = build_upsert_row("F1", {**{f: None for f in FACILITY_SUPPLEMENTAL_FIELDS}, "building_use_type_override": "x"})
    assert "company_id" not in row
    assert "company_id" not in empty_profile_representation("F1")
    assert row["contract_version"] == CONTRACT_VERSION
    for bad in ("company_id", "contract_version", "factory_id", "created_at", "updated_at", "id"):
        with pytest.raises(ValidationError):
            LegalDiagnosisProfileBody(**{bad: "x"})


# T3-16 ownership regression (real router helper) A~E
def test_T3_16A_own_pass(monkeypatch):
    sb = FakeSupabase(factories=[{"id": "F1", "company_id": "C1"}])
    monkeypatch.setattr(fld_router, "_ensure_factory_own", lambda s, f, c: None)
    _ensure_profile_factory_access(sb, "F1", _cur())
    assert sb.counters["writes"] == 0


def test_T3_16B_foreign_404(monkeypatch):
    sb = FakeSupabase(factories=[{"id": "F1", "company_id": "C1"}])
    def own(s, f, c): raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(fld_router, "_ensure_factory_own", own)
    with pytest.raises(HTTPException) as ei:
        _ensure_profile_factory_access(sb, "F1", _cur(company_id="C2"))
    assert ei.value.status_code == 404


def test_T3_16C_missing_normal_404(monkeypatch):
    sb = FakeSupabase(factories=[])
    called = {"n": 0}
    monkeypatch.setattr(fld_router, "_ensure_factory_own", lambda s, f, c: called.__setitem__("n", called["n"] + 1))
    with pytest.raises(HTTPException) as ei:
        _ensure_profile_factory_access(sb, "F404", _cur())
    assert ei.value.status_code == 404 and called["n"] == 0


def test_T3_16D_missing_admin_404(monkeypatch):
    sb = FakeSupabase(factories=[])
    monkeypatch.setattr(fld_router, "_ensure_factory_own", lambda s, f, c: None)
    with pytest.raises(HTTPException) as ei:
        _ensure_profile_factory_access(sb, "F404", _cur(role_code="001"))
    assert ei.value.status_code == 404


def test_T3_16E_ownership_fail_no_db(monkeypatch):
    sb = FakeSupabase(factories=[{"id": "F1", "company_id": "C1"}])
    def own(s, f, c): raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(fld_router, "_ensure_factory_own", own)
    with pytest.raises(HTTPException):
        _ensure_profile_factory_access(sb, "F1", _cur(company_id="C2"))
    assert sb.counters["writes"] == 0


# ── retained value-contract tests ────────────────────────────────────
def test_numeric_negative_rejected():
    for f in ("work_height_m", "truck_loading_height_m", "manual_handling_weight_kg"):
        with pytest.raises(HTTPException) as ei:
            validate_profile({f: -1}, VOCAB)
        assert ei.value.status_code == 422


@pytest.mark.parametrize("field", ["business_activity_types", "hazardous_work_environments",
                                   "building_qualifications", "regulated_facility_types"])
def test_invalid_vocab_rejected(field):
    with pytest.raises(HTTPException) as ei:
        validate_profile({field: ["___INVALID___"]}, VOCAB)
    assert ei.value.status_code == 422


def test_material_profile_shape():
    with pytest.raises(HTTPException):
        validate_profile({"material_profile": [{"material_category": "위험물", "danger": 9}]}, VOCAB)
    with pytest.raises(HTTPException):
        validate_profile({"material_profile": [{"material_category": "___NOPE___"}]}, VOCAB)
    ok = validate_profile({"material_profile": [{"material_category": "위험물", "handling_modes": ["취급"]}]}, VOCAB)
    assert ok["material_profile"][0]["material_category"] == "위험물"
    assert validate_profile({"material_profile": []}, VOCAB)["material_profile"] == []


def test_ksic_list_multi():
    assert validate_profile({"ksic_list": ["C", "D"]}, VOCAB)["ksic_list"] == ["C", "D"]
    with pytest.raises(HTTPException):
        validate_profile({"ksic_list": [1, 2]}, VOCAB)


def test_load_vocab_from_db():
    v = load_marketing_vocab(FakeSupabase())
    assert "리모델링 수행" in v["business_activity_types"] and "위험물" in v["material_category"]


def test_server_managed_disjoint():
    assert set(SERVER_MANAGED_FIELDS).isdisjoint(set(FACILITY_SUPPLEMENTAL_FIELDS))
    assert set(OVERRIDE_FIELDS) == {"building_use_type_override", "main_structure_override"}


def test_get_missing_no_mutation():
    sb = FakeSupabase(profiles=[])
    out = get_profile(sb, "F404")
    assert out["profile_exists"] is False and sb.counters["writes"] == 0
    assert "total_floor_area" not in out


# route/import regression (real modules)
def test_route_import_regression():
    fac = importlib.import_module("routers.factories")
    fld = importlib.import_module("routers.factory_legal_diagnosis")
    fld_pairs = {(m, r.path) for r in fld.router.routes for m in getattr(r, "methods", set())}
    fac_paths = {r.path for r in fac.router.routes}
    assert "/factories/{factory_id}" in fac_paths and "/factories/{factory_id}/legal" in fac_paths
    assert ("GET", "/factories/{factory_id}/legal-diagnosis/profile") in fld_pairs
    assert ("PUT", "/factories/{factory_id}/legal-diagnosis/profile") in fld_pairs
