"""WO-DOC-G7-B2 — doc_lookup_client 단위 테스트.

DL-01: DOC_LOOKUP_URL 미설정 → endpoint_not_active 오류
DL-02: TAI_SERVICE_KEY 미설정 → config_missing 오류
DL-03: 정상 조회 성공 → DocLookupResult(status=FOUND, ref+format 포함)
DL-04: status=FOUND, format=md → Markdown 형식 그대로 반환 (json 자동 승격 없음)
DL-05: status=NOT_FOUND 응답 → DocLookupResult(status=NOT_FOUND)
DL-06: status=EXTRACTION_REF_MISSING 응답 → DocLookupResult 그대로 전달
DL-07: DOC 403 응답 → auth_failed 오류
DL-08: DOC 500 응답 → backend_error 오류
DL-09: 타임아웃 → connection_timeout 오류
DL-10: 네트워크 오류 → connection_error 오류
DL-11: status 필드 없는 200 응답 → unexpected_response 오류
DL-12: 기존 doc_digitize_client 미변경 — DocDigitizeResult import 성공

Production DB write = 0 (_parse_lookup_body 직접 호출 또는 mock httpx 사용).
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services.doc_lookup_client import (
    DocLookupError,
    DocLookupResult,
    _parse_lookup_body,
    lookup_extraction,
)


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _mock_resp(status_code: int, json_body=None) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    return mock


# ── DL-01: DOC_LOOKUP_URL 미설정 ─────────────────────────────────────────────

def test_DL01_missing_lookup_url(monkeypatch):
    monkeypatch.delenv("DOC_LOOKUP_URL", raising=False)
    monkeypatch.setenv("TAI_SERVICE_KEY", "some-key")
    with pytest.raises(DocLookupError) as exc_info:
        asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))
    assert exc_info.value.code == "endpoint_not_active"


# ── DL-02: TAI_SERVICE_KEY 미설정 ─────────────────────────────────────────────

def test_DL02_missing_service_key(monkeypatch):
    monkeypatch.setenv("DOC_LOOKUP_URL", "https://doc.example.com")
    monkeypatch.delenv("TAI_SERVICE_KEY", raising=False)
    with pytest.raises(DocLookupError) as exc_info:
        asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))
    assert exc_info.value.code == "config_missing"


# ── DL-03: 정상 조회 성공 ─────────────────────────────────────────────────────

def test_DL03_found_success(monkeypatch):
    monkeypatch.setenv("DOC_LOOKUP_URL", "https://doc.example.com")
    monkeypatch.setenv("TAI_SERVICE_KEY", "svc-key")
    body = {
        "status": "FOUND",
        "extraction_storage_ref": "doc-extractions/co-001/2026/11/log-001_contract.md",
        "extraction_format": "json",
    }
    mock_resp = _mock_resp(200, body)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))

    assert result.doc_log_id == "log-001"
    assert result.status == "FOUND"
    assert result.extraction_storage_ref == "doc-extractions/co-001/2026/11/log-001_contract.md"
    assert result.extraction_format == "json"


# ── DL-04: format=md → Markdown 형식 그대로 (json 자동 승격 없음) ─────────────

def test_DL04_markdown_format_not_promoted():
    body = {
        "status": "FOUND",
        "extraction_storage_ref": "doc-extractions/co-001/2026/11/log-001_contract.md",
        "extraction_format": "md",
    }
    result = _parse_lookup_body(body, "log-001")
    assert result.status == "FOUND"
    assert result.extraction_format == "md"
    # 'json'으로 자동 치환되지 않음 — MAP-02 실행은 호출자 책임
    assert result.extraction_format != "json"


# ── DL-05: status=NOT_FOUND ───────────────────────────────────────────────────

def test_DL05_not_found_forwarded():
    body = {"status": "NOT_FOUND"}
    result = _parse_lookup_body(body, "log-nope")
    assert result.doc_log_id == "log-nope"
    assert result.status == "NOT_FOUND"
    assert result.extraction_storage_ref is None
    assert result.extraction_format is None


# ── DL-06: status=EXTRACTION_REF_MISSING ─────────────────────────────────────

def test_DL06_extraction_ref_missing_forwarded():
    body = {"status": "EXTRACTION_REF_MISSING"}
    result = _parse_lookup_body(body, "log-002")
    assert result.status == "EXTRACTION_REF_MISSING"
    assert result.extraction_storage_ref is None


# ── DL-07: DOC 403 → auth_failed ─────────────────────────────────────────────

def test_DL07_doc_403_auth_failed(monkeypatch):
    monkeypatch.setenv("DOC_LOOKUP_URL", "https://doc.example.com")
    monkeypatch.setenv("TAI_SERVICE_KEY", "wrong-key")
    mock_resp = _mock_resp(403, {"error": "AUTH_FAILED"})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocLookupError) as exc_info:
            asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))
    assert exc_info.value.code == "auth_failed"


# ── DL-08: DOC 500 → backend_error ───────────────────────────────────────────

def test_DL08_doc_500_backend_error(monkeypatch):
    monkeypatch.setenv("DOC_LOOKUP_URL", "https://doc.example.com")
    monkeypatch.setenv("TAI_SERVICE_KEY", "svc-key")
    mock_resp = _mock_resp(500, {"error": "internal_error"})
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocLookupError) as exc_info:
            asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))
    assert exc_info.value.code == "backend_error"


# ── DL-09: 타임아웃 → connection_timeout ─────────────────────────────────────

def test_DL09_timeout(monkeypatch):
    monkeypatch.setenv("DOC_LOOKUP_URL", "https://doc.example.com")
    monkeypatch.setenv("TAI_SERVICE_KEY", "svc-key")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocLookupError) as exc_info:
            asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))
    assert exc_info.value.code == "connection_timeout"


# ── DL-10: 네트워크 오류 → connection_error ───────────────────────────────────

def test_DL10_network_error(monkeypatch):
    monkeypatch.setenv("DOC_LOOKUP_URL", "https://doc.example.com")
    monkeypatch.setenv("TAI_SERVICE_KEY", "svc-key")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DocLookupError) as exc_info:
            asyncio.run(lookup_extraction(doc_log_id="log-001", company_id="co-001"))
    assert exc_info.value.code == "connection_error"


# ── DL-11: status 필드 없는 200 응답 → unexpected_response ───────────────────

def test_DL11_missing_status_field():
    body = {"extraction_storage_ref": "some-ref"}  # status 없음
    with pytest.raises(DocLookupError) as exc_info:
        _parse_lookup_body(body, "log-001")
    assert exc_info.value.code == "unexpected_response"


# ── DL-12: 기존 doc_digitize_client 미변경 ────────────────────────────────────

def test_DL12_digitize_client_import_unaffected():
    from services.doc_digitize_client import DocDigitizeResult, digitize  # noqa: F401
    result = DocDigitizeResult(doc_log_id="log-x", duplicate=False)
    assert result.doc_log_id == "log-x"
    assert result.duplicate is False
