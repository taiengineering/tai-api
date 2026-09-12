"""WO-SAFETY-LIBRARY-002 daily ingest orchestration tests. No live KOSHA/R2/DB."""
from __future__ import annotations

import asyncio

from services.kosha_safety_materials.daily_sync import (
    EXIT_FAIL,
    EXIT_OK,
    network_preflight,
    run_daily,
    try_acquire_lock,
)


def _latest(sid="snap-9223", n=9223):
    return {
        "id": sid,
        "status": "COMPLETED",
        "snapshot_hash": "abc",
        "unique_count": n,
    }


def _ok_preflight():
    return {"ok": True, "code": "NETWORK_PREFLIGHT_OK", "reason": None, "http_status": 200}


def _ok_consistency(*, snapshot_id: str):
    return {
        "ok": True,
        "membership": 9223,
        "list_universe": 9223,
        "stats_universe": 9223,
        "historical_leak": 0,
    }


def _done_detail(**over):
    base = {
        "status": "FULL_SWEEP_COMPLETE",
        "pending_before": 0,
        "pending_after": 0,
        "remaining": 0,
        "selected": 0,
        "new_detail_rows": 0,
        "stop_reason": None,
    }
    base.update(over)
    return base


def _done_storage(**over):
    base = {
        "status": "STORAGE_SWEEP_COMPLETE_WITH_HOLDS",
        "batches": 1,
        "stored": 0,
        "remaining": 0,
        "actionable_pending": 0,
        "HOLD": 0,
        "held": 168,
        "existing_open_holds": 168,
        "r2_overwrite": 0,
        "r2_delete": 0,
    }
    base.update(over)
    return base


async def _run(**kw):
    defaults = dict(
        preflight_fn=_ok_preflight,
        latest_completed_fn=_latest,
        consistency_fn=_ok_consistency,
        host="test-host",
        max_detail_batches=8,
    )
    defaults.update(kw)
    return await run_daily(**defaults)


def test_a1_no_change_pending_zero_success():
    calls = {"detail": 0, "storage": 0, "sync": 0}

    async def sync_fn(*, dry_run, start_page):
        calls["sync"] += 1
        assert dry_run is False and start_page == 1
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0, "snapshot_id": None}

    def detail_batch_fn(*, snapshot_id, batch_size):
        calls["detail"] += 1
        assert snapshot_id == "snap-9223"
        assert batch_size == 100
        return _done_detail()

    def storage_fn(*, snapshot_id):
        calls["storage"] += 1
        assert snapshot_id == "snap-9223"
        return _done_storage(status="FULL_BULK_COMPLETE", held=0, existing_open_holds=0)

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_OK
    assert report["final_status"] == "SUCCESS"
    assert report["snapshot_result"] == "SNAPSHOT_NO_CHANGE"
    assert calls["sync"] == calls["detail"] == calls["storage"] == 1
    assert report["detail_pending"] == 0
    assert report["storage_pending"] == 0


def test_a2_new_catalog_snapshot_detail_storage_success():
    async def sync_fn(*, dry_run, start_page):
        return {"status": "COMPLETED", "catalog_dml": 4, "snapshot_hash": "newhash"}

    def latest():
        return _latest("snap-new", 9227)

    def detail_batch_fn(*, snapshot_id, batch_size):
        assert snapshot_id == "snap-new"
        return _done_detail(pending_before=4, new_detail_rows=4)

    def storage_fn(*, snapshot_id):
        return _done_storage(status="FULL_BULK_COMPLETE", stored=3, batches=2, held=0, existing_open_holds=0)

    report, code = asyncio.run(_run(
        sync_fn=sync_fn, latest_completed_fn=latest,
        detail_batch_fn=detail_batch_fn, storage_fn=storage_fn,
        consistency_fn=lambda **k: {
            "ok": True, "membership": 9227, "list_universe": 9227,
            "stats_universe": 9227, "historical_leak": 0,
        },
    ))
    assert code == EXIT_OK
    assert report["catalog_new"] == 4
    assert report["snapshot_id"] == "snap-new"
    assert report["detail_new"] == 4
    assert report["storage_completed"] == 3


def test_a3_snapshot_no_change_still_resumes_detail_and_storage():
    """Yesterday snapshot completed; detail/storage still pending today."""
    detail_calls = {"n": 0}

    async def sync_fn(*, dry_run, start_page):
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0}

    def detail_batch_fn(*, snapshot_id, batch_size):
        detail_calls["n"] += 1
        if detail_calls["n"] == 1:
            return {
                "status": "BATCH_OK",
                "pending_before": 12,
                "pending_after": 2,
                "remaining": 2,
                "selected": 10,
                "new_detail_rows": 10,
                "stop_reason": None,
            }
        return _done_detail(pending_before=2, new_detail_rows=2)

    def storage_fn(*, snapshot_id):
        return _done_storage(stored=2, remaining=0, actionable_pending=0)

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_OK
    assert report["snapshot_result"] == "SNAPSHOT_NO_CHANGE"
    assert detail_calls["n"] == 2
    assert report["detail_new"] == 12
    assert report["storage_completed"] == 2


def test_a4_network_failure_does_not_sync():
    called = {"sync": 0}

    async def sync_fn(*, dry_run, start_page):
        called["sync"] += 1
        raise AssertionError("sync must not run after preflight fail")

    def boom_detail(*, snapshot_id, batch_size):
        raise AssertionError("detail must not run")

    def boom_storage(*, snapshot_id):
        raise AssertionError("storage must not run")

    report, code = asyncio.run(_run(
        preflight_fn=lambda: {"ok": False, "code": "NETWORK_PREFLIGHT_FAIL", "reason": "CODE10"},
        sync_fn=sync_fn,
        detail_batch_fn=boom_detail,
        storage_fn=boom_storage,
    ))
    assert code == EXIT_FAIL
    assert report["final_status"] == "NETWORK_PREFLIGHT_FAIL"
    assert called["sync"] == 0
    assert report["snapshot_result"] is None


def test_a5_detail_systemic_does_not_start_storage():
    storage = {"n": 0}

    async def sync_fn(*, dry_run, start_page):
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0}

    def detail_batch_fn(*, snapshot_id, batch_size):
        return {
            "status": "QUOTA_BLOCKED",
            "stop_reason": "QUOTA_BLOCKED",
            "pending_before": 9,
            "pending_after": 9,
            "remaining": 9,
            "selected": 0,
            "new_detail_rows": 0,
        }

    def storage_fn(*, snapshot_id):
        storage["n"] += 1
        raise AssertionError("storage must not start after DETAIL_STOP")

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_FAIL
    assert report["final_status"] == "DETAIL_STOP"
    assert storage["n"] == 0


def test_a6_open_holds_excluded_pipeline_continues():
    async def sync_fn(*, dry_run, start_page):
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0}

    def detail_batch_fn(*, snapshot_id, batch_size):
        return _done_detail()

    def storage_fn(*, snapshot_id):
        return _done_storage(
            status="STORAGE_SWEEP_COMPLETE_WITH_HOLDS",
            actionable_pending=0,
            remaining=0,
            held=168,
            existing_open_holds=168,
            HOLD=0,
        )

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_OK
    assert report["existing_open_holds"] == 168
    assert report["storage_pending"] == 0


def test_a7_no_progress_stops_nonzero():
    async def sync_fn(*, dry_run, start_page):
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0}

    def detail_batch_fn(*, snapshot_id, batch_size):
        return {
            "status": "BATCH_OK",
            "pending_before": 7,
            "pending_after": 7,
            "remaining": 7,
            "selected": 7,
            "new_detail_rows": 0,
        }

    def storage_fn(*, snapshot_id):
        raise AssertionError("storage must not run after NO_PROGRESS")

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_FAIL
    assert report["final_status"] == "NO_PROGRESS"


def test_a8_storage_asset_level_hold_other_assets_continue():
    async def sync_fn(*, dry_run, start_page):
        return {"status": "COMPLETED", "catalog_dml": 1}

    def detail_batch_fn(*, snapshot_id, batch_size):
        return _done_detail(new_detail_rows=1, pending_before=1)

    def storage_fn(*, snapshot_id):
        return _done_storage(
            status="STORAGE_SWEEP_COMPLETE_WITH_HOLDS",
            stored=2,
            HOLD=1,
            new_hold_count=1,
            remaining=0,
            actionable_pending=0,
            held=169,
            existing_open_holds=169,
        )

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_OK
    assert report["new_hold_count"] == 1
    assert report["storage_completed"] == 2
    assert report["storage_pending"] == 0


def test_a9_immutable_r2_overwrite_and_delete_zero():
    async def sync_fn(*, dry_run, start_page):
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0}

    def detail_batch_fn(*, snapshot_id, batch_size):
        return _done_detail()

    def storage_fn(*, snapshot_id):
        return _done_storage(r2_overwrite=0, r2_delete=0, stored=1)

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_OK
    assert report["r2_overwrite"] == 0
    assert report["r2_delete"] == 0


def test_a9b_overwrite_is_storage_stop():
    async def sync_fn(*, dry_run, start_page):
        return {"status": "SNAPSHOT_NO_CHANGE", "catalog_dml": 0}

    def detail_batch_fn(*, snapshot_id, batch_size):
        return _done_detail()

    def storage_fn(*, snapshot_id):
        return _done_storage(r2_overwrite=1, r2_delete=0)

    report, code = asyncio.run(_run(sync_fn=sync_fn, detail_batch_fn=detail_batch_fn, storage_fn=storage_fn))
    assert code == EXIT_FAIL
    assert report["failure_code"] == "R2_MUTATION_FORBIDDEN"


def test_preflight_missing_key():
    out = network_preflight(service_key="", get_fn=lambda *a, **k: (200, "ok"))
    assert out["ok"] is False
    assert out["reason"] == "SERVICE_KEY_MISSING"


def test_preflight_code10_stops():
    out = network_preflight(
        service_key="k",
        get_fn=lambda *a, **k: (200, '<response><header><resultCode>10</resultCode></header></response>'),
    )
    assert out["ok"] is False
    assert out["reason"] == "CODE10"


def test_preflight_http_403():
    out = network_preflight(service_key="k", get_fn=lambda *a, **k: (403, "denied"))
    assert out["ok"] is False
    assert out["reason"] == "AUTH"


def test_single_flight_second_acquire_is_none(monkeypatch):
    import fcntl

    class Boom:
        def fileno(self):
            return 7
        def write(self, _x):
            return None
        def flush(self):
            return None
        def close(self):
            return None

    def fake_open(*_a, **_k):
        return Boom()

    def fake_flock(_fd, flags):
        if flags & fcntl.LOCK_NB:
            raise BlockingIOError()

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr("fcntl.flock", fake_flock)
    assert try_acquire_lock("/tmp/kosha-daily-test.lock") is None
