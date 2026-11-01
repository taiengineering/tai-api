"""WO-036 OBJ01 [5] Map 검증.

테스트 범위:
  M01 — ParsedDocument.columns: CSV parse 후 columns 필드 채워짐
  M02 — run_map() CSV → MappingStatus.MAPPED, columns/records 정확
  M03 — run_map() XLSX 2시트 → MappedDocument 2개
  M04 — run_map() BLOCKED 파일 → MappingStatus.BLOCKED
  M05 — run_map() ERROR 파일 → MappingStatus.ERROR
  M06 — column 수 == record 셀 수 (각 행)
  M07 — row 순서 MappedDocument에서 보존
  M08 — HTTP include_map=true → mapped + triage + parsed 모두 포함
  M09 — HTTP include_parse=true only → mapped absent
  M10 — HTTP include_map=true, CSV → MappedFileResult status=MAPPED
  M11 — HTTP include_map=true, PDF → MappedFileResult status=BLOCKED
  M12 — Mixed CSV+PDF → CSV=MAPPED, PDF=BLOCKED

WO-036-R1-REVISED: 문서 제목·헤더 추출
  R1-T01 — CSV → title_info.title_status=NOT_FOUND, candidates 없음
  R1-T02 — CSV → title_info.column_headers == parsed columns
  R1-T03 — XLSX 표준 헤더(복수 셀) → title_status=NOT_FOUND (제목 생성 금지)
  R1-T04 — XLSX 단독 셀 첫 행 → CANDIDATE, source location 정확
  R1-T05 — XLSX 2시트 → 각 시트 독립 title_info (sheet_name 구분)
  R1-T06 — 파일명 ≠ title_info 내 candidates (파일명 자동 승격 금지)
  R1-T07 — 행 0·행 1 둘 다 단독 셀 → candidates 2개, 원본 위치 각각 보존
  R1-T08 — 동일 파일명 복수 업로드 → title 혼동 없음 (file_key 구분)
  R1-T09 — title_info 추가로 MappedDocument.records 손실 없음
  R1-T10 — HTTP include_map=true → title_info 응답 포함
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from services.onboarding_digitization.models import (
    FileStatus,
    MappingStatus,
    ParseStatus,
    PreflightResult,
    CheckDetail,
    TitleStatus,
)
from services.onboarding_digitization.triage_svc import run_triage
from services.onboarding_digitization.parse_svc import run_parse
from services.onboarding_digitization.map_svc import run_map


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _make_preflight_result(filename: str, status: FileStatus) -> PreflightResult:
    return PreflightResult(
        filename=filename,
        status=status,
        checks=[CheckDetail(name="STUB", passed=status == FileStatus.PASS, detail="stub")],
    )


def _make_supabase_mock() -> MagicMock:
    sb = MagicMock()
    tbl = MagicMock()
    sb.table.return_value = tbl
    tbl.select.return_value = tbl
    tbl.eq.return_value = tbl
    tbl.limit.return_value = tbl
    tbl.execute.return_value = MagicMock(data=[{"id": "company-001"}])
    return sb


def _make_http_app(monkeypatch):
    monkeypatch.setenv("DIGITIZATION_SYNTHETIC_ENABLED", "true")
    import routers.onboarding_digitization as dig_router
    from routers.auth import get_current_user
    app = FastAPI()
    app.include_router(dig_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-001", "role_code": "001"}
    return app


def _parse_pipeline(filenames_data: dict[str, bytes]) -> "ParseReport":
    """filename → bytes 딕셔너리로 parse까지 실행하는 헬퍼."""
    preflight_results = [
        _make_preflight_result(fn, FileStatus.PASS) for fn in filenames_data
    ]
    triage = run_triage(source_id="src-test", preflight_results=preflight_results)
    return run_parse(
        source_id="src-test",
        file_bytes_dict=filenames_data,
        triage_report=triage,
    )


def _make_xlsx_bytes(sheets: list[tuple[str, list[list]]]) -> bytes:
    """sheets = [(sheet_name, [[header...], [row...], ...])]"""
    import openpyxl
    wb = openpyxl.Workbook()
    for i, (sheet_name, rows) in enumerate(sheets):
        if i == 0:
            ws = wb.active
            ws.title = sheet_name
        else:
            ws = wb.create_sheet(sheet_name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── M01: ParsedDocument.columns CSV parse 후 채워짐 ──────────────────────────

def test_m01_csv_parsed_document_has_columns():
    """M01: CSV parse 후 ParsedDocument.columns에 헤더 열명이 채워짐 (WO-036 보정)."""
    csv_bytes = b"name,age,city\nAlice,30,Seoul\nBob,25,Busan\n"
    parse_result = _parse_pipeline({"data.csv": csv_bytes})
    fr = parse_result.file_results[0]
    assert fr.status == ParseStatus.OK
    assert fr.document is not None
    assert fr.document.columns == ["name", "age", "city"], (
        f"columns 필드 미채움: {fr.document.columns}"
    )
    # csv_rows에는 헤더 행 없음
    assert fr.document.csv_rows[0] == ["Alice", "30", "Seoul"]


# ── M02: run_map() CSV → MappingStatus.MAPPED ────────────────────────────────

def test_m02_run_map_csv_mapped():
    """M02: CSV parse 후 run_map() → MappingStatus.MAPPED, columns/records 정확."""
    csv_bytes = b"item,qty\nA,10\nB,20\n"
    parse_result = _parse_pipeline({"items.csv": csv_bytes})
    mapping = run_map(source_id="src-m02", parse_report=parse_result)

    assert len(mapping.file_results) == 1
    mfr = mapping.file_results[0]
    assert mfr.status == MappingStatus.MAPPED
    assert mfr.documents is not None
    assert len(mfr.documents) == 1

    doc = mfr.documents[0]
    assert doc.sub_type == "csv"
    assert doc.columns == ["item", "qty"]
    assert doc.total_rows == 2
    assert doc.records == [["A", "10"], ["B", "20"]]


# ── M03: run_map() XLSX 2시트 → MappedDocument 2개 ───────────────────────────

def test_m03_run_map_xlsx_two_sheets():
    """M03: XLSX 2시트 → MappedFileResult 1개, MappedDocument 2개."""
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [["X", "Y"], ["r0", "r1"]]),
        ("Sheet2", [["A", "B", "C"], ["s0", "s1", "s2"]]),
    ])
    parse_result = _parse_pipeline({"report.xlsx": xlsx_bytes})
    mapping = run_map(source_id="src-m03", parse_report=parse_result)

    mfr = mapping.file_results[0]
    assert mfr.status == MappingStatus.MAPPED
    assert mfr.documents is not None
    assert len(mfr.documents) == 2

    doc1 = next(d for d in mfr.documents if d.sheet_name == "Sheet1")
    doc2 = next(d for d in mfr.documents if d.sheet_name == "Sheet2")

    assert doc1.columns == ["X", "Y"]
    assert doc1.records == [["r0", "r1"]]
    assert doc2.columns == ["A", "B", "C"]
    assert doc2.records == [["s0", "s1", "s2"]]


# ── M04: run_map() BLOCKED 파일 → MappingStatus.BLOCKED ─────────────────────

def test_m04_run_map_pdf_blocked():
    """M04: PDF (parse_eligible=False) → MappingStatus.BLOCKED."""
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    parse_result = _parse_pipeline({"manual.pdf": pdf_bytes})
    mapping = run_map(source_id="src-m04", parse_report=parse_result)

    mfr = mapping.file_results[0]
    assert mfr.status == MappingStatus.BLOCKED
    assert mfr.documents is None


# ── M05: run_map() ERROR 파일 → MappingStatus.ERROR ─────────────────────────

def test_m05_run_map_parse_error_propagated():
    """M05: Parse ERROR (손상 XLSX) → MappingStatus.ERROR."""
    broken_xlsx = b"not-an-xlsx"
    parse_result = _parse_pipeline({"bad.xlsx": broken_xlsx})
    mapping = run_map(source_id="src-m05", parse_report=parse_result)

    mfr = mapping.file_results[0]
    assert mfr.status == MappingStatus.ERROR
    assert mfr.reason is not None


# ── M06: column 수 == record 셀 수 ───────────────────────────────────────────

def test_m06_column_count_matches_record_width():
    """M06: MappedDocument.columns 수와 records 각 행 셀 수가 일치."""
    csv_bytes = b"col1,col2,col3\nv1,v2,v3\nv4,v5,v6\n"
    parse_result = _parse_pipeline({"data.csv": csv_bytes})
    mapping = run_map(source_id="src-m06", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    col_count = len(doc.columns)
    for i, row in enumerate(doc.records):
        assert len(row) == col_count, (
            f"행 {i}: columns={col_count}, cells={len(row)}"
        )


# ── M07: row 순서 보존 ────────────────────────────────────────────────────────

def test_m07_row_order_preserved():
    """M07: MappedDocument.records 행 순서가 원본 파일과 동일."""
    rows = [f"R{i},V{i}" for i in range(10)]
    csv_bytes = ("col,val\n" + "\n".join(rows) + "\n").encode("utf-8")
    parse_result = _parse_pipeline({"ordered.csv": csv_bytes})
    mapping = run_map(source_id="src-m07", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    for i, record in enumerate(doc.records):
        assert record[0] == f"R{i}", f"순서 불일치: 인덱스 {i}, 값 {record[0]}"


# ── M08: HTTP include_map=true → mapped + triage + parsed 포함 ───────────────

def test_m08_http_include_map_returns_all(monkeypatch):
    """M08: include_map=true → mapped/triage/parsed 모두 응답에 포함."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    csv_bytes = b"item,qty\nA,10\n"
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[("files", ("items.csv", csv_bytes, "text/csv"))],
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data.get("triage") is not None, "triage 없음"
    assert data.get("parsed") is not None, "parsed 없음"
    assert data.get("mapped") is not None, "mapped 없음"


# ── M09: HTTP include_parse=true only → mapped absent ────────────────────────

def test_m09_http_include_parse_no_map(monkeypatch):
    """M09: include_parse=true, include_map 미전달 → mapped null."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_parse=true",
            files=[("files", ("data.csv", b"col\nval\n", "text/csv"))],
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data.get("triage") is not None
    assert data.get("parsed") is not None
    assert data.get("mapped") is None, "include_map 없는데 mapped 존재"


# ── M10: HTTP include_map=true, CSV → MAPPED ─────────────────────────────────

def test_m10_http_csv_mapped_result(monkeypatch):
    """M10: CSV 파일 → mapped.file_results[0].status == MAPPED."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    csv_bytes = b"name,age\nAlice,30\n"
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[("files", ("people.csv", csv_bytes, "text/csv"))],
        )

    assert resp.status_code == 200, resp.text
    mapped_results = resp.json()["data"]["mapped"]["file_results"]
    assert len(mapped_results) == 1
    assert mapped_results[0]["status"] == "MAPPED"
    docs = mapped_results[0]["documents"]
    assert docs is not None and len(docs) == 1
    assert docs[0]["columns"] == ["name", "age"]


# ── M11: HTTP include_map=true, PDF → BLOCKED ────────────────────────────────

def test_m11_http_pdf_mapped_blocked(monkeypatch):
    """M11: PDF 파일 → mapped.file_results[0].status == BLOCKED."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[("files", ("manual.pdf", pdf_bytes, "application/pdf"))],
        )

    assert resp.status_code == 200, resp.text
    mapped_results = resp.json()["data"]["mapped"]["file_results"]
    assert mapped_results[0]["status"] == "BLOCKED"
    assert mapped_results[0].get("documents") is None


# ── M12: Mixed CSV+PDF → CSV=MAPPED, PDF=BLOCKED ─────────────────────────────

def test_m12_mixed_csv_pdf(monkeypatch):
    """M12: CSV+PDF 혼합 → 각각 MAPPED/BLOCKED 독립 결과."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    csv_bytes = b"col\nval\n"
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[
                ("files", ("data.csv", csv_bytes, "text/csv")),
                ("files", ("report.pdf", pdf_bytes, "application/pdf")),
            ],
        )

    assert resp.status_code == 200, resp.text
    mapped_results = resp.json()["data"]["mapped"]["file_results"]
    assert len(mapped_results) == 2

    by_name = {r["filename"]: r for r in mapped_results}
    assert by_name["data.csv"]["status"] == "MAPPED"
    assert by_name["report.pdf"]["status"] == "BLOCKED"


# ── WO-036-R1-REVISED: 문서 제목·헤더 추출 ────────────────────────────────────


# ── R1-T01: CSV → title_status=NOT_FOUND, candidates 없음 ─────────────────────

def test_r1_t01_csv_title_not_found():
    """R1-T01: CSV는 문서 제목 추출 대상 아님 → title_status=NOT_FOUND, candidates=[]."""
    csv_bytes = b"name,age\nAlice,30\n"
    parse_result = _parse_pipeline({"data.csv": csv_bytes})
    mapping = run_map(source_id="src-r1t01", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    assert doc.title_info is not None
    assert doc.title_info.title_status == TitleStatus.NOT_FOUND
    assert doc.title_info.candidates == []


# ── R1-T02: CSV → title_info.column_headers == parsed columns ────────────────

def test_r1_t02_csv_column_headers_preserved():
    """R1-T02: CSV title_info.column_headers가 parse에서 추출한 컬럼명과 동일."""
    csv_bytes = b"item,qty,price\nA,10,500\n"
    parse_result = _parse_pipeline({"items.csv": csv_bytes})
    mapping = run_map(source_id="src-r1t02", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    assert doc.title_info is not None
    assert doc.title_info.column_headers == ["item", "qty", "price"]
    assert doc.title_info.filename == "items.csv"
    assert doc.title_info.sheet_name == ""


# ── R1-T03: XLSX 표준 헤더(복수 셀) → title_status=NOT_FOUND ─────────────────

def test_r1_t03_xlsx_standard_header_no_title():
    """R1-T03: XLSX 첫 행이 여러 열 제목 → 제목 후보 없음, NOT_FOUND (제목 생성 금지)."""
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [["물질명", "보관량", "보관장소"], ["A", "10", "창고1"]]),
    ])
    parse_result = _parse_pipeline({"register.xlsx": xlsx_bytes})
    mapping = run_map(source_id="src-r1t03", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    assert doc.title_info is not None
    assert doc.title_info.title_status == TitleStatus.NOT_FOUND
    assert doc.title_info.candidates == []


# ── R1-T04: XLSX 단독 셀 첫 행 → CANDIDATE, source location 정확 ──────────────

def test_r1_t04_xlsx_single_cell_title_candidate():
    """R1-T04: XLSX 첫 행이 단독 셀 → CANDIDATE, 원본 위치(row=0, col, value) 정확."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "관리현황"
    ws.append(["유해화학물질 관리대장"])  # 단독 셀 — 제목 후보
    ws.append(["물질명", "보관량", "보관장소"])  # 실제 헤더 (parse는 이것도 data row로 읽음)
    ws.append(["A", "10", "창고1"])
    buf = io.BytesIO()
    wb.save(buf)

    parse_result = _parse_pipeline({"register.xlsx": buf.getvalue()})
    mapping = run_map(source_id="src-r1t04", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    assert doc.title_info is not None
    assert doc.title_info.title_status == TitleStatus.CANDIDATE
    assert len(doc.title_info.candidates) >= 1

    cand = doc.title_info.candidates[0]
    assert cand.value == "유해화학물질 관리대장"
    assert cand.status == TitleStatus.CANDIDATE
    assert cand.source.row_index == 0
    assert cand.source.sheet_name == "관리현황"
    assert cand.source.cell_value == "유해화학물질 관리대장"
    assert cand.basis != ""


# ── R1-T05: XLSX 2시트 → 각 시트 독립 title_info ─────────────────────────────

def test_r1_t05_xlsx_two_sheets_independent_title_info():
    """R1-T05: XLSX 2시트 → 각각 독립 title_info (sheet_name 구분, 혼동 없음)."""
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [["Sheet1 타이틀"], ["col1", "col2"]]),
        ("Sheet2", [["A", "B", "C"], ["v1", "v2", "v3"]]),
    ])
    parse_result = _parse_pipeline({"multi.xlsx": xlsx_bytes})
    mapping = run_map(source_id="src-r1t05", parse_report=parse_result)

    docs = mapping.file_results[0].documents
    assert len(docs) == 2

    doc_s1 = next(d for d in docs if d.sheet_name == "Sheet1")
    doc_s2 = next(d for d in docs if d.sheet_name == "Sheet2")

    # Sheet1: 단독 셀 → CANDIDATE
    assert doc_s1.title_info is not None
    assert doc_s1.title_info.title_status == TitleStatus.CANDIDATE
    assert doc_s1.title_info.sheet_name == "Sheet1"
    assert doc_s1.title_info.candidates[0].source.sheet_name == "Sheet1"

    # Sheet2: 3개 셀 헤더 → NOT_FOUND
    assert doc_s2.title_info is not None
    assert doc_s2.title_info.title_status == TitleStatus.NOT_FOUND
    assert doc_s2.title_info.sheet_name == "Sheet2"


# ── R1-T06: 파일명 ≠ title candidates (파일명 자동 승격 금지) ─────────────────

def test_r1_t06_filename_not_promoted_as_title():
    """R1-T06: 파일명이 title_info.candidates에 자동으로 들어가면 안 됨."""
    csv_bytes = b"col\nval\n"
    parse_result = _parse_pipeline({"유해화학물질_관리대장.csv": csv_bytes})
    mapping = run_map(source_id="src-r1t06", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    ti = doc.title_info
    assert ti is not None
    assert ti.title_status == TitleStatus.NOT_FOUND
    # 파일명이 candidates에 없어야 함
    candidate_values = [c.value for c in ti.candidates]
    assert "유해화학물질_관리대장.csv" not in candidate_values
    assert "유해화학물질_관리대장" not in candidate_values


# ── R1-T07: 행 0·행 1 둘 다 단독 셀 → candidates 2개, 위치 각각 ─────────────

def test_r1_t07_multiple_candidates_positions_preserved():
    """R1-T07: 행 0과 행 1 모두 단독 셀 → candidates 2개, 원본 위치 각각 보존."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append(["문서 부제목"])   # row 0 (parse → columns)
    ws.append(["문서 메인제목"]) # row 1 (parse → data rows[0])
    ws.append(["col1", "col2"]) # row 2 (parse → data rows[1])
    buf = io.BytesIO()
    wb.save(buf)

    parse_result = _parse_pipeline({"doc.xlsx": buf.getvalue()})
    mapping = run_map(source_id="src-r1t07", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    ti = doc.title_info
    assert ti is not None
    assert len(ti.candidates) == 2

    row0_cand = next(c for c in ti.candidates if c.source.row_index == 0)
    row1_cand = next(c for c in ti.candidates if c.source.row_index == 1)

    assert row0_cand.value == "문서 부제목"
    assert row1_cand.value == "문서 메인제목"
    assert row0_cand.source.row_index == 0
    assert row1_cand.source.row_index == 1


# ── R1-T08: 동일 파일명 복수 업로드 → title 혼동 없음 ──────────────────────────

def test_r1_t08_duplicate_filename_title_no_confusion(monkeypatch):
    """R1-T08: 동일 파일명·다른 내용 업로드 → 각 MappedDocument title_info 독립."""
    import openpyxl, io as _io
    def _make_xlsx(title: str) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([title])
        ws.append(["col"])
        ws.append(["val"])
        buf = _io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[
                ("files", ("report.xlsx", _make_xlsx("제목A"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("files", ("report.xlsx", _make_xlsx("제목B"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )

    assert resp.status_code == 200, resp.text
    mapped_results = resp.json()["data"]["mapped"]["file_results"]
    assert len(mapped_results) == 2

    titles = []
    for mfr in mapped_results:
        if mfr["status"] == "MAPPED" and mfr.get("documents"):
            for doc in mfr["documents"]:
                if doc.get("title_info") and doc["title_info"].get("candidates"):
                    titles.append(doc["title_info"]["candidates"][0]["value"])

    assert "제목A" in titles and "제목B" in titles, f"제목 혼동 발생: {titles}"
    assert titles[0] != titles[1], "두 파일의 title이 같으면 안 됨"


# ── R1-T09: title_info 추가로 records 손실 없음 ──────────────────────────────

def test_r1_t09_records_unchanged_after_title_extraction():
    """R1-T09: title_info 추가로 MappedDocument.records 행 데이터 손실/변경 없음."""
    csv_bytes = b"a,b\nR0C0,R0C1\nR1C0,R1C1\nR2C0,R2C1\n"
    parse_result = _parse_pipeline({"data.csv": csv_bytes})
    mapping = run_map(source_id="src-r1t09", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    assert len(doc.records) == 3
    assert doc.records[0] == ["R0C0", "R0C1"]
    assert doc.records[1] == ["R1C0", "R1C1"]
    assert doc.records[2] == ["R2C0", "R2C1"]
    # title_info도 존재
    assert doc.title_info is not None


# ── R1-T10: HTTP include_map=true → title_info 응답 포함 ─────────────────────

def test_r1_t10_http_title_info_in_response(monkeypatch):
    """R1-T10: HTTP include_map=true → mapped documents에 title_info 포함."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    csv_bytes = b"col1,col2\nv1,v2\n"
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[("files", ("data.csv", csv_bytes, "text/csv"))],
        )

    assert resp.status_code == 200, resp.text
    mapped_results = resp.json()["data"]["mapped"]["file_results"]
    doc = mapped_results[0]["documents"][0]

    ti = doc.get("title_info")
    assert ti is not None, "title_info 없음 — R1-REVISED 미적용"
    assert "title_status" in ti
    assert "candidates" in ti
    assert "column_headers" in ti
    assert ti["title_status"] == "NOT_FOUND"  # CSV → NOT_FOUND
    assert ti["column_headers"] == ["col1", "col2"]


# ── WO-036-R2: 제목·열 제목 구분 정확화 ──────────────────────────────────────


# ── R2-T01: 행 0=제목(단독 셀), 행 1=열 제목(복수 셀) → column_headers=행 1 ──

def test_r2_t01_title_row0_headers_row1():
    """R2-T01: 행 0 단독 셀 + 행 1 복수 셀 → column_headers=행 1, row_index=1."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "관리현황"
    ws.append(["유해화학물질 관리대장"])          # 행 0 — 제목 후보
    ws.append(["물질명", "보관량", "보관장소"])   # 행 1 — 실제 열 제목
    ws.append(["톨루엔", "100", "창고A"])         # 행 2 — 데이터
    buf = io.BytesIO()
    wb.save(buf)

    parse_result = _parse_pipeline({"register.xlsx": buf.getvalue()})
    mapping = run_map(source_id="src-r2t01", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    ti = doc.title_info
    assert ti is not None
    assert ti.title_status == TitleStatus.CANDIDATE
    assert ti.candidates[0].value == "유해화학물질 관리대장"

    # 핵심: 열 제목은 행 0이 아닌 행 1 내용
    assert ti.column_headers == ["물질명", "보관량", "보관장소"], (
        f"열 제목 오류: {ti.column_headers!r} (제목 행이 열 제목으로 표시됨)"
    )
    assert ti.column_header_row_index == 1, (
        f"column_header_row_index={ti.column_header_row_index}, 1이어야 함"
    )


# ── R2-T02: 행 0=정상 헤더(복수 셀) → column_headers=행 0, row_index=0 ────────

def test_r2_t02_normal_header_row0():
    """R2-T02: 표준 다중 열 헤더 → column_headers=행 0, row_index=0 (기존 동작 유지)."""
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [["물질명", "보관량", "보관장소"], ["톨루엔", "100", "창고A"]]),
    ])
    parse_result = _parse_pipeline({"normal.xlsx": xlsx_bytes})
    mapping = run_map(source_id="src-r2t02", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    ti = doc.title_info
    assert ti is not None
    assert ti.title_status == TitleStatus.NOT_FOUND
    assert ti.column_headers == ["물질명", "보관량", "보관장소"]
    assert ti.column_header_row_index == 0


# ── R2-T03: 행 0·행 1 모두 단독 셀 → 행 1을 열 제목으로 오인하지 않음 ──────────

def test_r2_t03_both_rows_single_cell_headers_stay_row0():
    """R2-T03: 행 0·행 1 둘 다 단독 셀 → 행 1은 열 제목 후보 아님, column_headers=행 0."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["제목1"])    # 행 0 — 단독 셀
    ws.append(["제목2"])    # 행 1 — 단독 셀 (≥2 셀 아님)
    ws.append(["col1", "col2"])
    buf = io.BytesIO()
    wb.save(buf)

    parse_result = _parse_pipeline({"ambiguous.xlsx": buf.getvalue()})
    mapping = run_map(source_id="src-r2t03", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]
    ti = doc.title_info
    assert ti is not None
    # 후보 2개 (행 0·1 모두 단독 셀)
    assert len(ti.candidates) == 2
    # 행 1이 단독 셀이므로 실제 열 제목으로 승격되지 않음 → row_index=0 유지
    assert ti.column_header_row_index == 0, (
        f"단독 셀 행 1이 열 제목으로 잘못 승격됨 (row_index={ti.column_header_row_index})"
    )


# ── R2-T04: 열 제목 구분 후에도 원본 records 보존 ──────────────────────────────

def test_r2_t04_records_preserved_with_r2_fix():
    """R2-T04: R2 보정 후에도 MappedDocument.records 전체 데이터 손실 없음."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["문서 제목"])            # 행 0
    ws.append(["A", "B", "C"])        # 행 1 (실제 헤더)
    ws.append(["r0c0", "r0c1", "r0c2"])  # 행 2 (데이터)
    ws.append(["r1c0", "r1c1", "r1c2"])  # 행 3 (데이터)
    buf = io.BytesIO()
    wb.save(buf)

    parse_result = _parse_pipeline({"data.xlsx": buf.getvalue()})
    mapping = run_map(source_id="src-r2t04", parse_report=parse_result)

    doc = mapping.file_results[0].documents[0]

    # title_info: 열 제목 = 행 1 내용
    assert doc.title_info.column_headers == ["A", "B", "C"]
    assert doc.title_info.column_header_row_index == 1

    # MappedDocument.columns: parse 원본 그대로 (첫 행)
    # records: parse가 헤더 이후 행 → rows[0]=행 1(헤더로 보임), rows[1]=행 2, rows[2]=행 3
    # 전체 행 수 보존 (parse rows = 3행: 헤더/데이터2)
    assert doc.total_rows == 3  # parse row count: row1 + row2 + row3
    assert len(doc.records) == 3


# ── R2-T05: HTTP 통합 — title/column_headers 응답 정합성 ─────────────────────

def test_r2_t05_http_column_headers_distinction(monkeypatch):
    """R2-T05: HTTP include_map=true, 제목행+헤더행 구조 → 응답의 column_headers가 올바름."""
    import openpyxl, io as _io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["유해화학물질 관리대장"])
    ws.append(["물질명", "보관량", "보관장소"])
    ws.append(["톨루엔", "100", "창고A"])
    buf = _io.BytesIO()
    wb.save(buf)

    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_map=true",
            files=[("files", ("register.xlsx", buf.getvalue(),
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        )

    assert resp.status_code == 200, resp.text
    mfr = resp.json()["data"]["mapped"]["file_results"][0]
    doc = mfr["documents"][0]
    ti = doc["title_info"]

    assert ti["candidates"][0]["value"] == "유해화학물질 관리대장"
    assert ti["column_headers"] == ["물질명", "보관량", "보관장소"], (
        f"응답의 column_headers 오류: {ti['column_headers']}"
    )
    assert ti["column_header_row_index"] == 1
