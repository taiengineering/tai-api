"""PATCH-5B-SIZE-POLICY: 64 MiB SoT, oversize HOLD, 0/NULL not pre-network oversize."""
from __future__ import annotations

import hashlib
import os
import tempfile

from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError, fetch_https_binary
from services.kosha_safety_materials.storage.hold_store import HOLD_REASONS, MemoryHoldStore
from services.kosha_safety_materials.storage.limits import MAX_BINARY_BYTES, OVERSIZE_REASON, is_metadata_oversize
from services.kosha_safety_materials.storage.r2_store import MAX_BYTES as R2_MAX, R2Store
from services.kosha_safety_materials.storage.runner import _store_one
from services.kosha_safety_materials.storage.store import StorageError, store_asset_original
from services.kosha_safety_materials.storage.version_service import MemoryVersionStore
from tests.test_kosha_binary_fetch import PDF, opener_for
from tests.test_kosha_r2_store import FakeS3
from tests.test_kosha_storage_hold import (
    MID, NO, PDF_NAME, _ProdHolds, _ProdVersions, _atch_json, _detail_json, _item,
)
from tests.test_kosha_storage_store import _payload


def test_source_and_r2_share_64mib_sot():
    assert MAX_BINARY_BYTES == 64 * 1024 * 1024
    assert R2_MAX == MAX_BINARY_BYTES
    from services.kosha_safety_materials.storage.binary_fetch import MAX_BYTES as SRC_MAX
    assert SRC_MAX == MAX_BINARY_BYTES
    assert OVERSIZE_REASON in HOLD_REASONS


def test_metadata_size_policy_bounds():
    assert is_metadata_oversize(22_450_545) is False
    assert is_metadata_oversize(MAX_BINARY_BYTES) is False
    assert is_metadata_oversize(MAX_BINARY_BYTES + 1) is True
    assert is_metadata_oversize(0) is False
    assert is_metadata_oversize(None) is False


def test_positive_metadata_oversize_holds_without_kosha_binary():
    holds = _ProdHolds()
    item = _item()
    item["file_size"] = MAX_BINARY_BYTES + 1
    out = _store_one(
        item,
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_ProdVersions(),
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no detail")),
        fetch_atch_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no atch")),
        fetch_file_list_fn=lambda n: (_ for _ in ()).throw(AssertionError("no files")),
        fetch_binary_fn=lambda **k: (_ for _ in ()).throw(AssertionError("binary GET 0")),
    )
    assert out["status"] == "HOLD"
    assert out["reason"] == OVERSIZE_REASON
    assert out["binary_get"] == 0
    assert holds.inserts == 1
    out2 = _store_one(
        item,
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_ProdVersions(),
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no detail")),
        fetch_atch_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no atch")),
        fetch_file_list_fn=lambda n: (_ for _ in ()).throw(AssertionError("no files")),
        fetch_binary_fn=lambda **k: (_ for _ in ()).throw(AssertionError("binary GET 0")),
    )
    assert out2["hold_inserted"] == 0
    assert holds.inserts == 1
    from services.kosha_safety_materials.storage.eligibility import pending_without_version
    pending = pending_without_version(
        [item, _item(asset_id=1, file_name="ok.pdf", seq=9)],
        set(),
        holds.open_asset_ids("snap-1"),
    )
    assert [p["asset_id"] for p in pending] == [1]


def test_zero_and_null_size_are_not_pre_network_oversize():
    holds = _ProdHolds()
    for size in (0, None):
        try:
            _store_one(
                _item(file_size=size) if size is not None else {**_item(), "file_size": None},
                membership_ids={MID},
                r2=R2Store(FakeS3()),
                versions=_ProdVersions(),
                snapshot_id="snap-1",
                holds=holds,
                fetch_detail_fn=lambda medseq: _detail_json("999"),
                fetch_atch_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no atch")),
                fetch_file_list_fn=lambda n: (_ for _ in ()).throw(AssertionError("no files")),
                fetch_binary_fn=lambda **k: (_ for _ in ()).throw(AssertionError("binary GET 0")),
            )
            assert False
        except StorageError as e:
            assert e.code == "BINARY_INTEGRITY_BLOCKED"
        assert holds.inserts == 0


def test_content_length_oversize_reads_no_body_and_holds():
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "big.pdf")
        huge = str(MAX_BINARY_BYTES + 1)
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/big": (
                200, {"Content-Type": "application/pdf", "Content-Length": huge}, PDF * 10,
            ),
        })
        try:
            fetch_https_binary("https://portal.kosha.or.kr/big", dest, opener=opener, expect_pdf=True)
            assert False
        except BinaryFetchError as e:
            assert e.code == OVERSIZE_REASON
            assert e.body_bytes_read == 0
        assert not os.path.isfile(dest) or os.path.getsize(dest) == 0


def test_stream_oversize_discards_partial_and_holds_in_store():
    holds = _ProdHolds()
    s3 = FakeS3()

    def fetch_binary(**k):
        dest = os.path.join(tempfile.mkdtemp(), "ov.pdf")
        big = b"%PDF-" + (b"x" * 200)
        opener, _, _ = opener_for({
            "https://portal.kosha.or.kr/stream": (200, {"Content-Type": "application/pdf"}, big),
        })
        return fetch_https_binary(
            "https://portal.kosha.or.kr/stream", dest, opener=opener, expect_pdf=True, max_bytes=100,
        )

    out = _store_one(
        _item(),
        membership_ids={MID},
        r2=R2Store(s3),
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
    assert out["status"] == "HOLD"
    assert out["reason"] == OVERSIZE_REASON
    assert s3.puts == 0
    assert holds.inserts == 1


def test_normal_under_limit_still_stores():
    sha = hashlib.sha256(PDF).hexdigest()
    s3 = FakeS3()
    vs = MemoryVersionStore()

    def fetch(**k):
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    out = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"}, fetch_fn=fetch, r2=R2Store(s3), versions=vs, version_payload=_payload(),
    )
    assert out["status"] == "NEW_VERSION"
    assert s3.puts == 1
    assert vs.dml == 1
