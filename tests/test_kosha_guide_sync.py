"""OBJ-KG KOSHA GUIDE full-set current promotion — F1–F12."""
from __future__ import annotations

import inspect
import os
import pathlib
import re

from routers import kosha_collect as kc
from services import kosha_guide_sync as gsync
from services.kosha_guide_sync import (
    CATEGORY_NAME_BY_CODE,
    EXPECTED_FIELDS,
    SOURCE_CALL_API_ID,
    SOURCE_PATH,
    MemoryGuideStore,
    official_fetch_page,
    sync_kosha_guides,
)

SQL = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..",
    "supabase",
    "migrations",
    "20260913_kosha_guide_current_snapshot.sql",
))

OK_URL = "https://portal.kosha.or.kr/openapi/v1/file/down/FL00015883045/7"
CTC_URL = "https://portal.kosha.or.kr/openapi/v1/file/down/CTC2026012909222643246624/1"


def _item(no, title="가이드", date="2018-11-27", url=OK_URL):
    return {
        "techGdlnNo": no,
        "techGdlnNm": title,
        "techGdlnOfancYmd": date,
        "fileDownloadUrl": url,
    }


def _page(items, total):
    return {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {
            "pageNo": 1,
            "numOfRows": len(items),
            "totalCount": total,
            "items": {"item": items},
        },
    }


def _fetch(items, page_size=2, totals=None):
    declared = len(items)

    def fetch_page(page_no, num_of_rows):
        start = (page_no - 1) * page_size
        chunk = items[start:start + page_size]
        total = declared if totals is None else totals[min(page_no - 1, len(totals) - 1)]
        return _page(chunk, total)

    return fetch_page


def _run(items, store=None, dry_run=False, page_size=2, fetch_page=None):
    return sync_kosha_guides(
        dry_run=dry_run,
        fetch_page=fetch_page or _fetch(items, page_size=page_size),
        store=store if store is not None else MemoryGuideStore(),
        page_size=page_size,
    )


def test_f1_valid_two_page_completed():
    items = [
        _item("A-1-2018", "구리"),
        _item("A-6-2018", "납"),
        _item("G-1-2018", "일반"),
    ]
    store = MemoryGuideStore()
    r = _run(items, store=store, page_size=2)
    assert r.status == "COMPLETED"
    assert r.declared == r.fetched == r.unique == 3
    assert r.duplicates == 0
    assert r.call_api_id == "1050"
    assert r.source_path == SOURCE_PATH
    assert len(store.current_ids()) == 3
    assert store.catalog["A-1-2018"]["metadata_license"] == "CLEAR"
    assert store.catalog["A-1-2018"]["original_rights_mode"] == "LINK_ONLY"
    assert store.catalog["A-1-2018"]["binary_storage_allowed"] is False
    assert store.catalog["A-1-2018"]["category_name"] == "시료채취·분석"
    snaps = [s for s in store.snapshots if s["status"] == "COMPLETED"]
    assert len(snaps) == 1
    assert snaps[0]["call_api_id"] == "1050"


def test_f2_med_schema_reject_no_mutation():
    med = {
        "MED_SJ_NM": "안전자료",
        "MED_URL": "https://www.kosha.or.kr/x?medSeq=1",
        "MED_COMPY_DY": "20260101",
    }
    store = MemoryGuideStore()
    r = _run([med], store=store, page_size=10)
    assert r.status == "REJECT"
    assert r.extra["error_code"] == "WRONG_SOURCE"
    assert r.business_dml == 0
    assert store.catalog == {}
    assert store.snapshots == []
    assert store.current_ids() == []


def test_f3_missing_body_reject():
    def fetch_page(page_no, num_of_rows):
        return {"header": {"resultCode": "00"}}

    store = MemoryGuideStore()
    r = sync_kosha_guides(fetch_page=fetch_page, store=store, dry_run=False, page_size=10)
    assert r.status == "REJECT"
    assert r.extra["error_code"] == "MISSING_BODY"
    assert store.dml == 0


def test_f3_empty_success_total_zero_reject():
    def fetch_page(page_no, num_of_rows):
        return {
            "header": {"resultCode": "00"},
            "body": {"totalCount": 0, "items": {"item": []}},
        }

    store = MemoryGuideStore()
    r = sync_kosha_guides(fetch_page=fetch_page, store=store, dry_run=False, page_size=10)
    assert r.status == "REJECT"
    assert r.extra["error_code"] == "TOTAL_ZERO"
    assert store.dml == 0


def test_f4_total_count_mismatch_preserves_old_current():
    first = [_item("A-1-2018"), _item("A-6-2018"), _item("G-1-2018")]
    store = MemoryGuideStore()
    r1 = _run(first, store=store, page_size=2)
    assert r1.status == "COMPLETED"
    old_ids = store.current_ids()
    old_hash = r1.snapshot_hash

    def fetch_drift(page_no, num_of_rows):
        if page_no == 1:
            return _page(first[:2], 3)
        return _page(first[2:], 4)

    r2 = sync_kosha_guides(fetch_page=fetch_drift, store=store, dry_run=False, page_size=2)
    assert r2.status == "FAILED"
    assert r2.extra["error_code"] == "TOTAL_DRIFT"
    assert store.current_ids() == old_ids
    assert store.get_latest_completed()["snapshot_hash"] == old_hash


def test_f5_duplicate_key_preserves_old_current():
    first = [_item("A-1-2018"), _item("A-6-2018")]
    store = MemoryGuideStore()
    assert _run(first, store=store, page_size=10).status == "COMPLETED"
    old = store.current_ids()
    dupes = [_item("A-1-2018", "하나"), _item("A-1-2018", "둘")]
    r = _run(dupes, store=store, page_size=10)
    assert r.status == "FAILED"
    assert r.extra["error_code"] == "DUPLICATE_KEY"
    assert store.current_ids() == old


def test_f6_missing_required_reject():
    cases = [
        _item("", "제목"),
        _item("A-1-2018", ""),
        {**_item("A-1-2018"), "techGdlnOfancYmd": ""},
        {**_item("A-1-2018"), "fileDownloadUrl": ""},
        {**_item("A-1-2018"), "techGdlnOfancYmd": "20181127"},
    ]
    for raw in cases:
        store = MemoryGuideStore()
        r = _run([raw], store=store, page_size=10)
        assert r.status == "REJECT", raw
        assert store.current_ids() == []
        assert store.dml == 0


def test_f7_malformed_url_hold_excluded_from_current():
    items = [
        _item("A-1-2018", url=OK_URL),
        _item("A-6-2018", url="https://evil.example/file.pdf"),
    ]
    store = MemoryGuideStore()
    r = _run(items, store=store, page_size=10)
    assert r.status == "COMPLETED"
    assert r.hold_count == 1
    assert store.current_ids() == ["A-1-2018"]
    assert "A-6-2018" in store.catalog
    assert "A-6-2018" not in store.current_ids()


def test_f8_four_part_code_name_null():
    items = [
        _item("A-G-1-2025", "4파트"),
        _item("A-1-2018", "3파트"),
    ]
    store = MemoryGuideStore()
    r = _run(items, store=store, page_size=10)
    assert r.status == "COMPLETED"
    four = store.catalog["A-G-1-2025"]
    three = store.catalog["A-1-2018"]
    assert four["category_code"] == "A-G"
    assert four["category_name"] is None
    assert three["category_code"] == "A"
    assert three["category_name"] == CATEGORY_NAME_BY_CODE["A"]
    assert "category" not in four


def test_f9_same_hash_no_change():
    items = [_item("A-1-2018"), _item("C-1-2018")]
    store = MemoryGuideStore()
    r1 = _run(items, store=store, page_size=10)
    dml_after_first = store.dml
    r2 = _run(items, store=store, page_size=10)
    assert r1.status == "COMPLETED"
    assert r2.status == "SNAPSHOT_NO_CHANGE"
    assert r2.business_dml == 0
    assert store.dml == dml_after_first
    assert len([s for s in store.snapshots if s["status"] == "COMPLETED"]) == 1


def test_f10_change_promotes_new_current_only():
    v1 = [_item("A-1-2018", "구제목"), _item("C-1-2018")]
    store = MemoryGuideStore()
    r1 = _run(v1, store=store, page_size=10)
    v2 = [_item("A-1-2018", "신제목"), _item("C-1-2018"), _item("G-1-2018")]
    r2 = _run(v2, store=store, page_size=10)
    assert r1.status == r2.status == "COMPLETED"
    assert r1.snapshot_hash != r2.snapshot_hash
    assert store.current_ids() == ["A-1-2018", "C-1-2018", "G-1-2018"]
    completed = [s for s in store.snapshots if s["status"] == "COMPLETED"]
    assert len(completed) == 2
    assert store.get_latest_completed()["id"] == r2.snapshot_id
    latest_members = {i["guide_id"] for i in store.items if i["snapshot_id"] == r2.snapshot_id}
    assert latest_members == set(store.current_ids())


def test_f11_running_failure_keeps_previous_completed():
    first = [_item("A-1-2018"), _item("C-1-2018")]
    store = MemoryGuideStore()
    r1 = _run(first, store=store, page_size=10)
    old = store.current_ids()
    store.fail_on_membership = True
    r2 = _run([_item("A-1-2018", "바뀜"), _item("C-1-2018"), _item("G-1-2018")], store=store, page_size=10)
    assert r1.status == "COMPLETED"
    assert r2.status == "FAILED"
    assert store.current_ids() == old
    assert any(s["status"] == "FAILED" for s in store.snapshots)
    assert store.get_latest_completed()["id"] == r1.snapshot_id


def test_f12_dry_run_zero_business_dml():
    items = [_item("A-1-2018"), _item("C-1-2018")]
    store = MemoryGuideStore()
    r = _run(items, store=store, dry_run=True, page_size=10)
    assert r.status == "DRY_RUN"
    assert r.dry_run is True
    assert r.declared == r.fetched == r.unique == 2
    assert r.snapshot_hash
    assert r.business_dml == 0
    assert store.dml == 0
    assert store.catalog == {}
    assert store.snapshots == []
    assert store.current_ids() == []


def test_call_api_id_not_injectable_on_public_paths():
    assert SOURCE_CALL_API_ID == "1050"
    assert SOURCE_PATH == "koshaguide/getKoshaGuide"
    assert EXPECTED_FIELDS == (
        "techGdlnNo", "techGdlnNm", "techGdlnOfancYmd", "fileDownloadUrl",
    )
    assert list(inspect.signature(official_fetch_page).parameters) == ["page_no", "num_of_rows"]
    assert "call_api_id" not in inspect.signature(sync_kosha_guides).parameters
    assert "call_api_id" not in inspect.signature(kc._collect_guide).parameters
    assert "dry_run" in inspect.signature(kc._collect_guide).parameters
    src = inspect.getsource(kc._collect_guide)
    assert "kosha_guide" in src
    assert "sync_kosha_guides" in src
    assert "_make_id(" not in src
    assert "call_api_id" not in src
    fetch_src = inspect.getsource(official_fetch_page)
    assert "SOURCE_CALL_API_ID" in fetch_src
    assert "SOURCE_PATH" in fetch_src


def test_ctc_url_allowed_and_no_binary_storage_path():
    items = [_item("A-G-12-2026", url=CTC_URL)]
    store = MemoryGuideStore()
    r = _run(items, store=store, page_size=10)
    assert r.status == "COMPLETED"
    assert r.hold_count == 0
    src = inspect.getsource(gsync)
    assert "put_object" not in src
    assert "R2" not in src
    assert "storage.from" not in src


def test_migration_additive_and_current_view():
    sql = pathlib.Path(SQL).read_text(encoding="utf-8")
    n = re.sub(r"\s+", " ", sql).lower()
    assert "alter table public.kosha_guide" in n
    assert "add column if not exists" in n
    assert "drop column" not in n
    assert "drop table" not in n
    assert "create table if not exists public.kosha_guide_snapshots" in n
    assert "create table if not exists public.kosha_guide_snapshot_items" in n
    assert "create or replace view public.kosha_guide_current" in n
    assert "status = 'completed'" in n
    view = sql.lower().split("create or replace view public.kosha_guide_current as")[1]
    select_list = view.split("comment")[0]
    assert "raw_json" not in select_list
    assert "grant select on public.kosha_guide_current" in n
    assert "kosha_safety_materials" not in n
    assert "knowledge_items" not in n
