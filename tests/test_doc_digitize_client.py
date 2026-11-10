"""WO-DOC-G7-B1 Work B — doc_digitize_client 단위 테스트.

DC-01: 신규 처리 — extraction_storage_ref 수신·전달
DC-02: 신규 처리 — extraction_storage_ref=null → None
DC-03: 신규 처리 — extraction_storage_ref 필드 없음 → None
DC-04: 중복 응답 → extraction_storage_ref=None (기존 doc_log_id만)
DC-05: extraction_storage_warning 수신·전달
DC-06: 기존 storage_ref 필드 유지 확인
DC-07: 기존 storage_warning 필드 유지 확인

Production DB write = 0 (_parse_200_body 직접 호출).
"""
from __future__ import annotations

import pytest

from services.doc_digitize_client import DocDigitizeError, _parse_200_body


# ── 최소 신규 처리 응답 픽스처 ─────────────────────────────────────────────────

def _new_body(**overrides) -> dict:
    base = {
        "ok": True,
        "doc_log_id": "log-001",
        "duplicate": False,
        "primitive_id": "prim-001",
        "v1_status": "pass",
        "v2_status": "pass",
        "file_hash": "abc123",
        "file_size_bytes": 1024,
        "storage_ref": "doc-originals/t1/2026/11/log-001_test.pdf",
    }
    base.update(overrides)
    return base


# ── DC-01: extraction_storage_ref 수신 ───────────────────────────────────────

def test_DC01_extraction_storage_ref_forwarded():
    body = _new_body(
        extraction_storage_ref="doc-extractions/t1/2026/11/log-001_test.md"
    )
    result = _parse_200_body(body)
    assert result.extraction_storage_ref == "doc-extractions/t1/2026/11/log-001_test.md"
    assert result.duplicate is False


# ── DC-02: extraction_storage_ref=null ───────────────────────────────────────

def test_DC02_extraction_storage_ref_null():
    body = _new_body(extraction_storage_ref=None)
    result = _parse_200_body(body)
    assert result.extraction_storage_ref is None


# ── DC-03: extraction_storage_ref 필드 없음 ──────────────────────────────────

def test_DC03_extraction_storage_ref_absent():
    body = _new_body()
    assert "extraction_storage_ref" not in body
    result = _parse_200_body(body)
    assert result.extraction_storage_ref is None


# ── DC-04: 중복 응답 → extraction_storage_ref=None ───────────────────────────

def test_DC04_duplicate_no_extraction_ref():
    body = {
        "ok": True,
        "doc_log_id": "log-dup-001",
        "duplicate": True,
    }
    result = _parse_200_body(body)
    assert result.duplicate is True
    assert result.extraction_storage_ref is None
    assert result.primitive_id is None


# ── DC-05: extraction_storage_warning 수신 ───────────────────────────────────

def test_DC05_extraction_storage_warning_forwarded():
    body = _new_body(
        extraction_storage_ref=None,
        extraction_storage_warning="추출 결과 저장 실패: bucket error",
    )
    result = _parse_200_body(body)
    assert result.extraction_storage_warning == "추출 결과 저장 실패: bucket error"
    assert result.extraction_storage_ref is None


# ── DC-06: 기존 storage_ref 유지 ─────────────────────────────────────────────

def test_DC06_existing_storage_ref_preserved():
    body = _new_body(storage_ref="doc-originals/t1/2026/11/log-001_test.pdf")
    result = _parse_200_body(body)
    assert result.storage_ref == "doc-originals/t1/2026/11/log-001_test.pdf"


# ── DC-07: 기존 storage_warning 유지 ─────────────────────────────────────────

def test_DC07_existing_storage_warning_preserved():
    body = _new_body(storage_warning="원본 파일 저장 실패")
    result = _parse_200_body(body)
    assert result.storage_warning == "원본 파일 저장 실패"
