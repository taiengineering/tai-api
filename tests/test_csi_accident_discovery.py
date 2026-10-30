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
    DOWNLOAD_API_URL,
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


def _csv_dist(content_url: str, fmt: str | None = "CSV") -> dict:
    d: dict = {"@type": "DataDownload", "contentUrl": content_url}
    if fmt is not None:
        d["encodingFormat"] = fmt
    return d


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
        known_file_detail_sn="1",
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
        known_file_detail_sn="1",
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
        known_file_detail_sn="1",
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
        known_file_detail_sn="1",
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


# ─────────────────────────────────────────────────────────────────────────────
# P14 — same atchFileId, different fileDetailSn → AMBIGUOUS_LATEST_ARTIFACT
# ─────────────────────────────────────────────────────────────────────────────

def test_p14_same_attachment_different_fdsn_ambiguous():
    url_a = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_A&fileDetailSn=1"
    url_b = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_A&fileDetailSn=2"
    page = _make_page(_csv_dist(url_a, "CSV"), _csv_dist(url_b, "CSV"))
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "AMBIGUOUS_LATEST_ARTIFACT"


# ─────────────────────────────────────────────────────────────────────────────
# P15 — same attachment + same date, different fileDetailSn in known → NEW_ARTIFACT
# ─────────────────────────────────────────────────────────────────────────────

def test_p15_known_fdsn_differs_new_artifact():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_attachment_id=ATCH_FILE_ID,
        known_file_detail_sn="99",
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NEW_ARTIFACT"
    assert result.artifact is not None
    assert result.artifact.file_detail_sn == "1"


# ─────────────────────────────────────────────────────────────────────────────
# P16 — only one of three comparison fields provided → COMPARISON_INPUT_INCOMPLETE
# ─────────────────────────────────────────────────────────────────────────────

def test_p16_file_detail_sn_only_incomplete():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        known_file_detail_sn="1",
    )
    assert result.status == "FAILED"
    assert result.error_code == "COMPARISON_INPUT_INCOMPLETE"


# ─────────────────────────────────────────────────────────────────────────────
# P17 — all distributions have no encodingFormat → NO_ARTIFACT (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────

def test_p17_missing_encoding_format_no_artifact():
    no_fmt_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId={ATCH_FILE_ID}&fileDetailSn=1"
    page = _make_page(_csv_dist(no_fmt_url, fmt=None))
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "NO_ARTIFACT"


# ─────────────────────────────────────────────────────────────────────────────
# P18 — CSV dist A + no-format dist B + JSON dist C → only A selected
# ─────────────────────────────────────────────────────────────────────────────

def test_p18_mixed_formats_only_csv_selected():
    csv_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_CSV&fileDetailSn=1"
    no_fmt_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_NOFMT&fileDetailSn=1"
    json_url = f"https://www.data.go.kr{DOWNLOAD_PATH}?atchFileId=FILE_JSON&fileDetailSn=1"
    page = _make_page(
        _csv_dist(csv_url, fmt="CSV"),
        _csv_dist(no_fmt_url, fmt=None),
        _csv_dist(json_url, fmt="JSON"),
    )
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "DISCOVERED"
    assert result.artifact is not None
    assert result.artifact.attachment_id == "FILE_CSV"


# ─────────────────────────────────────────────────────────────────────────────
# P19 — now_fn() raises RuntimeError with secret → DISCOVERY_UNEXPECTED, no leak
# ─────────────────────────────────────────────────────────────────────────────

def test_p19_now_fn_raises_no_secret_leaked():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        now_fn=lambda: (_ for _ in ()).throw(RuntimeError("SECRET=super_secret_now_key")),
    )
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_UNEXPECTED"
    assert result.error_message == "RuntimeError"
    assert "SECRET" not in (result.error_message or "")
    assert "super_secret" not in (result.error_message or "")


# ─────────────────────────────────────────────────────────────────────────────
# P20 — now_fn returns non-datetime object → DISCOVERY_UNEXPECTED (AttributeError)
# ─────────────────────────────────────────────────────────────────────────────

def test_p20_now_fn_returns_non_datetime():
    result = discover_latest_artifact(
        http_get=_HTTP_CURRENT,
        now_fn=lambda: object(),
    )
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_UNEXPECTED"


# ─────────────────────────────────────────────────────────────────────────────
# WP-C — API fallback path (portal JSON-LD distribution[] removed ~2026-09-15)
# ─────────────────────────────────────────────────────────────────────────────

_KNOWN_DETAIL_PK = "uddi:7efed86b-d0ca-4a4b-8115-dea5840f29a9"


def _make_page_onclick(
    detail_pk: str = _KNOWN_DETAIL_PK,
    dataset_id: str = DATASET_ID,
) -> bytes:
    """Page with JSON-LD but no distribution — has fn_fileDataDown onclick."""
    ld = json.dumps({"@context": "https://schema.org", "@type": "Dataset"})
    return (
        f"<html><head>"
        f'<script type="application/ld+json">{ld}</script>'
        f"</head><body>"
        f"<a onclick=\"fn_fileDataDown('{dataset_id}', '{detail_pk}', '', '1', '27')\">다운로드</a>"
        f"</body></html>"
    ).encode()


def _make_http_post_ok(
    atch_file_id: str = ATCH_FILE_ID,
    file_detail_sn: str = "1",
) -> Callable[[str, dict], bytes]:
    def _post(url: str, params: dict) -> bytes:
        assert url == DOWNLOAD_API_URL
        return json.dumps({
            "status": True,
            "atchFileId": atch_file_id,
            "fileDetailSn": file_detail_sn,
        }).encode()
    return _post


# ── WPC-01: fallback path resolves correctly → DISCOVERED ────────────────────

def test_wpc01_api_fallback_discovered():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())
    result = discover_latest_artifact(
        http_get=http_get,
        http_post=_make_http_post_ok(),
    )
    assert result.status == "DISCOVERED"
    assert result.artifact is not None
    assert result.artifact.attachment_id == ATCH_FILE_ID
    assert result.artifact.file_detail_sn == "1"
    assert result.artifact.effective_date == DATASET_EFFECTIVE_DATE
    assert result.artifact.download_url == _KNOWN_CONTENT_URL


# ── WPC-02: fallback → NO_CHANGE when known matches API response ──────────────

def test_wpc02_api_fallback_no_change():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())
    result = discover_latest_artifact(
        http_get=http_get,
        http_post=_make_http_post_ok(),
        known_attachment_id=ATCH_FILE_ID,
        known_file_detail_sn="1",
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NO_CHANGE"
    assert result.artifact is not None


# ── WPC-03: fallback → NEW_ARTIFACT when API returns different attachment ─────

def test_wpc03_api_fallback_new_artifact():
    new_att = "FILE_000000009999999"
    new_meta = _make_meta(alternate_name="국토안전관리원_건설안전사고사례_20261130")
    http_get = _make_http_get(new_meta, _make_page_onclick())
    result = discover_latest_artifact(
        http_get=http_get,
        http_post=_make_http_post_ok(atch_file_id=new_att),
        known_attachment_id=ATCH_FILE_ID,
        known_file_detail_sn="1",
        known_effective_date=DATASET_EFFECTIVE_DATE,
    )
    assert result.status == "NEW_ARTIFACT"
    assert result.artifact is not None
    assert result.artifact.attachment_id == new_att
    assert result.artifact.effective_date == "2026-11-30"


# ── WPC-04: no onclick and no distribution → still NO_ARTIFACT (fail-closed) ──

def test_wpc04_no_onclick_no_distribution_no_artifact():
    page = b"<html><head><script type='application/ld+json'>{}</script></head></html>"
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "NO_ARTIFACT"


# ── WPC-05: onclick for wrong dataset_id is ignored → NO_ARTIFACT ─────────────

def test_wpc05_onclick_wrong_dataset_id_ignored():
    page = _make_page_onclick(dataset_id="99999999")
    http_get = _make_http_get(_META_CURRENT, page)
    result = discover_latest_artifact(http_get=http_get)
    assert result.status == "FAILED"
    assert result.error_code == "NO_ARTIFACT"


# ── WPC-06: POST network error → DISCOVERY_HTTP_ERROR ────────────────────────

def test_wpc06_post_network_error():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())

    def _fail_post(url: str, params: dict) -> bytes:
        raise OSError("connection refused")

    result = discover_latest_artifact(http_get=http_get, http_post=_fail_post)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_HTTP_ERROR"


# ── WPC-07: POST returns status=false → NO_ARTIFACT ──────────────────────────

def test_wpc07_post_status_false():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())

    def _false_post(url: str, params: dict) -> bytes:
        return json.dumps({"status": False}).encode()

    result = discover_latest_artifact(http_get=http_get, http_post=_false_post)
    assert result.status == "FAILED"
    assert result.error_code == "NO_ARTIFACT"


# ── WPC-08: POST returns bad JSON → DISCOVERY_PARSE_ERROR ────────────────────

def test_wpc08_post_bad_json():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())

    def _bad_json_post(url: str, params: dict) -> bytes:
        return b"not json {"

    result = discover_latest_artifact(http_get=http_get, http_post=_bad_json_post)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_PARSE_ERROR"


# ── WPC-09: POST returns missing atchFileId → DISCOVERY_PARSE_ERROR ──────────

def test_wpc09_post_missing_atch_file_id():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())

    def _no_id_post(url: str, params: dict) -> bytes:
        return json.dumps({"status": True, "fileDetailSn": "1"}).encode()

    result = discover_latest_artifact(http_get=http_get, http_post=_no_id_post)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_PARSE_ERROR"


# ── WPC-10: _build_download_url always uses www.data.go.kr (API cannot inject host) ──

def test_wpc10_fallback_url_always_on_allowed_host():
    """_build_download_url hardcodes www.data.go.kr — the POST API response cannot
    inject a different host via atchFileId because the URL is constructed from
    DOWNLOAD_PATH (constant), not from any field returned by the API."""
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())
    result = discover_latest_artifact(
        http_get=http_get,
        http_post=_make_http_post_ok(),
    )
    assert result.status == "DISCOVERED"
    assert result.artifact is not None
    from urllib.parse import urlparse
    parsed = urlparse(result.artifact.download_url)
    assert parsed.scheme == "https"
    assert parsed.netloc in ALLOWED_DOWNLOAD_HOSTS
    assert parsed.path == DOWNLOAD_PATH


# ── WPC-11: http_post signature is injectable (regression guard) ──────────────

def test_wpc11_http_post_is_injectable():
    import inspect
    sig = inspect.signature(discover_latest_artifact)
    assert "http_post" in sig.parameters


# ── WPC-12: atchFileId with special/unsafe chars rejected → DISCOVERY_PARSE_ERROR ──

def test_wpc12_atch_file_id_special_chars_rejected():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())
    bad_ids = [
        "FILE_123&evil=x",   # query injection
        "FILE_123#anchor",   # fragment injection
        "FILE_123?q=1",      # extra query param
        "FILE_123\nfoo",     # newline
        "FILE_abc123",       # non-digits after FILE_
        "NOTFILE_123",       # wrong prefix
        "",                  # empty
    ]
    for bad_id in bad_ids:
        def _post(url: str, params: dict, bid: str = bad_id) -> bytes:
            return json.dumps({"status": True, "atchFileId": bid, "fileDetailSn": "1"}).encode()
        result = discover_latest_artifact(http_get=http_get, http_post=_post)
        assert result.status == "FAILED", f"expected FAILED for atchFileId={bad_id!r}"
        assert result.error_code == "DISCOVERY_PARSE_ERROR", f"wrong code for atchFileId={bad_id!r}"


# ── WPC-13: fileDetailSn zero → DISCOVERY_PARSE_ERROR ────────────────────────

def test_wpc13_file_detail_sn_zero_rejected():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())

    def _zero_sn_post(url: str, params: dict) -> bytes:
        return json.dumps({"status": True, "atchFileId": ATCH_FILE_ID, "fileDetailSn": "0"}).encode()

    result = discover_latest_artifact(http_get=http_get, http_post=_zero_sn_post)
    assert result.status == "FAILED"
    assert result.error_code == "DISCOVERY_PARSE_ERROR"


# ── WPC-14: fileDetailSn non-numeric variants → DISCOVERY_PARSE_ERROR ─────────

def test_wpc14_file_detail_sn_nonnumeric_rejected():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())
    bad_sns = ["abc", "1.5", "-1", "1a", ""]
    for bad_sn in bad_sns:
        def _post(url: str, params: dict, sn: str = bad_sn) -> bytes:
            return json.dumps({"status": True, "atchFileId": ATCH_FILE_ID, "fileDetailSn": sn}).encode()
        result = discover_latest_artifact(http_get=http_get, http_post=_post)
        assert result.status == "FAILED", f"expected FAILED for fileDetailSn={bad_sn!r}"
        assert result.error_code == "DISCOVERY_PARSE_ERROR", f"wrong code for fileDetailSn={bad_sn!r}"


# ── WPC-15: status non-bool-True variants rejected → NO_ARTIFACT ─────────────

def test_wpc15_status_non_bool_true_rejected():
    http_get = _make_http_get(_META_CURRENT, _make_page_onclick())
    bad_statuses = ["true", "True", 1, 0, None]
    for bad_s in bad_statuses:
        def _post(url: str, params: dict, s=bad_s) -> bytes:
            return json.dumps({"status": s, "atchFileId": ATCH_FILE_ID, "fileDetailSn": "1"}).encode()
        result = discover_latest_artifact(http_get=http_get, http_post=_post)
        assert result.status == "FAILED", f"expected FAILED for status={bad_s!r}"
        assert result.error_code == "NO_ARTIFACT", f"wrong code for status={bad_s!r}"
