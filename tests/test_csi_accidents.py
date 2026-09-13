"""OBJ-CSI CSI-02/05 core: C01–C62 source contract, public read, graph adapter."""
from __future__ import annotations

import csv
import inspect
import io
import json
import os
import pathlib
import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.csi_accidents.contract import (
    APPLY_ENABLE_ENV,
    DECLARED_ROWS,
    FINGERPRINT_VERSION,
    HEADER_COUNT,
    OFFICIAL_BYTES,
    OFFICIAL_FILENAME,
    OFFICIAL_HEADERS,
    OFFICIAL_SHA256,
    PARSED_ROWS_PROBE,
    SOURCE_ENCODING,
    SOURCE_ID,
)
from services.csi_accidents.graph_adapter import GRAPH_WRITES_OPEN, graph_eligible, is_csi_content_id
from services.csi_accidents.identity import (
    identity_fingerprint,
    missing_to_null,
    normalize_row,
    source_content_hash,
)
from services.csi_accidents.parse import CsiSyncError, decode_cp949, parse_official_bytes
from services.csi_accidents.storage_policy import R2_WRITES_OPEN, REUSE_EXISTING_BUCKET, storage_report
from services.csi_accidents.store import MemoryCsiStore
from services.csi_accidents.sync import sync_csi_accidents
from services.csi_accidents import sync as sync_mod

SQL = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "supabase",
        "migrations",
        "20260913_csi_accident_catalog.sql",
    )
)
HARDENING_SQL = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "supabase",
        "migrations",
        "20260913_csi_accident_privilege_hardening.sql",
    )
)
OFFICIAL_CSV = "/tmp/csi-01/dataset.bin"


def _row(title="사고A", occurred="2019-07-01 07:10", **over):
    raw = {h: "값" for h in OFFICIAL_HEADERS}
    raw["사고명"] = title
    raw["사고일시"] = occurred
    raw["사망자"] = "0"
    raw["부상자"] = "1"
    raw["사고경위"] = "경위"
    raw["재발방지대책"] = "대책"
    raw.update(over)
    return raw


def _csv_bytes(rows, encoding="cp949"):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(OFFICIAL_HEADERS)
    for raw in rows:
        w.writerow([raw[h] for h in OFFICIAL_HEADERS])
    return buf.getvalue().encode(encoding)


def _sync(rows, store=None, dry_run=False, encoding="cp949", **kw):
    store = store if store is not None else MemoryCsiStore()
    result = sync_csi_accidents(
        data=_csv_bytes(rows, encoding=encoding),
        dry_run=dry_run,
        store=store,
        skip_file_pin=True,
        **kw,
    )
    return result, store


@pytest.fixture
def apply_on(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")


def test_c01_official_74_headers():
    assert len(OFFICIAL_HEADERS) == HEADER_COUNT == 74
    assert OFFICIAL_HEADERS[0] == "사고명"
    assert OFFICIAL_HEADERS[-1] == "재발방지대책"
    data = _csv_bytes([_row()])
    parsed = parse_official_bytes(data)
    assert parsed.headers == list(OFFICIAL_HEADERS)


def test_c02_cp949_decode():
    data = _csv_bytes([_row(title="한글사고")])
    text = decode_cp949(data)
    assert "한글사고" in text
    parsed = parse_official_bytes(data)
    assert parsed.encoding == SOURCE_ENCODING
    assert parsed.rows[0]["사고명"] == "한글사고"


def test_c03_http_utf8_charset_ignored():
    data = _csv_bytes([_row(title="본문CP949")])
    http_charset = "UTF-8"
    assert http_charset != SOURCE_ENCODING
    text = decode_cp949(data)
    assert "본문CP949" in text
    utf8_body = _csv_bytes([_row(title="UTF본문")], encoding="utf-8")
    with pytest.raises(CsiSyncError) as e:
        decode_cp949(utf8_body)
    assert e.value.code == "CP949_DECODE"


def test_c04_probe_contract_and_optional_full_file():
    assert PARSED_ROWS_PROBE == 37196
    assert DECLARED_ROWS == 14289
    assert OFFICIAL_BYTES == 36318137
    assert OFFICIAL_SHA256 == "080618b19adc9973ee347600f2ca8211a601695ea4660a8dd520f9f55cacac4c"
    assert OFFICIAL_FILENAME == "건설안전사고사례(_25.6.30)csv.csv"
    data = _csv_bytes([_row("a"), _row("b", occurred="2019-07-02 08:00")])
    parsed = parse_official_bytes(data)
    assert len(parsed.rows) == 2
    if os.path.exists(OFFICIAL_CSV):
        blob = pathlib.Path(OFFICIAL_CSV).read_bytes()
        full = parse_official_bytes(blob)
        assert len(full.rows) == PARSED_ROWS_PROBE
        assert full.headers == list(OFFICIAL_HEADERS)


def test_c05_malformed_fail():
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(OFFICIAL_HEADERS)
    w.writerow(["only", "three", "cols"])
    data = buf.getvalue().encode("cp949")
    with pytest.raises(CsiSyncError) as e:
        parse_official_bytes(data)
    assert e.value.code == "MALFORMED_CSV"


def test_c06_blank_to_null():
    raw = _row(**{"공종(대분류)": "  ", "공사종류": ""})
    n = normalize_row(raw, 1)
    assert n.process_major is None
    assert n.construction_type is None


def test_c07_placeholder_to_null():
    raw = _row(**{"공종(대분류)": "미입력", "사고객체(소분류)": "미입력"})
    n = normalize_row(raw, 1)
    assert n.process_major is None
    assert n.object_minor is None
    assert missing_to_null("미입력") is None


def test_c08_raw_json_preserves_placeholder():
    raw = _row(**{"공종(대분류)": "미입력"})
    n = normalize_row(raw, 1)
    assert n.raw["공종(대분류)"] == "미입력"
    assert n.process_major is None


def test_c09_full_row_hash_deterministic():
    raw = _row()
    assert source_content_hash(raw) == source_content_hash(dict(raw))
    assert len(source_content_hash(raw)) == 64


def test_c10_narrative_changes_version_hash():
    a = _row(**{"사고경위": "원문1"})
    b = _row(**{"사고경위": "원문2"})
    assert source_content_hash(a) != source_content_hash(b)
    assert identity_fingerprint(a) == identity_fingerprint(b)


def test_c11_content_id_independent_from_version_hash(apply_on):
    v1 = [_row(title="동일사고", **{"사고경위": "초판"})]
    r1, store = _sync(v1, dry_run=False)
    cid = store.current_content_ids()[0]
    h1 = store.items[0]["source_content_hash"]
    v2 = [_row(title="동일사고", **{"사고경위": "개정"})]
    r2, store = _sync(v2, store=store, dry_run=False)
    assert r1.status == r2.status == "COMPLETED"
    assert store.current_content_ids() == [cid]
    h2 = [i for i in store.items if i["snapshot_id"] == r2.snapshot_id][0]["source_content_hash"]
    assert h1 != h2
    assert cid.startswith("CSI:")


def test_c12_unique_fingerprint_ready(apply_on):
    rows = [
        _row("A", "2019-07-01 07:10"),
        _row("B", "2019-07-02 08:00"),
    ]
    r, store = _sync(rows, dry_run=False)
    assert r.status == "COMPLETED"
    assert r.ready == 2
    assert r.hold == 0
    assert all(c["identity_status"] == "READY" for c in store.cases.values())


def test_c13_duplicate_fingerprint_hold(apply_on):
    rows = [
        _row("같은이름", "2019-07-01 07:10", **{"사고경위": "경위1"}),
        _row("같은이름", "2019-07-01 07:10", **{"사고경위": "경위2"}),
    ]
    r, store = _sync(rows, dry_run=False)
    assert r.hold == 2
    assert r.ready == 0
    assert r.collision_fingerprints == 1
    assert len(store.cases) == 2
    assert all(c["identity_status"] == "HOLD" for c in store.cases.values())
    assert len({c["content_id"] for c in store.cases.values()}) == 2


def test_c14_collision_group_all_hold(apply_on):
    rows = [
        _row("충돌", "2020-01-01 10:00", **{"사고경위": "a"}),
        _row("충돌", "2020-01-01 10:00", **{"사고경위": "b"}),
        _row("충돌", "2020-01-01 10:00", **{"사고경위": "c"}),
    ]
    r, store = _sync(rows, dry_run=False)
    assert r.hold == 3
    assert r.ready == 0
    assert all(i["identity_status"] == "HOLD" for i in store.items)


def test_c15_exact_row_hash_reuses_case(apply_on):
    first = [_row("고정", "2021-03-01 11:00"), _row("다른", "2021-03-02 11:00")]
    r1, store = _sync(first, dry_run=False)
    assert r1.status == "COMPLETED"
    target = _row("고정", "2021-03-01 11:00")
    cid_fixed = [
        c["content_id"]
        for c in store.cases.values()
        if c["identity_fingerprint"] == identity_fingerprint(target)
    ][0]
    second = [_row("고정", "2021-03-01 11:00"), _row("제3", "2021-03-03 11:00")]
    r2, store = _sync(second, store=store, dry_run=False)
    assert r2.status == "COMPLETED"
    assert cid_fixed in store.current_content_ids()
    latest = [
        i
        for i in store.items
        if i["snapshot_id"] == r2.snapshot_id and i["content_id"] == cid_fixed
    ][0]
    assert latest["source_content_hash"] == source_content_hash(target)
    assert r2.unchanged == 1


def test_c16_unique_historical_fingerprint_reuses_case(apply_on):
    r1, store = _sync([_row("이력", "2022-01-01 10:00", **{"사고경위": "v1"})], dry_run=False)
    cid = next(iter(store.cases))
    r2, store = _sync([_row("이력", "2022-01-01 10:00", **{"사고경위": "v2"})], store=store, dry_run=False)
    assert r2.changed == 1
    assert r2.new == 0
    assert next(iter(store.cases)) == cid
    assert len(store.cases) == 1


def test_c17_ambiguous_historical_fingerprint_hold(apply_on):
    collide = [
        _row("모호", "2022-05-05 05:05", **{"사고경위": "하나"}),
        _row("모호", "2022-05-05 05:05", **{"사고경위": "둘"}),
    ]
    r1, store = _sync(collide, dry_run=False)
    assert r1.hold == 2
    later = [_row("모호", "2022-05-05 05:05", **{"사고경위": "셋"})]
    r2, store = _sync(later, store=store, dry_run=False)
    assert r2.status == "COMPLETED"
    assert r2.hold == 1
    assert r2.ready == 0
    assert all(c["identity_status"] == "HOLD" for c in store.cases.values())
    assert len(store.cases) == 3


def test_c18_failed_snapshot_does_not_become_current(apply_on):
    first = [_row("유지", "2018-01-01 01:00")]
    r1, store = _sync(first, dry_run=False)
    old = store.current_content_ids()
    store.fail_on_membership = True
    r2, store = _sync([_row("새", "2018-02-02 02:00")], store=store, dry_run=False)
    assert r1.status == "COMPLETED"
    assert r2.status == "FAILED"
    assert store.current_content_ids() == old
    assert store.get_latest_completed()["id"] == r1.snapshot_id


def test_c19_latest_completed_is_current(apply_on):
    r1, store = _sync([_row("1", "2017-01-01 00:00")], dry_run=False)
    r2, store = _sync([_row("2", "2017-02-01 00:00")], store=store, dry_run=False)
    assert r1.status == r2.status == "COMPLETED"
    assert store.get_latest_completed()["id"] == r2.snapshot_id
    assert store.current_content_ids() == [
        i["content_id"] for i in store.items if i["snapshot_id"] == r2.snapshot_id
    ]
    assert "current" not in store.cases[store.current_content_ids()[0]]


def test_c20_declared_parsed_mismatch_allowed():
    r, store = _sync([_row("x"), _row("y", occurred="2019-08-01 00:00")], dry_run=True)
    assert r.status == "DRY_RUN"
    assert r.parsed_rows == 2
    assert r.declared_rows == DECLARED_ROWS
    assert r.row_count_mismatch is True
    assert r.extra["row_count_mismatch_recorded"] is True
    assert store.dml == 0


def test_c21_kosha_tables_untouched():
    sql = pathlib.Path(SQL).read_text(encoding="utf-8")
    n = sql.lower()
    assert "create table if not exists public.csi_accident_cases" in n
    assert "create table if not exists public.csi_accident_snapshots" in n
    assert "create table if not exists public.csi_accident_snapshot_items" in n
    assert "kosha_accident_cases" not in n
    assert "kosha_construction_accidents" not in n
    assert "alter table public.kosha_" not in n
    assert "knowledge_relation" not in n
    assert "drop table" not in n
    view = n.split("create or replace view public.csi_accident_current as")[1]
    assert "raw_json" not in view.split("comment")[0]
    assert "grant select on public.csi_accident_current to service_role" in n
    assert "grant select on public.csi_accident_current to anon" not in n


def test_c22_graph_writes_zero_in_sync(apply_on):
    src = inspect.getsource(sync_mod)
    assert "knowledge_graph" not in src
    assert "hydrate" not in src
    assert GRAPH_WRITES_OPEN is False
    assert R2_WRITES_OPEN is False
    r, store = _sync([_row("g")], dry_run=False)
    assert r.graph_writes == 0
    assert store.graph_writes == 0
    assert r.kosha_writes == 0
    assert graph_eligible(
        snapshot_status="COMPLETED", identity_status="HOLD", latest_completed=True
    ) is False
    assert graph_eligible(
        snapshot_status="COMPLETED", identity_status="READY", latest_completed=True
    ) is True


def test_c23_source_key_nullable_unavailable(apply_on):
    r, store = _sync([_row("키없음")], dry_run=False)
    case = next(iter(store.cases.values()))
    assert case["source_key"] is None
    assert case["source_id"] == SOURCE_ID
    item = store.items[0]
    assert item["source_item_url"] is None


def test_c24_content_id_csi_namespace(apply_on):
    r, store = _sync([_row("네임스페이스")], dry_run=False)
    cid = next(iter(store.cases))
    assert is_csi_content_id(cid)
    uuid.UUID(cid.split("CSI:", 1)[1])
    assert FINGERPRINT_VERSION == "CSI_EVENT_FINGERPRINT_V1"
    assert store.cases[cid]["fingerprint_version"] == FINGERPRINT_VERSION


def test_c25_dry_run_db_write_zero():
    store = MemoryCsiStore()
    r, store = _sync([_row("dry")], store=store, dry_run=True)
    assert r.status == "DRY_RUN"
    assert r.business_dml == 0
    assert store.dml == 0
    assert store.cases == {}
    assert store.snapshots == []
    assert r.graph_writes == 0
    assert r.r2_writes == 0


def test_apply_gate_blocks_without_env(monkeypatch):
    monkeypatch.delenv(APPLY_ENABLE_ENV, raising=False)
    r, store = _sync([_row("gate")], dry_run=False)
    assert r.status == "REJECT"
    assert r.extra["error_code"] == "APPLY_GATE"
    assert store.dml == 0


def test_blank_and_placeholder_share_fingerprint():
    a = _row(**{"공종(대분류)": "", "공종(소분류)": "미입력"})
    b = _row(**{"공종(대분류)": "미입력", "공종(소분류)": ""})
    assert identity_fingerprint(a) == identity_fingerprint(b)


def test_wrong_headers_fail():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["not", "official"])
    w.writerow(["1", "2"])
    with pytest.raises(CsiSyncError) as e:
        parse_official_bytes(buf.getvalue().encode("cp949"))
    assert e.value.code == "HEADER_MISMATCH"


def test_storage_policy_no_bucket_reuse():
    report = storage_report()
    assert report["reuse_existing_bucket"] is False
    assert report["r2_writes_open"] is False
    assert report["overwrite"] is False
    assert report["delete"] is False
    assert REUSE_EXISTING_BUCKET is False


def test_current_view_sql_uses_completed_only():
    sql = pathlib.Path(SQL).read_text(encoding="utf-8")
    n = re.sub(r"\s+", " ", sql).lower()
    assert "status = 'completed'" in n
    assert "current boolean" not in n
    assert "is_current" not in n


def test_c26_failed_membership_isolated_from_history(apply_on):
    r1, store = _sync([_row("유지", "2018-01-01 01:00")], dry_run=False)
    prior = store.get_latest_completed()["id"]
    prior_ids = store.current_content_ids()
    hist_before = {r["content_id"] for r in store.load_reconciliation_history()}
    store.fail_on_membership = True
    r2, store = _sync([_row("실패전용", "2018-02-02 02:00")], store=store, dry_run=False)
    assert r1.status == "COMPLETED"
    assert r2.status == "FAILED"
    assert store.get_latest_completed()["id"] == prior
    assert store.current_content_ids() == prior_ids
    assert any(s["id"] == r2.snapshot_id and s["status"] == "FAILED" for s in store.snapshots)
    hist_after = {r["content_id"] for r in store.load_reconciliation_history()}
    assert hist_after == hist_before
    failed_only = set(store.cases) - hist_after
    assert failed_only
    assert all(cid not in hist_after for cid in failed_only)
    src = inspect.getsource(sync_mod.sync_csi_accidents)
    assert src.find("insert_running_snapshot") < src.find("upsert_cases")
    assert src.find("insert_running_snapshot") < src.find("insert_membership")


def test_c27_failed_only_hash_not_exact_row_match(apply_on):
    store = MemoryCsiStore()
    r1, store = _sync([_row("기존", "2019-01-01 00:00")], store=store, dry_run=False)
    failed_row = _row("실패해시", "2019-02-02 00:00", **{"사고경위": "failed-only"})
    h_failed = source_content_hash(failed_row)
    store.fail_on_membership = True
    r2, store = _sync([failed_row], store=store, dry_run=False)
    assert r2.status == "FAILED"
    hist_hashes = set()
    for rec in store.load_reconciliation_history():
        hist_hashes |= rec["source_content_hashes"]
    assert h_failed not in hist_hashes
    failed_cids = set(store.cases) - {r["content_id"] for r in store.load_reconciliation_history()}
    store.fail_on_membership = False
    r3, store = _sync([failed_row], store=store, dry_run=False)
    assert r3.status == "COMPLETED"
    latest = [i for i in store.items if i["snapshot_id"] == r3.snapshot_id]
    assert latest[0]["identity_reason"] != "EXACT_ROW_HASH"
    assert latest[0]["identity_reason"] == "UNIQUE_FINGERPRINT"
    assert latest[0]["content_id"] not in failed_cids


def test_c28_failed_hold_does_not_pollute_ready(apply_on):
    ready_row = _row("안정", "2020-01-01 10:00", **{"사고경위": "v1"})
    r1, store = _sync([ready_row], dry_run=False)
    cid = store.current_content_ids()[0]
    assert store.load_reconciliation_history()[0]["identity_status"] == "READY"
    store.fail_on_membership = True
    collide = [
        _row("안정", "2020-01-01 10:00", **{"사고경위": "충돌1"}),
        _row("안정", "2020-01-01 10:00", **{"사고경위": "충돌2"}),
    ]
    r2, store = _sync(collide, store=store, dry_run=False)
    assert r2.status == "FAILED"
    hist = [r for r in store.load_reconciliation_history() if r["content_id"] == cid]
    assert len(hist) == 1
    assert hist[0]["identity_status"] == "READY"
    store.fail_on_membership = False
    later = [_row("안정", "2020-01-01 10:00", **{"사고경위": "v2-성공"})]
    r3, store = _sync(later, store=store, dry_run=False)
    assert r3.status == "COMPLETED"
    latest = [i for i in store.items if i["snapshot_id"] == r3.snapshot_id][0]
    assert latest["content_id"] == cid
    assert latest["identity_reason"] == "UNIQUE_HISTORICAL_FINGERPRINT"
    assert latest["identity_status"] == "READY"


def test_c29_running_failed_items_excluded_from_history(apply_on):
    r1, store = _sync([_row("완료", "2021-01-01 00:00")], dry_run=False)
    store.fail_on_complete = True
    r2, store = _sync([_row("실패아이템", "2021-02-02 00:00")], store=store, dry_run=False)
    assert r2.status == "FAILED"
    failed_items = [i for i in store.items if i["snapshot_id"] == r2.snapshot_id]
    assert failed_items
    hist = store.load_reconciliation_history()
    hist_ids = {r["content_id"] for r in hist}
    hist_hashes = set().union(*(r["source_content_hashes"] for r in hist))
    assert failed_items[0]["content_id"] not in hist_ids
    assert {i["source_content_hash"] for i in failed_items}.isdisjoint(hist_hashes)
    assert r1.snapshot_id == store.get_latest_completed()["id"]


def test_c30_completed_items_included_in_history(apply_on):
    row = _row("히스토리", "2021-03-03 00:00")
    r, store = _sync([row], dry_run=False)
    assert r.status == "COMPLETED"
    hist = store.load_reconciliation_history()
    assert len(hist) == 1
    assert hist[0]["content_id"] == store.current_content_ids()[0]
    assert source_content_hash(row) in hist[0]["source_content_hashes"]
    assert hist[0]["identity_status"] == "READY"
    assert r.extra["history_source"] == "COMPLETED_SNAPSHOTS_ONLY"
    hist_src = inspect.getsource(sync_mod._history)
    assert "load_reconciliation_history" in hist_src
    assert "list_cases" not in hist_src


def test_c31_service_role_delete_grant_zero():
    sql = pathlib.Path(SQL).read_text(encoding="utf-8")
    grants = [
        ln.strip().lower()
        for ln in sql.splitlines()
        if ln.strip().lower().startswith("grant ") and "csi_accident" in ln.lower()
    ]
    assert grants
    for g in grants:
        assert "delete" not in g
    n = sql.lower()
    assert "revoke delete on public.csi_accident_cases from service_role" in n
    assert "revoke delete on public.csi_accident_snapshots from service_role" in n
    assert "revoke delete on public.csi_accident_snapshot_items from service_role" in n


def test_c32_no_drop_or_truncate():
    sql = pathlib.Path(SQL).read_text(encoding="utf-8")
    n = re.sub(r"\s+", " ", sql).lower()
    assert "drop table" not in n
    assert "truncate" not in n
    assert "drop view" not in n


def _hardening():
    return pathlib.Path(HARDENING_SQL).read_text(encoding="utf-8")


def _hardening_norm():
    return re.sub(r"\s+", " ", _hardening()).lower()


def test_c33_public_table_privileges_explicit_revoke():
    n = _hardening_norm()
    for table in (
        "public.csi_accident_cases",
        "public.csi_accident_snapshots",
        "public.csi_accident_snapshot_items",
    ):
        assert f"revoke all on {table} from public" in n


def test_c34_anon_authenticated_table_privileges_revoke():
    n = _hardening_norm()
    for table in (
        "public.csi_accident_cases",
        "public.csi_accident_snapshots",
        "public.csi_accident_snapshot_items",
    ):
        assert f"revoke all on {table} from anon" in n
        assert f"revoke all on {table} from authenticated" in n


def test_c35_service_role_dangerous_table_privileges_revoke():
    n = _hardening_norm()
    for table in (
        "public.csi_accident_cases",
        "public.csi_accident_snapshots",
        "public.csi_accident_snapshot_items",
    ):
        assert f"grant select, insert, update on {table} to service_role" in n
        assert f"revoke delete, truncate, references, trigger on {table} from service_role" in n


def test_c36_current_view_public_anon_authenticated_revoke():
    n = _hardening_norm()
    assert "revoke all on public.csi_accident_current from public" in n
    assert "revoke all on public.csi_accident_current from anon" in n
    assert "revoke all on public.csi_accident_current from authenticated" in n


def test_c37_current_view_service_role_select_only():
    n = _hardening_norm()
    assert "grant select on public.csi_accident_current to service_role" in n
    grants = [
        ln.strip().lower()
        for ln in _hardening().splitlines()
        if ln.strip().lower().startswith("grant ") and "csi_accident_current" in ln.lower()
    ]
    assert grants == ["grant select on public.csi_accident_current to service_role;"]
    assert "revoke insert, update, delete, truncate, references, trigger on public.csi_accident_current from service_role" in n


def test_c38_hardening_migration_no_destructive_execution():
    sql = _hardening()
    n = re.sub(r"\s+", " ", sql).lower()
    assert "drop table" not in n
    assert "drop view" not in n
    non_revoke = "\n".join(
        ln
        for ln in sql.splitlines()
        if not ln.strip().lower().startswith(("revoke ", "grant ", "--"))
        and ln.strip()
    ).lower()
    assert "truncate" not in non_revoke
    assert "delete from" not in non_revoke
    assert "insert into" not in non_revoke
    assert re.search(r"\bupdate\s+public\.", non_revoke) is None


READY_UUID = "12345678-1234-4123-8123-123456789abc"
HOLD_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
READY_ID = f"CSI:{READY_UUID}"
HOLD_ID = f"CSI:{HOLD_UUID}"
FORBIDDEN_PUBLIC = (
    "raw_json",
    "identity_fingerprint",
    "identity_reason",
    "source_content_hash",
    "snapshot_id",
    "row_number",
    "user_id",
    "company_id",
    "factory_id",
    "diagnosis_id",
    "file_sha256",
    "case_no",
)


def _pub_row(uid, status="READY", occurred="2020-01-02T00:00:00+09:00", **over):
    row = {
        "content_id": f"CSI:{uid}",
        "identity_status": status,
        "identity_fingerprint": "SECRET_FP",
        "identity_reason": "COLLISION",
        "source_content_hash": "abc123",
        "snapshot_id": "snap-1",
        "row_number": 99,
        "raw_json": {"사고명": "secret"},
        "title": "READY 지게차 사고",
        "summary": "용접 작업 중 발생",
        "occurred_at": occurred,
        "construction_type": "건축",
        "process_major": "건축",
        "process_minor": "철골",
        "object_major": "건설기계",
        "object_minor": "지게차",
        "work_process": "하역",
        "accident_type_major": "떨어짐",
        "accident_type": "떨어짐",
        "cause_major": "관리적원인",
        "cause_mid": "작업관리",
        "cause_minor": "작업방법",
        "cause_detail": "신호 미흡",
        "death_count": 0,
        "injury_count": 1,
        "source_dataset_url": "https://www.data.go.kr/data/15108262/fileData.do",
        "source_item_url": "https://evil.example/case/1",
        "user_id": "u1",
        "company_id": "c1",
        "factory_id": "f1",
        "diagnosis_id": "d1",
        "file_sha256": "deadbeef",
        "case_no": "FABRICATED",
    }
    row.update(over)
    return row


def _csi_client(rows):
    from services.csi_accidents.public import MemoryCsiPublicStore
    import routers.public_csi_accidents as csi_router

    store = MemoryCsiPublicStore(rows)
    csi_router.configure_csi_public(store)
    app = FastAPI()
    app.include_router(csi_router.router)
    return TestClient(app), store, csi_router


def test_c39_public_list_ready_only():
    client, _, router = _csi_client(
        [
            _pub_row(READY_UUID, title="READY만"),
            _pub_row(HOLD_UUID, status="HOLD", title="HOLD제목", occurred="2021-01-01T00:00:00+09:00"),
        ]
    )
    try:
        r = client.get("/public/accidents/csi")
        assert r.status_code == 200
        body = r.json()
        ids = [i["content_id"] for i in body["items"]]
        assert ids == [READY_ID]
        assert body["total"] == 1
        assert body["content_type"] == "ACCIDENT"
    finally:
        router.reset_csi_public()


def test_c40_hold_excluded_from_list():
    from services.csi_accidents.public import MemoryCsiPublicStore, list_public_accidents

    store = MemoryCsiPublicStore(
        [
            _pub_row(READY_UUID),
            _pub_row(HOLD_UUID, status="HOLD", title="HOLD는검색제외", summary="지게차"),
        ]
    )
    body = list_public_accidents(store)
    assert all(i["content_id"] != HOLD_ID for i in body["items"])
    assert body["total"] == 1


def test_c41_hold_detail_404():
    client, _, router = _csi_client(
        [_pub_row(HOLD_UUID, status="HOLD", title="HOLD상세")]
    )
    try:
        r = client.get(f"/public/accidents/csi/{HOLD_UUID}")
        assert r.status_code == 404
        assert r.json()["detail"] == "NOT_FOUND"
    finally:
        router.reset_csi_public()


def test_c42_uuid_maps_to_csi_namespace():
    from services.csi_accidents.public import content_id_from_uuid

    assert content_id_from_uuid(READY_UUID) == READY_ID
    client, _, router = _csi_client([_pub_row(READY_UUID)])
    try:
        r = client.get(f"/public/accidents/csi/{READY_UUID}")
        assert r.status_code == 200
        assert r.json()["content_id"] == READY_ID
        assert r.json()["content_type"] == "ACCIDENT"
    finally:
        router.reset_csi_public()


def test_c43_public_response_forbidden_fields_absent():
    client, _, router = _csi_client([_pub_row(READY_UUID)])
    try:
        listed = client.get("/public/accidents/csi").json()["items"][0]
        detail = client.get(f"/public/accidents/csi/{READY_UUID}").json()
        for payload in (listed, detail):
            for field in FORBIDDEN_PUBLIC:
                assert field not in payload
            dumped = json.dumps(payload, ensure_ascii=False)
            assert "SECRET_FP" not in dumped
            assert "secret" not in dumped
            assert "FABRICATED" not in dumped
            assert "deadbeef" not in dumped
    finally:
        router.reset_csi_public()


def test_c44_pagination_db_bounded():
    from services.csi_accidents.public import SupabaseCsiPublicStore
    from tests.test_knowledge_graph import FakeSB

    src = inspect.getsource(SupabaseCsiPublicStore.list_ready)
    assert ".range(" in src
    assert "execute().data" not in src.split(".range")[0]
    sb = FakeSB()
    for i in range(5):
        sb.seed(
            "csi_accident_current",
            _pub_row(f"12345678-1234-4123-8123-123456789ab{i}", occurred=f"2020-01-0{i+1}T00:00:00+09:00"),
        )
    out = SupabaseCsiPublicStore(sb).list_ready(q=None, page=2, page_size=2)
    assert ("range", 2, 3) in sb.ops
    assert len(out.items) <= 2
    assert not any(op[0] in {"insert", "update", "delete"} for op in sb.ops)


def test_c45_deterministic_ordering():
    from services.csi_accidents.public import MemoryCsiPublicStore, list_public_accidents

    u1 = "00000000-0000-4000-8000-000000000001"
    u2 = "00000000-0000-4000-8000-000000000002"
    u3 = "00000000-0000-4000-8000-000000000003"
    store = MemoryCsiPublicStore(
        [
            _pub_row(u2, occurred="2020-01-01T00:00:00+09:00", title="same-day-b"),
            _pub_row(u1, occurred="2020-01-01T00:00:00+09:00", title="same-day-a"),
            _pub_row(u3, occurred="2021-01-01T00:00:00+09:00", title="later"),
        ]
    )
    ids = [i["content_id"] for i in list_public_accidents(store)["items"]]
    assert ids == [f"CSI:{u3}", f"CSI:{u1}", f"CSI:{u2}"]


def test_c46_q_search_ready_only():
    from services.csi_accidents.public import MemoryCsiPublicStore, list_public_accidents

    store = MemoryCsiPublicStore(
        [
            _pub_row(READY_UUID, title="지게차 READY"),
            _pub_row(HOLD_UUID, status="HOLD", title="지게차 HOLD", object_minor="지게차"),
        ]
    )
    body = list_public_accidents(store, q="지게차")
    assert body["total"] == 1
    assert body["items"][0]["content_id"] == READY_ID
    assert body["items"][0]["content_type"] == "ACCIDENT"


def test_c47_search_input_sanitizer_filter_injection_guard():
    from services.csi_accidents.public import PublicCsiQueryError, sanitize_q, SupabaseCsiPublicStore

    for raw in (
        "title.eq.1",
        "*,identity_status.eq.HOLD",
        "a,b",
        "foo%bar",
        "foo_bar",
        "x);select",
        "지게차.*",
    ):
        with pytest.raises(PublicCsiQueryError) as exc:
            sanitize_q(raw)
        assert exc.value.code == "Q_INVALID"
    with pytest.raises(PublicCsiQueryError) as exc:
        sanitize_q("가" * 81)
    assert exc.value.code == "Q_TOO_LONG"
    assert sanitize_q(" 지게차 ") == "지게차"
    src = inspect.getsource(SupabaseCsiPublicStore.list_ready)
    assert "sanitize_q(q)" in src
    assert "escape_ilike" in src


def test_c48_source_attribution_exact():
    client, _, router = _csi_client([_pub_row(READY_UUID)])
    try:
        item = client.get(f"/public/accidents/csi/{READY_UUID}").json()
        assert item["source_id"] == "CSI"
        assert item["source_name"] == "국토안전관리원(CSI)"
        assert item["source_dataset_url"] == "https://www.data.go.kr/data/15108262/fileData.do"
        assert item["tai_url"] == f"https://taieng.co.kr/accident/csi/{READY_UUID}"
    finally:
        router.reset_csi_public()


def test_c49_source_item_url_and_case_no_not_fabricated():
    from services.csi_accidents.public import public_item

    item = public_item(_pub_row(READY_UUID))
    assert item["source_item_url"] is None
    assert "case_no" not in item
    src = pathlib.Path("routers/public_csi_accidents.py").read_text(encoding="utf-8") + pathlib.Path(
        "services/csi_accidents/public.py"
    ).read_text(encoding="utf-8")
    assert "safe.csi.go.kr" not in src
    assert "사고번호" not in src


def test_c50_kosha_accident_hydration_unchanged():
    from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
    from tests.test_knowledge_graph import FakeSB

    sb = FakeSB()
    sb.seed(
        "kosha_accident_cases",
        {"id": "acc-d1", "title": "지게차 전복", "reg_dt": "2019-03-01", "file_url": "https://kosha.example/d1"},
    )
    rec = ProductionKnowledgeHydrator(sb).get("ACCIDENT", "acc-d1")
    assert rec is not None
    assert rec.content_type == "ACCIDENT"
    assert rec.content_id == "acc-d1"
    assert rec.source_name == "KOSHA"
    assert rec.tai_url == "https://taieng.co.kr/accident/acc-d1"
    assert rec.published_at == "2019-03-01"


def test_c51_csi_hydration_current_ready_only():
    from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
    from tests.test_knowledge_graph import FakeSB

    sb = FakeSB()
    sb.seed("csi_accident_current", _pub_row(READY_UUID))
    rec = ProductionKnowledgeHydrator(sb).get("ACCIDENT", READY_ID)
    assert rec is not None
    assert rec.content_type == "ACCIDENT"
    assert rec.content_id == READY_ID
    assert rec.source_name == "국토안전관리원(CSI)"
    assert rec.summary == "용접 작업 중 발생"
    assert rec.published_at == "2020-01-02T00:00:00+09:00"
    assert rec.is_public_current is True


def test_c52_csi_hold_hydration_zero():
    from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
    from tests.test_knowledge_graph import FakeSB

    sb = FakeSB()
    sb.seed("csi_accident_current", _pub_row(HOLD_UUID, status="HOLD"))
    rec = ProductionKnowledgeHydrator(sb).get("ACCIDENT", HOLD_ID)
    assert rec is None


def test_c53_construction_table_query_zero():
    from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
    from tests.test_knowledge_graph import FakeSB
    from scripts.refresh_knowledge_graph import load_production_sources

    sb = FakeSB()
    sb.seed("kosha_accident_cases", {"id": "d1", "title": "지게차", "reg_dt": "2019-01-01"})
    sb.seed("csi_accident_current", _pub_row(READY_UUID))
    sb.seed("kosha_construction_accidents", {"id": "c1", "accident_summary": "굴착"})
    ProductionKnowledgeHydrator(sb).get_many([("ACCIDENT", "d1"), ("ACCIDENT", READY_ID)])
    load_production_sources(sb, {"accident"})
    assert not any(op[0] == "select" and op[1] == "kosha_construction_accidents" for op in sb.ops)


def test_c54_csi_tai_url_future_route_exact():
    from services.csi_accidents.public import csi_tai_url
    from services.knowledge_graph_svc import default_tai_url

    assert csi_tai_url(READY_ID) == f"https://taieng.co.kr/accident/csi/{READY_UUID}"
    assert default_tai_url("ACCIDENT", READY_ID) == f"https://taieng.co.kr/accident/csi/{READY_UUID}"
    assert default_tai_url("ACCIDENT", "acc-d1") == "https://taieng.co.kr/accident/acc-d1"


def test_c55_accident_loader_kosha_plus_csi_ready():
    from scripts.refresh_knowledge_graph import load_production_sources
    from tests.test_knowledge_graph import FakeSB

    sb = FakeSB()
    sb.seed("kosha_accident_cases", {"id": "d1", "title": "KOSHA", "reg_dt": "2019-01-01", "file_url": "u"})
    sb.seed("csi_accident_current", _pub_row(READY_UUID))
    sb.seed("csi_accident_current", _pub_row(HOLD_UUID, status="HOLD"))
    stats = {}
    items, errors = load_production_sources(sb, {"accident"}, stats=stats)
    assert errors == {}
    ids = {r["content_id"] for r in items["accident"]}
    assert ids == {"d1", READY_ID}
    assert stats["accident_kosha_scanned"] == 1
    assert stats["accident_csi_scanned"] == 1
    assert stats["accident_construction_included"] == 0


def test_c56_csi_source_content_hash_used_as_source_version():
    from services.knowledge_graph_producers import produce_accident_relations

    cands = produce_accident_relations(
        [
            {
                "content_id": READY_ID,
                "title": "지게차 전복",
                "summary": "요약",
                "object_minor": "지게차",
                "source_version": "hash-from-current",
                "identity_status": "READY",
            }
        ]
    )
    assert cands
    assert all(c.source_version == "hash-from-current" for c in cands)
    assert all(c.source_content_type == "ACCIDENT" for c in cands)
    assert all(c.source_content_id == READY_ID for c in cands)


def test_c57_kosha_load_fail_accident_fail_closed():
    from scripts.refresh_knowledge_graph import load_production_sources, produce_all
    from tests.test_knowledge_graph import FakeSB

    class Boom(FakeSB):
        def table(self, name):
            if name == "kosha_accident_cases":
                raise RuntimeError("KOSHA_DOWN")
            return super().table(name)

    sb = Boom()
    sb.seed("csi_accident_current", _pub_row(READY_UUID))
    items, errors = load_production_sources(sb, {"accident"})
    assert "accident" in errors
    assert "accident" not in items
    produced = produce_all(items, {}, failed_sources=errors)
    assert "accident" not in produced


def test_c58_csi_load_fail_accident_fail_closed():
    from scripts.refresh_knowledge_graph import load_production_sources, produce_all
    from tests.test_knowledge_graph import FakeSB

    class Boom(FakeSB):
        def table(self, name):
            if name == "csi_accident_current":
                raise RuntimeError("CSI_DOWN")
            return super().table(name)

    sb = Boom()
    sb.seed("kosha_accident_cases", {"id": "d1", "title": "KOSHA", "reg_dt": "2019-01-01"})
    items, errors = load_production_sources(sb, {"accident"})
    assert "accident" in errors
    assert "accident" not in items
    produced = produce_all({"accident": [{"content_id": "d1", "title": "지게차"}]}, {}, failed_sources=errors)
    assert "accident" not in produced


def test_c59_no_partial_stale_on_source_failure():
    from services.knowledge_graph_producers import produce_accident_relations
    from services.knowledge_graph_svc import MemoryGraphStore, refresh_graph

    store = MemoryGraphStore()
    cands = produce_accident_relations([{"content_id": "abc-1", "id": "abc-1", "title": "지게차 전복"}])
    first = refresh_graph(store=store, produced_by_source={"accident": cands}, scanned_by_source={"accident": 1}, apply=True)
    assert first.status == "COMPLETED"
    edge = next(iter(store.edges.values()))
    report = refresh_graph(
        store=store,
        produced_by_source={},
        scanned_by_source={"accident": 0},
        failed_sources={"accident": "CSI_LOAD_FAIL"},
        apply=True,
    )
    assert report.stale_count == 0
    assert edge["is_active"] is True
    assert edge.get("stale_at") is None


def test_c60_graph_dry_run_writes_zero(tmp_path, capsys):
    from scripts.refresh_knowledge_graph import main as refresh_main
    from services.csi_accidents.graph_adapter import GRAPH_WRITES_OPEN

    assert GRAPH_WRITES_OPEN is False
    fixture = tmp_path / "acc.json"
    fixture.write_text(
        json.dumps({"accident": [{"content_id": READY_ID, "title": "지게차 전복", "object_minor": "지게차"}]}),
        encoding="utf-8",
    )
    rc = refresh_main(["--source", "accident", "--fixture-json", str(fixture), "--context", "equipment:forklift"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["db_write"] == 0
    assert payload.get("dry_run") is True


def test_c61_existing_relation_aliases_unchanged():
    from services.knowledge_graph_rules import CONTROLLED_RULES

    aliases = {r.relation_key: r.aliases for r in CONTROLLED_RULES}
    assert aliases["forklift"] == ("지게차", "포크리프트", "forklift")
    assert aliases["welding"] == ("용접작업", "용접", "welding")
    assert aliases["excavation"] == ("굴착작업", "굴착", "excavation")
    assert aliases["fall"] == ("떨어짐", "추락", "fall")
    methods = {r.relation_key: r.method for r in CONTROLLED_RULES if r.relation_key in aliases}
    assert methods["forklift"] == "CONTROLLED_KEYWORD"
    src = pathlib.Path("services/knowledge_graph_rules.py").read_text(encoding="utf-8")
    assert "rule_id=\"EQUIPMENT_FORKLIFT_V1\"" in src or 'rule_id="EQUIPMENT_FORKLIFT_V1"' in src


def test_c62_content_type_remains_accident():
    from services.knowledge_graph_producers import produce_accident_relations
    from services.knowledge_graph_hydrate import ProductionKnowledgeHydrator
    from tests.test_knowledge_graph import FakeSB

    cands = produce_accident_relations(
        [{"content_id": READY_ID, "title": "지게차", "object_minor": "지게차", "identity_status": "READY"}]
    )
    assert cands
    assert all(c.source_content_type == "ACCIDENT" for c in cands)
    sb = FakeSB()
    sb.seed("csi_accident_current", _pub_row(READY_UUID))
    rec = ProductionKnowledgeHydrator(sb).get("ACCIDENT", READY_ID)
    assert rec.content_type == "ACCIDENT"
    pub = pathlib.Path("router_registry/public.py").read_text(encoding="utf-8")
    assert "routers.public_csi_accidents" in pub
    assert "content_type = CSI" not in pathlib.Path("services/csi_accidents/public.py").read_text(encoding="utf-8")
