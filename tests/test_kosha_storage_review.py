"""FINAL-SWEEP: asset-level review HOLD vs systemic STOP."""
from __future__ import annotations

from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError
from services.kosha_safety_materials.storage.classify import (
    ContentAnomalyGuard,
    REVIEW_REASON,
    SYSTEMIC_STOP,
    classify_asset_failure,
)
from services.kosha_safety_materials.storage.r2_store import R2Store
from services.kosha_safety_materials.storage.runner import _store_one, apply_assets
from tests.test_kosha_r2_store import FakeS3
from tests.test_kosha_storage_hold import (
    MID, NO, PDF_NAME, _ProdHolds, _ProdVersions, _atch_json, _detail_json, _item,
)
from tests.test_kosha_storage_runner_guard import _FakeStore, _Prod


def _files():
    return [{"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": PDF_NAME}]


def test_classifier_holds_only_allowlisted_subreasons():
    for code in (
        "PDF_MAGIC_MISMATCH", "HTML_NOT_BINARY", "JSON_NOT_BINARY", "TEXT_NOT_BINARY",
        "LICENSE_CHANGED_REVIEW_REQUIRED", "SOURCE_MEDSEQ_MISMATCH",
    ):
        d = classify_asset_failure(code)
        assert d.action == "HOLD"
        assert d.reason == REVIEW_REASON
        assert d.subreason == code
    for code in (
        "HOST_NOT_ALLOWED", "REDIRECT_HOST_BLOCKED", "SCHEME_NOT_ALLOWED",
        "READBACK_MISMATCH", "R2_OBJECT_CONFLICT", "QUOTA_BLOCKED",
        "EMPTY_BODY", "ASSET_ID_REQUIRED",
    ):
        d = classify_asset_failure(code)
        assert d.action == "STOP"
    d = classify_asset_failure("BRAND_NEW_UNKNOWN")
    assert d.action == "STOP"


def test_json_and_text_not_binary_are_review_holds():
    for code in ("JSON_NOT_BINARY", "TEXT_NOT_BINARY"):
        holds = _ProdHolds()

        def fetch_binary(**k):
            raise BinaryFetchError(code, status=200, body_bytes_read=4)

        out = _store_one(
            _item(),
            membership_ids={MID},
            r2=R2Store(FakeS3()),
            versions=_ProdVersions(),
            snapshot_id="snap-1",
            holds=holds,
            fetch_detail_fn=lambda medseq: _detail_json(medseq),
            fetch_atch_fn=lambda medseq: _atch_json(),
            fetch_file_list_fn=lambda atcfl_no: _files(),
            fetch_binary_fn=fetch_binary,
        )
        assert out["status"] == "HOLD"
        assert out["reason"] == REVIEW_REASON
        assert out["subreason"] == code
        assert holds.inserts == 1
        obs = holds.rows[0]["observed_files"][0]
        assert obs["subreason"] == code
        assert obs["http_status"] == 200


def test_host_not_allowed_still_stops():
    holds = _ProdHolds()

    def fetch_binary(**k):
        raise BinaryFetchError("HOST_NOT_ALLOWED", status=200, body_bytes_read=0)

    try:
        _store_one(
            _item(),
            membership_ids={MID},
            r2=R2Store(FakeS3()),
            versions=_ProdVersions(),
            snapshot_id="snap-1",
            holds=holds,
            fetch_detail_fn=lambda medseq: _detail_json(medseq),
            fetch_atch_fn=lambda medseq: _atch_json(),
            fetch_file_list_fn=lambda atcfl_no: _files(),
            fetch_binary_fn=fetch_binary,
        )
        assert False
    except Exception as e:
        from services.kosha_safety_materials.storage.store import StorageError
        assert isinstance(e, StorageError)
        assert e.code == "BINARY_INTEGRITY_BLOCKED"
        assert e.subreason == "HOST_NOT_ALLOWED"
    assert holds.inserts == 0


def test_three_consecutive_html_holds_stop_systemic(monkeypatch):
    holds = _ProdHolds()
    n = {"i": 0}

    def boom(item, **k):
        n["i"] += 1
        return {
            "status": "HOLD",
            "reason": REVIEW_REASON,
            "subreason": "HTML_NOT_BINARY",
            "asset_id": item.get("asset_id"),
            "hold_inserted": 1,
            "r2_put": 0,
            "version_dml": 0,
            "binary_get": 1,
        }

    monkeypatch.setattr("services.kosha_safety_materials.storage.runner._store_one", boom)
    items = [
        {"asset_id": 1, "material_id": "m1"},
        {"asset_id": 2, "material_id": "m1"},
        {"asset_id": 3, "material_id": "m1"},
        {"asset_id": 4, "material_id": "m1"},
    ]
    try:
        apply_assets(items, store=_FakeStore(), query=None, r2=None, versions=_Prod(), holds=holds)
        assert False
    except StopRun as e:
        assert e.reason == SYSTEMIC_STOP
        assert e.evidence.get("asset_id") == 3
    assert n["i"] == 3


def test_content_guard_resets_on_other_result():
    g = ContentAnomalyGuard()
    assert g.note(status="HOLD", subreason="HTML_NOT_BINARY") is None
    assert g.note(status="HOLD", subreason="HTML_NOT_BINARY") is None
    assert g.note(status="NEW_VERSION", subreason=None) is None
    assert g.note(status="HOLD", subreason="HTML_NOT_BINARY") is None
    assert g.note(status="HOLD", subreason="HTML_NOT_BINARY") is None
    assert g.note(status="HOLD", subreason="HTML_NOT_BINARY") == SYSTEMIC_STOP


def test_unknown_exception_stops_not_hold(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("surprise")

    monkeypatch.setattr("services.kosha_safety_materials.storage.runner._store_one", boom)
    try:
        apply_assets(
            [{"asset_id": 9, "material_id": "m1"}],
            store=_FakeStore(), query=None, r2=None, versions=_Prod(),
        )
        assert False
    except StopRun as e:
        assert e.reason == "RuntimeError"
        assert e.evidence.get("asset_id") == 9
