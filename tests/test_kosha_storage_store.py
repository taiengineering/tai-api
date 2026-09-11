"""WP-1C-5A store_asset_original mock sequence. live GET/PUT = 0."""
from __future__ import annotations

import hashlib

from services.kosha_safety_materials.storage.r2_store import R2Error, R2Store
from services.kosha_safety_materials.storage.store import StorageError, store_asset_original
from services.kosha_safety_materials.storage.version_service import MemoryVersionStore
from tests.test_kosha_r2_store import FakeS3


PDF = b"%PDF-1.4\nend\n"


def _payload():
    return {
        "asset_id": 1,
        "source_file_name": "a.pdf",
        "source_content_type": "application/pdf",
        "source_file_size": len(PDF),
        "source_fetched_at": "2026-09-11T00:00:00+00:00",
        "license_observed_at": "2026-09-11T00:00:00+00:00",
        "license_observed_type": "1",
        "license_name": None,
        "license_source_url": None,
        "storage_basis": "KOGL",
        "source_med_seq": "1",
        "source_url": "https://portal.kosha.or.kr/x",
        "med_gonggongnuri_raw": "01",
        "med_gonggongnuri_nm_raw": None,
        "is_derivative": False,
    }


def test_dry_run_zero_io():
    s3 = FakeS3()
    r2 = R2Store(s3)
    vs = MemoryVersionStore()
    out = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"},
        fetch_fn=lambda **k: (_ for _ in ()).throw(AssertionError("no fetch")),
        r2=r2, versions=vs, version_payload=_payload(), dry_run=True,
    )
    assert out["status"] == "DRY_RUN"
    assert s3.puts == 0 and vs.dml == 0


def test_historical_blocked_before_fetch():
    s3 = FakeS3()
    try:
        store_asset_original(
            kogl_type="1", content_type="PDF", material_id="hist",
            atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
            membership_ids={"m1"},
            fetch_fn=lambda **k: (_ for _ in ()).throw(AssertionError("no fetch")),
            r2=R2Store(s3), versions=MemoryVersionStore(), version_payload=_payload(),
        )
        assert False
    except StorageError as e:
        assert e.code == "HISTORICAL_STORAGE_FORBIDDEN"


def test_full_sequence_put_then_promote_and_readback_mismatch_skips_db():
    s3 = FakeS3()
    r2 = R2Store(s3)
    vs = MemoryVersionStore()
    sha = hashlib.sha256(PDF).hexdigest()

    def fetch(**k):
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    out = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"}, fetch_fn=fetch, r2=r2, versions=vs, version_payload=_payload(),
    )
    assert out["status"] == "NEW_VERSION"
    assert s3.puts == 1
    assert vs.current_count(out["source_asset_key"]) == 1

    vs2 = MemoryVersionStore()
    s3b = FakeS3()
    r2b = R2Store(s3b)

    def fetch_bad(**k):
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    orig_put = r2b.put_new

    def put_then_tamper(*a, **kw):
        st = orig_put(*a, **kw)
        s3b.objects[a[0]]["Body"] = b"TAMPER"
        return st

    r2b.put_new = put_then_tamper  # type: ignore
    try:
        store_asset_original(
            kogl_type="1", content_type="PDF", material_id="m1",
            atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
            membership_ids={"m1"}, fetch_fn=fetch_bad, r2=r2b, versions=vs2, version_payload=_payload(),
        )
        assert False
    except StorageError as e:
        assert e.code == "READBACK_MISMATCH"
    assert vs2.rows == []
    assert vs2.dml == 0


def test_orphan_when_promote_fails_after_put():
    s3 = FakeS3()
    r2 = R2Store(s3)
    vs = MemoryVersionStore()
    vs.fail_next_insert = True
    sha = hashlib.sha256(PDF).hexdigest()

    def fetch(**k):
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    try:
        store_asset_original(
            kogl_type="1", content_type="PDF", material_id="m1",
            atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
            membership_ids={"m1"}, fetch_fn=fetch, r2=r2, versions=vs, version_payload=_payload(),
        )
        assert False
    except StorageError as e:
        assert e.code == "ORPHAN_OBJECT_CANDIDATE"
    assert s3.puts == 1
    assert vs.rows == []


def test_second_run_no_change_put_zero_and_orphan_resume():
    s3 = FakeS3()
    r2 = R2Store(s3)
    vs = MemoryVersionStore()
    sha = hashlib.sha256(PDF).hexdigest()

    def fetch(**k):
        return {"data": PDF, "sha256": sha, "content_type": "application/pdf"}

    first = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"}, fetch_fn=fetch, r2=r2, versions=vs, version_payload=_payload(),
    )
    assert first["status"] == "NEW_VERSION"
    assert s3.puts == 1
    vid = vs.current(first["source_asset_key"])["id"]
    second = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"}, fetch_fn=fetch, r2=r2, versions=vs, version_payload=_payload(),
    )
    assert second["status"] == "NO_CHANGE"
    assert s3.puts == 1
    assert vs.current(first["source_asset_key"])["id"] == vid
    assert vs.current(first["source_asset_key"])["content_checksum"] == sha
    assert vs.current(first["source_asset_key"])["storage_key"] == first["storage_key"]

    vs3 = MemoryVersionStore()
    r2b = R2Store(s3)
    resume = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"}, fetch_fn=fetch, r2=r2b, versions=vs3, version_payload=_payload(),
    )
    assert resume["status"] == "NEW_VERSION"
    assert resume["put"] == "OBJECT_EXISTS_VERIFIED"
    assert s3.puts == 1


def test_store_blocks_video_and_type2():
    s3 = FakeS3()
    try:
        store_asset_original(
            kogl_type="1", content_type="VIDEO", material_id="m1",
            atcfl_no="N", atcfl_seq=1, file_name="a.mp4",
            membership_ids={"m1"},
            fetch_fn=lambda **k: (_ for _ in ()).throw(AssertionError("no fetch")),
            r2=R2Store(s3), versions=MemoryVersionStore(), version_payload=_payload(),
        )
        assert False
    except Exception as e:
        assert getattr(e, "code", "") == "VIDEO_BINARY_FORBIDDEN"
    try:
        store_asset_original(
            kogl_type="2", content_type="PDF", material_id="m1",
            atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
            membership_ids={"m1"},
            fetch_fn=lambda **k: (_ for _ in ()).throw(AssertionError("no fetch")),
            r2=R2Store(s3), versions=MemoryVersionStore(), version_payload=_payload(),
        )
        assert False
    except Exception as e:
        assert getattr(e, "code", "") == "LICENSE_STORAGE_FORBIDDEN"


def test_transient_retry_creates_one_version_and_exhausted_does_no_dml(tmp_path):
    import os
    from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError, fetch_https_binary
    from tests.test_kosha_binary_fetch import PDF as BINPDF, _flaky_opener

    url = "https://portal.kosha.or.kr/file"
    dest = str(tmp_path / "ok.pdf")
    opener, h = _flaky_opener(BINPDF, succeed_on=2, mode="before")

    def fetch_ok(**k):
        got = fetch_https_binary(url, dest, opener=opener, expect_pdf=True, sleeper=lambda s: None)
        data = open(got["dest_path"], "rb").read()
        return {"data": data, "sha256": got["sha256"], "content_type": "application/pdf"}

    s3 = FakeS3()
    vs = MemoryVersionStore()
    out = store_asset_original(
        kogl_type="1", content_type="PDF", material_id="m1",
        atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
        membership_ids={"m1"}, fetch_fn=fetch_ok, r2=R2Store(s3), versions=vs, version_payload=_payload(),
    )
    assert out["status"] == "NEW_VERSION"
    assert len(vs.rows) == 1
    assert s3.puts == 1
    assert h.opens == 2

    dest2 = str(tmp_path / "fail.pdf")
    opener2, h2 = _flaky_opener(BINPDF, succeed_on=99, mode="before")

    def fetch_fail(**k):
        return fetch_https_binary(url, dest2, opener=opener2, expect_pdf=True, sleeper=lambda s: None)

    s3b = FakeS3()
    vsb = MemoryVersionStore()
    try:
        store_asset_original(
            kogl_type="1", content_type="PDF", material_id="m1",
            atcfl_no="N", atcfl_seq=1, file_name="a.pdf",
            membership_ids={"m1"}, fetch_fn=fetch_fail, r2=R2Store(s3b), versions=vsb, version_payload=_payload(),
        )
        assert False
    except BinaryFetchError as e:
        assert e.code == "TRANSIENT_UPSTREAM_FAILURE"
    assert h2.opens == 3
    assert s3b.puts == 0
    assert vsb.rows == []
    assert vsb.dml == 0
