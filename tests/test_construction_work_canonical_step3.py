"""WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 STEP3 — construction_works canonical API wiring.

검증: WorkCreate/WorkPatch +5 canonical(strict numeric≥0 / strict boolean), CREATE(exclude_none:
false/0 보존·omitted 부재), PATCH sparse(canonical explicit-null clear·false/0 보존·legacy None skip),
GET list/detail 5필드 반출, ownership 실패 시 write 0, E15/legal/route 부재.
라우터 실행 테스트는 get_supabase·_ensure_site_own·_ensure_child_site_own 를 monkeypatch 하고
FakeSB(construction_works store)로 실 함수(create_work/update_work/get_work/list_works)를 호출한다.
"""
import copy
import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.construction_workflow_router as R
from schemas.construction import WorkCreate, WorkPatch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


SID = "11111111-1111-1111-1111-111111111111"
WID = "22222222-2222-2222-2222-222222222222"
C5 = ["work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
      "has_manual_heavy_handling", "manual_handling_weight_kg"]
NUM = ["work_height_m", "truck_loading_height_m", "manual_handling_weight_kg"]
BOOL = ["has_truck_loading_unloading", "has_manual_heavy_handling"]


# ── schema strict / semantics ──
def _wc(**kw):
    base = {"work_name": "용접", "work_date": "2026-09-01"}
    base.update(kw)
    return WorkCreate(**base)


def test_W3_01_create_has_5():
    for f in C5:
        assert f in WorkCreate.model_fields


def test_W3_02_patch_has_5():
    for f in C5:
        assert f in WorkPatch.model_fields


def test_W3_12_negative_rejected():
    for f in NUM:
        with pytest.raises(ValidationError):
            WorkPatch(**{f: -1})


def test_W3_13_numeric_string_rejected():
    for f in NUM:
        with pytest.raises(ValidationError):
            WorkPatch(**{f: "12"})


def test_W3_14_numeric_bool_rejected():
    for f in NUM:
        with pytest.raises(ValidationError):
            WorkPatch(**{f: True})


def test_numeric_int_float_zero_null_ok():
    assert WorkPatch(work_height_m=0).work_height_m == 0
    assert WorkPatch(work_height_m=3).work_height_m == 3
    assert WorkPatch(truck_loading_height_m=2.5).truck_loading_height_m == 2.5
    assert WorkPatch(work_height_m=None).work_height_m is None


def test_numeric_array_object_rejected():
    for bad in [[1], {"a": 1}]:
        with pytest.raises(ValidationError):
            WorkPatch(work_height_m=bad)


def test_W3_15_boolean_integer_rejected():
    for f in BOOL:
        for bad in [0, 1]:
            with pytest.raises(ValidationError):
                WorkPatch(**{f: bad})


def test_W3_16_boolean_string_rejected():
    for f in BOOL:
        for bad in ["true", "false"]:
            with pytest.raises(ValidationError):
                WorkPatch(**{f: bad})


def test_boolean_true_false_null_ok():
    assert WorkPatch(has_truck_loading_unloading=True).has_truck_loading_unloading is True
    assert WorkPatch(has_manual_heavy_handling=False).has_manual_heavy_handling is False
    assert WorkPatch(has_truck_loading_unloading=None).has_truck_loading_unloading is None


def test_W3_26_27_E_and_legal_absent_in_model():
    E = ["has_excavation", "has_demolition", "has_tower_crane", "has_confined_space",
         "has_asbestos_demo", "has_blasting", "has_diving", "has_asbestos",
         "has_chemical_substance", "has_gas", "has_high_pressure_gas", "has_water_tank",
         "is_energy_intensive", "is_multi_use"]
    for f in E:
        assert f not in WorkCreate.model_fields and f not in WorkPatch.model_fields
    for f in ["process_id", "subcontractor_id", "special_work_type", "hazard_codes", "worker_count"]:
        assert f in WorkCreate.model_fields


# ── router harness ──
class _Res:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Q:
    def __init__(self, store, counters):
        self.store = store
        self.c = counters
        self._f = {}
        self._upd = None
        self._ins = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._f[col] = val
        return self

    def limit(self, n):
        return self

    def range(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def update(self, d):
        self._upd = d
        self.c["writes"] += 1
        return self

    def insert(self, d):
        self._ins = d
        self.c["writes"] += 1
        return self

    def execute(self):
        self.c["reads"] += 1
        rows = [r for r in self.store if all(r.get(k) == v for k, v in self._f.items())]
        if self._upd is not None:
            for r in rows:
                r.update(self._upd)
            return _Res(copy.deepcopy(rows))
        if self._ins is not None:
            d = dict(self._ins)
            d.setdefault("id", WID)
            self.store.append(d)
            return _Res([copy.deepcopy(d)])
        return _Res(copy.deepcopy(rows), count=len(rows))


class _T:
    def __init__(self, store, counters):
        self.store = store
        self.c = counters

    def select(self, *a, **k):
        return _Q(self.store, self.c)

    def update(self, d):
        return _Q(self.store, self.c).update(d)

    def insert(self, d):
        return _Q(self.store, self.c).insert(d)

    def eq(self, *a, **k):
        return _Q(self.store, self.c).eq(*a, **k)


class FakeSB:
    def __init__(self, works=None):
        self.stores = {"construction_works": works if works is not None else []}
        self.counters = {"reads": 0, "writes": 0}

    def table(self, n):
        self.stores.setdefault(n, [])
        return _T(self.stores[n], self.counters)


def _env(monkeypatch, own_ok=True, works=None):
    sb = FakeSB(works=works)
    monkeypatch.setattr(R, "get_supabase", lambda: sb)

    def sown(s, sid, cur):
        if not own_ok:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")

    def cown(s, tbl, rid, cur, nf):
        if not own_ok:
            raise HTTPException(status_code=404, detail=nf)
        r = s.table(tbl).select("id").eq("id", rid).limit(1).execute()
        if not r.data:
            raise HTTPException(status_code=404, detail=nf)

    monkeypatch.setattr(R, "_ensure_site_own", sown)
    monkeypatch.setattr(R, "_ensure_child_site_own", cown)
    return sb


def test_W3_04_05_06_create_false_zero_omitted(monkeypatch):
    sb = _env(monkeypatch, works=[])
    _run(R.create_work(SID, _wc(has_truck_loading_unloading=False, manual_handling_weight_kg=0), {}))
    row = sb.stores["construction_works"][0]
    assert row["has_truck_loading_unloading"] is False and row["manual_handling_weight_kg"] == 0
    assert "work_height_m" not in row


def test_W3_19_create_own_pass(monkeypatch):
    sb = _env(monkeypatch, works=[])
    r = _run(R.create_work(SID, _wc(work_height_m=3.5), {}))
    assert r["status"] == "success" and sb.stores["construction_works"][0]["work_height_m"] == 3.5


def test_W3_20_create_foreign_404_no_write(monkeypatch):
    sb = _env(monkeypatch, own_ok=False, works=[])
    with pytest.raises(HTTPException) as e:
        _run(R.create_work(SID, _wc(), {}))
    assert e.value.status_code == 404 and sb.counters["writes"] == 0


def test_W3_07_patch_omitted_preserve(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID, "work_height_m": 9, "has_truck_loading_unloading": True}])
    _run(R.update_work(WID, WorkPatch(worker_count=5), {}))
    row = sb.stores["construction_works"][0]
    assert row["work_height_m"] == 9 and row["has_truck_loading_unloading"] is True and row["worker_count"] == 5


def test_W3_08_patch_null_clears_numeric(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID, "work_height_m": 9}])
    _run(R.update_work(WID, WorkPatch(**{"work_height_m": None}), {}))
    assert sb.stores["construction_works"][0]["work_height_m"] is None


def test_W3_09_patch_null_clears_boolean(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID, "has_manual_heavy_handling": True}])
    _run(R.update_work(WID, WorkPatch(**{"has_manual_heavy_handling": None}), {}))
    assert sb.stores["construction_works"][0]["has_manual_heavy_handling"] is None


def test_W3_10_patch_zero_preserved(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID}])
    _run(R.update_work(WID, WorkPatch(manual_handling_weight_kg=0), {}))
    assert sb.stores["construction_works"][0]["manual_handling_weight_kg"] == 0


def test_W3_11_patch_false_preserved(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID}])
    _run(R.update_work(WID, WorkPatch(has_truck_loading_unloading=False), {}))
    assert sb.stores["construction_works"][0]["has_truck_loading_unloading"] is False


def test_legacy_field_none_skip(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID, "work_height_m": 1}])
    _run(R.update_work(WID, WorkPatch(**{"notes": None, "work_height_m": None}), {}))
    row = sb.stores["construction_works"][0]
    assert "notes" not in row and row["work_height_m"] is None


def test_W3_17_list_carries_5(monkeypatch):
    sb = _env(monkeypatch, works=[{
        "id": WID, "site_id": SID, "is_active": True,
        "work_height_m": 3.5, "has_truck_loading_unloading": False,
        "truck_loading_height_m": 2.0, "has_manual_heavy_handling": True,
        "manual_handling_weight_kg": 25,
    }])
    r = _run(R.list_works(SID, None, None, None, 1, 20, {}))
    it = r["data"]["items"][0]
    for f in C5:
        assert f in it


def test_W3_18_detail_carries_5(monkeypatch):
    sb = _env(monkeypatch, works=[{"id": WID, "site_id": SID, "work_height_m": 3.5, "manual_handling_weight_kg": 0}])
    r = _run(R.get_work(WID, {}))
    assert r["data"]["work_height_m"] == 3.5 and r["data"]["manual_handling_weight_kg"] == 0


def test_W3_21_patch_foreign_404_no_write(monkeypatch):
    sb = _env(monkeypatch, own_ok=False, works=[{"id": WID, "site_id": SID}])
    with pytest.raises(HTTPException) as e:
        _run(R.update_work(WID, WorkPatch(work_height_m=1), {}))
    assert e.value.status_code == 404 and sb.counters["writes"] == 0


def test_W3_22_patch_missing_404(monkeypatch):
    sb = _env(monkeypatch, works=[])
    with pytest.raises(HTTPException) as e:
        _run(R.update_work(WID, WorkPatch(work_height_m=1), {}))
    assert e.value.status_code == 404 and sb.counters["writes"] == 0


def test_W3_24_25_28_static():
    src = open(R.__file__).read()
    assert "WORK_CANONICAL_NULL_CLEAR_FIELDS" in src
    E = ["has_excavation", "has_demolition", "has_tower_crane", "has_confined_space",
         "has_asbestos_demo", "has_blasting", "has_diving", "has_asbestos",
         "has_chemical_substance", "has_gas", "has_high_pressure_gas", "has_water_tank",
         "is_energy_intensive", "is_multi_use"]
    for e in E:
        assert e not in src
    assert "legal_" not in src
    assert "legal-diagnosis" not in src and "/works/legal" not in src
