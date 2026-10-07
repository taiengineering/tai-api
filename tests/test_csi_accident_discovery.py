"""WP-1D Wave2B — CSI Artifact Discovery tests (D01 ~ D12, P01 ~ P13).

All tests use mock HTTP — zero external calls, zero production DB mutation.
"""
from __future__ import annotations

import csv
import inspect
import io
import json
from typing import Callable

import pytest

from services.csi_accidents.contract import (
    ALLOWED_DOWNLOAD_HOSTS,
    ATCH_FILE_ID,
    DATASET_EFFECTIVE_DATE,
    DATASET_ID,
    DATASET_NAME,
    DATASET_URL,
    DECLARED_ROWS,
    DOWNLOAD_PATH,
    METADATA_URL,
    OFFICIAL_HEADERS,
)
from services.csi_accidents.discovery import (
    CsiArtifactDescriptor,
    DiscoveryResult,
    discover_latest_artifact,
)
from services.csi_accidents.store import MemoryCsiStore
from services.csi_accidents.sync import sync_csi_accidents


# ─── Fixture helpers ──────────────────────────────────────────────────────────

_KNOWN_CONTENT_URL = (
    f"https://www.data.go.kr{DOWNLOAD_PATH}"
    f"?atchFileId={ATCH_FILE_ID}&fileDetailSn=1&insertDataPrcus=N"
)


def _make_meta(
    name: str = DATASET_NAME,
    alternate_name: str = f"국토안전관리원_건설안전사고사례_20250630",
    dataset_id: str = DATASET_ID,
    modified: str = "2026-09-15",
    url_override: str | None = None,
) -> bytes:
    url = url_override or f"https://www.data.go.kr/data/{dataset_id}/fileData.do"
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": name,
        "alternateName": alternate_name,
        "url": url,
        "dateModified": modified,
        "datasetTimeInterval": "연간",
        "encodingFormat": "CSV",
    }).encode()


def _make_page(*distributions: dict) -> bytes:
    ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "distribution": list(distributions),
    })
    return (
        f"<html><head>"
        f'<script type="application/ld+json">{ld}</script>'
        f"</head><body></body></html>"
    ).encode()


def _csv_dist(content_url: str, fmt: str = "CSV") -> dict:
    return {"@type": "DataDownload", "encodingFormat": fmt, "contentUrl": content_url}


def _make_page_csv(*content_urls: str) -> bytes:
    return _make_page(*[_csv_dist(u) for u in content_urls])


def _make_http_get(meta: bytes, page: bytes) -> Callable[[str], bytes]:
    def _get(url: str) -> bytes:
        if url == METADATA_URL:
            return meta
        if url == DATASET_URL:
            return page
        raise ValueError(f"unexpected URL in mock: {url!r}")
    return _get


_META_CURRENT = _make_meta()
_PAGE_CURRENT = _make_page_csv(_KNOWN_CONTENT_URL)
_HTTP_CURRENT = _make_http_get(_META_CURRENT, _PAGE_CURRENT)


def _row(title: str = "사고A", occurred: str = "2019-07-01 07:10", **over) -> dict:
    raw = {h: "값" for h in OFFICIAL_HEADERS}
    raw["사고명"] = title
    raw["사고일시"] = occurred
    raw["사망자"] = "0"
    raw["부상자"] = "1"
    raw["사고경위"] = "경위"
    raw["재발방지대책"] = "대책"
    raw.update(over)
    return raw


def _csv_bytes(rows: list, headers=None, encoding: str = "cp949") -> bytes:
    hdrs = headers or list(OFFICIAL_HEADERS)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(hdrs)
    for raw in rows:
        w.writerow([raw.get(h, "값") for h in hdrs])
    return buf.getvalue().encode(encoding)


# ─────────────────────────────────────────────────────────────────────────────
# D01 — default call → DISCOVERED, effective_date extracted correctly
# ─────────────────────────────────────────────────────────────────────────────

def test_d01_current_effective_date():
    result = discover_latest_artifact(http_get=_HTTP_CURRENT)
    assert result.status == "DISCOVERED"
    assert result.artifact is not None
    assert result.artifact.effective_date == "2025-06-30"
    assert result.artifact.dataset_id == DATASET_ID


# ─────────────────────────────────────────────────────────────────────────────
# D02 — wrong dataset_id in metadata URL → DATASET_ID_MISMATCH
# ─────────────────────────────────────────────────────────────────────────────

def test_d02_dataset_id_mismatch():
    wrong_meta = _make_meta(dataset_id="15080650")
    http_get = _make_http_get(wrong_meta, _PAGE_CURRENT)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "DATASET_ID_MISMATCH"
    assert result.artifact is None


# ─────────────────────────────────────────────────────────────────────────────
# D03 — new artifact (2026-11-30) with known comparison → NEW_ARTIFACT
# ─────────────────────────────────────────────────────────────────────────────

def test_d03_new_artifact():
    new_att_id = "FILE_000000009999999"
    new_url = (
        f"https://www.data.go.kr{DOWNLOAD_PATH}"
        f"?atchFileId={new_att_id}&fileDetailSn=1&insertDataPrcus=N"
    )
    new_meta = _make_meta(alternate_name="국토안전관리원_건설안전사고사례_20261130")
    new_page = _make_page_csv(new_url)
    http_get = _make_http_get(new_meta, new_page)

    result = discover_latest_artifact(
        http_get=http_get,
        known_attachment_id=ATCH_FILE_ID,
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NEW_ARTIFACT"
    assert result.artifact is not None
    assert result.artifact.effective_date == "2026-11-30"
    assert result.artifact.attachment_id == new_att_id


# ─────────────────────────────────────────────────────────────────────────────
# D04 — same artifact with explicit comparison → NO_CHANGE
# ─────────────────────────────────────────────────────────────────────────────

def test_d04_no_change():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_attachment_id=ATCH_FILE_ID,
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NO_CHANGE"
    assert result.artifact is not None
    assert result.artifact.attachment_id == ATCH_FILE_ID
    assert result.artifact.effective_date == DATASET_EFFECTIVE_DATE


# ─────────────────────────────────────────────────────────────────────────────
# D05 — two distinct CSV attachment IDs → AMBIGUOUS_LATEST_ARTIFACT
# ─────────────────────────────────────────────────────────────────────────────

def test_d05_ambiguous_latest_artifact():
    url_a = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_000000001111111&fileDetailSn=1"
    url_b = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_000000002222222&fileDetailSn=1"
    page = _make_page_csv(url_a, url_b)
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "AMBIGUOUS_LATEST_ARTIFACT"


# ─────────────────────────────────────────────────────────────────────────────
# D06 — alternateName has no date suffix → EFFECTIVE_DATE_UNRESOLVED
# ─────────────────────────────────────────────────────────────────────────────

def test_d06_effective_date_unresolved():
    no_date_meta = _make_meta(alternate_name="국토안전관리원_건설안전사고사례")
    http_get = _make_http_get(no_date_meta, _PAGE_CURRENT)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "EFFECTIVE_DATE_UNRESOLVED"


# ─────────────────────────────────────────────────────────────────────────────
# D07 — download URL on untrusted host → UNTRUSTED_DOWNLOAD_HOST
# ─────────────────────────────────────────────────────────────────────────────

def test_d07_untrusted_download_host():
    bad_url = f"https://example.com{DOWNLOAD_PATH}?atchFileId={ATCH_FILE_ID}&fileDetailSn=1"
    bad_page = _make_page_csv(bad_url)
    http_get = _make_http_get(_META_CURRENT, bad_page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "UNTRUSTED_DOWNLOAD_HOST"


# ─────────────────────────────────────────────────────────────────────────────
# D08 — baseline regression: current fixture reproduces all known constants
# ─────────────────────────────────────────────────────────────────────────────

def test_d08_current_baseline_regression():
    result = discover_latest_artifact(http_get=_HTTP_CURRENT)
    a = result.artifact
    assert a is not None
    assert a.dataset_id == DATASET_ID
    assert a.dataset_name == DATASET_NAME
    assert a.attachment_id == ATCH_FILE_ID
    assert a.effective_date == DATASET_EFFECTIVE_DATE
    assert a.file_detail_sn == "1"
    assert a.source_page_url == DATASET_URL
    assert a.portal_modified_at == "2026-09-15"
    assert a.download_url == _KNOWN_CONTENT_URL
    assert a.alternate_name == "국토안전관리원_건설안전사고사례_20250630"
    # filename not available at discovery stage
    assert a.filename is None
    assert a.bytes is None
    assert a.sha256 is None


# ─────────────────────────────────────────────────────────────────────────────
# D09 — header drift in new artifact → HEADER_MISMATCH / auto-apply blocked
# ─────────────────────────────────────────────────────────────────────────────

def test_d09_header_drift_rejected():
    headers_73 = list(OFFICIAL_HEADERS[:73])
    row = {h: "val" for h in headers_73}
    data = _csv_bytes([row], headers=headers_73)

    result = sync_csi_accidents(data=data, skip_file_pin=True, store=MemoryCsiStore())
    assert result.status == "REJECT"
    assert result.extra["error_code"] == "HEADER_MISMATCH"
    assert result.business_dml == 0


# ─────────────────────────────────────────────────────────────────────────────
# D10 — declared != parsed rows → evidence recorded, not rejected for mismatch
# ─────────────────────────────────────────────────────────────────────────────

def test_d10_declared_row_mismatch_evidence():
    rows = [_row(title=f"사고{i}") for i in range(5)]
    data = _csv_bytes(rows)
    result = sync_csi_accidents(data=data, skip_file_pin=True, store=MemoryCsiStore())
    assert result.status != "REJECT"
    assert result.row_count_mismatch is True
    assert result.extra.get("row_count_mismatch_recorded") is True
    assert result.extra["declared_vs_parsed"]["declared"] == DECLARED_ROWS
    assert result.extra["declared_vs_parsed"]["parsed"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# D11 — discovery HTTP failure → FAILED, no DB writes
# ─────────────────────────────────────────────────────────────────────────────

def test_d11_discovery_failure_preserves_current():
    def _fail(_url: str) -> bytes:
        raise OSError("network timeout simulation")

    result = discover_latest_artifact(http_get=_fail)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_HTTP_ERROR"
    assert result.artifact is None
    assert result.error_message is not None
    assert "SECRET" not in (result.error_message or "")


def test_d11b_metadata_parse_failure_preserves_current():
    def _bad_json(_url: str) -> bytes:
        return b"not valid json {"

    result = discover_latest_artifact(http_get=_bad_json)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_PARSE_ERROR"
    assert result.artifact is None


# ─────────────────────────────────────────────────────────────────────────────
# D12 — discover_latest_artifact has injectable http_get (tests never hit net)
# ─────────────────────────────────────────────────────────────────────────────

def test_d12_http_get_is_injectable():
    sig = inspect.signature(discover_latest_artifact)
    assert "http_get" in sig.parameters


def test_d12b_no_artifact_found_in_page() -> None:
    page_no_dist = b"<html><head><script type='application/ld+json'>{}</script></head></html>"
    http_get = _make_http_get(_META_CURRENT, page_no_dist)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "NO_ARTIFACT"


# ─────────────────────────────────────────────────────────────────────────────
# P01 — default call (no comparison args) → DISCOVERED
# ─────────────────────────────────────────────────────────────────────────────

def test_p01_default_is_discovered():
    result = discover_latest_artifact(http_get=_HTTP_CURRENT)
    assert result.status == "DISCOVERED"
    assert result.artifact is not None


# ─────────────────────────────────────────────────────────────────────────────
# P02 — explicit current comparison → NO_CHANGE
# ─────────────────────────────────────────────────────────────────────────────

def test_p02_explicit_no_change():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_attachment_id=ATCH_FILE_ID,
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NO_CHANGE"


# ─────────────────────────────────────────────────────────────────────────────
# P03 — new portal artifact + current DB identity → NEW_ARTIFACT
# ─────────────────────────────────────────────────────────────────────────────

def test_p03_explicit_new_artifact():
    new_att = "FILE_NEW_2026"
    new_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId={new_att}&fileDetailSn=1"
    new_meta = _make_meta(alternate_name="국토안전관리원_건설안전사고사례_20261130")
    http_get = _make_http_get(new_meta, _make_page_csv(new_url))

    result = discover_latest_artifact(
        http_get=http_get,
        known_attachment_id=ATCH_FILE_ID,
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NEW_ARTIFACT"
    assert result.artifact is not None


# ─────────────────────────────────────────────────────────────────────────────
# P04 — partial comparison (one arg None) → COMPARISON_INPUT_INCOMPLETE
# ─────────────────────────────────────────────────────────────────────────────

def test_p04_attachment_only_incomplete():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_attachment_id=ATCH_FILE_ID,
        known_effective_date=None,
    )
    assert result.status == "FAILED"
    assert result.error_code == "COMPARISON_INPUT_INCOMPLETE"


def test_p04b_effective_date_only_incomplete():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_attachment_id=None,
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "FAILED"
    assert result.error_code == "COMPARISON_INPUT_INCOMPLETE"


# ─────────────────────────────────────────────────────────────────────────────
# P05 — dataset_id substring attack in metadata URL → DATASET_ID_MISMATCH
# ─────────────────────────────────────────────────────────────────────────────

def test_p05_dataset_url_substring_attack():
    # /data/99999999/fileData.do?foo=15108262 must not pass
    attack_meta = _make_meta(url_override=f"https://www.data.go.kr/data/99999999/fileData.do?foo={DATASET_ID}")
    http_get = _make_http_get(attack_meta, _PAGE_CURRENT)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "DATASET_ID_MISMATCH"


# ─────────────────────────────────────────────────────────────────────────────
# P06 — correct dataset URL but wrong dataset name → DATASET_NAME_MISMATCH
# ─────────────────────────────────────────────────────────────────────────────

def test_p06_wrong_dataset_name():
    wrong_name_meta = _make_meta(name="국토안전관리원_다른데이터셋")
    http_get = _make_http_get(wrong_name_meta, _PAGE_CURRENT)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "DATASET_NAME_MISMATCH"


# ─────────────────────────────────────────────────────────────────────────────
# P07 — alternateName with impossible date (month 13) → EFFECTIVE_DATE_UNRESOLVED
# ─────────────────────────────────────────────────────────────────────────────

def test_p07_invalid_calendar_date():
    bad_date_meta = _make_meta(alternate_name="국토안전관리원_건설안전사고사례_20261399")
    http_get = _make_http_get(bad_date_meta, _PAGE_CURRENT)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "EFFECTIVE_DATE_UNRESOLVED"


# ─────────────────────────────────────────────────────────────────────────────
# P08 — http:// download URL → UNTRUSTED_DOWNLOAD_HOST (scheme rejected)
# ─────────────────────────────────────────────────────────────────────────────

def test_p08_http_scheme_rejected():
    http_url = f"http://www.data.go.kr{DOWNLOAD_PATH}?atchFileId={ATCH_FILE_ID}&fileDetailSn=1"
    page = _make_page_csv(http_url)
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "UNTRUSTED_DOWNLOAD_HOST"


# ─────────────────────────────────────────────────────────────────────────────
# P09 — correct host but wrong path → UNTRUSTED_DOWNLOAD_HOST
# ─────────────────────────────────────────────────────────────────────────────

def test_p09_wrong_download_path_rejected():
    bad_path_url = f"https://www.data.go.kr/not-download?atchFileId={ATCH_FILE_ID}&fileDetailSn=1"
    page = _make_page_csv(bad_path_url)
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "UNTRUSTED_DOWNLOAD_HOST"


# ─────────────────────────────────────────────────────────────────────────────
# P10 — contentUrl missing fileDetailSn → DISCOVERY_PARSE_ERROR
# ─────────────────────────────────────────────────────────────────────────────

def test_p10_missing_file_detail_sn():
    no_sn_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId={ATCH_FILE_ID}&insertDataPrcus=N"
    page = _make_page_csv(no_sn_url)
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_PARSE_ERROR"
    assert result.artifact is None


# ─────────────────────────────────────────────────────────────────────────────
# P11 — non-CSV distribution ignored, CSV selected without ambiguity
# ─────────────────────────────────────────────────────────────────────────────

def test_p11_non_csv_distribution_ignored():
    csv_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId={ATCH_FILE_ID}&fileDetailSn=1"
    json_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_JSON_FORMAT&fileDetailSn=2"
    page = _make_page(
        _csv_dist(csv_url, fmt="CSV"),
        _csv_dist(json_url, fmt="JSON"),
    )
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "DISCOVERED"
    assert result.artifact is not None
    assert result.artifact.attachment_id == ATCH_FILE_ID


# ─────────────────────────────────────────────────────────────────────────────
# P12 — two CSV distributions with distinct IDs → AMBIGUOUS_LATEST_ARTIFACT
# ─────────────────────────────────────────────────────────────────────────────

def test_p12_two_csv_distributions_ambiguous():
    url_a = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_CSV_A&fileDetailSn=1"
    url_b = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_CSV_B&fileDetailSn=1"
    page = _make_page(_csv_dist(url_a, "CSV"), _csv_dist(url_b, "CSV"))
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "AMBIGUOUS_LATEST_ARTIFACT"


# ─────────────────────────────────────────────────────────────────────────────
# P13 — unexpected exception → DISCOVERY_UNEXPECTED, no secret leaked
# ─────────────────────────────────────────────────────────────────────────────

def test_p13_unexpected_exception_sanitized():
    def _raise_runtime(_url: str) -> bytes:
        raise RuntimeError("SECRET=super_secret_key request failed")

    result = discover_latest_artifact(http_get=_raise_runtime)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_UNEXPECTED"
    assert result.error_message == "RuntimeError"
    assert "SECRET" not in (result.error_message or "")
    assert "super_secret" not in (result.error_message or "")


# ─────────────────────────────────────────────────────────────────────────────
# Extra — both None explicitly → DISCOVERED
# ─────────────────────────────────────────────────────────────────────────────

def test_d_discovered_when_no_known_baseline():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_attachment_id=None,
        known_effective_date=None,
    )
    assert result.status == "DISCOVERED"
    assert result.artifact is not None


# ─────────────────────────────────────────────────────────────────────────────
# Extra — duplicate same attachment URL not ambiguous
# ─────────────────────────────────────────────────────────────────────────────

def test_d_duplicate_same_attachment_not_ambiguous():
    page = _make_page_csv(_KNOWN_CONTENT_URL, _KNOWN_CONTENT_URL)
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "DISCOVERED"


# ─────────────────────────────────────────────────────────────────────────────
# Extra — ALLOWED_DOWNLOAD_HOSTS contract
# ─────────────────────────────────────────────────────────────────────────────

def test_d_allowed_hosts_contract():
    assert "www.data.go.kr" in ALLOWED_DOWNLOAD_HOSTS
    assert "data.go.kr" in ALLOWED_DOWNLOAD_HOSTS
    assert "example.com" not in ALLOWED_DOWNLOAD_HOSTS


# ─────────────────────────────────────────────────────────────────────────────
# Extra — DOWNLOAD_PATH and DATASET_NAME contract
# ─────────────────────────────────────────────────────────────────────────────

def test_d_static_constants():
    assert DOWNLOAD_PATH == "/cmm/cmm/fileDownload.do"
    assert DATASET_NAME == "국토안전관리원_건설안전사고사례"
