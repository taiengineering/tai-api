"""WP01-A Snapshot Compare — 단위/통합 테스트.

WO-E2E2000-WP01-A-PR628-CORRECTION-001

커버리지:
  C01~C07  _canonical_hash / _diff_facilities (change_type / missing vs null)
  B01~B10  load_baseline_facility (sector 필터 / status 필터 / DB 오류 분리)
  K01~K06  collector (INDUSTRIAL / BUILDING / CONSTRUCTION)
  S01~S22  compare_snapshot 통합
  R01~R11  라우터 엔드포인트
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

_FAC_ID = str(uuid4())
_SITE_ID = str(uuid4())
_COMPANY_ID = str(uuid4())
_DIAG_ID = str(uuid4())

_FACILITY_V1 = {"worker_count": 50, "ksic_major": "C10"}
_FACILITY_V2 = {"worker_count": 80, "ksic_major": "C10"}  # changed worker_count


def _c10_row(facility: dict, sector: str = "INDUSTRIAL", status: str = "ACTIVE") -> dict:
    """C10 행 — sector/status/input_data 포함 (신규 쿼리 계약 반영)."""
    return {
        "id": _DIAG_ID,
        "input_data": {"factory_id": _FAC_ID, "sector": sector},
        "full_result": {
            "facility_used": facility,
            "obligations_raw": [],
            "sector": sector,
        },
        "created_at": "2026-10-10T00:00:00+00:00",
        "source_type": "saas",
        "status": status,
    }


class _R:
    def __init__(self, data):
        self.data = data
        self.count = len(data) if data else 0


class _Q:
    """필터 적용 체인 mock 쿼리."""

    def __init__(self, rows: list):
        self._rows = list(rows)
        self._filters: list = []

    def select(self, *_, **__):
        return self

    def eq(self, col: str, val: Any):
        self._filters.append((col, val))
        return self

    def in_(self, col: str, vals: list):
        return self

    def order(self, *_, **__):
        return self

    def limit(self, n: int):
        self._n = n
        return self

    def execute(self):
        rows = [r for r in self._rows if self._match(r)]
        n = getattr(self, "_n", len(rows))
        return _R(rows[:n])

    def _match(self, row: dict) -> bool:
        for col, val in self._filters:
            if col == "input_data->>factory_id":
                if (row.get("input_data") or {}).get("factory_id") != val:
                    return False
            elif col == "input_data->>sector":
                if (row.get("input_data") or {}).get("sector") != val:
                    return False
            elif col == "status":
                if row.get("status") != val:
                    return False
            elif col == "source_type":
                if row.get("source_type") != val:
                    return False
            elif col == "id":
                if str(row.get("id") or "") != str(val):
                    return False
            # 나머지 eq 조건은 무시(팩토리 소유권 등 타 테이블)
        return True


class _FakeSupa:
    def __init__(self, tables: Dict[str, list]):
        self._tables = tables

    def table(self, name: str) -> _Q:
        return _Q(self._tables.get(name, []))


# ══════════════════════════════════════════════════════════════════════════════
# C01~C07  _canonical_hash / _diff_facilities
# ══════════════════════════════════════════════════════════════════════════════

from services.wp01_snapshot_compare.compare import _canonical_hash, _diff_facilities


def test_C01_hash_deterministic():
    h1 = _canonical_hash({"a": 1, "b": True})
    h2 = _canonical_hash({"a": 1, "b": True})
    assert h1 == h2


def test_C02_hash_key_order_invariant():
    h1 = _canonical_hash({"a": 1, "b": 2})
    h2 = _canonical_hash({"b": 2, "a": 1})
    assert h1 == h2


def test_C03_hash_different_values_differ():
    assert _canonical_hash({"a": 1}) != _canonical_hash({"a": 2})


def test_C04_diff_changed_field_with_change_type():
    diffs = _diff_facilities({"a": 1}, {"a": 2})
    assert len(diffs) == 1
    d = diffs[0]
    assert d["field"] == "a"
    assert d["change_type"] == "CHANGED"
    assert d["baseline_value"] == 1
    assert d["current_value"] == 2


def test_C05_diff_added_removed_change_types():
    diffs = _diff_facilities({"a": 1, "b": 2}, {"b": 3, "c": 4})
    by_field = {d["field"]: d for d in diffs}
    assert by_field["a"]["change_type"] == "REMOVED"
    assert by_field["b"]["change_type"] == "CHANGED"
    assert by_field["c"]["change_type"] == "ADDED"


def test_C06_missing_vs_null_distinguished():
    """키 누락과 명시적 null 은 별도 change_type 으로 구분된다."""
    # baseline: {"x": None} (명시적 null) vs current: {} (키 없음)
    diffs_a = _diff_facilities({"x": None}, {})
    assert len(diffs_a) == 1
    assert diffs_a[0]["change_type"] == "REMOVED"
    assert diffs_a[0]["baseline_value"] is None

    # baseline: {} (키 없음) vs current: {"x": None} (명시적 null)
    diffs_b = _diff_facilities({}, {"x": None})
    assert len(diffs_b) == 1
    assert diffs_b[0]["change_type"] == "ADDED"
    assert diffs_b[0]["current_value"] is None


def test_C07_hash_missing_vs_null_differ():
    """해시: 키 누락과 명시적 null 은 서로 다른 해시."""
    assert _canonical_hash({"a": None}) != _canonical_hash({})


# ══════════════════════════════════════════════════════════════════════════════
# B01~B10  load_baseline_facility
# ══════════════════════════════════════════════════════════════════════════════

from services.wp01_snapshot_compare.baseline import load_baseline_facility
from services.wp01_snapshot_compare.errors import BaselineNotFound, BaselineQueryError


def test_B01_returns_facility_used_and_snapshot_id():
    supa = _FakeSupa({"anonymous_diagnosis_results": [_c10_row(_FACILITY_V1)]})
    fac, sid = load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")
    assert fac == _FACILITY_V1
    assert sid == _DIAG_ID


def test_B02_no_rows_raises_not_found():
    supa = _FakeSupa({"anonymous_diagnosis_results": []})
    with pytest.raises(BaselineNotFound):
        load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")


def test_B03_missing_facility_used_raises():
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [{
            "id": _DIAG_ID,
            "input_data": {"factory_id": _FAC_ID, "sector": "INDUSTRIAL"},
            "full_result": {"obligations_raw": []},
            "created_at": "2026-10-10T00:00:00+00:00",
            "source_type": "saas",
            "status": "ACTIVE",
        }]
    })
    with pytest.raises(BaselineNotFound):
        load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")


def test_B04_full_result_not_dict_raises():
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [{
            "id": _DIAG_ID,
            "input_data": {"factory_id": _FAC_ID, "sector": "INDUSTRIAL"},
            "full_result": "not_a_dict",
            "created_at": "2026-10-10T00:00:00+00:00",
            "source_type": "saas",
            "status": "ACTIVE",
        }]
    })
    with pytest.raises(BaselineNotFound):
        load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")


def test_B05_empty_factory_id_raises_query_error():
    supa = _FakeSupa({})
    with pytest.raises(BaselineQueryError):
        load_baseline_facility(supa, "", "INDUSTRIAL")


def test_B06_db_exception_raises_query_error():
    """DB 오류 → BaselineQueryError (UNRESOLVED), not BaselineNotFound (BASELINE_REQUIRED)."""
    class _BadSupa:
        def table(self, *_):
            raise RuntimeError("DB down")

    with pytest.raises(BaselineQueryError):
        load_baseline_facility(_BadSupa(), _FAC_ID, "INDUSTRIAL")


def test_B07_sector_filter_wrong_sector_returns_not_found():
    """다른 섹터(BUILDING) C10 행은 INDUSTRIAL 조회에서 걸러진다."""
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [_c10_row(_FACILITY_V1, sector="BUILDING")]
    })
    with pytest.raises(BaselineNotFound):
        load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")


def test_B08_sector_filter_matching_sector_found():
    """같은 섹터(INDUSTRIAL) C10 행 → 정상 반환."""
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [_c10_row(_FACILITY_V1, sector="INDUSTRIAL")]
    })
    fac, sid = load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")
    assert fac == _FACILITY_V1


def test_B09_status_expired_filtered_out():
    """status=EXPIRED 행은 active baseline 후보 아님."""
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [_c10_row(_FACILITY_V1, status="EXPIRED")]
    })
    with pytest.raises(BaselineNotFound):
        load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")


def test_B10_snapshot_id_returned():
    supa = _FakeSupa({"anonymous_diagnosis_results": [_c10_row(_FACILITY_V1)]})
    _, sid = load_baseline_facility(supa, _FAC_ID, "INDUSTRIAL")
    assert sid == _DIAG_ID


# ══════════════════════════════════════════════════════════════════════════════
# K01~K06  collector
# ══════════════════════════════════════════════════════════════════════════════

from services.wp01_snapshot_compare.collector import (
    collect_current_facility_industrial,
    collect_current_facility_building,
    collect_current_facility_construction,
)
from services.wp01_snapshot_compare.errors import CollectionError
from schemas.legal_engine import (
    SafeIndustrialConsumerInput,
    SafeBuildingConsumerInput,
    SafeConstructionConsumerInput,
)


def _patch_work_mat_eq(monkeypatch):
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda s, f: [])
    monkeypatch.setattr("services.material_source.store.load_factory_material_rows_optional", lambda s, f: [])
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", lambda s, f: [])


def test_K01_industrial_returns_facility_dict(monkeypatch):
    from services import safe_industrial_leg_runtime as R
    from services.safe_industrial_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION

    _patch_work_mat_eq(monkeypatch)
    monkeypatch.setattr(
        R, "assemble_industrial_marketing_contract",
        lambda s, fid: {
            "contract_version": CONTRACT_VERSION,
            "sector": "INDUSTRIAL",
            "factory_id": fid,
            "values": {f: None for f in TARGET_FIELDS},
            "unresolved_fields": list(TARGET_FIELDS),
            "provenance": {},
        }
    )
    fac, unresolved = collect_current_facility_industrial(
        object(), _FAC_ID, SafeIndustrialConsumerInput(worker_count=50)
    )
    assert isinstance(fac, dict)
    assert "worker_count" in fac
    assert fac["worker_count"] == 50


def test_K02_industrial_collection_error_propagated(monkeypatch):
    from services import safe_industrial_leg_runtime as R

    _patch_work_mat_eq(monkeypatch)
    monkeypatch.setattr(
        R, "assemble_industrial_marketing_contract",
        lambda s, fid: (_ for _ in ()).throw(RuntimeError("DB fail")),
    )
    with pytest.raises(CollectionError):
        collect_current_facility_industrial(object(), _FAC_ID, SafeIndustrialConsumerInput())


def test_K03_building_no_h01_db_write(monkeypatch):
    """allow_h01_db_write=False 강제 — hydrate_factory_h01 호출 금지."""
    _patch_work_mat_eq(monkeypatch)
    _called = {"hydrate": False}

    def _fake_hydrate(s, fid):
        _called["hydrate"] = True
        return {"updated": True, "floor_count": 5, "building_height": 10.0, "mgm_bldrgst_pk": "pk"}

    monkeypatch.setattr("services.building_register_hydration.hydrate_factory_h01", _fake_hydrate)

    fac_row = {
        "has_boiler": True, "is_multi_use": False,
        "employee_count": 30, "building_area": 1000.0, "elevator_count": 1,
        "floor_count": None, "building_height": None,
        "building_register_updated_at": None,
        "bdmgtsn": None, "mgm_bldrgst_pk": None,
    }
    supa = _FakeSupa({"factories": [fac_row]})
    fac, unresolved, h01_absent = collect_current_facility_building(
        supa, _FAC_ID, SafeBuildingConsumerInput()
    )
    assert not _called["hydrate"], "H01 DB write must be blocked in compare path"
    assert isinstance(h01_absent, set)


def test_K04_building_returns_facility_dict(monkeypatch):
    _patch_work_mat_eq(monkeypatch)
    fac_row = {
        "has_boiler": True, "is_multi_use": False,
        "employee_count": 30, "building_area": 1000.0, "elevator_count": 0,
        "floor_count": 3, "building_height": 12.0,
        "building_register_updated_at": "2026-01-01T00:00:00Z",
        "bdmgtsn": None, "mgm_bldrgst_pk": "PK1",
    }
    supa = _FakeSupa({"factories": [fac_row]})
    fac, unresolved, h01_absent = collect_current_facility_building(
        supa, _FAC_ID, SafeBuildingConsumerInput(worker_count=30)
    )
    assert isinstance(fac, dict)
    assert "worker_count" in fac


def test_K05_construction_bridge_error_becomes_collection_error(monkeypatch):
    from services import safe_construction_leg_runtime as CR

    _patch_work_mat_eq(monkeypatch)
    monkeypatch.setattr(
        CR, "assemble_construction_marketing_contract",
        lambda s, site_id: {"factory_id": None, "values": {}, "unresolved_fields": [], "provenance": {}},
    )
    monkeypatch.setattr(CR, "project_cst_process_codes", lambda codes: {})
    monkeypatch.setattr(CR, "project_cst_work_codes", lambda codes: {})
    monkeypatch.setattr(
        "services.safe_construction_leg_runtime._load_site_process_work_type_codes", lambda s, sid: []
    )
    monkeypatch.setattr(
        "services.safe_construction_leg_runtime._load_site_work_type_codes", lambda s, sid: []
    )
    with pytest.raises(CollectionError):
        collect_current_facility_construction(object(), _SITE_ID, SafeConstructionConsumerInput())


def test_K06_construction_returns_factory_id(monkeypatch):
    from services import safe_construction_leg_runtime as CR

    _patch_work_mat_eq(monkeypatch)
    monkeypatch.setattr(
        CR, "assemble_construction_marketing_contract",
        lambda s, site_id: {
            "factory_id": _FAC_ID,
            "values": {"worker_count": 10},
            "unresolved_fields": [],
            "provenance": {},
        },
    )
    monkeypatch.setattr(CR, "project_cst_process_codes", lambda codes: {})
    monkeypatch.setattr(CR, "project_cst_work_codes", lambda codes: {})
    monkeypatch.setattr(
        "services.safe_construction_leg_runtime._load_site_process_work_type_codes", lambda s, sid: []
    )
    monkeypatch.setattr(
        "services.safe_construction_leg_runtime._load_site_work_type_codes", lambda s, sid: []
    )
    fac, unresolved, factory_id = collect_current_facility_construction(
        object(), _SITE_ID, SafeConstructionConsumerInput()
    )
    assert factory_id == _FAC_ID
    assert isinstance(fac, dict)


# ══════════════════════════════════════════════════════════════════════════════
# S01~S22  compare_snapshot 통합
# ══════════════════════════════════════════════════════════════════════════════

from services.wp01_snapshot_compare.compare import compare_snapshot


def _patch_ind_collector(monkeypatch, facility: dict, unresolved: list = None):
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_industrial",
        lambda s, fid, ci, app3=None: (facility, unresolved or []),
    )


def _c10_supa(facility: dict, sector: str = "INDUSTRIAL") -> _FakeSupa:
    return _FakeSupa({"anonymous_diagnosis_results": [_c10_row(facility, sector=sector)]})


def _no_c10_supa() -> _FakeSupa:
    return _FakeSupa({"anonymous_diagnosis_results": []})


# S01 — UNCHANGED
def test_S01_unchanged(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "UNCHANGED"
    assert result["diff"] == []
    assert result["baseline_hash"] == result["current_hash"]


# S02 — CHANGED
def test_S02_changed(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V2)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "CHANGED"
    assert len(result["diff"]) >= 1
    changed_fields = {d["field"] for d in result["diff"]}
    assert "worker_count" in changed_fields


# S03 — CHANGED diff contains baseline/current values
def test_S03_changed_diff_values(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V2)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    worker_diff = next(d for d in result["diff"] if d["field"] == "worker_count")
    assert worker_diff["baseline_value"] == 50
    assert worker_diff["current_value"] == 80
    assert "change_type" in worker_diff


# S04 — BASELINE_REQUIRED (no C10 row)
def test_S04_baseline_required_no_row(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    result = compare_snapshot(_no_c10_supa(), sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "BASELINE_REQUIRED"
    assert result["diff"] == []
    assert result["baseline_hash"] is None
    assert result["baseline_snapshot_id"] is None


# S05 — BASELINE_REQUIRED (C10 row without facility_used)
def test_S05_baseline_required_no_facility_used(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _FakeSupa({"anonymous_diagnosis_results": [{
        "id": _DIAG_ID,
        "input_data": {"factory_id": _FAC_ID, "sector": "INDUSTRIAL"},
        "full_result": {"obligations_raw": []},
        "created_at": "2026-10-10T00:00:00Z",
        "source_type": "saas",
        "status": "ACTIVE",
    }]})
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "BASELINE_REQUIRED"


# S06 — UNRESOLVED (CollectionError)
def test_S06_unresolved_collection_error(monkeypatch):
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_industrial",
        lambda s, fid, ci, app3=None: (_ for _ in ()).throw(CollectionError("DB fail")),
    )
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "UNRESOLVED"
    assert "DB fail" in result.get("unresolved_reason", "")


# S07 — UNRESOLVED unknown sector
def test_S07_unresolved_unknown_sector(monkeypatch):
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="UNKNOWN", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "UNRESOLVED"


# S08 — sector field returned in result
def test_S08_sector_in_result(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["sector"] == "INDUSTRIAL"


# S09 — BUILDING H01 absent field → 항상 UNRESOLVED (기존 스냅샷에 값 여부 무관)
def test_S09_building_h01_absent_always_unresolved(monkeypatch):
    """H01 원천 확인 불가 → 기존 스냅샷에 값이 없어도 UNRESOLVED."""
    baseline = {"has_boiler": True}  # floor_count 없음
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_building",
        lambda s, fid, ci, **kw: ({"has_boiler": True}, [], {"floor_count"}),
    )
    supa = _c10_supa(baseline, sector="BUILDING")
    result = compare_snapshot(supa, sector="BUILDING", factory_id=_FAC_ID, consumer_input=SafeBuildingConsumerInput())
    assert result["status"] == "UNRESOLVED"
    assert "floor_count" in result.get("unresolved_reason", "")


# S10 — BUILDING H01 absent field in baseline → UNRESOLVED (regression check)
def test_S10_building_h01_absent_in_baseline_unresolved(monkeypatch):
    baseline = {"has_boiler": True, "floor_count": 5}
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_building",
        lambda s, fid, ci, **kw: ({"has_boiler": True}, [], {"floor_count"}),
    )
    supa = _c10_supa(baseline, sector="BUILDING")
    result = compare_snapshot(supa, sector="BUILDING", factory_id=_FAC_ID, consumer_input=SafeBuildingConsumerInput())
    assert result["status"] == "UNRESOLVED"


# S11 — CONSTRUCTION missing site_id → UNRESOLVED
def test_S11_construction_missing_site_id(monkeypatch):
    supa = _c10_supa(_FACILITY_V1, sector="CONSTRUCTION")
    result = compare_snapshot(
        supa, sector="CONSTRUCTION", factory_id=_FAC_ID, consumer_input=SafeConstructionConsumerInput(),
        site_id=None,
    )
    assert result["status"] == "UNRESOLVED"


# S12 — CONSTRUCTION UNCHANGED
def test_S12_construction_unchanged(monkeypatch):
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_construction",
        lambda s, sid, ci, **kw: (_FACILITY_V1, [], _FAC_ID),
    )
    supa = _c10_supa(_FACILITY_V1, sector="CONSTRUCTION")
    result = compare_snapshot(
        supa, sector="CONSTRUCTION", factory_id=_FAC_ID,
        consumer_input=SafeConstructionConsumerInput(), site_id=_SITE_ID,
    )
    assert result["status"] == "UNCHANGED"


# S13 — CONSTRUCTION CHANGED
def test_S13_construction_changed(monkeypatch):
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_construction",
        lambda s, sid, ci, **kw: (_FACILITY_V2, [], _FAC_ID),
    )
    supa = _c10_supa(_FACILITY_V1, sector="CONSTRUCTION")
    result = compare_snapshot(
        supa, sector="CONSTRUCTION", factory_id=_FAC_ID,
        consumer_input=SafeConstructionConsumerInput(), site_id=_SITE_ID,
    )
    assert result["status"] == "CHANGED"


# S14 — unresolved_fields preserved in result
def test_S14_unresolved_fields_in_result(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1, unresolved=["ksic_major"])
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert "ksic_major" in result["unresolved_fields"]


# S15 — UNCHANGED: both hashes equal
def test_S15_unchanged_hashes_equal(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["baseline_hash"] is not None
    assert result["current_hash"] is not None
    assert result["baseline_hash"] == result["current_hash"]


# S16 — CHANGED: hashes differ
def test_S16_changed_hashes_differ(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V2)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["baseline_hash"] != result["current_hash"]


# S17 — DB 오류 → UNRESOLVED (not BASELINE_REQUIRED)
def test_S17_db_error_returns_unresolved(monkeypatch):
    """C10 조회 자체 실패 → UNRESOLVED, not BASELINE_REQUIRED."""
    class _BadSupa:
        def table(self, *_):
            raise RuntimeError("Connection refused")

    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    result = compare_snapshot(_BadSupa(), sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "UNRESOLVED"
    assert result["baseline_hash"] is None


# S18 — 다른 섹터 C10 row → BASELINE_REQUIRED
def test_S18_wrong_sector_returns_baseline_required(monkeypatch):
    """BUILDING 섹터 C10 행을 INDUSTRIAL 비교에서 사용하면 안 됨."""
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [_c10_row(_FACILITY_V1, sector="BUILDING")]
    })
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "BASELINE_REQUIRED"


# S19 — baseline_snapshot_id 포함 반환
def test_S19_baseline_snapshot_id_returned(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["baseline_snapshot_id"] == _DIAG_ID


# S20 — Appendix3 active → app3_projection passed to collector
def test_S20_app3_projection_passed_to_collector(monkeypatch):
    received_app3 = {"called": None}

    def _fake_collector(s, fid, ci, app3=None):
        received_app3["called"] = app3
        return (_FACILITY_V1, [])

    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.collect_current_facility_industrial",
        _fake_collector,
    )
    supa = _c10_supa(_FACILITY_V1)
    _fake_app3 = {"appendix3_item_no": 1}
    compare_snapshot(
        supa,
        sector="INDUSTRIAL",
        factory_id=_FAC_ID,
        consumer_input=SafeIndustrialConsumerInput(),
        app3_projection=_fake_app3,
    )
    assert received_app3["called"] == _fake_app3


# S21 — diff entry has change_type field
def test_S21_diff_has_change_type(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V2)
    supa = _c10_supa(_FACILITY_V1)
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    for entry in result["diff"]:
        assert "change_type" in entry
        assert entry["change_type"] in ("ADDED", "REMOVED", "CHANGED")


# S22 — EXPIRED status row → BASELINE_REQUIRED
def test_S22_expired_status_row_baseline_required(monkeypatch):
    _patch_ind_collector(monkeypatch, _FACILITY_V1)
    supa = _FakeSupa({
        "anonymous_diagnosis_results": [_c10_row(_FACILITY_V1, status="EXPIRED")]
    })
    result = compare_snapshot(supa, sector="INDUSTRIAL", factory_id=_FAC_ID, consumer_input=SafeIndustrialConsumerInput())
    assert result["status"] == "BASELINE_REQUIRED"


# ══════════════════════════════════════════════════════════════════════════════
# R01~R11  라우터 엔드포인트
# ══════════════════════════════════════════════════════════════════════════════

from main import app


def _user(company_id: str = _COMPANY_ID) -> dict:
    return {"id": str(uuid4()), "company_id": company_id, "email": "t@test.com"}


def _auth_header(token: str = "Bearer tok") -> dict:
    return {"authorization": token}


def _stub_auth(monkeypatch, user: dict):
    monkeypatch.setattr("routers.legal_engine.get_current_user", lambda *_, **__: user)


def _stub_factory_own(monkeypatch, ok: bool = True):
    if ok:
        monkeypatch.setattr("routers.legal_engine._ensure_factory_own", lambda s, fid, u: None)
    else:
        monkeypatch.setattr(
            "routers.legal_engine._ensure_factory_own",
            lambda s, fid, u: (_ for _ in ()).throw(HTTPException(404, "not found")),
        )


def _stub_saas(monkeypatch):
    monkeypatch.setattr("routers.legal_engine.require_active_company_saas", lambda s, cid: None)


def _stub_supabase(monkeypatch, tables: dict = None):
    monkeypatch.setattr("routers.legal_engine.get_supabase", lambda: _FakeSupa(tables or {}))


def _stub_compare(monkeypatch, result: dict):
    monkeypatch.setattr(
        "services.wp01_snapshot_compare.compare.compare_snapshot",
        lambda *a, **kw: result,
    )


def _stub_app3(monkeypatch, projection=None):
    monkeypatch.setattr(
        "routers.legal_engine.check_saas_appendix3_contract",
        lambda s, fid, sector, inp: projection,
    )


_UNCHANGED_RESULT = {
    "status": "UNCHANGED",
    "diff": [],
    "unresolved_fields": [],
    "h01_absent_fields": [],
    "baseline_snapshot_id": _DIAG_ID,
    "baseline_hash": "abc",
    "current_hash": "abc",
    "sector": "INDUSTRIAL",
}


client = TestClient(app, raise_server_exceptions=True)


# R01 — INDUSTRIAL compare: get_current_user 예외가 엔드포인트 밖으로 전파됨
def test_R01_industrial_unauthenticated(monkeypatch):
    compare_called = {"called": False}

    def _deny(*_, **__):
        raise HTTPException(status_code=401, detail="인증 필요")

    def _track_compare(*_, **__):
        compare_called["called"] = True
        return {"status": "UNCHANGED"}

    _stub_supabase(monkeypatch)
    monkeypatch.setattr("routers.legal_engine.get_current_user", _deny)
    monkeypatch.setattr("services.wp01_snapshot_compare.compare.compare_snapshot", _track_compare)

    import routers.legal_engine as LE
    from schemas.legal_engine import LegCompareIndustrialBody, SafeIndustrialConsumerInput
    import asyncio
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            LE.compare_industrial_snapshot(
                LegCompareIndustrialBody(factory_id=_FAC_ID, input=SafeIndustrialConsumerInput()),
                authorization="Bearer bad_token",
            )
        )
    assert exc_info.value.status_code == 401
    assert not compare_called["called"]


# R02 — INDUSTRIAL compare ownership 실패 → 404 (compare 미호출)
def test_R02_industrial_ownership_fail(monkeypatch):
    compare_called = {"called": False}
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch, ok=False)

    def _track_compare(*_, **__):
        compare_called["called"] = True
        return {"status": "UNCHANGED"}

    monkeypatch.setattr("services.wp01_snapshot_compare.compare.compare_snapshot", _track_compare)

    import routers.legal_engine as LE
    from schemas.legal_engine import LegCompareIndustrialBody, SafeIndustrialConsumerInput
    import asyncio
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            LE.compare_industrial_snapshot(
                LegCompareIndustrialBody(factory_id=_FAC_ID, input=SafeIndustrialConsumerInput()),
                authorization="Bearer tok",
            )
        )
    assert exc_info.value.status_code == 404
    assert not compare_called["called"]


# R03 — INDUSTRIAL compare 성공 → status/data envelope
def test_R03_industrial_compare_success(monkeypatch):
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch)
    _stub_saas(monkeypatch)
    _stub_app3(monkeypatch)
    _stub_compare(monkeypatch, _UNCHANGED_RESULT)
    resp = client.post(
        "/legal-engine/diagnose/compare/industrial",
        json={"factory_id": _FAC_ID, "input": {}},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["status"] == "UNCHANGED"


# R04 — BUILDING compare 성공
def test_R04_building_compare_success(monkeypatch):
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch)
    _stub_saas(monkeypatch)
    _stub_app3(monkeypatch)
    _stub_compare(monkeypatch, {**_UNCHANGED_RESULT, "sector": "BUILDING"})
    resp = client.post(
        "/legal-engine/diagnose/compare/building",
        json={"factory_id": _FAC_ID, "input": {}},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["sector"] == "BUILDING"


# R05 — BUILDING compare ownership 실패 → 404 (compare 미호출)
def test_R05_building_ownership_fail(monkeypatch):
    compare_called = {"called": False}
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch, ok=False)

    def _track_compare(*_, **__):
        compare_called["called"] = True
        return {"status": "UNCHANGED"}

    monkeypatch.setattr("services.wp01_snapshot_compare.compare.compare_snapshot", _track_compare)

    import routers.legal_engine as LE
    from schemas.legal_engine import LegCompareBuildingBody, SafeBuildingConsumerInput
    import asyncio
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            LE.compare_building_snapshot(
                LegCompareBuildingBody(factory_id=_FAC_ID, input=SafeBuildingConsumerInput()),
                authorization="Bearer tok",
            )
        )
    assert exc_info.value.status_code == 404
    assert not compare_called["called"]


# R06 — CONSTRUCTION compare site 없으면 404
def test_R06_construction_site_not_found(monkeypatch):
    _stub_auth(monkeypatch, _user())
    monkeypatch.setattr(
        "routers.legal_engine.get_supabase",
        lambda: _FakeSupa({"construction_sites": []}),
    )
    resp = client.post(
        "/legal-engine/diagnose/compare/construction",
        json={"site_id": _SITE_ID, "input": {}},
        headers=_auth_header(),
    )
    assert resp.status_code == 404


# R07 — CONSTRUCTION compare factory_id 없으면 409
def test_R07_construction_no_factory_id(monkeypatch):
    _stub_auth(monkeypatch, _user())
    site_row = {"id": _SITE_ID, "company_id": _COMPANY_ID, "factory_id": None}
    monkeypatch.setattr(
        "routers.legal_engine.get_supabase",
        lambda: _FakeSupa({"construction_sites": [site_row]}),
    )
    monkeypatch.setattr("routers.legal_engine._ensure_own_company", lambda cid, u, s, msg: None)
    monkeypatch.setattr("routers.legal_engine.require_active_company_saas", lambda s, cid: None)
    resp = client.post(
        "/legal-engine/diagnose/compare/construction",
        json={"site_id": _SITE_ID, "input": {}},
        headers=_auth_header(),
    )
    assert resp.status_code == 409


# R08 — CONSTRUCTION compare 성공
def test_R08_construction_compare_success(monkeypatch):
    _stub_auth(monkeypatch, _user())
    site_row = {"id": _SITE_ID, "company_id": _COMPANY_ID, "factory_id": _FAC_ID}
    monkeypatch.setattr(
        "routers.legal_engine.get_supabase",
        lambda: _FakeSupa({"construction_sites": [site_row]}),
    )
    monkeypatch.setattr("routers.legal_engine._ensure_own_company", lambda cid, u, s, msg: None)
    monkeypatch.setattr("routers.legal_engine.require_active_company_saas", lambda s, cid: None)
    _stub_app3(monkeypatch)
    _stub_compare(monkeypatch, {**_UNCHANGED_RESULT, "sector": "CONSTRUCTION"})
    resp = client.post(
        "/legal-engine/diagnose/compare/construction",
        json={"site_id": _SITE_ID, "input": {}},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["sector"] == "CONSTRUCTION"


# R09 — compare endpoint LEG 미호출 (run_leg_diagnosis 호출 없음)
def test_R09_no_leg_execution(monkeypatch):
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch)
    _stub_saas(monkeypatch)
    _stub_app3(monkeypatch)
    _leg_called = {"called": False}

    def _fake_run_leg(step1):
        _leg_called["called"] = True
        return {}

    monkeypatch.setattr("services.leg_diagnosis_svc.run_leg_diagnosis", _fake_run_leg)
    _stub_compare(monkeypatch, _UNCHANGED_RESULT)
    client.post(
        "/legal-engine/diagnose/compare/industrial",
        json={"factory_id": _FAC_ID, "input": {}},
        headers=_auth_header(),
    )
    assert not _leg_called["called"], "compare endpoint must NOT call run_leg_diagnosis"


# R10 — INDUSTRIAL compare: check_saas_appendix3_contract 호출됨
def test_R10_industrial_app3_contract_called(monkeypatch):
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch)
    _stub_saas(monkeypatch)
    _stub_compare(monkeypatch, _UNCHANGED_RESULT)
    app3_called = {"called": False}

    def _track_app3(s, fid, sector, inp):
        app3_called["called"] = True
        return None

    monkeypatch.setattr("routers.legal_engine.check_saas_appendix3_contract", _track_app3)
    client.post(
        "/legal-engine/diagnose/compare/industrial",
        json={"factory_id": _FAC_ID, "input": {}},
        headers=_auth_header(),
    )
    assert app3_called["called"], "compare endpoint must call check_saas_appendix3_contract for input parity"


# R11 — baseline_snapshot_id가 응답 data에 포함됨
def test_R11_baseline_snapshot_id_in_response(monkeypatch):
    _stub_supabase(monkeypatch)
    _stub_auth(monkeypatch, _user())
    _stub_factory_own(monkeypatch)
    _stub_saas(monkeypatch)
    _stub_app3(monkeypatch)
    _stub_compare(monkeypatch, _UNCHANGED_RESULT)
    resp = client.post(
        "/legal-engine/diagnose/compare/industrial",
        json={"factory_id": _FAC_ID, "input": {}},
        headers=_auth_header(),
    )
    assert resp.json()["data"]["baseline_snapshot_id"] == _DIAG_ID
