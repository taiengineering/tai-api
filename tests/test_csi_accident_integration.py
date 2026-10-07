"""WP-1D Wave2B — CSI Accident Integration tests (I01 ~ I14).

All tests use injectable HTTP + MemoryCsiStore — zero external calls, zero Production writes.
"""
from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from unittest.mock import patch
from uuid import uuid4

import pytest

from services.csi_accidents.contract import (
    APPLY_ENABLE_ENV,
    ATCH_FILE_ID,
    DATASET_EFFECTIVE_DATE,
    DATASET_ID,
    DATASET_NAME,
    DATASET_URL,
    DOWNLOAD_PATH,
    METADATA_URL,
    OFFICIAL_HEADERS,
)
from services.csi_accidents.discovery import parse_download_identity
from services.csi_accidents.refresh import RefreshResult, refresh_latest_csi_artifact
from services.csi_accidents.store import MemoryCsiStore
from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters
from services.public_data_sync.adapters.csi_accident import CsiAccidentAdapter
from services.public_data_sync.contracts import RunContext, RunStatus, TriggerKind
from services.public_data_sync.registry import registry


# ─── Constants ────────────────────────────────────────────────────────────────

_BASELINE_DOWNLOAD_URL = (
    f"https://www.data.go.kr{DOWNLOAD_PATH}"
    f"?atchFileId={ATCH_FILE_ID}&fileDetailSn=1&insertDataPrcus=N"
)
_BASELINE_DATE = DATASET_EFFECTIVE_DATE
_BASELINE_ATCH = ATCH_FILE_ID
_BASELINE_FDSN = "1"

_NEW_ATCH = "FILE_NEW_2026_11"
_NEW_FDSN = "1"
_NEW_DATE = "2026-11-30"
_NEW_FILENAME = "건설안전사고사례(_26.11.30)csv.csv"
_NEW_DOWNLOAD_URL = (
    f"https://www.data.go.kr{DOWNLOAD_PATH}"
    f"?atchFileId={_NEW_ATCH}&fileDetailSn={_NEW_FDSN}"
)


# ─── Store helpers ────────────────────────────────────────────────────────────

def _store_with_baseline(
    effective_date: str = _BASELINE_DATE,
    download_url: str = _BASELINE_DOWNLOAD_URL,
    sha256: str = "aabbccdd" * 8,
) -> MemoryCsiStore:
    """Return a MemoryCsiStore pre-loaded with one COMPLETED 2025 baseline snapshot."""
    store = MemoryCsiStore()
    snap = {
        "id": "snap-baseline-001",
        "status": "COMPLETED",
        "dataset_id": DATASET_ID,
        "effective_date": effective_date,
        "filename": "건설안전사고사례(_25.6.30)csv.csv",
        "bytes": 36318137,
        "file_sha256": sha256,
        "encoding": "cp949",
        "declared_rows": 14289,
        "parsed_rows": 37196,
        "row_count_mismatch": True,
        "header_count": 74,
        "download_url": download_url,
        "proposed_raw_object_key": f"csi/{DATASET_ID}/{effective_date}/{sha256}/baseline.csv",
        "r2_written": False,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T01:00:00",
        "failure_reason": None,
    }
    store.snapshots.append(snap)
    return store


# ─── Discovery HTTP helpers ───────────────────────────────────────────────────

def _meta_bytes(
    alternate_name: str = f"국토안전관리원_건설안전사고사례_20250630",
    dataset_id: str = DATASET_ID,
    modified: str = "2026-09-15",
) -> bytes:
    url = f"https://www.data.go.kr/data/{dataset_id}/fileData.do"
    return json.dumps({
        "@type": "Dataset",
        "name": DATASET_NAME,
        "alternateName": alternate_name,
        "url": url,
        "dateModified": modified,
    }).encode()


def _page_bytes(content_url: str) -> bytes:
    ld = json.dumps({
        "@type": "Dataset",
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "CSV", "contentUrl": content_url},
        ],
    })
    return (
        f'<html><head><script type="application/ld+json">{ld}</script></head></html>'
    ).encode()


def _make_http_get(meta: bytes, page: bytes) -> Callable[[str], bytes]:
    def _get(url: str) -> bytes:
        if url == METADATA_URL:
            return meta
        if url == DATASET_URL:
            return page
        raise ValueError(f"unexpected URL: {url!r}")
    return _get


def _http_no_change() -> Callable[[str], bytes]:
    """Discovery returns NO_CHANGE (portal = same 2025 baseline)."""
    meta = _meta_bytes(alternate_name="국토안전관리원_건설안전사고사례_20250630")
    page = _page_bytes(_BASELINE_DOWNLOAD_URL)
    return _make_http_get(meta, page)


def _http_new_artifact() -> Callable[[str], bytes]:
    """Discovery returns NEW_ARTIFACT (portal = 2026-11-30 new file)."""
    meta = _meta_bytes(alternate_name="국토안전관리원_건설안전사고사례_20261130")
    page = _page_bytes(_NEW_DOWNLOAD_URL)
    return _make_http_get(meta, page)


def _http_fail() -> Callable[[str], bytes]:
    """Discovery fails (wrong dataset_id in meta)."""
    meta = _meta_bytes(dataset_id="99999999")
    page = _page_bytes(_BASELINE_DOWNLOAD_URL)
    return _make_http_get(meta, page)


# ─── CSV helpers ──────────────────────────────────────────────────────────────

def _valid_row(**over) -> dict:
    row = {h: "값" for h in OFFICIAL_HEADERS}
    row["사고명"] = "통합테스트사고"
    row["사고일시"] = "2019-07-01 07:10"
    row["사망자"] = "0"
    row["부상자"] = "1"
    row["사고경위"] = "경위"
    row["재발방지대책"] = "대책"
    row.update(over)
    return row


def _csv_bytes(rows: list, headers=None, encoding: str = "cp949") -> bytes:
    hdrs = headers or list(OFFICIAL_HEADERS)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(hdrs)
    for r in rows:
        w.writerow([r.get(h, "값") for h in hdrs])
    return buf.getvalue().encode(encoding)


def _valid_csv_bytes(n: int = 3, encoding: str = "cp949") -> bytes:
    rows = [_valid_row(**{"사고명": f"사고{i}"}) for i in range(n)]
    return _csv_bytes(rows, encoding=encoding)


def _bad_header_csv_bytes() -> bytes:
    hdrs = list(OFFICIAL_HEADERS[:73]) + ["잘못된헤더"]
    rows = [_valid_row()]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(hdrs)
    for r in rows:
        w.writerow([r.get(h, "값") for h in hdrs])
    return buf.getvalue().encode("cp949")


def _make_http_download(
    data: bytes,
    filename: str,
) -> Callable[[str], tuple[bytes, str]]:
    def _dl(url: str) -> tuple[bytes, str]:
        return data, filename
    return _dl


# ─── Adapter helpers ──────────────────────────────────────────────────────────

def _ctx() -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id="CSI_ACCIDENT",
        trigger=TriggerKind.MANUAL,
        started_at=datetime.now(timezone.utc),
    )


def _adapter_with_refresh(result: RefreshResult) -> CsiAccidentAdapter:
    adapter = CsiAccidentAdapter()
    def _patched_run(ctx):
        return adapter._map(ctx, result)
    adapter.run = _patched_run  # type: ignore[method-assign]
    return adapter


# ─────────────────────────────────────────────────────────────────────────────
# I01 — current artifact → NO_CHANGE, metadata only, zero download, zero DML
# ─────────────────────────────────────────────────────────────────────────────

def test_i01_current_artifact_no_change():
    store = _store_with_baseline()
    result = refresh_latest_csi_artifact(
        http_get=_http_no_change(),
        store=store,
    )
    assert result.status == "NO_CHANGE"
    assert result.discovery_status == "NO_CHANGE"
    assert result.downloaded is False
    assert result.full_csv_downloads == 0
    assert result.dml == 0
    assert result.metadata_requests == 2


# ─────────────────────────────────────────────────────────────────────────────
# I02 — discovery FAILED → FAILED, zero download, zero DML
# ─────────────────────────────────────────────────────────────────────────────

def test_i02_discovery_failed():
    store = _store_with_baseline()
    result = refresh_latest_csi_artifact(
        http_get=_http_fail(),
        store=store,
    )
    assert result.status == "FAILED"
    assert result.downloaded is False
    assert result.full_csv_downloads == 0
    assert result.dml == 0
    assert result.error_code is not None


# ─────────────────────────────────────────────────────────────────────────────
# I03 — NEW_ARTIFACT → exactly 1 download, dynamic metadata, COMPLETED snapshot
# ─────────────────────────────────────────────────────────────────────────────

def test_i03_new_artifact_completed(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")
    store = _store_with_baseline()
    csv_data = _valid_csv_bytes(n=5)
    http_dl = _make_http_download(csv_data, _NEW_FILENAME)

    result = refresh_latest_csi_artifact(
        http_get=_http_new_artifact(),
        http_download=http_dl,
        store=store,
    )

    assert result.status == "COMPLETED"
    assert result.downloaded is True
    assert result.full_csv_downloads == 1
    assert result.metadata_requests == 2
    assert result.effective_date == _NEW_DATE
    assert result.attachment_id == _NEW_ATCH
    assert result.file_detail_sn == _NEW_FDSN
    assert result.filename == _NEW_FILENAME
    assert result.sha256 is not None
    assert result.parsed_rows == 5
    assert result.snapshot_id is not None
    assert result.dml > 0

    # Dynamic metadata must NOT leak 2025 baseline into new snapshot
    new_snap = store.get_latest_completed()
    assert new_snap is not None
    assert new_snap["effective_date"] == _NEW_DATE
    assert new_snap["download_url"] == _NEW_DOWNLOAD_URL
    assert new_snap["filename"] == _NEW_FILENAME


# ─────────────────────────────────────────────────────────────────────────────
# I04 — new artifact bad header → FAILED, old COMPLETED snapshot preserved
# ─────────────────────────────────────────────────────────────────────────────

def test_i04_bad_header_old_snapshot_preserved(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")
    store = _store_with_baseline()
    baseline_id = store.get_latest_completed()["id"]

    http_dl = _make_http_download(_bad_header_csv_bytes(), _NEW_FILENAME)

    result = refresh_latest_csi_artifact(
        http_get=_http_new_artifact(),
        http_download=http_dl,
        store=store,
    )

    assert result.status == "FAILED"
    assert result.full_csv_downloads == 1
    # Old COMPLETED snapshot remains current
    assert store.get_latest_completed()["id"] == baseline_id


# ─────────────────────────────────────────────────────────────────────────────
# I05 — CP949 decode failure → FAILED, old snapshot preserved
# ─────────────────────────────────────────────────────────────────────────────

def test_i05_decode_failure_old_snapshot_preserved(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")
    store = _store_with_baseline()
    baseline_id = store.get_latest_completed()["id"]

    # Bytes that are not valid cp949
    bad_bytes = bytes([0x81, 0x40, 0x81, 0x40] * 10)
    http_dl = _make_http_download(bad_bytes, _NEW_FILENAME)

    result = refresh_latest_csi_artifact(
        http_get=_http_new_artifact(),
        http_download=http_dl,
        store=store,
    )

    assert result.status == "FAILED"
    assert store.get_latest_completed()["id"] == baseline_id


# ─────────────────────────────────────────────────────────────────────────────
# I06 — filename unresolved → CSI_FILENAME_UNRESOLVED, DML = 0
# ─────────────────────────────────────────────────────────────────────────────

def test_i06_filename_unresolved(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")
    store = _store_with_baseline()

    from services.csi_accidents.refresh import RefreshError

    def _dl_no_filename(url: str) -> tuple[bytes, str]:
        raise RefreshError("CSI_FILENAME_UNRESOLVED", "no Content-Disposition")

    result = refresh_latest_csi_artifact(
        http_get=_http_new_artifact(),
        http_download=_dl_no_filename,
        store=store,
    )

    assert result.status == "FAILED"
    assert result.error_code == "CSI_FILENAME_UNRESOLVED"
    assert result.dml == 0
    assert result.full_csv_downloads == 0


# ─────────────────────────────────────────────────────────────────────────────
# I07 — same SHA with conflicting metadata → FAILED (DUPLICATE_SHA_CONFLICT)
# ─────────────────────────────────────────────────────────────────────────────

def test_i07_same_sha_conflicting_metadata(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")

    # Compute sha of the csv we'll try to sync
    csv_data = _valid_csv_bytes(n=3)
    from services.csi_accidents.sync import file_sha256
    sha = file_sha256(csv_data)

    # Pre-populate store with a COMPLETED snapshot having same SHA but a different effective_date
    store = _store_with_baseline(
        effective_date="2025-01-01",
        download_url=_BASELINE_DOWNLOAD_URL,
        sha256=sha,
    )

    # Discovery returns NEW_ARTIFACT (different date)
    http_dl = _make_http_download(csv_data, _NEW_FILENAME)
    result = refresh_latest_csi_artifact(
        http_get=_http_new_artifact(),
        http_download=http_dl,
        store=store,
    )

    assert result.status == "FAILED"
    assert result.error_code == "DUPLICATE_SHA_CONFLICT"


# ─────────────────────────────────────────────────────────────────────────────
# I08 — write failure → new snapshot FAILED, old COMPLETED still current
# ─────────────────────────────────────────────────────────────────────────────

def test_i08_write_failure_old_snapshot_preserved(monkeypatch):
    monkeypatch.setenv(APPLY_ENABLE_ENV, "1")
    store = _store_with_baseline()
    baseline_id = store.get_latest_completed()["id"]
    store.fail_on_membership = True

    csv_data = _valid_csv_bytes(n=3)
    http_dl = _make_http_download(csv_data, _NEW_FILENAME)

    result = refresh_latest_csi_artifact(
        http_get=_http_new_artifact(),
        http_download=http_dl,
        store=store,
    )

    assert result.status == "FAILED"
    # Old COMPLETED snapshot is still the latest
    assert store.get_latest_completed()["id"] == baseline_id
    # New snapshot exists but is FAILED
    failed_snaps = [s for s in store.snapshots if s["status"] == "FAILED"]
    assert len(failed_snaps) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# I09 — adapter NO_CHANGE mapping → RunStatus.NO_CHANGE, change_detected=False
# ─────────────────────────────────────────────────────────────────────────────

def test_i09_adapter_no_change_mapping():
    result = RefreshResult(
        status="NO_CHANGE",
        discovery_status="NO_CHANGE",
        effective_date=_BASELINE_DATE,
        attachment_id=_BASELINE_ATCH,
        file_detail_sn=_BASELINE_FDSN,
        metadata_requests=2,
        full_csv_downloads=0,
        dml=0,
    )
    adapter = _adapter_with_refresh(result)
    run_result = adapter.run(_ctx())
    assert run_result.status == RunStatus.NO_CHANGE
    assert run_result.change_detected is False
    assert run_result.details.get("full_csv_downloads") == 0


# ─────────────────────────────────────────────────────────────────────────────
# I10 — adapter COMPLETED mapping → RunStatus.SUCCESS, change_detected=True
# ─────────────────────────────────────────────────────────────────────────────

def test_i10_adapter_completed_mapping():
    snap_id = "snap-new-001"
    result = RefreshResult(
        status="COMPLETED",
        discovery_status="NEW_ARTIFACT",
        effective_date=_NEW_DATE,
        attachment_id=_NEW_ATCH,
        file_detail_sn=_NEW_FDSN,
        downloaded=True,
        bytes=12345,
        sha256="deadbeef" * 8,
        filename=_NEW_FILENAME,
        parsed_rows=10,
        new=8,
        changed=2,
        unchanged=0,
        snapshot_id=snap_id,
        metadata_requests=2,
        full_csv_downloads=1,
        dml=5,
    )
    adapter = _adapter_with_refresh(result)
    run_result = adapter.run(_ctx())
    assert run_result.status == RunStatus.SUCCESS
    assert run_result.change_detected is True
    assert run_result.created == 8
    assert run_result.changed == 2
    assert run_result.source_version == snap_id
    assert run_result.content_hash == "deadbeef" * 8


# ─────────────────────────────────────────────────────────────────────────────
# I11 — adapter FAILED mapping → RunStatus.FAILED, stable error_code
# ─────────────────────────────────────────────────────────────────────────────

def test_i11_adapter_failed_mapping():
    result = RefreshResult(
        status="FAILED",
        discovery_status="FAILED",
        error_code="CSI_BASELINE_MISSING",
        error_message="no COMPLETED snapshot",
        metadata_requests=0,
        full_csv_downloads=0,
    )
    adapter = _adapter_with_refresh(result)
    run_result = adapter.run(_ctx())
    assert run_result.status == RunStatus.FAILED
    assert run_result.error_code == "CSI_BASELINE_MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# I12 — builtin adapter registration: csi_accident present
# ─────────────────────────────────────────────────────────────────────────────

def test_i12_builtin_adapter_registration():
    from services.public_data_sync.errors import AdapterNotRegisteredError
    test_reg = AdapterRegistry()
    with patch("services.public_data_sync.adapters.adapter_registry", test_reg):
        register_builtin_adapters()
    assert "csi_accident" in test_reg.registered_keys()
    try:
        test_reg.get("csi_accident")
        found = True
    except AdapterNotRegisteredError:
        found = False
    assert found is True


# ─────────────────────────────────────────────────────────────────────────────
# I13 — registry CSI_ACCIDENT: FILE_SNAPSHOT / FILE / DAILY
# ─────────────────────────────────────────────────────────────────────────────

def test_i13_registry_csi_accident():
    from services.public_data_sync.contracts import SourceMode, SourceKind
    spec = registry.get("CSI_ACCIDENT")
    assert spec.sync_mode == SourceMode.FILE_SNAPSHOT
    assert spec.source_kind == SourceKind.FILE
    assert spec.refresh_policy == "DAILY"
    assert spec.adapter_key == "csi_accident"
    assert spec.auto_refresh_candidate is True


# ─────────────────────────────────────────────────────────────────────────────
# I14 — T07/T17 stale debt: DATA_GO_KR now canonical for KECO credential_pool
# ─────────────────────────────────────────────────────────────────────────────

def test_i14_keco_credential_pool_data_go_kr():
    spec = registry.get("KECO_15149420")
    assert spec.credential_pool == "DATA_GO_KR"
    assert spec.rate_limit_group == "KECO"
    assert spec.credential_pool != spec.rate_limit_group


# ─────────────────────────────────────────────────────────────────────────────
# Extra — no baseline snapshot → CSI_BASELINE_MISSING
# ─────────────────────────────────────────────────────────────────────────────

def test_extra_no_baseline_returns_failed():
    store = MemoryCsiStore()  # empty
    result = refresh_latest_csi_artifact(
        http_get=_http_no_change(),
        store=store,
    )
    assert result.status == "FAILED"
    assert result.error_code == "CSI_BASELINE_MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# Extra — parse_download_identity public helper
# ─────────────────────────────────────────────────────────────────────────────

def test_extra_parse_download_identity():
    att_id, fdsn = parse_download_identity(_BASELINE_DOWNLOAD_URL)
    assert att_id == ATCH_FILE_ID
    assert fdsn == "1"
