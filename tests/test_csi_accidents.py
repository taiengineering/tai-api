"""OBJ-CSI CSI-02/03 core: C01–C25 source contract, identity, snapshot."""
from __future__ import annotations

import csv
import inspect
import io
import os
import pathlib
import re
import uuid

import pytest

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
