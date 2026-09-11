"""WP-1C-4B current detail enrichment — no live KOSHA, no data.go.kr."""
from __future__ import annotations

import inspect
import json
import os
import urllib.error

from routers import kosha_collect as kc
from services.kosha_safety_materials import enrichment as enr
from services.kosha_safety_materials.asset_parser import parse_attachments
from services.kosha_safety_materials.detail_client import (
    MaterialFetchError,
    StopRun,
    classify_http_status,
    post_json,
)
from services.kosha_safety_materials.license_policy import decide
from services.kosha_safety_materials.normalizer import canonical_hash, normalize_detail
from services.kosha_safety_materials.parser import parse_detail
from services.kosha_safety_materials.writer import MemoryStore, Writer

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "kosha")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _wrap(js, status=200):
    return {"ok": True, "status": status, "json": js, "final_url": "https://portal.kosha.or.kr/x"}


def _store(*, n=5, existing=0, unique=None, historical=0):
    s = MemoryStore()
    sid = "snap-1"
    unique = n if unique is None else unique
    s.snapshots.append({
        "id": sid, "status": "COMPLETED", "unique_count": unique,
        "snapshot_hash": "hash-1", "completed_at": "2026-09-11T00:00:00+00:00",
    })
    for i in range(1, n + 1):
        mid = f"m{i:03d}"
        seq = str(i)
        url = f"https://portal.kosha.or.kr/archive/x?medSeq={seq}"
        s.catalog[mid] = {"id": mid, "title": f"자료 {i}", "url": url}
        s.items.append({
            "snapshot_id": sid, "material_id": mid, "source_med_seq": seq,
            "source_url": url, "source_title": f"자료 {i}",
        })
    for i in range(1, existing + 1):
        mid = f"m{i:03d}"
        s.details[mid] = {
            "material_id": mid, "source_content_hash": "existing",
            "enrichment_status": "OK", "source_med_seq": str(i),
        }
    for i in range(historical):
        hid = f"h{i}"
        s.catalog[hid] = {"id": hid, "title": "과거", "url": "https://portal.kosha.or.kr/x?medSeq=99999"}
    return s


def _ok_fetch(seq):
    js = _load("f1_kogl04_atch.json")
    js["payload"]["list"][0]["medSeq"] = int(seq)
    return _wrap(js)


def _ok_atch(_seq):
    return _wrap(_load("f1_atch.json"))


def test_snapshot_precondition_completed_and_count():
    s = _store(n=5)
    pre = enr.snapshot_precondition(s)
    assert pre["membership_count"] == 5
    s.snapshots[0]["unique_count"] = 4
    try:
        enr.snapshot_precondition(s)
        assert False
    except enr.SnapshotInvalid:
        pass


def test_latest_completed_only_and_historical_excluded():
    s = _store(n=3, historical=2)
    s.snapshots.append({
        "id": "old", "status": "FAILED", "unique_count": 1,
        "completed_at": "2026-09-12T00:00:00+00:00",
    })
    pre = enr.snapshot_precondition(s)
    assert pre["snapshot"]["id"] == "snap-1"
    pending = enr.select_pending(s, "snap-1", limit=100)
    ids = {p["material_id"] for p in pending}
    assert "h0" not in ids and "h1" not in ids
    assert ids == {"m001", "m002", "m003"}


def test_existing_detail_excluded_and_missing_selected_ordered():
    s = _store(n=5, existing=2)
    pending = enr.select_pending(s, "snap-1", limit=100)
    assert [p["source_med_seq"] for p in pending] == ["3", "4", "5"]
    first = enr.select_pending(s, "snap-1", limit=2)
    assert [p["source_med_seq"] for p in first] == ["3", "4"]


def test_batch_size_100_cap_and_resume_next_missing():
    s = _store(n=250, existing=0)
    batch = enr.select_pending(s, "snap-1", limit=100)
    assert len(batch) == 100
    assert batch[0]["source_med_seq"] == "1"
    assert batch[-1]["source_med_seq"] == "100"
    w = Writer(dry_run=False, store=s)
    r = enr.enrich_one(batch[0], w, fetch_detail_fn=_ok_fetch, fetch_attachments_fn=_ok_atch, sleep_s=0)
    assert r["result"] == "INSERT"
    nxt = enr.select_pending(s, "snap-1", limit=100)
    assert nxt[0]["source_med_seq"] == "2"
    assert "m001" not in {x["material_id"] for x in nxt}


def test_429_403_401_no_failure_row_and_stop():
    s = _store(n=3)

    def boom(reason, status):
        def fd(_seq):
            raise StopRun(reason, http_status=status, endpoint="selectMediaList")
        return fd

    for reason, status in (("QUOTA_BLOCKED", 429), ("ACCESS_BLOCKED", 403), ("ACCESS_BLOCKED", 401)):
        st = _store(n=3)
        out = enr.run_one_batch(
            st, run_snapshot_id="snap-1", batch_size=3, dry_run=False, sleep_s=0,
            fetch_detail_fn=boom(reason, status), fetch_attachments_fn=_ok_atch, sleeper=lambda *_: None,
            log=lambda *_: None,
        )
        assert out["status"] == reason
        assert st.count("kosha_safety_material_details") == 0
        assert out["new_detail_rows"] == 0


def test_transient_stop_remains_resumable():
    s = _store(n=2)
    calls = {"n": 0}

    def fd(_seq):
        calls["n"] += 1
        raise StopRun("TRANSIENT_UPSTREAM_FAILURE", http_status=503, endpoint="selectMediaList")

    out = enr.run_one_batch(
        s, run_snapshot_id="snap-1", batch_size=2, dry_run=False, sleep_s=0,
        fetch_detail_fn=fd, fetch_attachments_fn=_ok_atch, sleeper=lambda *_: None, log=lambda *_: None,
    )
    assert out["status"] == "TRANSIENT_UPSTREAM_FAILURE"
    assert s.count("kosha_safety_material_details") == 0
    assert len(enr.select_pending(s, "snap-1", limit=10)) == 2


def test_http_status_classifier_and_forbidden_binary_path():
    assert classify_http_status(429) == "QUOTA_BLOCKED"
    assert classify_http_status(403) == "ACCESS_BLOCKED"
    assert classify_http_status(401) == "ACCESS_BLOCKED"
    assert classify_http_status(404) == "DETAIL_HTTP_404"
    assert classify_http_status(500) == "TRANSIENT_UPSTREAM"
    try:
        post_json("downloadAtchFile", {"medSeq": 1})
        assert False
    except MaterialFetchError as e:
        assert e.code == "FORBIDDEN_PATH"
    try:
        post_json("getFileList", {"medSeq": 1})
        assert False
    except MaterialFetchError as e:
        assert e.code == "FORBIDDEN_PATH"


def test_404_empty_malformed_write_validated_failed():
    s = _store(n=3)
    w = Writer(dry_run=False, store=s)

    def fd404(_seq):
        raise MaterialFetchError("DETAIL_HTTP_404", status=404)

    r = enr.enrich_one(s.items[0], w, fetch_detail_fn=fd404, fetch_attachments_fn=_ok_atch, sleep_s=0)
    assert r["result"] == "FAILED"
    assert r["failure_reason"] == "DETAIL_HTTP_404"
    assert s.details["m001"]["enrichment_status"] == "FAILED"

    def fd_empty(_seq):
        return _wrap(_load("f8_empty.json"))

    r2 = enr.enrich_one(s.items[1], w, fetch_detail_fn=fd_empty, fetch_attachments_fn=_ok_atch, sleep_s=0)
    assert r2["result"] == "FAILED"
    assert r2["failure_reason"] == "DETAIL_EMPTY"

    def fd_bad(_seq):
        return _wrap(_load("f6_malformed.json"))

    r3 = enr.enrich_one(s.items[2], w, fetch_detail_fn=fd_bad, fetch_attachments_fn=_ok_atch, sleep_s=0)
    assert r3["result"] == "FAILED"
    assert r3["write"]["detail_writes"] == 1


def test_medseq_mismatch_no_write_stop():
    s = _store(n=2)

    def fd(_seq):
        return _wrap(_load("f7_medseq_mismatch.json"))

    out = enr.run_one_batch(
        s, run_snapshot_id="snap-1", batch_size=2, dry_run=False, sleep_s=0,
        fetch_detail_fn=fd, fetch_attachments_fn=_ok_atch, sleeper=lambda *_: None, log=lambda *_: None,
    )
    assert out["status"] == "MEDSEQ_MISMATCH"
    assert s.count("kosha_safety_material_details") == 0


def test_catalog_snapshot_historical_r2_binary_guards():
    s = _store(n=2)
    cat_before = s.count("kosha_safety_materials")
    snap_before = s.count("kosha_safety_material_snapshots")
    items_before = s.count("kosha_safety_material_snapshot_items")
    hist_id = "h0"
    s.catalog[hist_id] = {"id": hist_id, "title": "과거", "url": "https://portal.kosha.or.kr/x?medSeq=9"}
    out = enr.run_until_done(
        s, batch_size=100, dry_run=False, sleep_s=0,
        fetch_detail_fn=_ok_fetch, fetch_attachments_fn=_ok_atch,
        sleeper=lambda *_: None, log=lambda *_: None,
    )
    assert out["status"] == "FULL_SWEEP_COMPLETE"
    assert s.dml["catalog"] == 0
    assert s.dml["snapshots"] == 0
    assert s.dml["snapshot_items"] == 0
    assert s.dml["asset_versions"] == 0
    assert s.binary_gets == 0
    assert s.r2_ops == 0
    assert s.data_go_kr_calls == 0
    assert s.count("kosha_safety_materials") == cat_before + 1  # historical catalog row we added locally
    assert hist_id not in s.details
    assert s.count("kosha_safety_material_snapshots") == snap_before
    assert s.count("kosha_safety_material_snapshot_items") == items_before
    assert out["totals"]["new_detail_rows"] == 2


def test_video_storage_false_unknown_link_only_same_hash_no_change():
    assert decide("00").render_policy == "LINK_ONLY"
    assert decide("UNKNOWN").render_policy == "LINK_ONLY"
    d = decide("1", "VIDEO", official_embed_confirmed=False)
    assert d.storage_allowed is False
    assert d.render_policy == "LINK_ONLY"
    s = _store(n=1)
    w = Writer(dry_run=False, store=s)
    item = s.items[0]
    r1 = enr.enrich_one(item, w, fetch_detail_fn=_ok_fetch, fetch_attachments_fn=_ok_atch, sleep_s=0)
    assert r1["result"] == "INSERT"
    # first sweep skips existing
    r2 = enr.enrich_one(item, w, fetch_detail_fn=_ok_fetch, fetch_attachments_fn=_ok_atch, sleep_s=0)
    assert r2["result"] == "SKIP_EXISTING"
    # writer NO_CHANGE if allow_update and same hash
    detail = r1["detail"]
    assets = r1["assets"]
    wr = w.upsert(detail, assets, allow_update=True)
    assert wr["op"] == "NO_CHANGE"
    assert wr["detail_writes"] == 0 and wr["asset_writes"] == 0
    for a in assets:
        assert a["storage_allowed"] is False
        assert a["local_storage_url"] is None


def test_dry_run_plan_api0_dml0():
    s = _store(n=12, existing=2)
    before = dict(s.dml)
    plan = enr.dry_run_plan(s, batch_size=100)
    assert plan["status"] == "DRY_RUN"
    assert plan["membership"] == 12
    assert plan["existing_detail_in_current"] == 2
    assert plan["pending_missing"] == 10
    assert plan["planned_first_batch"] == 10
    assert plan["api_calls"] == 0
    assert s.dml == before
    assert s.data_go_kr_calls == 0


def test_existing_20_update0_on_first_sweep():
    s = _store(n=5, existing=2)
    hashes = {k: dict(v) for k, v in s.details.items()}
    enr.run_until_done(
        s, batch_size=100, dry_run=False, sleep_s=0,
        fetch_detail_fn=_ok_fetch, fetch_attachments_fn=_ok_atch,
        sleeper=lambda *_: None, log=lambda *_: None,
    )
    for mid, row in hashes.items():
        assert s.details[mid]["source_content_hash"] == row["source_content_hash"]
        assert s.details[mid]["enrichment_status"] == "OK"


def test_other_collectors_unwired_and_no_data_go_kr():
    src = inspect.getsource(enr)
    assert "apis.data.go.kr" not in src
    assert "selectMediaList01" not in src
    for fn in (
        kc._collect_accident_cases, kc._collect_construction_accidents,
        kc._collect_safety_light, kc._collect_risk_assessment, kc._collect_guide,
        kc._collect_safety_materials,
    ):
        assert "run_one_batch" not in inspect.getsource(fn)
    assert "safety-material-details" in inspect.getsource(kc._dispatch)
    assert "safety-material-details" not in inspect.getsource(kc.collect_all).split("targets =")[1].split("]")[0]


def test_duplicate_asset_checksum_does_not_update_none():
    from services.kosha_safety_materials.asset_parser import logical_checksum
    s = MemoryStore()
    s.catalog["m001"] = {"id": "m001", "title": "t", "url": "https://portal.kosha.or.kr/x"}
    w = Writer(dry_run=False, store=s)
    detail = {
        "material_id": "m001", "source_provider": "KOSHA", "source_med_seq": "1",
        "source_url": "https://portal.kosha.or.kr/x", "source_title": "t",
        "source_description": None, "source_published_at": None, "source_updated_at": None,
        "kogl_type": "4", "license_name": None, "license_source_url": None,
        "commercial_allowed": False, "modification_allowed": False,
        "render_policy": "LINK_ONLY", "content_type": "PDF", "thumbnail_url": None,
        "source_checked_at": "2026-09-11T00:00:00+00:00", "source_content_hash": "h1",
        "enrichment_status": "OK", "failure_reason": None,
    }
    a = {
        "material_id": "m001", "asset_type": "PDF", "file_name": "a.pdf",
        "source_file_url": None, "external_url": "https://portal.kosha.or.kr/x",
        "embed_url": None, "mime_type": "application/pdf", "file_size": 1,
        "local_storage_url": None, "checksum": logical_checksum("m001", "NO", 1, "a.pdf"),
        "display_order": 0, "storage_allowed": False, "is_original": True,
    }
    r = w.upsert(detail, [a, dict(a)], allow_update=False)
    assert r["op"] == "INSERT"
    assert s.count("kosha_safety_material_assets") == 1


def test_failure_validator_mandatory_blocks_invalid_identity():
    s = _store(n=1)
    w = Writer(dry_run=False, store=s)
    r = enr.validate_and_write_failure(
        w, material_id="m001", url="https://evil.example/x", title="t", medseq="1", reason="DETAIL_EMPTY",
    )
    assert r["result"] == "BLOCKED"
    assert s.count("kosha_safety_material_details") == 0
