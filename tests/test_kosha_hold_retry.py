"""WP-4B-1 targeted HOLD retry orchestration. Fixture/mock only — production mutation 0."""
from __future__ import annotations

import hashlib

from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError
from services.kosha_safety_materials.storage.hold_retry import (
    BINARY_UNAVAILABLE_REASON,
    FILENAME_MISMATCH_REASON,
    FROZEN_SNAPSHOT_ID,
    MULTI_MATCH_REASON,
    RESOLUTION_NOTE_BINARY,
    RESOLUTION_NOTE_MULTI,
    RESOLUTION_NOTE_STALE,
    RETRYABLE_REASONS,
    apply_targeted_hold_retry,
    assert_retryable_reason,
    hold_retry_dry_run,
)
from services.kosha_safety_materials.storage.hold_store import HoldError, MemoryHoldStore
from services.kosha_safety_materials.storage.limits import OVERSIZE_REASON
from services.kosha_safety_materials.storage.r2_store import ALLOWED_BUCKET, R2Store
from services.kosha_safety_materials.storage.store import StorageError
from tests.test_kosha_binary_fetch import PDF
from tests.test_kosha_r2_store import FakeS3
from tests.test_kosha_storage_hold import (
    MID, NO, PDF_NAME, _ProdHolds, _atch_json, _detail_json, _item,
)


class _WritableVersions:
    def __init__(self):
        self.rows = {}
        self.dml = 0
        self.fail_promote = False

    def current(self, key):
        return self.rows.get(key)

    def current_count(self, key):
        return 1 if key in self.rows else 0

    def current_for_asset(self, asset_id):
        out = []
        for r in self.rows.values():
            if r.get("asset_id") == asset_id and r.get("is_current_version"):
                out.append(r)
        return out

    def promote(self, payload):
        if self.fail_promote:
            from services.kosha_safety_materials.storage.version_service import VersionError
            raise VersionError("DB_INSERT_FAILED")
        self.dml += 1
        row = dict(payload)
        row["id"] = self.dml
        row["is_current_version"] = True
        row["is_derivative"] = False
        row.setdefault("storage_bucket", ALLOWED_BUCKET)
        self.rows[payload["source_asset_key"]] = row
        return {"status": "NEW_VERSION", "id": self.dml, "dml": 1, "row": row}


def _dup_atch():
    row = {"contsAtcflNo": NO, "contsAtcflSeq": 1, "orgnlAtchFileNm": PDF_NAME}
    return {"status": 200, "json": {"payload": {"list": [row, row]}}}


def _dup_files():
    row = {"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": PDF_NAME}
    return [row, row]


def _ok_files():
    return [{"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": PDF_NAME}]


def _pdf_binary():
    sha = hashlib.sha256(PDF).hexdigest()
    n = {"c": 0}

    def fetch_binary(**k):
        n["c"] += 1
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    return fetch_binary, n


def _record(holds, asset_id, reason, snapshot_id="snap-1"):
    holds.record_open(
        snapshot_id=snapshot_id,
        asset_id=asset_id,
        material_id=MID,
        source_med_seq="38141",
        reason=reason,
        expected_file_name=PDF_NAME,
        observed_files=[],
    )


def test_retryable_reasons_exactly_two():
    assert RETRYABLE_REASONS == {
        "SOURCE_ASSET_MULTI_MATCH",
        "SOURCE_BINARY_UNAVAILABLE",
    }
    assert_retryable_reason(MULTI_MATCH_REASON)
    assert_retryable_reason(BINARY_UNAVAILABLE_REASON)
    try:
        assert_retryable_reason(FILENAME_MISMATCH_REASON)
        assert False
    except HoldError as e:
        assert e.code == "HOLD_REASON_NOT_RETRYABLE"
    try:
        assert_retryable_reason(OVERSIZE_REASON)
        assert False
    except HoldError as e:
        assert e.code == "HOLD_REASON_NOT_RETRYABLE"


def test_filename_mismatch_rejected_from_retry_scope():
    holds = _ProdHolds()
    _record(holds, 4523, FILENAME_MISMATCH_REASON)
    try:
        apply_targeted_hold_retry(
            snapshot_id="snap-1",
            holds=holds,
            items_by_asset_id={4523: _item()},
            membership_ids={MID},
            r2=R2Store(FakeS3()),
            versions=_WritableVersions(),
            reasons=[FILENAME_MISMATCH_REASON],
        )
        assert False
    except StopRun as e:
        assert e.reason == "HOLD_REASON_NOT_RETRYABLE"
    assert holds.open_rows("snap-1")[0]["status"] == "OPEN"


def test_oversize_rejected_from_retry_scope():
    holds = _ProdHolds()
    _record(holds, 99, OVERSIZE_REASON)
    try:
        apply_targeted_hold_retry(
            snapshot_id="snap-1",
            holds=holds,
            items_by_asset_id={99: _item(asset_id=99)},
            membership_ids={MID},
            r2=R2Store(FakeS3()),
            versions=_WritableVersions(),
            reasons=[OVERSIZE_REASON],
        )
        assert False
    except StopRun as e:
        assert e.reason == "HOLD_REASON_NOT_RETRYABLE"
    assert holds.open_rows("snap-1")[0]["status"] == "OPEN"


def test_dry_run_targets_from_open_holds_not_hardcoded_ids():
    holds = MemoryHoldStore()
    snap = FROZEN_SNAPSHOT_ID
    for i in range(9):
        _record(holds, 1000 + i, MULTI_MATCH_REASON, snap)
    for i in range(65):
        _record(holds, 2000 + i, BINARY_UNAVAILABLE_REASON, snap)
    for i in range(88):
        _record(holds, 3000 + i, FILENAME_MISMATCH_REASON, snap)
    for i in range(6):
        _record(holds, 4000 + i, OVERSIZE_REASON, snap)
    plan = hold_retry_dry_run(snapshot_id=snap, holds=holds, enforce_baseline=True)
    assert plan["status"] == "HOLD_RETRY_DRY_RUN"
    assert plan["open_holds"] == 168
    assert plan["multi_match_open"] == 9
    assert plan["binary_unavailable_open"] == 65
    assert plan["target_total"] == 74
    assert plan["excluded_filename"] == 88
    assert plan["excluded_oversize"] == 6
    assert plan["excluded_total"] == 94
    assert plan["target_total"] + plan["excluded_total"] == 168
    assert len(plan["multi_match_target_ids"]) == 9
    assert len(plan["binary_retry_target_ids"]) == 65
    assert 1000 in plan["multi_match_target_ids"]
    assert 3000 not in plan["multi_match_target_ids"]
    assert 3000 not in plan["binary_retry_target_ids"]
    assert plan["kosha_binary_get"] == 0
    assert plan["r2_put"] == 0
    assert plan["version_dml"] == 0
    assert plan["hold_dml"] == 0


def test_dry_run_does_not_call_store_or_resolve():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    plan = hold_retry_dry_run(snapshot_id="snap-1", holds=holds)
    assert plan["target_total"] == 1
    assert holds.open_rows("snap-1")[0]["status"] == "OPEN"


def _apply_ok(*, reason, atch, files, item=None):
    holds = _ProdHolds()
    item = item or _item(asset_id=6484)
    _record(holds, item["asset_id"], reason)
    fetch_binary, n = _pdf_binary()
    vs = _WritableVersions()
    store = R2Store(FakeS3())
    out = apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={item["asset_id"]: item},
        membership_ids={MID},
        r2=store,
        versions=vs,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: atch,
        fetch_file_list_fn=lambda atcfl_no: files,
        fetch_binary_fn=fetch_binary,
    )
    return out, holds, vs, n, store


def test_multi_match_reason_accepted_and_resolves_after_storage():
    out, holds, vs, n, r2 = _apply_ok(
        reason=MULTI_MATCH_REASON, atch=_dup_atch(), files=_dup_files(),
    )
    assert out["resolved"] == 1
    assert out["open_kept"] == 0
    row = holds.rows[0]
    assert row["status"] == "RESOLVED"
    assert row["resolution_note"] == RESOLUTION_NOTE_MULTI
    assert row["resolved_at"].endswith("+09:00")
    assert vs.dml == 1
    assert n["c"] >= 1
    assert len(vs.current_for_asset(6484)) == 1


def test_binary_unavailable_reason_accepted_and_resolves_after_storage():
    item = _item(asset_id=2029, file_size=0)
    out, holds, vs, n, r2 = _apply_ok(
        reason=BINARY_UNAVAILABLE_REASON, atch=_atch_json(), files=_ok_files(), item=item,
    )
    assert out["resolved"] == 1
    assert holds.rows[0]["status"] == "RESOLVED"
    assert holds.rows[0]["resolution_note"] == RESOLUTION_NOTE_BINARY
    assert vs.dml == 1


def test_failed_binary_keeps_open():
    holds = _ProdHolds()
    item = _item(asset_id=2029, file_size=0)
    _record(holds, 2029, BINARY_UNAVAILABLE_REASON)

    def fetch_binary(**k):
        raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)

    out = apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={2029: item},
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_WritableVersions(),
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: _ok_files(),
        fetch_binary_fn=fetch_binary,
    )
    assert out["resolved"] == 0
    assert out["open_kept"] == 1
    assert holds.rows[0]["status"] == "OPEN"
    assert holds.inserts == 1


def test_storage_failure_keeps_open():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)

    def store_one(item, **k):
        raise StorageError("R2_PUT_ERROR")

    out = apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={6484: _item(asset_id=6484)},
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_WritableVersions(),
        store_one_fn=store_one,
    )
    assert out["open_kept"] == 1
    assert holds.rows[0]["status"] == "OPEN"


def test_version_failure_keeps_open():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    vs = _WritableVersions()
    vs.fail_promote = True
    fetch_binary, _n = _pdf_binary()
    out = apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={6484: _item(asset_id=6484)},
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=vs,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _dup_atch(),
        fetch_file_list_fn=lambda atcfl_no: _dup_files(),
        fetch_binary_fn=fetch_binary,
    )
    assert out["resolved"] == 0
    assert out["open_kept"] == 1
    assert holds.rows[0]["status"] == "OPEN"
    assert vs.dml == 0


def test_integrity_failure_keeps_open():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)

    def fetch_binary(**k):
        raise BinaryFetchError("EMPTY_BODY")

    out = apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={6484: _item(asset_id=6484)},
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_WritableVersions(),
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _dup_atch(),
        fetch_file_list_fn=lambda atcfl_no: _dup_files(),
        fetch_binary_fn=fetch_binary,
    )
    assert out["resolved"] == 0
    assert out["open_kept"] == 1
    assert holds.rows[0]["status"] == "OPEN"


def test_resolve_failure_after_storage_stops():
    class _FailResolve(_ProdHolds):
        def resolve_open(self, **k):
            raise HoldError("HOLD_WRITE_FAILED")

    holds = _FailResolve()
    _record(holds, 6484, MULTI_MATCH_REASON)
    fetch_binary, _n = _pdf_binary()
    vs = _WritableVersions()
    r2 = R2Store(FakeS3())
    try:
        apply_targeted_hold_retry(
            snapshot_id="snap-1",
            holds=holds,
            items_by_asset_id={6484: _item(asset_id=6484)},
            membership_ids={MID},
            r2=r2,
            versions=vs,
            fetch_detail_fn=lambda medseq: _detail_json(medseq),
            fetch_atch_fn=lambda medseq: _dup_atch(),
            fetch_file_list_fn=lambda atcfl_no: _dup_files(),
            fetch_binary_fn=fetch_binary,
        )
        assert False
    except StopRun as e:
        assert e.reason == "HOLD_RESOLVE_FAILED"
    assert vs.dml == 1
    assert holds.rows[0]["status"] == "OPEN"
    assert r2.puts == 1


def _verified_current_fixture(*, storage_key="kosha/x", body=b"%PDF-1.4 stale", **overrides):
    item = _item(asset_id=6484)
    item["source_asset_key"] = item["checksum"]
    sha = hashlib.sha256(body).hexdigest()
    s3 = FakeS3()
    s3.objects[storage_key] = {
        "Body": body,
        "ContentType": "application/pdf",
        "Metadata": {},
        "ETag": '"not-sha"',
    }
    vs = _WritableVersions()
    row = {
        "asset_id": 6484,
        "is_current_version": True,
        "is_derivative": False,
        "storage_bucket": ALLOWED_BUCKET,
        "storage_key": storage_key,
        "content_checksum": sha,
        "source_asset_key": item["source_asset_key"],
    }
    row.update(overrides)
    vs.rows[row["source_asset_key"]] = row
    return item, vs, R2Store(s3), s3


def _stale_retry(holds, item, vs, r2, fetch_binary):
    return apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={item["asset_id"]: item},
        membership_ids={MID},
        r2=r2,
        versions=vs,
        fetch_detail_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no detail")),
        fetch_atch_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no atch")),
        fetch_file_list_fn=lambda n: (_ for _ in ()).throw(AssertionError("no files")),
        fetch_binary_fn=fetch_binary,
    )


def test_verified_existing_current_resolves_without_binary_or_version_dml():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    item, vs, r2, s3 = _verified_current_fixture()
    called = {"n": 0}

    def fetch_binary(**k):
        called["n"] += 1
        raise AssertionError("binary GET 0 for verified stale recovery")

    dml0 = vs.dml
    puts0 = r2.puts
    out = _stale_retry(holds, item, vs, r2, fetch_binary)
    assert out["resolved"] == 1
    assert called["n"] == 0
    assert vs.dml == dml0 == 0
    assert r2.puts == puts0 == 0
    assert s3.puts == 0
    row = holds.rows[0]
    assert row["status"] == "RESOLVED"
    assert row["resolution_note"] == RESOLUTION_NOTE_STALE
    assert row["resolved_at"].endswith("+09:00")


def test_existing_current_source_asset_key_mismatch_stops_open():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    item, vs, r2, _s3 = _verified_current_fixture(source_asset_key="other-identity")
    called = {"n": 0}

    def fetch_binary(**k):
        called["n"] += 1
        raise AssertionError("binary GET 0")

    try:
        _stale_retry(holds, item, vs, r2, fetch_binary)
        assert False
    except StopRun as e:
        assert e.reason == "VERSION_IDENTITY_MISMATCH"
    assert called["n"] == 0
    assert vs.dml == 0
    assert r2.puts == 0
    assert holds.rows[0]["status"] == "OPEN"


def test_existing_current_count_gt_one_stops_open():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    item, vs, r2, _s3 = _verified_current_fixture()
    vs.rows["other"] = dict(vs.rows[item["source_asset_key"]], source_asset_key="other")
    called = {"n": 0}

    def fetch_binary(**k):
        called["n"] += 1
        raise AssertionError("binary GET 0")

    try:
        _stale_retry(holds, item, vs, r2, fetch_binary)
        assert False
    except StopRun as e:
        assert e.reason == "CURRENT_NOT_UNIQUE"
    assert called["n"] == 0
    assert holds.rows[0]["status"] == "OPEN"


def test_existing_current_r2_readback_failure_stops_open():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    item, vs, r2, s3 = _verified_current_fixture()
    s3.objects["kosha/x"]["Body"] = b"tampered-not-matching-checksum"
    called = {"n": 0}

    def fetch_binary(**k):
        called["n"] += 1
        raise AssertionError("binary GET 0")

    try:
        _stale_retry(holds, item, vs, r2, fetch_binary)
        assert False
    except StopRun as e:
        assert e.reason == "READBACK_MISMATCH"
    assert called["n"] == 0
    assert vs.dml == 0
    assert r2.puts == 0
    assert holds.rows[0]["status"] == "OPEN"


def test_existing_current_missing_storage_fields_stops_open():
    called = {"n": 0}

    def fetch_binary(**k):
        called["n"] += 1
        raise AssertionError("binary GET 0")

    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    item, vs, r2, _s3 = _verified_current_fixture(storage_key="")
    try:
        _stale_retry(holds, item, vs, r2, fetch_binary)
        assert False
    except StopRun as e:
        assert e.reason == "VERSION_OBJECT_MISSING"
    assert holds.rows[0]["status"] == "OPEN"

    holds2 = _ProdHolds()
    _record(holds2, 6484, MULTI_MATCH_REASON)
    item2, vs2, r22, _s32 = _verified_current_fixture(content_checksum="")
    try:
        _stale_retry(holds2, item2, vs2, r22, fetch_binary)
        assert False
    except StopRun as e:
        assert e.reason == "VERSION_READBACK_MISMATCH"
    assert called["n"] == 0
    assert holds2.rows[0]["status"] == "OPEN"


def test_verified_stale_resolve_db_failure_stops_open():
    class _FailResolve(_ProdHolds):
        def resolve_open(self, **k):
            raise HoldError("HOLD_WRITE_FAILED")

    holds = _FailResolve()
    _record(holds, 6484, MULTI_MATCH_REASON)
    item, vs, r2, _s3 = _verified_current_fixture()
    called = {"n": 0}

    def fetch_binary(**k):
        called["n"] += 1
        raise AssertionError("binary GET 0")

    try:
        _stale_retry(holds, item, vs, r2, fetch_binary)
        assert False
    except StopRun as e:
        assert e.reason == "HOLD_RESOLVE_FAILED"
    assert called["n"] == 0
    assert vs.dml == 0
    assert r2.puts == 0
    assert holds.rows[0]["status"] == "OPEN"


def test_postcondition_requires_exactly_one_current_version():
    holds = _ProdHolds()
    _record(holds, 6484, MULTI_MATCH_REASON)
    vs = _WritableVersions()

    def store_one(item, **k):
        vs.rows["a"] = {
            "asset_id": 6484, "is_current_version": True, "is_derivative": False,
            "storage_bucket": ALLOWED_BUCKET, "storage_key": "k1", "content_checksum": "c1",
            "source_asset_key": "a",
        }
        vs.rows["b"] = {
            "asset_id": 6484, "is_current_version": True, "is_derivative": False,
            "storage_bucket": ALLOWED_BUCKET, "storage_key": "k2", "content_checksum": "c2",
            "source_asset_key": "b",
        }
        return {
            "status": "NEW_VERSION",
            "source_asset_key": "a",
            "content_checksum": "c1",
            "storage_key": "k1",
        }

    try:
        apply_targeted_hold_retry(
            snapshot_id="snap-1",
            holds=holds,
            items_by_asset_id={6484: _item(asset_id=6484)},
            membership_ids={MID},
            r2=R2Store(FakeS3()),
            versions=vs,
            store_one_fn=store_one,
        )
        assert False
    except StopRun as e:
        assert e.reason == "CURRENT_NOT_UNIQUE"
    assert holds.rows[0]["status"] == "OPEN"


def test_filename_and_oversize_unreachable_from_default_retry():
    holds = _ProdHolds()
    _record(holds, 4523, FILENAME_MISMATCH_REASON)
    _record(holds, 77, OVERSIZE_REASON)
    _record(holds, 6484, MULTI_MATCH_REASON)
    fetch_binary, n = _pdf_binary()
    out = apply_targeted_hold_retry(
        snapshot_id="snap-1",
        holds=holds,
        items_by_asset_id={
            4523: _item(asset_id=4523),
            77: _item(asset_id=77),
            6484: _item(asset_id=6484),
        },
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_WritableVersions(),
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _dup_atch(),
        fetch_file_list_fn=lambda atcfl_no: _dup_files(),
        fetch_binary_fn=fetch_binary,
    )
    statuses = {r["asset_id"]: r["status"] for r in holds.rows}
    assert statuses[4523] == "OPEN"
    assert statuses[77] == "OPEN"
    assert statuses[6484] == "RESOLVED"
    assert out["attempted"] == 1
    assert n["c"] >= 1
