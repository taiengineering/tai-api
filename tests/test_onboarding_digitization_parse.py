"""WO-035 OBJ01 [3] Triage + [4] Parse 검증.

테스트 범위:
  T01 — run_triage() CSV PASS → parse_eligible=True, SPREADSHEET
  T02 — run_triage() XLSX PASS → parse_eligible=True, SPREADSHEET
  T03 — run_triage() PDF PASS → parse_eligible=False (PDF_PARSE_BLOCKED)
  T04 — run_triage() ZIP BLOCKED → parse_eligible=False (PREFLIGHT_BLOCKED)
  T05 — run_parse() CSV → ParseStatus.OK, preview 정확
  T06 — run_parse() XLSX → ParseStatus.OK, sheets 포함
  T07 — run_parse() PDF → ParseStatus.BLOCKED
  T08 — run_parse() max_preview_rows 제한 준수
  T09 — run_triage() XLSX FAIL → parse_eligible=False
  T10 — HTTP include_parse 미전달 → triage/parsed null
  T11 — HTTP include_parse=true → triage+parsed 포함
  T12 — CSV EUC-KR → run_parse() ParseStatus.OK
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from services.onboarding_digitization.models import (
    FileStatus,
    ParseStatus,
    PreflightResult,
    CheckDetail,
    TriageCategory,
    TriageReport,
)
from services.onboarding_digitization.triage_svc import run_triage
from services.onboarding_digitization.parse_svc import run_parse


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _make_preflight_result(filename: str, status: FileStatus) -> PreflightResult:
    return PreflightResult(
        filename=filename,
        status=status,
        checks=[CheckDetail(name="STUB", passed=status == FileStatus.PASS, detail="stub")],
    )


def _make_xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


def _make_supabase_mock(company_exists: bool = True) -> MagicMock:
    sb = MagicMock()
    tbl = MagicMock()
    sb.table.return_value = tbl
    tbl.select.return_value = tbl
    tbl.eq.return_value = tbl
    tbl.limit.return_value = tbl
    tbl.execute.return_value = MagicMock(data=[{"id": "company-001"}] if company_exists else [])
    return sb


def _make_upload_file(filename: str, data: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    mock = MagicMock(spec=UploadFile)
    mock.filename = filename
    mock.content_type = content_type
    call_count = {"n": 0}

    async def _read(size: int = -1) -> bytes:
        if call_count["n"] == 0:
            call_count["n"] += 1
            return data
        return b""

    mock.read = _read
    return mock


# ── T01: CSV PASS → parse_eligible=True ──────────────────────────────────────

def test_t01_triage_csv_pass_eligible():
    """T01: CSV Preflight PASS → parse_eligible=True, category=SPREADSHEET."""
    pf = _make_preflight_result("data.csv", FileStatus.PASS)
    result = run_triage(source_id="src-001", preflight_results=[pf])
    assert len(result.file_results) == 1
    tr = result.file_results[0]
    assert tr.parse_eligible is True
    assert tr.category == TriageCategory.SPREADSHEET
    assert tr.sub_type == "csv"
    assert tr.ineligible_reason is None


# ── T02: XLSX PASS → parse_eligible=True ─────────────────────────────────────

def test_t02_triage_xlsx_pass_eligible():
    """T02: XLSX Preflight PASS → parse_eligible=True, category=SPREADSHEET."""
    pf = _make_preflight_result("report.xlsx", FileStatus.PASS)
    result = run_triage(source_id="src-002", preflight_results=[pf])
    tr = result.file_results[0]
    assert tr.parse_eligible is True
    assert tr.category == TriageCategory.SPREADSHEET
    assert tr.sub_type == "xlsx"


# ── T03: PDF PASS → parse_eligible=False (PDF_PARSE_BLOCKED) ─────────────────

def test_t03_triage_pdf_pass_not_eligible():
    """T03: PDF Preflight PASS이어도 parse_eligible=False (파서 미탑재)."""
    pf = _make_preflight_result("manual.pdf", FileStatus.PASS)
    result = run_triage(source_id="src-003", preflight_results=[pf])
    tr = result.file_results[0]
    assert tr.parse_eligible is False
    assert tr.category == TriageCategory.PDF_DOCUMENT
    assert "PDF_PARSE_BLOCKED" in (tr.ineligible_reason or "")


# ── T04: ZIP BLOCKED → parse_eligible=False ──────────────────────────────────

def test_t04_triage_zip_blocked_not_eligible():
    """T04: ZIP Preflight BLOCKED → PREFLIGHT_BLOCKED 사유로 parse_eligible=False."""
    pf = _make_preflight_result("archive.zip", FileStatus.BLOCKED)
    result = run_triage(source_id="src-004", preflight_results=[pf])
    tr = result.file_results[0]
    assert tr.parse_eligible is False
    assert tr.category == TriageCategory.ARCHIVE
    assert "PREFLIGHT_BLOCKED" in (tr.ineligible_reason or "")


# ── T05: run_parse() CSV → ParseStatus.OK ─────────────────────────────────────

def test_t05_parse_csv_ok():
    """T05: 정상 CSV → ParseStatus.OK, preview.columns/rows 정확."""
    csv_bytes = b"name,age\nAlice,30\nBob,25\n"
    pf = _make_preflight_result("data.csv", FileStatus.PASS)
    triage = run_triage(source_id="src-005", preflight_results=[pf])
    parse_result = run_parse(
        source_id="src-005",
        file_bytes_dict={"data.csv": csv_bytes},
        triage_report=triage,
    )
    assert len(parse_result.file_results) == 1
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.OK
    assert fr.preview is not None
    assert fr.preview.columns == ["name", "age"]
    assert fr.preview.rows == [["Alice", "30"], ["Bob", "25"]]
    assert fr.preview.total_rows == 2


# ── T06: run_parse() XLSX → ParseStatus.OK, sheets 포함 ─────────────────────

def test_t06_parse_xlsx_ok():
    """T06: 최소 XLSX → ParseStatus.OK, sheets 리스트 반환."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["품명", "수량"])
    ws.append(["부품A", 100])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    pf = _make_preflight_result("inventory.xlsx", FileStatus.PASS)
    triage = run_triage(source_id="src-006", preflight_results=[pf])
    parse_result = run_parse(
        source_id="src-006",
        file_bytes_dict={"inventory.xlsx": xlsx_bytes},
        triage_report=triage,
    )
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.OK
    assert fr.sheets is not None
    assert len(fr.sheets) == 1
    sheet = fr.sheets[0]
    assert sheet.sheet_name == "Sheet1"
    assert sheet.columns == ["품명", "수량"]
    assert sheet.rows[0] == ["부품A", "100"]
    assert sheet.total_rows == 1


# ── T07: run_parse() PDF → ParseStatus.BLOCKED ───────────────────────────────

def test_t07_parse_pdf_blocked():
    """T07: PDF (parse_eligible=False) → ParseStatus.BLOCKED."""
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    pf = _make_preflight_result("manual.pdf", FileStatus.PASS)
    triage = run_triage(source_id="src-007", preflight_results=[pf])
    parse_result = run_parse(
        source_id="src-007",
        file_bytes_dict={"manual.pdf": pdf_bytes},
        triage_report=triage,
    )
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.BLOCKED
    assert fr.reason is not None


# ── T08: max_preview_rows 제한 ───────────────────────────────────────────────

def test_t08_csv_max_preview_rows():
    """T08: max_preview_rows=2 → preview.rows 최대 2행, total_rows는 실제 행수."""
    lines = ["col1,col2"] + [f"row{i},val{i}" for i in range(5)]
    csv_bytes = "\n".join(lines).encode("utf-8")

    pf = _make_preflight_result("big.csv", FileStatus.PASS)
    triage = run_triage(source_id="src-008", preflight_results=[pf])
    parse_result = run_parse(
        source_id="src-008",
        file_bytes_dict={"big.csv": csv_bytes},
        triage_report=triage,
        max_preview_rows=2,
    )
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.OK
    assert fr.preview is not None
    assert len(fr.preview.rows) == 2  # 미리보기 2행
    assert fr.preview.total_rows == 5  # 실제 5행


def test_t08_xlsx_max_preview_rows():
    """T08: XLSX max_preview_rows=1 → rows 최대 1행, total_rows=3."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["A", "B"])
    for i in range(3):
        ws.append([f"r{i}", str(i)])
    buf = io.BytesIO()
    wb.save(buf)

    pf = _make_preflight_result("multi.xlsx", FileStatus.PASS)
    triage = run_triage(source_id="src-008b", preflight_results=[pf])
    parse_result = run_parse(
        source_id="src-008b",
        file_bytes_dict={"multi.xlsx": buf.getvalue()},
        triage_report=triage,
        max_preview_rows=1,
    )
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.OK
    sheet = fr.sheets[0]
    assert len(sheet.rows) == 1
    assert sheet.total_rows == 3


# ── T09: XLSX Preflight FAIL → parse_eligible=False ──────────────────────────

def test_t09_triage_xlsx_fail_not_eligible():
    """T09: XLSX Preflight FAIL → parse_eligible=False."""
    pf = _make_preflight_result("bad.xlsx", FileStatus.FAIL)
    result = run_triage(source_id="src-009", preflight_results=[pf])
    tr = result.file_results[0]
    assert tr.parse_eligible is False
    assert "PREFLIGHT_FAIL" in (tr.ineligible_reason or "")


# ── T10: HTTP include_parse 미전달 → triage/parsed null ──────────────────────

def test_t10_http_no_include_parse(monkeypatch):
    """T10: include_parse 쿼리 없이 요청 → triage, parsed null."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")

    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(dig_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}

    supabase_mock = _make_supabase_mock(company_exists=True)
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=supabase_mock),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake",
            files=[("files", ("data.csv", b"name\nAlice\n", "text/csv"))],
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data.get("triage") is None
    assert data.get("parsed") is None


# ── T11: HTTP include_parse=true → triage+parsed 포함 ────────────────────────

def test_t11_http_include_parse_true(monkeypatch):
    """T11: include_parse=true → triage.file_results + parsed.file_results 포함."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")

    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(dig_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}

    supabase_mock = _make_supabase_mock(company_exists=True)
    csv_bytes = b"item,qty\nA,10\nB,20\n"
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=supabase_mock),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_parse=true",
            files=[("files", ("items.csv", csv_bytes, "text/csv"))],
        )

    assert resp.status_code == 200, f"Unexpected: {resp.status_code} {resp.text}"
    data = resp.json()["data"]
    assert data.get("triage") is not None, "triage 없음"
    assert data.get("parsed") is not None, "parsed 없음"
    triage_results = data["triage"]["file_results"]
    assert len(triage_results) == 1
    assert triage_results[0]["parse_eligible"] is True
    parsed_results = data["parsed"]["file_results"]
    assert len(parsed_results) == 1
    assert parsed_results[0]["status"] == "OK"
    assert parsed_results[0]["preview"]["columns"] == ["item", "qty"]


# ── T12: CSV EUC-KR → run_parse() 정상 디코딩 ────────────────────────────────

def test_t12_parse_csv_euckr():
    """T12: EUC-KR CSV → ParseStatus.OK, 첫 행 컬럼 정상 디코딩."""
    csv_bytes = "이름,나이\n홍길동,30\n임꺽정,25\n".encode("euc-kr")
    pf = _make_preflight_result("kr.csv", FileStatus.PASS)
    triage = run_triage(source_id="src-012", preflight_results=[pf])
    parse_result = run_parse(
        source_id="src-012",
        file_bytes_dict={"kr.csv": csv_bytes},
        triage_report=triage,
    )
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.OK
    assert fr.preview is not None
    assert "이름" in fr.preview.columns
    assert fr.preview.rows[0][0] == "홍길동"


# ── WO-035 R1 보정 테스트 ──────────────────────────────────────────────────────


def _make_http_app(monkeypatch):
    """TestClient 앱 공용 팩토리."""
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")
    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user
    app = FastAPI()
    app.include_router(dig_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}
    return app


# ── R1-T01: 동일 파일명·다른 내용 → 각각 다른 파싱 결과 ──────────────────────

def test_r1_t01_duplicate_filename_different_content(monkeypatch):
    """R1-T01: 동일 파일명이지만 내용이 다른 파일 2개 → 각각 다른 파싱 결과."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock(company_exists=True)
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_parse=true",
            files=[
                ("files", ("data.csv", b"col\nFIRST\n", "text/csv")),
                ("files", ("data.csv", b"col\nSECOND\n", "text/csv")),
            ],
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # bundle: 2개 파일, 각각 다른 sha256
    bundle_files = data["bundle"]["files"]
    assert len(bundle_files) == 2
    assert bundle_files[0]["sha256"] != bundle_files[1]["sha256"]
    assert bundle_files[0]["file_key"] != bundle_files[1]["file_key"]

    # parsed: 두 결과가 다른 내용
    parsed = data["parsed"]["file_results"]
    assert len(parsed) == 2
    rows_0 = parsed[0]["preview"]["rows"]
    rows_1 = parsed[1]["preview"]["rows"]
    assert rows_0 != rows_1, "동일 파일명·다른 내용인데 파싱 결과가 같음 (R1-01 미수정)"
    # 첫 번째 파일에서 FIRST, 두 번째에서 SECOND
    values = {rows_0[0][0], rows_1[0][0]}
    assert "FIRST" in values and "SECOND" in values


# ── R1-T02: 동일 파일명·동일 내용 → 각각 별도 입력 파일로 유지 ─────────────

def test_r1_t02_duplicate_filename_same_content(monkeypatch):
    """R1-T02: 동일 파일명·동일 내용 2개 → 각각 독립 파일로 처리."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock(company_exists=True)
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_parse=true",
            files=[
                ("files", ("same.csv", b"col\nSAME\n", "text/csv")),
                ("files", ("same.csv", b"col\nSAME\n", "text/csv")),
            ],
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # bundle: 2개 항목 (동일 sha이지만 별도 입력)
    assert len(data["bundle"]["files"]) == 2
    keys = [f["file_key"] for f in data["bundle"]["files"]]
    assert keys[0] != keys[1], "동일 내용이어도 file_key는 달라야 함 (index 다름)"

    # parsed: 2개 결과
    assert len(data["parsed"]["file_results"]) == 2


# ── R1-T03: 150행 CSV → document에 150행, preview에 100행 ─────────────────────

def test_r1_t03_csv_full_data_vs_preview():
    """R1-T03: 150행 CSV — preview.rows 100행, document.csv_rows 150행."""
    lines = ["col1,col2"] + [f"row{i},val{i}" for i in range(150)]
    csv_bytes = "\n".join(lines).encode("utf-8")

    pf = _make_preflight_result("big.csv", FileStatus.PASS)
    triage = run_triage(source_id="src-r1t03", preflight_results=[pf])
    result = run_parse(
        source_id="src-r1t03",
        file_bytes_dict={"big.csv": csv_bytes},
        triage_report=triage,
        max_preview_rows=100,
    )
    fr = result.file_results[0]
    assert fr.status == ParseStatus.OK

    # 미리보기: 100행
    assert fr.preview is not None
    assert len(fr.preview.rows) == 100
    assert fr.preview.total_rows == 150

    # 전체 데이터: 150행
    assert fr.document is not None
    assert fr.document.csv_rows is not None
    assert len(fr.document.csv_rows) == 150
    assert fr.document.total_rows == 150


# ── R1-T04: CSV 원본 행 위치 유지 ────────────────────────────────────────────

def test_r1_t04_csv_row_position_preserved():
    """R1-T04: document.csv_rows의 인덱스가 원본 행 위치 보존."""
    csv_bytes = b"a,b\nR0C0,R0C1\nR1C0,R1C1\nR2C0,R2C1\n"
    pf = _make_preflight_result("pos.csv", FileStatus.PASS)
    triage = run_triage(source_id="src-r1t04", preflight_results=[pf])
    result = run_parse(
        source_id="src-r1t04",
        file_bytes_dict={"pos.csv": csv_bytes},
        triage_report=triage,
    )
    fr = result.file_results[0]
    assert fr.document is not None
    rows = fr.document.csv_rows
    assert rows[0] == ["R0C0", "R0C1"]  # row 2 (header=row 1)
    assert rows[1] == ["R1C0", "R1C1"]  # row 3
    assert rows[2] == ["R2C0", "R2C1"]  # row 4


# ── R1-T05: XLSX 시트·셀 위치 유지 ───────────────────────────────────────────

def test_r1_t05_xlsx_sheet_cell_position_preserved():
    """R1-T05: document.xlsx_sheets 순서와 셀 위치가 원본 보존."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Sheet1"
    ws1.append(["X", "Y"])
    ws1.append(["r0c0", "r0c1"])
    ws1.append(["r1c0", "r1c1"])
    ws2 = wb.create_sheet("Sheet2")
    ws2.append(["A", "B"])
    ws2.append(["s2r0c0", "s2r0c1"])
    buf = io.BytesIO()
    wb.save(buf)

    pf = _make_preflight_result("pos.xlsx", FileStatus.PASS)
    triage = run_triage(source_id="src-r1t05", preflight_results=[pf])
    result = run_parse(
        source_id="src-r1t05",
        file_bytes_dict={"pos.xlsx": buf.getvalue()},
        triage_report=triage,
    )
    fr = result.file_results[0]
    assert fr.document is not None
    sheets = fr.document.xlsx_sheets
    assert sheets[0].sheet_name == "Sheet1"
    assert sheets[0].rows[0] == ["r0c0", "r0c1"]
    assert sheets[0].rows[1] == ["r1c0", "r1c1"]
    assert sheets[1].sheet_name == "Sheet2"
    assert sheets[1].rows[0] == ["s2r0c0", "s2r0c1"]


# ── R1-T06: XLSX 수식 손실되지 않음 (R1-03) ──────────────────────────────────

def test_r1_t06_xlsx_formula_not_lost():
    """R1-T06: 수식 셀이 빈 문자열로 손실되지 않음 (data_only=False 보장)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Value", "Formula"])
    ws["A2"] = "Alice"
    ws["B2"] = 100
    ws["C2"] = "=B2*2"  # 수식 (캐시 없음)
    buf = io.BytesIO()
    wb.save(buf)

    pf = _make_preflight_result("formula.xlsx", FileStatus.PASS)
    triage = run_triage(source_id="src-r1t06", preflight_results=[pf])
    result = run_parse(
        source_id="src-r1t06",
        file_bytes_dict={"formula.xlsx": buf.getvalue()},
        triage_report=triage,
    )
    fr = result.file_results[0]
    assert fr.status == ParseStatus.OK
    formula_cell = fr.sheets[0].rows[0][2]  # C2 셀
    assert formula_cell != "", "수식 셀이 빈 문자열로 손실됨 (R1-03 미수정)"
    # 수식 문자열 또는 계산된 값이어야 함
    assert "=" in formula_cell or formula_cell != ""


# ── R1-T07: XLSX 처리 한도 초과 → ParseStatus.ERROR (R1-04) ─────────────────

def test_r1_t07_xlsx_row_limit_exceeded(monkeypatch):
    """R1-T07: XLSX 행 수가 _MAX_XLSX_ROWS 초과 → ParseStatus.ERROR."""
    from services.onboarding_digitization import parse_svc
    monkeypatch.setattr(parse_svc, "_MAX_XLSX_ROWS", 2)

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col"])
    for i in range(3):  # 3 data rows > limit 2
        ws.append([f"row{i}"])
    buf = io.BytesIO()
    wb.save(buf)

    pf = _make_preflight_result("limit.xlsx", FileStatus.PASS)
    triage = run_triage(source_id="src-r1t07", preflight_results=[pf])
    result = run_parse(
        source_id="src-r1t07",
        file_bytes_dict={"limit.xlsx": buf.getvalue()},
        triage_report=triage,
    )
    fr = result.file_results[0]
    assert fr.status == ParseStatus.ERROR, f"Expected ERROR, got {fr.status}"
    assert "LIMIT_EXCEEDED" in (fr.reason or ""), fr.reason


# ── R1-T08: include_parse=false → 기존 응답 호환, file_key 포함 ──────────────

def test_r1_t08_no_include_parse_backward_compat(monkeypatch):
    """R1-T08: include_parse 없는 요청도 bundle.files에 file_key 포함."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock(company_exists=True)
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake",
            files=[("files", ("data.csv", b"name\nAlice\n", "text/csv"))],
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    # triage/parsed는 null
    assert data.get("triage") is None
    assert data.get("parsed") is None
    # file_key는 설정됨
    file_key = data["bundle"]["files"][0]["file_key"]
    assert file_key != "", "file_key가 비어있음 — R1-01 미적용"
    assert ":" in file_key  # "{index}:{sha256}" 형식


# ── R1-T09: ZIP·PDF 기존 차단 유지 ──────────────────────────────────────────

def test_r1_t09_zip_pdf_still_blocked(monkeypatch):
    """R1-T09: R1 보정 후에도 ZIP(BLOCKED)·PDF(PDF_PARSE_BLOCKED) 차단 상태 유지."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock(company_exists=True)

    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("a.csv", b"x\n")
    zip_bytes = zip_buf.getvalue()

    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_parse=true",
            files=[
                ("files", ("report.pdf", pdf_bytes, "application/pdf")),
                ("files", ("archive.zip", zip_bytes, "application/zip")),
            ],
        )

    assert resp.status_code == 200, resp.text
    parsed = resp.json()["data"]["parsed"]["file_results"]

    pdf_result = next(r for r in parsed if r["filename"] == "report.pdf")
    zip_result = next(r for r in parsed if r["filename"] == "archive.zip")

    assert pdf_result["status"] == "BLOCKED", "PDF가 BLOCKED 아님"
    assert zip_result["status"] == "BLOCKED", "ZIP이 BLOCKED 아님"
