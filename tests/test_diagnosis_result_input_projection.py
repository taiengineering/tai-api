"""Unit tests - services.diagnosis_result_input_projection.

WO-FREE-RESULT-INPUT-SUMMARY-IMPL-001. catalog(diagnosis_input_fields)는 FakeSupabase 로
대체하므로 DB/network 불필요. normalize_sector_db/sector_codes_for_query 는 실제 모듈을
import 한다(레포 내 pytest 실행 전제).
"""
import importlib

mod = importlib.import_module("services.diagnosis_result_input_projection")
project = mod.project_free_input_snapshot


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc

    def select(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return _Resp(self._rows)


class FakeSupabase:
    """diagnosis_input_fields 조회만 흉내낸다."""

    def __init__(self, field_codes=None, raise_exc=None):
        self._rows = [{"field_code": c} for c in (field_codes or [])]
        self._raise = raise_exc

    def table(self, name):
        assert name == "diagnosis_input_fields"
        return _Query(self._rows, self._raise)


BUILDING_FREE = [
    "address", "total_floor_area", "floor_count", "basement_count",
    "building_use_type", "built_year", "main_structure", "worker_count",
    "has_structure", "structure_height_m", "has_hazmat_storage",
    "has_scaffold", "scaffold_height_m",
]


def _idata(form_data, sector="BUILDING"):
    return {"sector": sector, "raw_structured_input": {"form_data": form_data}}


def test_building_allowlist_projection():  # API-T2
    fd = {
        "address": "addr", "total_floor_area": 11860.03, "floor_count": 32,
        "basement_count": 3, "building_use_type": "office", "built_year": 2005,
        "main_structure": "RC", "worker_count": 38,
        "facility": {"total_floor_area": 11860.03}, "process": [], "equipment": [],
    }
    out = project(FakeSupabase(BUILDING_FREE), "BUILDING", _idata(fd))
    assert out["total_floor_area"] == 11860.03
    assert out["floor_count"] == 32
    assert out["building_use_type"] == "office"
    assert "facility" not in out and "process" not in out and "equipment" not in out


def test_industrial_projection():  # API-T3
    codes = ["address", "ksic_major", "worker_count", "total_floor_area"]
    fd = {"address": "addr", "ksic_major": "C", "worker_count": 50, "total_floor_area": 5000}
    out = project(FakeSupabase(codes), "INDUSTRIAL", _idata(fd, "INDUSTRIAL"))
    assert out["ksic_major"] == "C" and out["total_floor_area"] == 5000


def test_construction_projection():  # API-T4
    codes = ["project_address", "project_amount", "worker_count", "has_scaffold"]
    fd = {"project_address": "site", "project_amount": 30, "worker_count": 12, "has_scaffold": True}
    out = project(FakeSupabase(codes), "CONSTRUCTION", _idata(fd, "CONSTRUCTION"))
    assert out == {"project_address": "site", "project_amount": 30, "worker_count": 12, "has_scaffold": True}


def test_top_level_precedence_over_facility():  # API-T5 / WO 17
    fd = {"total_floor_area": 100, "facility": {"total_floor_area": 999}}
    out = project(FakeSupabase(["total_floor_area"]), "BUILDING", _idata(fd))
    assert out == {"total_floor_area": 100}


def test_facility_fallback_when_top_absent():
    fd = {"facility": {"floor_count": 7}}
    out = project(FakeSupabase(["floor_count"]), "BUILDING", _idata(fd))
    assert out == {"floor_count": 7}


def test_out_of_catalog_key_not_exposed():  # API-T6
    fd = {"total_floor_area": 100, "secret_internal": "x"}
    out = project(FakeSupabase(["total_floor_area"]), "BUILDING", _idata(fd))
    assert "secret_internal" not in out


def test_container_never_exposed_even_if_in_catalog():  # API-T7 (defensive)
    fd = {"facility": {"a": 1}, "process": [{"x": 1}]}
    out = project(FakeSupabase(["facility", "process"]), "BUILDING", _idata(fd))
    assert out == {}


def test_false_preserved():  # API-T8
    fd = {"has_scaffold": False}
    out = project(FakeSupabase(["has_scaffold"]), "BUILDING", _idata(fd))
    assert out["has_scaffold"] is False


def test_zero_preserved():  # API-T9
    fd = {"basement_count": 0}
    out = project(FakeSupabase(["basement_count"]), "BUILDING", _idata(fd))
    assert out["basement_count"] == 0


def test_none_excluded():
    fd = {"built_year": None, "floor_count": 5}
    out = project(FakeSupabase(["built_year", "floor_count"]), "BUILDING", _idata(fd))
    assert "built_year" not in out and out["floor_count"] == 5


def test_legacy_no_form_data_returns_empty():  # API-T10
    out = project(FakeSupabase(BUILDING_FREE), "BUILDING", {"sector": "BUILDING"})
    assert out == {}


def test_catalog_exception_fail_closed():  # API-T11
    out = project(FakeSupabase(raise_exc=RuntimeError("boom")), "BUILDING", _idata({"total_floor_area": 100}))
    assert out == {}


def test_catalog_zero_rows_fail_closed():  # API-T12
    out = project(FakeSupabase([]), "BUILDING", _idata({"total_floor_area": 100}))
    assert out == {}
