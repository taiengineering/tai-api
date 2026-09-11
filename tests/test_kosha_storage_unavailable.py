"""PATCH-5B-BINARY-UNAVAILABLE: HTTP 200 empty twice → HOLD; integrity still STOP."""
from __future__ import annotations

import hashlib

from services.kosha_safety_materials.storage.binary_fetch import (
    BinaryFetchError,
    confirm_empty_binary_get,
    is_http_200_empty_body,
)
from services.kosha_safety_materials.storage.hold_store import HOLD_REASONS, UNAVAILABLE_REASON
from services.kosha_safety_materials.storage.r2_store import R2Store
from services.kosha_safety_materials.storage.runner import _store_one
from services.kosha_safety_materials.storage.store import StorageError
from tests.test_kosha_binary_fetch import PDF
from tests.test_kosha_r2_store import FakeS3
from tests.test_kosha_storage_hold import (
    MID, NO, PDF_NAME, _ProdHolds, _ProdVersions, _atch_json, _detail_json, _item,
)


class _WritableVersions:
    def __init__(self):
        self.rows = {}
        self.dml = 0

    def current(self, key):
        return self.rows.get(key)

    def current_count(self, key):
        return 1 if key in self.rows else 0

    def promote(self, payload):
        self.dml += 1
        row = dict(payload)
        row["id"] = self.dml
        row["status"] = "NEW_VERSION"
        self.rows[payload["source_asset_key"]] = row
        return {"status": "NEW_VERSION", "id": self.dml, "dml": 1, "row": row}


def _files():
    return [{"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": PDF_NAME}]


def test_unavailable_reason_is_hold_allowlisted():
    assert UNAVAILABLE_REASON in HOLD_REASONS
    assert UNAVAILABLE_REASON == "SOURCE_BINARY_UNAVAILABLE"


def test_empty_without_http_200_is_not_unavailable():
    err = BinaryFetchError("EMPTY_BODY")
    assert is_http_200_empty_body(err) is False
    err200 = BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)
    assert is_http_200_empty_body(err200) is True
    magic = BinaryFetchError("PDF_MAGIC_MISMATCH", status=200, body_bytes_read=4)
    assert is_http_200_empty_body(magic) is False


def test_confirm_second_empty_raises_unavailable():
    n = {"c": 0}

    def once():
        n["c"] += 1
        raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)

    try:
        confirm_empty_binary_get(once)
        assert False
    except BinaryFetchError as e:
        assert e.code == UNAVAILABLE_REASON
        assert e.status == 200
        assert e.body_bytes_read == 0
    assert n["c"] == 2


def test_confirm_second_binary_returns_payload():
    n = {"c": 0}
    sha = hashlib.sha256(PDF).hexdigest()

    def once():
        n["c"] += 1
        if n["c"] == 1:
            raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    out = confirm_empty_binary_get(once)
    assert out["sha256"] == sha
    assert n["c"] == 2


def test_confirm_second_pdf_magic_does_not_become_hold():
    n = {"c": 0}

    def once():
        n["c"] += 1
        if n["c"] == 1:
            raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)
        raise BinaryFetchError("PDF_MAGIC_MISMATCH", status=200, body_bytes_read=4)

    try:
        confirm_empty_binary_get(once)
        assert False
    except BinaryFetchError as e:
        assert e.code == "PDF_MAGIC_MISMATCH"
    assert n["c"] == 2


def test_two_empty_200_holds_unavailable_without_put_or_version():
    holds = _ProdHolds()
    r2 = R2Store(FakeS3())
    vs = _ProdVersions()
    n = {"c": 0}

    def fetch_binary(**k):
        n["c"] += 1
        raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)

    out = _store_one(
        _item(asset_id=2029, file_size=0),
        membership_ids={MID},
        r2=r2,
        versions=vs,
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: _files(),
        fetch_binary_fn=fetch_binary,
    )
    assert out["status"] == "HOLD"
    assert out["reason"] == UNAVAILABLE_REASON
    assert out["r2_put"] == 0
    assert out["version_dml"] == 0
    assert out["binary_get"] == 2
    assert n["c"] == 2
    assert holds.inserts == 1
    obs = holds.rows[0]["observed_files"][0]
    assert obs["http_status"] == 200
    assert obs["body_bytes_read"] == 0
    assert obs["confirmation_count"] == 2
    assert "observed_at" in obs
    assert obs["expected_file_size"] == 0

    out2 = _store_one(
        _item(asset_id=2029, file_size=0),
        membership_ids={MID},
        r2=r2,
        versions=vs,
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: _files(),
        fetch_binary_fn=fetch_binary,
    )
    assert out2["hold_inserted"] == 0
    assert holds.inserts == 1


def test_second_get_binary_stores_normally():
    holds = _ProdHolds()
    s3 = FakeS3()
    vs = _WritableVersions()
    n = {"c": 0}
    sha = hashlib.sha256(PDF).hexdigest()

    def fetch_binary(**k):
        n["c"] += 1
        if n["c"] == 1:
            raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    out = _store_one(
        _item(),
        membership_ids={MID},
        r2=R2Store(s3),
        versions=vs,
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: _files(),
        fetch_binary_fn=fetch_binary,
    )
    assert out["status"] == "NEW_VERSION"
    assert n["c"] == 2
    assert s3.puts == 1
    assert vs.dml == 1
    assert holds.inserts == 0


def test_second_get_html_is_review_hold():
    holds = _ProdHolds()
    n = {"c": 0}

    def fetch_binary(**k):
        n["c"] += 1
        if n["c"] == 1:
            raise BinaryFetchError("EMPTY_BODY", status=200, body_bytes_read=0)
        raise BinaryFetchError("HTML_NOT_BINARY", status=200, body_bytes_read=0)

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
    assert out["reason"] == "SOURCE_ASSET_REVIEW_REQUIRED"
    assert out["subreason"] == "HTML_NOT_BINARY"
    assert holds.inserts == 1
    assert n["c"] == 2


def test_pdf_magic_mismatch_is_review_hold_without_confirm():
    holds = _ProdHolds()
    n = {"c": 0}

    def fetch_binary(**k):
        n["c"] += 1
        raise BinaryFetchError("PDF_MAGIC_MISMATCH", status=200, body_bytes_read=8)

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
    assert out["reason"] == "SOURCE_ASSET_REVIEW_REQUIRED"
    assert out["subreason"] == "PDF_MAGIC_MISMATCH"
    assert n["c"] == 1
    assert holds.inserts == 1
