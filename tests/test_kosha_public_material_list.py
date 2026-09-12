"""WP-3 current-snapshot list/stats. No live KOSHA/R2/DB writes."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.kosha_safety_materials.display import (
    CATALOG_EMBED,
    CurrentSnapshotUnavailable,
    ITEMS,
    MemoryDisplayStore,
    list_current_materials,
    load_public_material,
    stats_current_materials,
)
from services.kosha_safety_materials.writer import CATALOG

from tests.test_kosha_public_material_display import (
    FakeSigner,
    _pdf_asset,
    _seed_member,
    _version,
)


def _seed_library(store: MemoryDisplayStore) -> MemoryDisplayStore:
    store.snapshots.append(
        {"id": "snap1", "status": "COMPLETED", "completed_at": "2026-09-12T00:00:00+09:00"}
    )
    store.snapshots.append(
        {"id": "old", "status": "COMPLETED", "completed_at": "2026-01-01T00:00:00+09:00"}
    )
    rows = [
        ("c1", "지게차 안전", "EDUCATION", "MANUFACTURING", "2026-09-01T00:00:00"),
        ("c2", "추락 예방", "GUIDE", "CONSTRUCTION", "2026-09-02T00:00:00"),
        ("c3", "지게차 사고", "CASE_STUDY", "MANUFACTURING", "2026-09-02T00:00:00"),
        ("c4", "포스터", "POSTER", "SERVICE", "2026-08-01T00:00:00"),
        ("c5", "같은시각", "EDUCATION", "MANUFACTURING", "2026-09-02T00:00:00"),
    ]
    for mid, title, cat, sec, ts in rows:
        store.items.append({"snapshot_id": "snap1", "material_id": mid})
        store.catalog[mid] = {
            "id": mid,
            "title": title,
            "url": "https://k/" + mid,
            "category": cat,
            "industry_category": sec,
            "collected_at": ts,
        }
    store.catalog["hist"] = {
        "id": "hist",
        "title": "검사기술 상담사례집",
        "url": "https://k/h",
        "category": "EDUCATION",
        "industry_category": "MANUFACTURING",
        "collected_at": "2026-09-10T00:00:00",
    }
    store.items.append({"snapshot_id": "old", "material_id": "hist"})
    return store


def _client(monkeypatch, store):
    import routers.kosha_public_materials as mod

    monkeypatch.setattr(mod, "get_store", lambda: store)

    def _no_r2():
        raise AssertionError("R2 signer must not be used for list/stats")

    monkeypatch.setattr(mod, "get_signer", _no_r2)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


def test_list_current_members_only():
    st = _seed_library(MemoryDisplayStore())
    w0 = st.writes
    body = list_current_materials(st)
    ids = [i["id"] for i in body["items"]]
    assert body["snapshot_id"] == "snap1"
    assert body["total"] == 5
    assert "hist" not in ids
    assert set(ids) == {"c1", "c2", "c3", "c4", "c5"}
    assert st.writes == w0 == 0
    assert st.kosha_network == 0
    assert st.r2_put == 0 and st.r2_delete == 0


def test_historical_only_catalog_row_excluded_even_with_matching_title():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, q="검사기술")
    assert body["items"] == []
    assert body["total"] == 0


def test_title_search_current_scope_only():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, q="지게차")
    ids = [i["id"] for i in body["items"]]
    assert body["total"] == 2
    assert ids == ["c3", "c1"]
    assert "hist" not in ids


def test_category_filter():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, cat="EDUCATION")
    ids = [i["id"] for i in body["items"]]
    assert body["total"] == 2
    assert ids == ["c5", "c1"]


def test_sector_filter():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, sec="MANUFACTURING")
    ids = [i["id"] for i in body["items"]]
    assert body["total"] == 3
    assert ids == ["c3", "c5", "c1"]


def test_combined_filters():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, q="지게차", cat="EDUCATION", sec="MANUFACTURING")
    assert body["total"] == 1
    assert [i["id"] for i in body["items"]] == ["c1"]
    assert body["items"][0]["sector"] == "MANUFACTURING"


def test_pagination_no_overlap_or_gap():
    st = _seed_library(MemoryDisplayStore())
    p1 = list_current_materials(st, page=1, page_size=2)
    p2 = list_current_materials(st, page=2, page_size=2)
    p3 = list_current_materials(st, page=3, page_size=2)
    ids = [i["id"] for i in p1["items"] + p2["items"] + p3["items"]]
    assert p1["total"] == p2["total"] == p3["total"] == 5
    assert ids == ["c2", "c3", "c5", "c1", "c4"]
    assert len(set(ids)) == 5


def test_deterministic_ordering_collected_at_desc_id_asc():
    st = _seed_library(MemoryDisplayStore())
    ids = [i["id"] for i in list_current_materials(st)["items"]]
    # 2026-09-02: c2, c3, c5 (id ASC) then c1 then c4
    assert ids == ["c2", "c3", "c5", "c1", "c4"]


def test_filtered_total_is_current_and_filtered():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, cat="POSTER")
    assert body["total"] == 1
    assert body["items"][0]["id"] == "c4"


def test_stats_total_and_categories_current_only():
    st = _seed_library(MemoryDisplayStore())
    stats = stats_current_materials(st)
    assert stats["snapshot_id"] == "snap1"
    assert stats["total"] == 5
    assert stats["categories"] == {
        "EDUCATION": 2,
        "CASE_STUDY": 1,
        "GUIDE": 1,
        "POSTER": 1,
    }


def test_no_completed_snapshot_raises():
    st = MemoryDisplayStore()
    st.catalog["x"] = {"id": "x", "title": "누적"}
    with pytest.raises(CurrentSnapshotUnavailable):
        list_current_materials(st)
    with pytest.raises(CurrentSnapshotUnavailable):
        stats_current_materials(st)


def test_empty_filter_result_is_200_empty(monkeypatch):
    st = _seed_library(MemoryDisplayStore())
    c = _client(monkeypatch, st)
    r = c.get("/public/kosha/materials", params={"q": "없는제목XYZ"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_router_list_and_stats_no_r2_no_writes(monkeypatch):
    st = _seed_library(MemoryDisplayStore())
    w0 = st.writes
    c = _client(monkeypatch, st)
    lst = c.get("/public/kosha/materials")
    stt = c.get("/public/kosha/materials/stats")
    assert lst.status_code == 200
    assert stt.status_code == 200
    assert lst.json()["total"] == 5
    assert stt.json()["total"] == 5
    assert "hist" not in [i["id"] for i in lst.json()["items"]]
    assert st.writes == w0 == 0
    assert st.kosha_network == 0


def test_router_503_without_snapshot(monkeypatch):
    st = MemoryDisplayStore()
    c = _client(monkeypatch, st)
    assert c.get("/public/kosha/materials").status_code == 503
    assert c.get("/public/kosha/materials").json()["detail"] == "CURRENT_SNAPSHOT_UNAVAILABLE"
    assert c.get("/public/kosha/materials/stats").status_code == 503
    assert c.get("/public/kosha/materials/stats").json()["detail"] == "CURRENT_SNAPSHOT_UNAVAILABLE"


def test_stats_route_not_captured_as_material_id(monkeypatch):
    st = _seed_library(MemoryDisplayStore())
    c = _client(monkeypatch, st)
    r = c.get("/public/kosha/materials/stats")
    assert r.status_code == 200
    assert "categories" in r.json()


def test_listed_items_are_detail_eligible():
    st = _seed_library(MemoryDisplayStore())
    listed = list_current_materials(st)["items"]
    sg = FakeSigner()
    for item in listed:
        body = load_public_material(item["id"], store=st, signer=sg)
        assert body is not None
        assert body["id"] == item["id"]
    assert load_public_material("hist", store=st, signer=sg) is None
    assert sg.presigns == 0
    assert st.writes == 0


def test_page_size_capped_at_100():
    st = _seed_library(MemoryDisplayStore())
    body = list_current_materials(st, page_size=500)
    assert body["page_size"] == 100


def test_supabase_list_uses_inner_join_not_python_in_list():
    class FakeResult:
        def __init__(self):
            self.data = []
            self.count = 0

    class FakeQuery:
        def __init__(self):
            self.ops = []

        def select(self, *a, **k):
            self.ops.append(("select", a, k))
            return self

        def eq(self, *a):
            self.ops.append(("eq", a))
            return self

        def ilike(self, *a):
            self.ops.append(("ilike", a))
            return self

        def order(self, *a, **k):
            self.ops.append(("order", a, k))
            return self

        def range(self, *a):
            self.ops.append(("range", a))
            return self

        def limit(self, n):
            self.ops.append(("limit", n))
            return self

        def execute(self):
            return FakeResult()

    class FakeSB:
        def __init__(self):
            self.q = FakeQuery()

        def table(self, name):
            assert name == CATALOG
            return self.q

    from services.kosha_safety_materials.display import SupabaseDisplayStore

    sb = FakeSB()
    store = SupabaseDisplayStore(sb=sb)
    store.list_current("snap1", q="지게차", cat="EDUCATION", sec="MANUFACTURING", page=2, page_size=20)
    q = sb.q
    selects = [op for op in q.ops if op[0] == "select"]
    assert selects
    select_sql = selects[0][1][0]
    assert CATALOG_EMBED in select_sql
    assert "!inner" in select_sql
    eqs = [op[1] for op in q.ops if op[0] == "eq"]
    assert (f"{ITEMS}.snapshot_id", "snap1") in eqs
    assert ("category", "EDUCATION") in eqs
    assert ("industry_category", "MANUFACTURING") in eqs
    in_ops = [op for op in q.ops if op[0] == "in"]
    assert in_ops == []
    ranges = [op for op in q.ops if op[0] == "range"]
    assert ranges == [("range", (20, 39))]


def test_wp2_detail_regression_still_signs(monkeypatch):
    import routers.kosha_public_materials as mod

    st = _seed_member(MemoryDisplayStore())
    st.assets.append(_pdf_asset())
    st.versions.append(_version())
    monkeypatch.setattr(mod, "get_store", lambda: st)
    monkeypatch.setattr(mod, "get_signer", lambda: FakeSigner())
    app = FastAPI()
    app.include_router(mod.router)
    r = TestClient(app).get("/public/kosha/materials/m1")
    assert r.status_code == 200
    assert r.json()["assets"][0]["internally_available"] is True
