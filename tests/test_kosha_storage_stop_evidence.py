"""PATCH-5B-STOP-EVIDENCE: STOP JSON item + subreason. HOLD/STOP policy unchanged."""
from __future__ import annotations

import os
import tempfile

from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError, fetch_https_binary
from services.kosha_safety_materials.storage.r2_store import R2Store
from services.kosha_safety_materials.storage.runner import apply_assets, stop_run_payload
from services.kosha_safety_materials.storage.store import StorageError
from tests.test_kosha_binary_fetch import opener_for
from tests.test_kosha_r2_store import FakeS3
from tests.test_kosha_storage_hold import (
    MID, NO, PDF_NAME, _ProdHolds, _ProdVersions, _atch_json, _detail_json, _item,
)
from tests.test_kosha_storage_runner_guard import _FakeStore, _Prod


def test_empty_http_body_records_status_and_zero_bytes():
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "empty.pdf")
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/empty": (
                200, {"Content-Type": "application/pdf", "Content-Length": "0"}, b"",
            ),
        })
        try:
            fetch_https_binary(
                "https://portal.kosha.or.kr/empty", dest, opener=opener, expect_pdf=True,
            )
            assert False
        except BinaryFetchError as e:
            assert e.code == "EMPTY_BODY"
            assert e.status == 200
            assert e.body_bytes_read == 0
            assert e.declared_content_length == "0"


def test_html_not_binary_records_declared_length():
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "page.html")
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/html": (
                200,
                {"Content-Type": "text/html", "Content-Length": "12"},
                b"<html></html>",
            ),
        })
        try:
            fetch_https_binary(
                "https://portal.kosha.or.kr/html", dest, opener=opener, expect_pdf=True,
            )
            assert False
        except BinaryFetchError as e:
            assert e.code == "HTML_NOT_BINARY"
            assert e.status == 200
            assert e.body_bytes_read == 0
            assert e.declared_content_length == "12"


def test_apply_assets_empty_body_stop_includes_item_and_subreason(monkeypatch):
    item = {
        "asset_id": 2029,
        "material_id": "07e716336758f64f",
        "file_name": "348224_제조업-741-2012-베트남어.pdf",
        "file_size": 0,
        "source_med_seq": "38100",
    }

    def boom(*a, **k):
        raise StorageError(
            "BINARY_INTEGRITY_BLOCKED", "EMPTY_BODY",
            subreason="EMPTY_BODY",
            http_status=200,
            body_bytes_read=0,
            declared_content_length="0",
        )

    monkeypatch.setattr("services.kosha_safety_materials.storage.runner._store_one", boom)
    holds = _ProdHolds()
    try:
        apply_assets(
            [item], store=_FakeStore(), query=None, r2=None, versions=_Prod(), holds=holds,
        )
        assert False
    except StopRun as e:
        p = stop_run_payload(e)
        assert p["status"] == "BINARY_INTEGRITY_BLOCKED"
        assert p["stop_reason"] == "BINARY_INTEGRITY_BLOCKED"
        assert p["stop_subreason"] == "EMPTY_BODY"
        assert p["asset_id"] == 2029
        assert p["material_id"] == "07e716336758f64f"
        assert p["file_name"] == "348224_제조업-741-2012-베트남어.pdf"
        assert p["file_size"] == 0
        assert p["source_med_seq"] == "38100"
        assert p["http_status"] == 200
        assert p["body_bytes_read"] == 0
        assert p["declared_content_length"] == "0"
        assert e.reason == "BINARY_INTEGRITY_BLOCKED"
    assert holds.inserts == 0


def test_empty_body_without_http_200_is_still_stop():
    from services.kosha_safety_materials.storage.runner import _store_one

    holds = _ProdHolds()
    r2 = R2Store(FakeS3())
    item = _item(asset_id=2029, file_size=0)

    def fetch_binary(**k):
        raise BinaryFetchError("EMPTY_BODY", body_bytes_read=0)

    try:
        _store_one(
            item,
            membership_ids={MID},
            r2=r2,
            versions=_ProdVersions(),
            snapshot_id="snap-1",
            holds=holds,
            fetch_detail_fn=lambda medseq: _detail_json(medseq),
            fetch_atch_fn=lambda medseq: _atch_json(),
            fetch_file_list_fn=lambda atcfl_no: [
                {"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": PDF_NAME},
            ],
            fetch_binary_fn=fetch_binary,
        )
        assert False
    except StorageError as e:
        assert e.code == "BINARY_INTEGRITY_BLOCKED"
        assert e.subreason == "EMPTY_BODY"
        assert e.body_bytes_read == 0
    assert holds.inserts == 0
    assert r2.puts == 0


def test_filename_mismatch_is_still_hold_not_stop_json():
    from services.kosha_safety_materials.storage.runner import _store_one
    from tests.test_kosha_storage_hold import AI_NAME, OTHER_PDF

    holds = _ProdHolds()
    out = _store_one(
        _item(),
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_ProdVersions(),
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: [
            {"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": AI_NAME},
            {"atcflNo": NO, "atcflSeq": 2, "orgnlAtchFileNm": OTHER_PDF},
        ],
        fetch_binary_fn=lambda **k: (_ for _ in ()).throw(AssertionError("binary GET 0")),
    )
    assert out["status"] == "HOLD"
    assert holds.inserts == 1
