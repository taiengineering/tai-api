"""WO-SAFETY-LIBRARY-001 WP-1C-4A — safety-material snapshot sync."""
from __future__ import annotations

import asyncio
import hashlib
import inspect

import services.kosha_safety_material_sync as ksync
from routers import kosha_collect as kc
from services.kosha_safety_material_sync import (
    MemorySnapshotStore,
    catalog_row_from_official,
    classify_material,
    classify_sets,
    extract_medseq,
    kosha_service_key,
    make_id,
    media_list_params,
    normalize_db_row,
    normalize_official_item,
    snapshot_hash,
    sync_safety_materials,
    validate_complete,
)


def _raw(seq, title, date="20260101"):
    return {
        "MED_URL": f"https://www.kosha.or.kr/kosha/data/masterDetail1.do?medSeq={seq}",
        "MED_SJ_NM": title,
        "MED_COMPY_DY": date,
        "MED_CL_NM": "자료",
    }


def _fetch(items, page_size=2):
    declared = len(items)

    async def fetch_page(page):
        start = (page - 1) * page_size
        return items[start:start + page_size], declared

    return fetch_page


def _db_row_from_raw(raw, **overrides):
    mapped = catalog_row_from_official(raw)
    mapped.update(overrides)
    return mapped


def test_media_list_params_no_ctgr04():
    p = media_list_params(1)
    assert p == {"callApiId": "1030", "pageNo": 1, "numOfRows": 100}
    assert "ctgr04_kr" not in p


def test_medseq_url_extraction():
    seq, st = extract_medseq("https://www.kosha.or.kr/x?medSeq=050119")
    assert seq == "50119" and st == ksync.VALID_MEDSEQ
    seq, st = extract_medseq("https://www.kosha.or.kr/x")
    assert seq is None and st == ksync.MISSING_MEDSEQ
    seq, st = extract_medseq("https://www.kosha.or.kr/x?medSeq=abc")
    assert seq == "abc" and st == ksync.INVALID_MEDSEQ
    seq, st = extract_medseq("https://www.kosha.or.kr/x?medSeq=")
    assert seq is None and st == ksync.INVALID_MEDSEQ


def test_existing_id_compatibility_md5_url_title():
    url = "https://www.kosha.or.kr/kosha/data/masterDetail1.do?medSeq=50119"
    title = "건설현장 포스터"
    expected = hashlib.md5(f"{url}|{title}".encode()).hexdigest()[:16]
    assert make_id("mat", url, title) == expected
    raw = _raw("50119", title)
    assert catalog_row_from_official(raw)["id"] == expected
    raw_seq = dict(raw)
    raw_seq["MED_SEQ"] = "legacy-seq"
    assert catalog_row_from_official(raw_seq)["id"] == "legacy-seq"


def test_category_maps_to_industry_category_not_sector():
    row = catalog_row_from_official(_raw("1", "건설현장 포스터"))
    assert row["category"] == "POSTER"
    assert row["industry_category"] == "CONSTRUCTION"
    assert "sector" not in row
    assert classify_material("제조업 프레스 체크리스트") == ("CHECKLIST", "MANUFACTURING")


def test_empty_error_page_does_not_count_as_declared_change():
    items = [_raw(1, "a"), _raw(2, "b")]

    async def fetch_page(page):
        if page == 1:
            return items, 2
        return [], 0

    result = asyncio.run(ksync.fetch_official_full(fetch_page, max_pages=5, page_size=100))
    assert result["ok"] is True
    assert result["declared_total"] == 2
    assert len(result["items"]) == 2


def test_full_pagination_declared_fetched_match():
    items = [_raw(i, f"t{i}") for i in range(1, 6)]
    result = asyncio.run(ksync.fetch_official_full(_fetch(items, page_size=2), max_pages=10, page_size=2))
    assert result["ok"] is True
    assert result["declared_total"] == 5
    assert len(result["items"]) == 5
    gate = validate_complete(5, [normalize_official_item(x) for x in result["items"]])
    assert gate["ok"] is True
    assert gate["fetched_count"] == gate["unique_count"] == 5


def test_declared_mismatch_dml0():
    items = [_raw(i, f"t{i}") for i in range(1, 4)]

    async def fetch_page(page):
        chunk = items[(page - 1) * 2: page * 2]
        return chunk, 99

    store = MemorySnapshotStore()
    r = asyncio.run(sync_safety_materials(fetch_page=fetch_page, store=store, dry_run=False, max_pages=10))
    assert r["status"] == ksync.RESULT_FAILED
    assert "DECLARED_FETCHED_MISMATCH" in r["failure_reason"]
    assert r["catalog_dml"] == r["membership_dml"] == r["snapshot_dml"] == 0
    assert store.counts()[ksync.CATALOG_TABLE] == 0
    assert store.counts()[ksync.SNAPSHOT_TABLE] == 0


def test_duplicate_medseq_dml0():
    items = [_raw(7, "a"), _raw(7, "b")]
    store = MemorySnapshotStore()
    r = asyncio.run(sync_safety_materials(
        fetch_page=_fetch(items, page_size=10), store=store, dry_run=False, max_pages=5
    ))
    assert r["status"] == ksync.RESULT_FAILED
    assert "DUPLICATE_MEDSEQ" in r["failure_reason"]
    assert r["catalog_dml"] == 0 and r["snapshot_dml"] == 0


def test_invalid_medseq_dml0():
    bad = {
        "MED_URL": "https://www.kosha.or.kr/kosha/data/masterDetail1.do",
        "MED_SJ_NM": "no-seq",
        "MED_COMPY_DY": "20260101",
    }
    store = MemorySnapshotStore()
    r = asyncio.run(sync_safety_materials(
        fetch_page=_fetch([bad], page_size=10), store=store, dry_run=False, max_pages=5
    ))
    assert r["status"] == ksync.RESULT_FAILED
    assert "INVALID_MEDSEQ" in r["failure_reason"]
    assert r["catalog_dml"] == 0 and r["snapshot_dml"] == 0


def test_set_diff_buckets():
    off_keep = _official_item(_raw(1, "keep", "20240101"))
    off_new = _official_item(_raw(2, "brand new", "20250101"))
    off_possible = _official_item(_raw(3, "same title", "20230101"))
    off_amb = _official_item(_raw(4, "amb title", "20220101"))

    db = [
        normalize_db_row(_db_row_from_raw(_raw(1, "keep", "20240101"))),
        normalize_db_row(_db_row_from_raw(_raw(90, "historical", "20100101"))),
        normalize_db_row(_db_row_from_raw(_raw(80, "same title", "20230101"))),
        normalize_db_row(_db_row_from_raw(_raw(70, "amb title", "20220101"))),
        normalize_db_row(_db_row_from_raw(_raw(71, "amb title", "20220101"))),
    ]
    diff = classify_sets([off_keep, off_new, off_possible, off_amb], db)
    assert len(diff["current_existing"]) == 1
    assert len(diff["current_new"]) == 3
    assert len(diff["historical_not_current"]) == 4
    assert {r["medseq"] for r in diff["historical_not_current"]} == {"90", "80", "70", "71"}
    assert len(diff["possible_id_or_url_change"]) == 1
    assert len(diff["ambiguous_title_date"]) == 1
    assert len(diff["current_new_exact"]) == 1
    assert diff["current_new_exact"][0]["medseq"] == "2"


def _official_item(raw):
    it = normalize_official_item(raw)
    return {
        "url": it.url,
        "title": it.title,
        "norm_title": ksync.normalize_title(it.title),
        "date": it.date,
        "medseq": it.medseq,
        "medseq_status": it.medseq_status,
        "catalog_id": it.catalog_id,
        "raw": it.raw,
        "published_raw": it.published_raw,
        "category": it.category,
        "industry_category": it.industry_category,
    }


def test_snapshot_hash_deterministic():
    a = [_raw(2, "b", "20250102"), _raw(1, "a", "20250101")]
    b = [_raw(1, "a", "20250101"), _raw(2, "b", "20250102")]
    ha = snapshot_hash([normalize_official_item(x).hash_row() for x in a])
    hb = snapshot_hash([normalize_official_item(x).hash_row() for x in b])
    assert ha == hb
    assert len(ha) == 64
    hc = snapshot_hash([normalize_official_item(_raw(1, "a", "20250199")).hash_row()])
    hd = snapshot_hash([normalize_official_item(_raw(1, "a", "20250101")).hash_row()])
    assert hc != hd


def test_dry_run_dml0_and_apply_current_new_only():
    existing_raw = _raw(1, "건설 포스터", "20240101")
    new_raw = _raw(2, "신규 가이드", "20260101")
    hist_raw = _raw(90, "과거 자료", "20100101")
    store = MemorySnapshotStore([
        _db_row_from_raw(existing_raw),
        _db_row_from_raw(hist_raw),
    ])
    before = store.counts()
    fetch = _fetch([existing_raw, new_raw], page_size=10)
    dry = asyncio.run(sync_safety_materials(fetch_page=fetch, store=store, dry_run=True, max_pages=5))
    assert dry["status"] == ksync.RESULT_DRY_RUN
    assert dry["catalog_dml"] == dry["membership_dml"] == dry["snapshot_dml"] == 0
    assert store.counts() == before
    assert dry["current_existing"] == 1
    assert dry["current_new"] == 1
    assert dry["historical"] == 1
    assert dry["possible"] == 0 and dry["ambiguous"] == 0

    applied = asyncio.run(sync_safety_materials(fetch_page=fetch, store=store, dry_run=False, max_pages=5))
    assert applied["status"] == ksync.RESULT_COMPLETED
    assert applied["snapshot_status"] == "COMPLETED"
    assert applied["catalog_dml"] == 1
    assert applied["membership_dml"] == 2
    assert store.catalog_updates == 0
    assert store.catalog_deletes == 0
    assert hist_raw["MED_URL"]
    hist_id = catalog_row_from_official(hist_raw)["id"]
    assert hist_id in store.catalog
    new_id = catalog_row_from_official(new_raw)["id"]
    assert new_id in store.catalog
    existing_id = catalog_row_from_official(existing_raw)["id"]
    # existing catalog row not rewritten
    assert store.catalog[existing_id]["title"] == "건설 포스터"

    second = asyncio.run(sync_safety_materials(fetch_page=fetch, store=store, dry_run=False, max_pages=5))
    assert second["status"] == ksync.RESULT_NO_CHANGE
    assert second["catalog_dml"] == 0
    assert second["membership_dml"] == 0
    assert second["snapshot_dml"] == 0
    assert second["snapshot_hash"] == applied["snapshot_hash"]
    completed = [s for s in store.snapshots if s["status"] == "COMPLETED"]
    assert len(completed) == 1


def test_start_page_gt_1_cannot_complete_snapshot():
    store = MemorySnapshotStore()
    r = asyncio.run(sync_safety_materials(
        fetch_page=_fetch([_raw(1, "t")], page_size=10),
        store=store,
        dry_run=False,
        start_page=101,
    ))
    assert r["status"] == ksync.RESULT_REJECTED
    assert r["snapshot_status"] is None
    assert store.snapshots == []
    assert r["catalog_dml"] == 0


def test_building_api_key_unavailable_to_kosha(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    monkeypatch.delenv("KOSHA_SERVICE_KEY", raising=False)
    monkeypatch.setenv("BUILDING_API_KEY", "building-only-key")
    assert kosha_service_key() == ""
    assert kc._get_service_key() == ""
    src = inspect.getsource(kosha_service_key)
    assert 'os.getenv("BUILDING_API_KEY"' not in src
    assert "os.getenv('BUILDING_API_KEY'" not in src
    src_router = inspect.getsource(kc)
    assert 'os.getenv("BUILDING_API_KEY"' not in src_router


def test_other_collector_regression_not_rewired():
    for fn in (
        kc._collect_accident_cases,
        kc._collect_construction_accidents,
        kc._collect_safety_light,
        kc._collect_risk_assessment,
        kc._collect_guide,
    ):
        src = inspect.getsource(fn)
        assert "sync_safety_materials" not in src
    sm = inspect.getsource(kc._collect_safety_materials)
    assert "sync_safety_materials" in sm
    assert "kosha_accident_cases" in inspect.getsource(kc._collect_accident_cases)
    assert "kosha_construction_accidents" in inspect.getsource(kc._collect_construction_accidents)
    assert "kosha_construction_safety_light" in inspect.getsource(kc._collect_safety_light)
    assert "kosha_risk_assessment" in inspect.getsource(kc._collect_risk_assessment)
    assert "kosha_guide" in inspect.getsource(kc._collect_guide)


def test_possible_excluded_from_catalog_insert():
    existing = _db_row_from_raw(_raw(80, "same title", "20230101"))
    official_possible = _raw(3, "same title", "20230101")
    official_keep = _raw(1, "keep", "20240101")
    store = MemorySnapshotStore([existing, _db_row_from_raw(official_keep)])
    r = asyncio.run(sync_safety_materials(
        fetch_page=_fetch([official_keep, official_possible], page_size=10),
        store=store,
        dry_run=False,
        max_pages=5,
    ))
    # membership cannot include POSSIBLE without catalog insert → FAILED, no COMPLETED
    assert r["status"] == ksync.RESULT_FAILED
    assert r["snapshot_status"] == "FAILED"
    assert catalog_row_from_official(official_possible)["id"] not in store.catalog
    assert store.catalog_deletes == 0
    assert store.catalog_updates == 0
