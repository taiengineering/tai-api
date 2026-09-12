"""PATCH-5B-HOLD: filename mismatch holds without storing; stronger failures still STOP."""
from __future__ import annotations

from services.kosha_safety_materials.asset_parser import logical_checksum
from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError
from services.kosha_safety_materials.storage.hold_store import MemoryHoldStore
from services.kosha_safety_materials.storage.r2_store import R2Store
from services.kosha_safety_materials.storage.runner import _store_one
from services.kosha_safety_materials.storage.store import StorageError
from tests.test_kosha_r2_store import FakeS3


class _ProdVersions:
    def current(self, key):
        return None

    def current_count(self, key):
        return 0

    def promote(self, payload):
        raise AssertionError("version DML 0")


class _ProdHolds:
    """Production-shaped test double. Must not be MemoryHoldStore."""

    def __init__(self):
        self._inner = MemoryHoldStore()

    def open_asset_ids(self, snapshot_id):
        return self._inner.open_asset_ids(snapshot_id)

    def open_rows(self, snapshot_id, reason=None):
        return self._inner.open_rows(snapshot_id, reason)

    def record_open(self, **k):
        return self._inner.record_open(**k)

    @property
    def inserts(self):
        return self._inner.inserts

    @property
    def rows(self):
        return self._inner.rows


PDF_NAME = "커버.pdf"
AI_NAME = "커버.ai"
OTHER_PDF = "본문.pdf"
MID = "m1"
NO = "FL1"


def _item(**k):
    name = k.pop("file_name", PDF_NAME)
    seq = k.pop("seq", 1)
    base = {
        "asset_id": 4523,
        "material_id": MID,
        "asset_type": "PDF",
        "content_type": "PDF",
        "file_name": name,
        "file_size": 153077,
        "checksum": logical_checksum(MID, NO, seq, name),
        "kogl_type": "1",
        "source_med_seq": "38141",
    }
    base.update(k)
    return base


def _detail_json(medseq="38141", kogl="01"):
    return {
        "status": 200,
        "json": {
            "result": "success",
            "payload": {"list": [{
                "medSeq": medseq,
                "medGonggongnuri": kogl,
                "medGonggongnuriNm": "제1유형",
            }]},
        },
    }


def _atch_json(file_name=PDF_NAME, seq=1):
    return {
        "status": 200,
        "json": {"payload": {"list": [{
            "contsAtcflNo": NO, "contsAtcflSeq": seq, "orgnlAtchFileNm": file_name,
        }]}},
    }


def test_filename_mismatch_holds_without_binary_or_version_dml():
    holds = _ProdHolds()
    binary = []
    r2 = R2Store(FakeS3())
    vs = _ProdVersions()

    def fetch_binary(**k):
        binary.append(k)
        raise AssertionError("binary GET 0")

    out = _store_one(
        _item(),
        membership_ids={MID},
        r2=r2,
        versions=vs,
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: [
            {"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": AI_NAME},
            {"atcflNo": NO, "atcflSeq": 2, "orgnlAtchFileNm": OTHER_PDF},
        ],
        fetch_binary_fn=fetch_binary,
    )
    assert out["status"] == "HOLD"
    assert out["reason"] == "SOURCE_ASSET_FILENAME_MISMATCH"
    assert out["r2_put"] == 0
    assert out["version_dml"] == 0
    assert out["binary_get"] == 0
    assert binary == []
    assert r2.puts == 0
    assert holds.inserts == 1
    assert holds.open_asset_ids("snap-1") == {4523}

    out2 = _store_one(
        _item(),
        membership_ids={MID},
        r2=r2,
        versions=vs,
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq),
        fetch_atch_fn=lambda medseq: _atch_json(),
        fetch_file_list_fn=lambda atcfl_no: [
            {"atcflNo": NO, "atcflSeq": 1, "orgnlAtchFileNm": AI_NAME},
            {"atcflNo": NO, "atcflSeq": 2, "orgnlAtchFileNm": OTHER_PDF},
        ],
        fetch_binary_fn=fetch_binary,
    )
    assert out2["hold_inserted"] == 0
    assert holds.inserts == 1
    assert len(holds.rows) == 1


def test_held_asset_is_not_retried_from_pending():
    from services.kosha_safety_materials.storage.eligibility import pending_without_version
    holds = MemoryHoldStore()
    holds.record_open(
        snapshot_id="s", asset_id=4523, material_id=MID, source_med_seq="38141",
        reason="SOURCE_ASSET_FILENAME_MISMATCH", expected_file_name=PDF_NAME,
        observed_files=[],
    )
    pending = pending_without_version(
        [_item(), _item(asset_id=1, file_name="ok.pdf", seq=9)],
        set(),
        holds.open_asset_ids("s"),
    )
    assert [p["asset_id"] for p in pending] == [1]


def test_medseq_mismatch_is_review_hold_not_store():
    holds = _ProdHolds()
    out = _store_one(
        _item(),
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
    assert out["status"] == "HOLD"
    assert out["reason"] == "SOURCE_ASSET_REVIEW_REQUIRED"
    assert out["subreason"] == "SOURCE_MEDSEQ_MISMATCH"
    assert out["binary_get"] == 0
    assert holds.inserts == 1


def test_license_change_is_review_hold_not_store():
    holds = _ProdHolds()
    out = _store_one(
        _item(),
        membership_ids={MID},
        r2=R2Store(FakeS3()),
        versions=_ProdVersions(),
        snapshot_id="snap-1",
        holds=holds,
        fetch_detail_fn=lambda medseq: _detail_json(medseq, kogl="02"),
        fetch_atch_fn=lambda medseq: (_ for _ in ()).throw(AssertionError("no atch")),
        fetch_file_list_fn=lambda n: (_ for _ in ()).throw(AssertionError("no files")),
        fetch_binary_fn=lambda **k: (_ for _ in ()).throw(AssertionError("binary GET 0")),
    )
    assert out["status"] == "HOLD"
    assert out["reason"] == "SOURCE_ASSET_REVIEW_REQUIRED"
    assert out["subreason"] == "LICENSE_CHANGED_REVIEW_REQUIRED"
    assert out["binary_get"] == 0
    assert holds.inserts == 1


def test_empty_body_is_integrity_stop_not_hold():
    holds = _ProdHolds()
    r2 = R2Store(FakeS3())

    def fetch_binary(**k):
        raise BinaryFetchError("EMPTY_BODY")

    try:
        _store_one(
            _item(),
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
        assert "EMPTY_BODY" in str(e)
    except StopRun as e:
        assert e.reason != "HOLD"
        raise
    assert holds.inserts == 0
    assert r2.puts == 0


def test_memory_hold_duplicate_zero():
    h = MemoryHoldStore()
    a = h.record_open(
        snapshot_id="s", asset_id=4523, material_id="m1", source_med_seq="1",
        reason="SOURCE_ASSET_FILENAME_MISMATCH", expected_file_name="a.pdf",
        observed_files=[{"file_name": "b.pdf"}],
    )
    b = h.record_open(
        snapshot_id="s", asset_id=4523, material_id="m1", source_med_seq="1",
        reason="SOURCE_ASSET_FILENAME_MISMATCH", expected_file_name="a.pdf",
        observed_files=[{"file_name": "c.pdf"}],
    )
    assert a["inserted"] == 1 and b["inserted"] == 0
    assert h.inserts == 1
    assert len(h.rows) == 1
