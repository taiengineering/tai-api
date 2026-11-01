"""WO-034 OBJ01 Intake + Preflight 검증.

테스트 범위 (WO-034 §6):
  T01 — role_code "001" 정상 접수 → PASS SourceBundle
  T02 — role_code "031/032/033" → 403
  T03 — 존재하지 않는 company_id → 404
  T04 — HWP 파일 → status=UNSUPPORTED
  T05 — 파일 크기 경계값 정상 처리
  T06 — 파일 크기 초과 → 413
  T07 — 정상 CSV 기본 검사 → PASS
  T08 — PDF 형식 검사 (텍스트 추출 미실행) → PASS
  T09 — ZIP 내부 처리 차단 → BLOCKED
  T10 — 감사 실패(INTAKE_RECEIVED) → 503 (처리 시작 중단)
  T11 — 결과에 올바른 company_id·파일 해시 반영
  T12 — 기존 회사 온보딩 기능 import 무결성

합성 데이터만 사용 — 실 DB, 실 Storage 없음.
Supabase 및 audit_svc는 mock 처리.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from services.onboarding_digitization.intake_svc import (
    _MAX_BYTES,
    _MAX_ZIP_ENTRIES,
    _SCHEMA_VERSION,
    _detect_mime,
    _is_ooxml,
    _is_xlsx_workbook,
    _preflight_file,
    _read_with_size_limit,
    _sha256,
    _verify_company_exists,
    run_intake_preflight,
)
from services.onboarding_digitization.models import FileStatus

# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _make_xlsx_bytes() -> bytes:
    """최소 유효 OOXML 파일 생성."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


def _make_zip_bytes(members: dict[str, bytes] | None = None) -> bytes:
    """OOXML 아닌 일반 ZIP 파일 생성."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in (members or {"data.csv": b"name,age\n"}).items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_upload_file(filename: str, data: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    mock = MagicMock(spec=UploadFile)
    mock.filename = filename
    mock.content_type = content_type
    # read()가 처음 호출 시 data, 이후 b"" 반환
    call_count = {"n": 0}

    async def _read(size: int = -1) -> bytes:
        if call_count["n"] == 0:
            call_count["n"] += 1
            return data
        return b""

    mock.read = _read
    return mock


def _make_supabase_mock(company_exists: bool = True) -> MagicMock:
    sb = MagicMock()
    tbl = MagicMock()
    sb.table.return_value = tbl
    tbl.select.return_value = tbl
    tbl.eq.return_value = tbl
    tbl.limit.return_value = tbl
    if company_exists:
        tbl.execute.return_value = MagicMock(data=[{"id": "company-001"}])
    else:
        tbl.execute.return_value = MagicMock(data=[])
    return sb


# ── T01: 정상 CSV 접수 → PASS ──────────────────────────────────────────────────

def test_t01_csv_pass_normal_intake():
    """T01: role 001 정상 접수 — CSV 파일 → PASS SourceBundle."""
    async def _run():
        csv_data = b"name,age\n\xed\x95\x9c\xea\xb8\x80,30\n"  # UTF-8 한글 포함
        upload = _make_upload_file("employees.csv", csv_data, "text/csv")
        supabase = _make_supabase_mock(company_exists=True)

        bundle, report, _ = await run_intake_preflight(
            company_id="company-001",
            actor_id="user-001",
            upload_files=[upload],
            supabase=supabase,
        )

        assert bundle.company_id == "company-001"
        assert bundle.submitted_by == "user-001"
        assert len(bundle.files) == 1
        assert bundle.files[0].filename == "employees.csv"
        assert bundle.files[0].sha256 == hashlib.sha256(csv_data).hexdigest()
        assert report.overall_status == "PASS"
        assert report.file_results[0].status == FileStatus.PASS

    asyncio.run(_run())


# ── T02: role 031/032/033 → 403 ────────────────────────────────────────────────

def test_t02_role_031_forbidden():
    """T02: role_code 031 → 403."""
    from routers.onboarding_digitization import _require_role_001
    with pytest.raises(HTTPException) as exc:
        _require_role_001({"role_code": "031"})
    assert exc.value.status_code == 403


def test_t02_role_032_forbidden():
    from routers.onboarding_digitization import _require_role_001
    with pytest.raises(HTTPException) as exc:
        _require_role_001({"role_code": "032"})
    assert exc.value.status_code == 403


def test_t02_role_033_forbidden():
    from routers.onboarding_digitization import _require_role_001
    with pytest.raises(HTTPException) as exc:
        _require_role_001({"role_code": "033"})
    assert exc.value.status_code == 403


def test_t02_role_001_allowed():
    from routers.onboarding_digitization import _require_role_001
    _require_role_001({"role_code": "001"})  # 예외 없음


# ── T03: 존재하지 않는 company_id → 404 ────────────────────────────────────────

def test_t03_company_not_found():
    """T03: company_id 없음 → 404 (_ensure_own_company 우회 없음, C01)."""
    sb = _make_supabase_mock(company_exists=False)
    with pytest.raises(HTTPException) as exc:
        _verify_company_exists("nonexistent-company", sb)
    assert exc.value.status_code == 404


def test_t03_company_found_no_exception():
    sb = _make_supabase_mock(company_exists=True)
    _verify_company_exists("company-001", sb)  # 예외 없음


# ── T04: HWP → UNSUPPORTED ──────────────────────────────────────────────────────

def test_t04_hwp_unsupported():
    """T04: HWP 파일 → status=UNSUPPORTED (not UNSUPPORTED_FORMAT, C06)."""
    result = _preflight_file("document.hwp", b"HWP content", "application/octet-stream")
    assert result.status == FileStatus.UNSUPPORTED


def test_t04_hwpx_unsupported():
    result = _preflight_file("document.hwpx", b"HWPX content", "application/octet-stream")
    assert result.status == FileStatus.UNSUPPORTED


# ── T05: 파일 크기 경계값 ─────────────────────────────────────────────────────────

def test_t05_size_at_boundary_allowed():
    """T05: 정확히 _MAX_BYTES 크기 → 통과."""
    async def _run():
        data = b"A" * _MAX_BYTES
        upload = _make_upload_file("boundary.csv", data, "text/csv")
        result = await _read_with_size_limit(upload)
        assert len(result) == _MAX_BYTES

    asyncio.run(_run())


def test_t05_size_one_byte_over_rejected():
    """T05: _MAX_BYTES + 1 → 413."""
    async def _run():
        data = b"A" * (_MAX_BYTES + 1)
        state = {"called": False}

        async def _read_oversized(size: int = -1) -> bytes:
            if not state["called"]:
                state["called"] = True
                return data
            return b""

        mock = MagicMock(spec=UploadFile)
        mock.filename = "oversized.csv"
        mock.content_type = "text/csv"
        mock.read = _read_oversized

        with pytest.raises(HTTPException) as exc:
            await _read_with_size_limit(mock)
        assert exc.value.status_code == 413

    asyncio.run(_run())


# ── T06: magic bytes 불일치 ──────────────────────────────────────────────────────

def test_t06_pdf_magic_mismatch():
    """T06: .pdf 확장자이지만 magic bytes가 PDF 아님 → FAIL."""
    result = _preflight_file("not_a_pdf.pdf", b"This is not PDF content", "application/pdf")
    assert result.status == FileStatus.FAIL
    magic_check = next(c for c in result.checks if c.name == "MAGIC_BYTES")
    assert not magic_check.passed


def test_t06_pdf_magic_match():
    """T06: PDF 정상 magic bytes → magic_match=True."""
    pdf_data = b"%PDF-1.4\ncontent\n%%EOF"
    detected = _detect_mime(pdf_data[:8])
    assert detected == "application/pdf"


# ── T07: 정상 CSV Preflight → PASS ───────────────────────────────────────────────

def test_t07_csv_valid_utf8():
    """T07: 정상 UTF-8 CSV → PASS."""
    csv_data = b"name,age\nAlice,30\nBob,25\n"
    result = _preflight_file("data.csv", csv_data, "text/csv")
    assert result.status == FileStatus.PASS


def test_t07_csv_valid_euckr():
    """T07: EUC-KR 인코딩 CSV → PASS."""
    csv_data = "이름,나이\n홍길동,30\n".encode("euc-kr")
    result = _preflight_file("data.csv", csv_data, "text/csv")
    assert result.status == FileStatus.PASS


def test_t07_csv_empty_fail():
    """T07: 빈 CSV → FAIL."""
    result = _preflight_file("empty.csv", b"", "text/csv")
    assert result.status == FileStatus.FAIL


def test_t07_xlsx_valid():
    """T07: 정상 XLSX (OOXML) → PASS."""
    xlsx_data = _make_xlsx_bytes()
    result = _preflight_file("data.xlsx", xlsx_data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert result.status == FileStatus.PASS


def test_t07_xlsx_non_ooxml_fail():
    """T07: .xlsx 확장자이지만 OOXML 구조 없음 → FAIL."""
    zip_data = _make_zip_bytes()  # [Content_Types].xml 없음
    result = _preflight_file("not_ooxml.xlsx", zip_data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert result.status == FileStatus.FAIL
    ooxml_check = next(c for c in result.checks if c.name == "OOXML_STRUCTURE")
    assert not ooxml_check.passed


# ── T08: PDF 형식 검사 (텍스트 추출 미실행) ──────────────────────────────────────

def test_t08_pdf_valid_no_ocr_flag():
    """T08: 유효 PDF → PASS. OCR_NOT_SUPPORTED 확정 표시 없음 (C04)."""
    pdf_data = b"%PDF-1.4\ncontent\n%%EOF"
    result = _preflight_file("report.pdf", pdf_data, "application/pdf")
    assert result.status == FileStatus.PASS
    # Preflight에서 OCR_NOT_SUPPORTED 확정 표시 금지 확인
    ocr_checks = [c for c in result.checks if "OCR_NOT_SUPPORTED" in c.detail]
    assert not ocr_checks, "Preflight에서 OCR 판정 금지 위반"
    # TEXT_LAYER_DEFERRED check 존재 확인
    deferred = next((c for c in result.checks if c.name == "TEXT_LAYER_DEFERRED"), None)
    assert deferred is not None
    assert deferred.passed  # 이연 상태 표시는 passed=True


def test_t08_pdf_scan_no_ocr_judgment():
    """T08: 스캔 PDF (텍스트 없어도) → Preflight에서 OCR 판정 없음."""
    # 스캔본과 텍스트 PDF는 외부 구조가 동일, Preflight에서 구분 불가
    # 구분은 [4] Parse 단계에서 수행 (C04)
    scan_pdf = b"%PDF-1.4\n%%EOF"  # 최소 PDF
    result = _preflight_file("scanned.pdf", scan_pdf, "application/pdf")
    ocr_confirmed = [c for c in result.checks if "OCR_NOT_SUPPORTED" in c.detail and not c.passed]
    assert not ocr_confirmed, "Preflight에서 OCR_NOT_SUPPORTED 확정 표시 금지 위반"


# ── T09: ZIP 내부 처리 차단 ───────────────────────────────────────────────────────

def test_t09_zip_blocked():
    """T09: ZIP 파일 → status=BLOCKED (내부 처리 차단)."""
    zip_data = _make_zip_bytes({"data.csv": b"name,age\n", "doc.pdf": b"%PDF-1.4\n%%EOF"})
    result = _preflight_file("archive.zip", zip_data, "application/zip")
    assert result.status == FileStatus.BLOCKED
    blocked_check = next(c for c in result.checks if c.name == "ZIP_CONTENT_PROCESSING")
    assert not blocked_check.passed
    assert "OWNER_DECISION" in blocked_check.detail or "Owner" in blocked_check.detail


def test_t09_zip_structure_valid_but_blocked():
    """T09: ZIP 구조 정상이어도 내부 처리 차단."""
    zip_data = _make_zip_bytes()
    result = _preflight_file("data.zip", zip_data, "application/zip")
    assert result.status == FileStatus.BLOCKED
    struct_check = next(c for c in result.checks if c.name == "ZIP_STRUCTURE")
    assert struct_check.passed  # 구조는 정상


# ── T10: 감사 실패 → 503 (처리 시작 중단) ────────────────────────────────────────

def test_t10_audit_fail_closes_processing():
    """T10: audit_svc.record()가 None 반환 → 503 (fail-closed, C05)."""
    from routers.onboarding_digitization import _require_audit
    with patch("routers.onboarding_digitization.audit_svc.record", return_value=None):
        with pytest.raises(HTTPException) as exc:
            _require_audit(
                action="INTAKE_RECEIVED",
                entity_type="onboarding_digitization",
                actor_id="user-001",
                after_data={"company_id": "company-001"},
            )
    assert exc.value.status_code == 503


def test_t10_audit_success_returns_id():
    """T10: 감사 성공 → audit_id 반환."""
    from routers.onboarding_digitization import _require_audit
    with patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id-001"):
        audit_id = _require_audit(
            action="INTAKE_RECEIVED",
            entity_type="onboarding_digitization",
            actor_id="user-001",
            after_data={"company_id": "company-001"},
        )
    assert audit_id == "audit-id-001"


# ── T11: 결과에 올바른 company_id·파일 해시 반영 ──────────────────────────────────

def test_t11_bundle_has_correct_company_and_sha256():
    """T11: SourceBundle에 company_id와 파일 sha256 정확히 반영."""
    async def _run():
        csv_data = b"item_code,quantity\nITEM-001,100\n"
        upload = _make_upload_file("inventory.csv", csv_data, "text/csv")
        supabase = _make_supabase_mock(company_exists=True)

        bundle, report, _ = await run_intake_preflight(
            company_id="company-abc",
            actor_id="admin-001",
            upload_files=[upload],
            supabase=supabase,
        )

        assert bundle.company_id == "company-abc"
        assert bundle.submitted_by == "admin-001"
        assert len(bundle.files) == 1

        expected_sha = hashlib.sha256(csv_data).hexdigest()
        assert bundle.files[0].sha256 == expected_sha
        assert bundle.files[0].byte_size == len(csv_data)
        assert report.source_id == bundle.source_id

    asyncio.run(_run())


# ── T12: 기존 회사 온보딩 기능 영향 없음 ──────────────────────────────────────────

def test_t12_existing_onboarding_ops_import_intact():
    """T12: onboarding_ops 모듈 import 정상 (기존 기능 회귀 없음)."""
    import routers.onboarding_ops as ops
    assert hasattr(ops, "router")


def test_t12_new_router_import_intact():
    """T12: 신규 onboarding_digitization 라우터 import 정상."""
    import routers.onboarding_digitization as dig
    assert hasattr(dig, "router")


def test_t12_routers_have_distinct_prefixes():
    """T12: 기존 온보딩 라우터와 신규 디지털화 라우터 prefix 충돌 없음."""
    import routers.onboarding_digitization as dig
    new_prefix = dig.router.prefix
    assert "/digitization" in new_prefix or "/admin/companies" in new_prefix


# ── 추가: _is_ooxml / _detect_mime 단위 검사 ───────────────────────────────────

def test_detect_mime_pdf():
    assert _detect_mime(b"%PDF-1.4 content") == "application/pdf"


def test_detect_mime_zip():
    assert _detect_mime(b"PK\x03\x04 content") == "application/zip"


def test_detect_mime_unknown():
    assert _detect_mime(b"random data") == "application/octet-stream"


def test_is_ooxml_true():
    assert _is_ooxml(_make_xlsx_bytes()) is True


def test_is_ooxml_false_plain_zip():
    assert _is_ooxml(_make_zip_bytes()) is False


def test_sha256_stable():
    data = b"stable data"
    assert _sha256(data) == hashlib.sha256(data).hexdigest()


def test_is_xlsx_workbook_true():
    assert _is_xlsx_workbook(_make_xlsx_bytes()) is True


def test_is_xlsx_workbook_false_no_workbook():
    """[Content_Types].xml만 있고 xl/workbook.xml 없는 ZIP (DOCX 구조) → False."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<document/>")  # DOCX 구조
    assert _is_xlsx_workbook(buf.getvalue()) is False


# ── R1-01: 회사 목록 API size 계약 ────────────────────────────────────────────────

def test_r1_01_composable_uses_size_100():
    """R1-01: useDigitizationIntake loadCompanies가 size=100 이하로 요청."""
    import re
    ts_path = "vue3/src/pages/onboarding-digitization/useDigitizationIntake.ts"
    import os
    full_path = os.path.join(os.path.dirname(__file__), "..", "..", "tai-admin", ts_path)
    if not os.path.exists(full_path):
        pytest.skip("tai-admin repo not available in test environment")
    with open(full_path) as f:
        code = f.read()
    # size=500은 없어야 함
    assert "size=500" not in code, "size=500 은 API 계약 위반 — size=100 이하 사용"
    # size=100 사용 확인
    assert "size=100" in code


# ── R1-02: 합성 데이터 실행 경계 ─────────────────────────────────────────────────

def test_r1_02_synthetic_gate_blocks_without_env(monkeypatch):
    """R1-02: 환경변수 미설정 시 신규 API 비활성 → 503."""
    monkeypatch.delenv("DIGITIZATION_SYNTHETIC_ENABLED", raising=False)
    from routers.onboarding_digitization import _require_synthetic_gate
    with pytest.raises(HTTPException) as exc:
        _require_synthetic_gate()
    assert exc.value.status_code == 503


def test_r1_02_synthetic_gate_blocks_false_env(monkeypatch):
    """R1-02: 환경변수 false → 503."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "false")
    from routers.onboarding_digitization import _require_synthetic_gate
    with pytest.raises(HTTPException) as exc:
        _require_synthetic_gate()
    assert exc.value.status_code == 503


def test_r1_02_synthetic_gate_passes_with_env(monkeypatch):
    """R1-02: DIGITIZATION_SYNTHETIC_ENABLED=true → 통과."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")
    from routers.onboarding_digitization import _require_synthetic_gate
    _require_synthetic_gate()  # 예외 없음


# ── R1-03: 파일 형식 판정 보정 ───────────────────────────────────────────────────

def test_r1_03_pdf_wrong_mime_fails():
    """R1-03: 유효 PDF 내용이지만 MIME 선언 오류 → FAIL."""
    pdf_data = b"%PDF-1.4\ncontent\n%%EOF"
    result = _preflight_file("report.pdf", pdf_data, "text/html")  # 명백히 잘못된 MIME
    assert result.status == FileStatus.FAIL
    mime_check = next(c for c in result.checks if c.name == "MIME_DECLARED")
    assert not mime_check.passed


def test_r1_03_csv_wrong_mime_fails():
    """R1-03: 유효 CSV 내용이지만 MIME 선언 오류 → FAIL."""
    csv_data = b"name,age\nAlice,30\n"
    result = _preflight_file("data.csv", csv_data, "application/pdf")  # 잘못된 MIME
    assert result.status == FileStatus.FAIL
    mime_check = next(c for c in result.checks if c.name == "MIME_DECLARED")
    assert not mime_check.passed


def test_r1_03_docx_as_xlsx_fails():
    """R1-03: DOCX 구조(.xlsx 위장) → OOXML_STRUCTURE FAIL (xl/workbook.xml 없음)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<document/>")  # DOCX 고유 경로
    docx_as_xlsx = buf.getvalue()
    result = _preflight_file("disguised.xlsx", docx_as_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert result.status == FileStatus.FAIL
    ooxml_check = next(c for c in result.checks if c.name == "OOXML_STRUCTURE")
    assert not ooxml_check.passed


def test_r1_03_csv_magic_match_false_is_not_damage():
    """R1-03 P2: CSV magic_match=False는 손상 아닌 확인 불가 상태."""
    csv_data = b"name,age\nAlice,30\n"
    result = _preflight_file("data.csv", csv_data, "text/csv")
    assert result.status == FileStatus.PASS
    magic_check = next(c for c in result.checks if c.name == "MAGIC_BYTES")
    assert magic_check.passed  # CSV는 magic bytes 없음 → passed=True로 처리


# ── R1-04: ZIP 항목 수 초과 ────────────────────────────────────────────────────────

def test_r1_04_zip_entry_limit_enforced(monkeypatch):
    """R1-04: ZIP 항목 수 > _MAX_ZIP_ENTRIES → ZIP_STRUCTURE FAIL."""
    monkeypatch.setattr(
        "services.onboarding_digitization.intake_svc._MAX_ZIP_ENTRIES", 3
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(4):
            zf.writestr(f"file_{i}.txt", b"x")
    result = _preflight_file("many.zip", buf.getvalue(), "application/zip")
    struct_check = next(c for c in result.checks if c.name == "ZIP_STRUCTURE")
    assert not struct_check.passed
    assert result.status == FileStatus.FAIL


def test_r1_04_is_ooxml_entry_limit(monkeypatch):
    """R1-04: _is_ooxml에서도 항목 수 초과 시 False."""
    monkeypatch.setattr(
        "services.onboarding_digitization.intake_svc._MAX_ZIP_ENTRIES", 3
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "<wb/>")
        zf.writestr("a.xml", "")
        zf.writestr("b.xml", "")  # total 4 > 3
    assert _is_ooxml(buf.getvalue()) is False


# ── R1-05: 감사 추적 source_id 정합성 ─────────────────────────────────────────────

def test_r1_05_source_id_passed_through():
    """R1-05: 호출자가 source_id를 사전 제공하면 bundle·report 모두 동일 ID 사용."""
    async def _run():
        csv_data = b"item,qty\nA,10\n"
        upload = _make_upload_file("items.csv", csv_data, "text/csv")
        supabase = _make_supabase_mock(company_exists=True)
        pre_generated_id = "test-source-id-r1-05"

        bundle, report, _ = await run_intake_preflight(
            company_id="company-001",
            actor_id="admin-001",
            upload_files=[upload],
            supabase=supabase,
            source_id=pre_generated_id,
        )

        assert bundle.source_id == pre_generated_id
        assert report.source_id == pre_generated_id

    asyncio.run(_run())


# ── R1-06: HTTP 수준 통합 테스트 (TestClient) ──────────────────────────────────────

# ── R2-01: DB 접근 전 게이트 차단 순서 ────────────────────────────────────────────

def test_r2_01_gate_blocks_before_db_error(monkeypatch):
    """R2-01: 게이트 미활성 시 get_supabase() 오류보다 503이 우선."""
    monkeypatch.delenv("DIGITIZATION_SYNTHETIC_ENABLED", raising=False)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(dig_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}

    # get_supabase가 RuntimeError를 던져도 503이 먼저 나와야 함
    with patch("routers.onboarding_digitization.get_supabase",
               side_effect=RuntimeError("DB 연결 오류")):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake",
            files=[("files", ("data.csv", b"name\n", "text/csv"))],
        )

    assert resp.status_code == 503, f"Expected 503 from gate, got {resp.status_code}"
    assert "비활성" in resp.json().get("detail", "")


def test_r2_01_gate_passes_db_called(monkeypatch):
    """R2-01: 게이트 활성 시 get_supabase()가 정상 호출되어야 함."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(dig_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}

    db_called = {"called": False}
    def mock_get_supabase():
        db_called["called"] = True
        return _make_supabase_mock(company_exists=True)

    with (
        patch("routers.onboarding_digitization.get_supabase", side_effect=mock_get_supabase),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake",
            files=[("files", ("data.csv", b"name\n", "text/csv"))],
        )

    assert db_called["called"], "get_supabase()는 게이트 통과 후 호출되어야 함"


def test_r2_saas_core_conditional_registration(monkeypatch):
    """R2-01: saas_core ROUTERS에 digitization 라우터는 env 활성 시에만 포함."""
    import importlib

    # 비활성 환경
    monkeypatch.delenv("DIGITIZATION_SYNTHETIC_ENABLED", raising=False)
    import router_registry.saas_core as sc
    importlib.reload(sc)
    modules_off = [r["module"] for r in sc.ROUTERS]
    assert "routers.onboarding_digitization" not in modules_off

    # 활성 환경
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")
    importlib.reload(sc)
    modules_on = [r["module"] for r in sc.ROUTERS]
    assert "routers.onboarding_digitization" in modules_on


def test_r1_06_http_integration_csv_pass(monkeypatch):
    """R1-06: TestClient로 인증·파일·감사가 연결된 실제 요청 경로 검증."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(dig_router.router)

    # FastAPI dependency override — get_current_user를 mock으로 교체
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}

    supabase_mock = _make_supabase_mock(company_exists=True)

    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=supabase_mock),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id-http-001"),
    ):
        client = TestClient(app)
        csv_bytes = b"name,value\nrow1,100\n"
        resp = client.post(
            "/admin/companies/company-001/digitization/intake",
            files=[("files", ("data.csv", csv_bytes, "text/csv"))],
        )

    assert resp.status_code == 200, f"Unexpected status: {resp.status_code}, body: {resp.text}"
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["preflight"]["overall_status"] == "PASS"
    assert body["data"]["bundle"]["source_id"] is not None
