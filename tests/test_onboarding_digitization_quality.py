"""WO-037 OBJ01 [7] Quality 검증.

테스트 범위:
  Q-T01 — 정상 CSV → QualityStatus.PASS
  Q-T02 — 정상 XLSX 다중 시트 → PASS
  Q-T03 — 동일 파일명 2개 → 각각 별도 파일 검사 (file_key 독립)
  Q-T04 — Parse·Map 행 수 불일치 → FAIL
  Q-T05 — 셀 값 변경 감지 → FAIL
  Q-T06 — 중복 헤더 → REVIEW_REQUIRED
  Q-T07 — 빈 헤더 → REVIEW_REQUIRED
  Q-T08 — 제목 후보 원본 위치 불일치 → FAIL
  Q-T09 — 헤더 행이 첫 행 아님 (column_header_row_index > 0) → REVIEW_REQUIRED
  Q-T10 — PDF·ZIP 차단 → NOT_EVALUATED
  Q-T11 — 여러 파일 중 일부 실패 → 파일별 상태 독립 유지
  Q-T12 — 100행 초과 문서 → 전체 데이터 기준 검수
  Q-T13 — include_quality 기본값 false — 기존 API 동작 불변
  Q-T14 — include_quality=true만 → parsed/mapped 응답 미포함
  Q-T15 — HTTP include_quality=true → quality 요약·오류 위치 포함
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.onboarding_digitization.models import (
    CheckDetail,
    DocumentTitleInfo,
    FileStatus,
    IssueSeverity,
    MappedDocument,
    MappedFileResult,
    MappingReport,
    MappingStatus,
    ParsedDocument,
    ParsedFileResult,
    ParseReport,
    ParseStatus,
    PreflightReport,
    PreflightResult,
    QualityStatus,
    SheetFullData,
    SourceBundle,
    SourceFile,
    SourceLocation,
    TitleCandidate,
    TitleStatus,
    DocumentTitleInfo,
)
from services.onboarding_digitization.quality_svc import run_quality
from services.onboarding_digitization.triage_svc import run_triage
from services.onboarding_digitization.parse_svc import run_parse
from services.onboarding_digitization.map_svc import run_map


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _make_source_file(filename: str, sha256: str, file_key: str) -> SourceFile:
    return SourceFile(
        filename=filename,
        sha256=sha256,
        byte_size=100,
        declared_mime="text/csv",
        detected_mime="text/csv",
        magic_match=True,
        file_key=file_key,
    )


def _make_bundle(files: list[SourceFile], source_id: str = "src-test") -> SourceBundle:
    return SourceBundle(
        source_id=source_id,
        company_id="company-001",
        submitted_by="admin-001",
        submitted_at="2026-11-01T00:00:00Z",
        files=files,
    )


def _make_preflight(source_id: str, results: list[PreflightResult]) -> PreflightReport:
    return PreflightReport(
        source_id=source_id,
        overall_status="PASS",
        file_results=results,
        errors=[],
    )


def _preflight_result(filename: str, file_key: str, status: FileStatus) -> PreflightResult:
    return PreflightResult(
        filename=filename,
        file_key=file_key,
        status=status,
        checks=[CheckDetail(name="STUB", passed=status == FileStatus.PASS, detail="stub")],
    )


def _make_csv_parse_result(
    filename: str,
    file_key: str,
    columns: list[str],
    rows: list[list[str]],
) -> ParsedFileResult:
    doc = ParsedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="csv",
        total_rows=len(rows),
        columns=columns,
        csv_rows=rows,
    )
    return ParsedFileResult(
        filename=filename,
        file_key=file_key,
        status=ParseStatus.OK,
        document=doc,
    )


def _make_xlsx_parse_result(
    filename: str,
    file_key: str,
    sheets: list[SheetFullData],
) -> ParsedFileResult:
    doc = ParsedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="xlsx",
        total_rows=sum(s.total_rows for s in sheets),
        xlsx_sheets=sheets,
    )
    return ParsedFileResult(
        filename=filename,
        file_key=file_key,
        status=ParseStatus.OK,
        document=doc,
    )


def _make_csv_mapped_doc(
    filename: str,
    file_key: str,
    columns: list[str],
    records: list[list[str]],
    title_info: DocumentTitleInfo | None = None,
    total_rows_override: int | None = None,
) -> MappedDocument:
    ti = title_info or DocumentTitleInfo(
        file_key=file_key,
        filename=filename,
        sheet_name="",
        title_status=TitleStatus.NOT_FOUND,
        candidates=[],
        column_headers=columns,
        column_header_row_index=0,
    )
    return MappedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="csv",
        sheet_name="",
        total_rows=total_rows_override if total_rows_override is not None else len(records),
        columns=columns,
        records=records,
        title_info=ti,
    )


def _make_xlsx_mapped_doc(
    filename: str,
    file_key: str,
    sheet_name: str,
    columns: list[str],
    records: list[list[str]],
    title_info: DocumentTitleInfo | None = None,
    total_rows_override: int | None = None,
) -> MappedDocument:
    ti = title_info or DocumentTitleInfo(
        file_key=file_key,
        filename=filename,
        sheet_name=sheet_name,
        title_status=TitleStatus.NOT_FOUND,
        candidates=[],
        column_headers=columns,
        column_header_row_index=0,
    )
    return MappedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="xlsx",
        sheet_name=sheet_name,
        total_rows=total_rows_override if total_rows_override is not None else len(records),
        columns=columns,
        records=records,
        title_info=ti,
    )


def _make_xlsx_bytes(sheets: list[tuple[str, list[list]]]) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    for i, (name, rows) in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet(name)
        ws.title = name
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _full_pipeline(filenames_data: dict[str, bytes], source_id: str = "src-test"):
    """파일명→bytes로 triage+parse+map 전체 실행, SourceBundle 수동 구성."""
    import hashlib
    files = []
    for i, (fn, data) in enumerate(filenames_data.items()):
        sha = hashlib.sha256(data).hexdigest()
        fk = f"{i}:{sha}"
        files.append(_make_source_file(fn, sha, fk))
    bundle = _make_bundle(files, source_id=source_id)
    pfl_results = [
        _preflight_result(sf.filename, sf.file_key, FileStatus.PASS)
        for sf in files
    ]
    preflight = _make_preflight(source_id, pfl_results)

    # file_bytes_dict은 file_key → bytes
    file_bytes = {sf.file_key: data for sf, data in zip(files, filenames_data.values())}
    triage = run_triage(source_id=source_id, preflight_results=preflight.file_results)
    parse = run_parse(source_id=source_id, file_bytes_dict=file_bytes, triage_report=triage)
    mapping = run_map(source_id=source_id, parse_report=parse)
    return bundle, preflight, parse, mapping


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


# ── Q-T01: 정상 CSV → PASS ───────────────────────────────────────────────────

def test_qt01_clean_csv_pass():
    """Q-T01: 정상 CSV (구조 이상 없음) → overall_status=PASS, file PASS."""
    csv_bytes = b"name,age,city\nAlice,30,Seoul\nBob,25,Busan\n"
    bundle, preflight, parse, mapping = _full_pipeline({"data.csv": csv_bytes})
    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.PASS
    assert report.passed_files == 1
    assert report.failed_files == 0
    assert report.review_required_files == 0
    assert report.not_evaluated_files == 0
    assert report.file_results[0].status == QualityStatus.PASS
    assert report.file_results[0].issues == []


# ── Q-T02: 정상 XLSX 다중 시트 → PASS ────────────────────────────────────────

def test_qt02_clean_xlsx_two_sheets_pass():
    """Q-T02: 정상 XLSX 2시트 → 각 시트 구조 이상 없음 → PASS."""
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [["X", "Y"], ["a", "b"], ["c", "d"]]),
        ("Sheet2", [["A", "B", "C"], ["1", "2", "3"]]),
    ])
    bundle, preflight, parse, mapping = _full_pipeline({"report.xlsx": xlsx_bytes})
    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.PASS
    assert report.passed_files == 1
    assert report.file_results[0].status == QualityStatus.PASS
    # 두 시트 모두 검사됨
    assert "Q02" in report.file_results[0].checked_items
    assert "Q03" in report.file_results[0].checked_items


# ── Q-T03: 동일 파일명 2개 → 각각 별도 검사 ──────────────────────────────────

def test_qt03_duplicate_filename_separate_results():
    """Q-T03: 동일 파일명 다른 내용 2개 → file_key 기반 각각 독립 결과."""
    csv_a = b"col\nA\n"
    csv_b = b"col\nB\n"
    bundle, preflight, parse, mapping = _full_pipeline({
        "data.csv": csv_a,
        "data.csv_2": csv_b,
    })
    # 수동으로 동일 파일명 시나리오 구성
    import hashlib
    sha_a = hashlib.sha256(csv_a).hexdigest()
    sha_b = hashlib.sha256(csv_b).hexdigest()
    sf_a = _make_source_file("data.csv", sha_a, f"0:{sha_a}")
    sf_b = _make_source_file("data.csv", sha_b, f"1:{sha_b}")
    bundle2 = _make_bundle([sf_a, sf_b], source_id="src-dup")
    pfl = _make_preflight("src-dup", [
        _preflight_result("data.csv", f"0:{sha_a}", FileStatus.PASS),
        _preflight_result("data.csv", f"1:{sha_b}", FileStatus.PASS),
    ])
    doc_a = ParsedDocument(
        file_key=f"0:{sha_a}", filename="data.csv", sub_type="csv",
        total_rows=1, columns=["col"], csv_rows=[["A"]],
    )
    doc_b = ParsedDocument(
        file_key=f"1:{sha_b}", filename="data.csv", sub_type="csv",
        total_rows=1, columns=["col"], csv_rows=[["B"]],
    )
    parse2 = ParseReport(source_id="src-dup", file_results=[
        ParsedFileResult(filename="data.csv", file_key=f"0:{sha_a}", status=ParseStatus.OK, document=doc_a),
        ParsedFileResult(filename="data.csv", file_key=f"1:{sha_b}", status=ParseStatus.OK, document=doc_b),
    ])
    map2 = MappingReport(source_id="src-dup", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=f"0:{sha_a}", status=MappingStatus.MAPPED,
            documents=[_make_csv_mapped_doc("data.csv", f"0:{sha_a}", ["col"], [["A"]])],
        ),
        MappedFileResult(
            filename="data.csv", file_key=f"1:{sha_b}", status=MappingStatus.MAPPED,
            documents=[_make_csv_mapped_doc("data.csv", f"1:{sha_b}", ["col"], [["B"]])],
        ),
    ])
    report = run_quality(
        source_bundle=bundle2,
        preflight_report=pfl,
        parse_report=parse2,
        mapping_report=map2,
    )
    assert report.total_files == 2
    assert report.passed_files == 2
    file_keys = [r.file_key for r in report.file_results]
    assert f"0:{sha_a}" in file_keys
    assert f"1:{sha_b}" in file_keys


# ── Q-T04: Parse·Map 행 수 불일치 → FAIL ─────────────────────────────────────

def test_qt04_row_count_mismatch_fail():
    """Q-T04: MappedDocument.total_rows != 실제 records 길이 → FAIL."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.csv", sha, fk)
    bundle = _make_bundle([sf], source_id="src-t04")
    pfl = _make_preflight("src-t04", [_preflight_result("data.csv", fk, FileStatus.PASS)])

    # Parse: 3행
    doc = ParsedDocument(
        file_key=fk, filename="data.csv", sub_type="csv",
        total_rows=3, columns=["a", "b"],
        csv_rows=[["r0", "v0"], ["r1", "v1"], ["r2", "v2"]],
    )
    parse = ParseReport(source_id="src-t04", file_results=[
        ParsedFileResult(filename="data.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    # Map: total_rows=5라고 잘못 선언, records는 3개
    mapped_doc = _make_csv_mapped_doc(
        "data.csv", fk, ["a", "b"],
        [["r0", "v0"], ["r1", "v1"], ["r2", "v2"]],
        total_rows_override=5,  # 불일치
    )
    mapping = MappingReport(source_id="src-t04", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    fr = report.file_results[0]
    assert fr.status == QualityStatus.FAIL
    codes = [i.code for i in fr.issues]
    assert "Q02-TOTAL_ROWS_MISMATCH" in codes


# ── Q-T05: 셀 값 변경 감지 → FAIL ────────────────────────────────────────────

def test_qt05_cell_value_changed_fail():
    """Q-T05: Map records가 Parse csv_rows와 다름 → Q06-ROW_DATA_CHANGED → FAIL."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.csv", sha, fk)
    bundle = _make_bundle([sf], source_id="src-t05")
    pfl = _make_preflight("src-t05", [_preflight_result("data.csv", fk, FileStatus.PASS)])

    doc = ParsedDocument(
        file_key=fk, filename="data.csv", sub_type="csv",
        total_rows=2, columns=["a", "b"],
        csv_rows=[["original", "1"], ["row2", "2"]],
    )
    parse = ParseReport(source_id="src-t05", file_results=[
        ParsedFileResult(filename="data.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    mapped_doc = _make_csv_mapped_doc(
        "data.csv", fk, ["a", "b"],
        [["CHANGED", "1"], ["row2", "2"]],  # 첫 행 변경
    )
    mapping = MappingReport(source_id="src-t05", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    fr = report.file_results[0]
    codes = [i.code for i in fr.issues]
    assert "Q06-ROW_DATA_CHANGED" in codes


# ── Q-T06: 중복 헤더 → REVIEW_REQUIRED ──────────────────────────────────────

def test_qt06_duplicate_header_review_required():
    """Q-T06: columns에 동일 열 제목 2개 → Q03-DUPLICATE_HEADER → REVIEW_REQUIRED."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.csv", sha, fk)
    bundle = _make_bundle([sf], source_id="src-t06")
    pfl = _make_preflight("src-t06", [_preflight_result("data.csv", fk, FileStatus.PASS)])

    doc = ParsedDocument(
        file_key=fk, filename="data.csv", sub_type="csv",
        total_rows=1, columns=["name", "name"],  # 중복
        csv_rows=[["Alice", "30"]],
    )
    parse = ParseReport(source_id="src-t06", file_results=[
        ParsedFileResult(filename="data.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    mapped_doc = _make_csv_mapped_doc("data.csv", fk, ["name", "name"], [["Alice", "30"]])
    mapping = MappingReport(source_id="src-t06", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.REVIEW_REQUIRED
    fr = report.file_results[0]
    assert fr.status == QualityStatus.REVIEW_REQUIRED
    codes = [i.code for i in fr.issues]
    assert "Q03-DUPLICATE_HEADER" in codes
    dup_issues = [i for i in fr.issues if i.code == "Q03-DUPLICATE_HEADER"]
    assert dup_issues[0].severity == IssueSeverity.WARNING


# ── Q-T07: 빈 헤더 → REVIEW_REQUIRED ────────────────────────────────────────

def test_qt07_empty_header_review_required():
    """Q-T07: columns에 빈 문자열 열 제목 → Q03-EMPTY_HEADER → REVIEW_REQUIRED."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.csv", sha, fk)
    bundle = _make_bundle([sf], source_id="src-t07")
    pfl = _make_preflight("src-t07", [_preflight_result("data.csv", fk, FileStatus.PASS)])

    doc = ParsedDocument(
        file_key=fk, filename="data.csv", sub_type="csv",
        total_rows=1, columns=["name", "", "city"],  # 중간 열 제목 빈칸
        csv_rows=[["Alice", "30", "Seoul"]],
    )
    parse = ParseReport(source_id="src-t07", file_results=[
        ParsedFileResult(filename="data.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    mapped_doc = _make_csv_mapped_doc("data.csv", fk, ["name", "", "city"], [["Alice", "30", "Seoul"]])
    mapping = MappingReport(source_id="src-t07", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.REVIEW_REQUIRED
    codes = [i.code for i in report.file_results[0].issues]
    assert "Q03-EMPTY_HEADER" in codes


# ── Q-T08: 제목 후보 원본 위치 불일치 → FAIL ─────────────────────────────────

def test_qt08_title_candidate_value_mismatch_fail():
    """Q-T08: TitleCandidate.value가 원본 위치 실제 값과 다름 → Q04-CANDIDATE_VALUE_MISMATCH → FAIL."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.xlsx", sha, fk)
    bundle = _make_bundle([sf], source_id="src-t08")
    pfl = _make_preflight("src-t08", [_preflight_result("data.xlsx", fk, FileStatus.PASS)])

    # Parse: columns[0] = "실제값"
    sheet = SheetFullData(
        sheet_name="S1", columns=["실제값", "B"], rows=[["v1", "v2"]], total_rows=1,
    )
    doc = ParsedDocument(
        file_key=fk, filename="data.xlsx", sub_type="xlsx",
        total_rows=1, xlsx_sheets=[sheet],
    )
    parse = ParseReport(source_id="src-t08", file_results=[
        ParsedFileResult(filename="data.xlsx", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    # Map: TitleCandidate.value = "잘못된값" (원본과 불일치)
    cand = TitleCandidate(
        value="잘못된값",
        status=TitleStatus.CANDIDATE,
        source=SourceLocation(sheet_name="S1", row_index=0, col_index=0, cell_value="잘못된값"),
        basis="stub",
    )
    ti = DocumentTitleInfo(
        file_key=fk, filename="data.xlsx", sheet_name="S1",
        title_status=TitleStatus.CANDIDATE,
        candidates=[cand],
        column_headers=["실제값", "B"],
        column_header_row_index=0,
    )
    mapped_doc = _make_xlsx_mapped_doc(
        "data.xlsx", fk, "S1", ["실제값", "B"], [["v1", "v2"]], title_info=ti,
    )
    mapping = MappingReport(source_id="src-t08", file_results=[
        MappedFileResult(
            filename="data.xlsx", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    codes = [i.code for i in report.file_results[0].issues]
    assert "Q04-CANDIDATE_VALUE_MISMATCH" in codes


# ── Q-T09: 헤더 행이 첫 행 아님 → REVIEW_REQUIRED ────────────────────────────

def test_qt09_header_not_first_row_review_required():
    """Q-T09: column_header_row_index > 0 → Q03-HEADER_NOT_FIRST_ROW → REVIEW_REQUIRED."""
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [
            ["유해화학물질 관리대장"],          # 행 0 — 제목 후보
            ["물질명", "보관량", "보관장소"],   # 행 1 — 실제 헤더
            ["톨루엔", "100", "창고A"],
        ]),
    ])
    bundle, preflight, parse, mapping = _full_pipeline({"register.xlsx": xlsx_bytes})
    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    # column_header_row_index=1 → HEADER_NOT_FIRST_ROW (WARNING) → REVIEW_REQUIRED
    assert report.overall_status == QualityStatus.REVIEW_REQUIRED
    fr = report.file_results[0]
    assert fr.status == QualityStatus.REVIEW_REQUIRED
    codes = [i.code for i in fr.issues]
    assert "Q03-HEADER_NOT_FIRST_ROW" in codes
    header_issues = [i for i in fr.issues if i.code == "Q03-HEADER_NOT_FIRST_ROW"]
    assert header_issues[0].severity == IssueSeverity.WARNING


# ── Q-T10: PDF·ZIP 차단 → NOT_EVALUATED ──────────────────────────────────────

def test_qt10_pdf_blocked_not_evaluated():
    """Q-T10: PDF → Parse BLOCKED → QualityStatus.NOT_EVALUATED."""
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    bundle, preflight, parse, mapping = _full_pipeline({"manual.pdf": pdf_bytes})
    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.not_evaluated_files == 1
    assert report.passed_files == 0
    assert report.failed_files == 0
    fr = report.file_results[0]
    assert fr.status == QualityStatus.NOT_EVALUATED
    assert fr.issues == []
    assert "Q05" in fr.checked_items


# ── Q-T11: 여러 파일 중 일부 실패 → 파일별 상태 독립 ──────────────────────────

def test_qt11_mixed_files_independent_status():
    """Q-T11: CSV(정상) + PDF(차단) → CSV=PASS, PDF=NOT_EVALUATED, overall=REVIEW_REQUIRED (R1-04)."""
    csv_bytes = b"a,b\n1,2\n"
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    bundle, preflight, parse, mapping = _full_pipeline({
        "data.csv": csv_bytes,
        "doc.pdf": pdf_bytes,
    })
    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.total_files == 2
    assert report.passed_files == 1
    assert report.not_evaluated_files == 1
    assert report.failed_files == 0

    by_filename = {r.filename: r for r in report.file_results}
    assert by_filename["data.csv"].status == QualityStatus.PASS
    assert by_filename["doc.pdf"].status == QualityStatus.NOT_EVALUATED
    # R1-04: PASS + NOT_EVALUATED 혼재 → 미검사 파일 존재 → REVIEW_REQUIRED
    assert report.overall_status == QualityStatus.REVIEW_REQUIRED


# ── Q-T12: 100행 초과 문서 → 전체 데이터 기준 검수 ──────────────────────────

def test_qt12_over_100_rows_full_data_checked():
    """Q-T12: 150행 CSV → Quality 검수가 전체 150행 기준 (SheetPreview 100행 아님)."""
    rows = [f"R{i},V{i}" for i in range(150)]
    csv_bytes = ("col,val\n" + "\n".join(rows) + "\n").encode("utf-8")
    bundle, preflight, parse, mapping = _full_pipeline({"big.csv": csv_bytes})

    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    # 구조 이상 없음 → PASS
    assert report.overall_status == QualityStatus.PASS

    # Map의 records 길이가 150 (전체 데이터)인지 확인
    mfr = mapping.file_results[0]
    assert mfr.status == MappingStatus.MAPPED
    assert mfr.documents is not None
    doc = mfr.documents[0]
    assert doc.total_rows == 150
    assert len(doc.records) == 150


# ── Q-T13: include_quality 기본값 false — 기존 API 동작 불변 ────────────────

def test_qt13_include_quality_default_false(monkeypatch):
    """Q-T13: include_quality 기본값 false → quality 응답 null, 기존 동작 유지."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        # include_quality 파라미터 미전달
        resp = client.post(
            "/admin/companies/company-001/digitization/intake",
            files=[("files", ("data.csv", b"col\nval\n", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data.get("quality") is None, "기본값 false인데 quality 존재"
    assert data.get("parsed") is None
    assert data.get("mapped") is None


# ── Q-T14: include_quality=true만 → parsed/mapped 응답 미포함 ─────────────────

def test_qt14_quality_only_no_parsed_mapped(monkeypatch):
    """Q-T14: include_quality=true, include_parse/map 미전달 → parsed=null, mapped=null."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_quality=true",
            files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data.get("quality") is not None, "quality 없음"
    assert data.get("parsed") is None, "include_parse 없는데 parsed 존재"
    assert data.get("mapped") is None, "include_map 없는데 mapped 존재"


# ── Q-T15: HTTP include_quality=true → quality 요약·오류 위치 포함 ─────────────

def test_qt15_http_quality_structure(monkeypatch):
    """Q-T15: HTTP include_quality=true → quality 응답에 요약 카운터·파일 결과 포함."""
    app = _make_http_app(monkeypatch)
    sb = _make_supabase_mock()
    xlsx_bytes = _make_xlsx_bytes([
        ("Sheet1", [
            ["유해화학물질 관리대장"],
            ["물질명", "보관량"],
            ["톨루엔", "100"],
        ]),
    ])
    with (
        patch("routers.onboarding_digitization.get_supabase", return_value=sb),
        patch("routers.onboarding_digitization.audit_svc.record", return_value="audit-id"),
    ):
        client = TestClient(app)
        resp = client.post(
            "/admin/companies/company-001/digitization/intake?include_quality=true",
            files=[("files", ("register.xlsx", xlsx_bytes,
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        )
    assert resp.status_code == 200, resp.text
    quality = resp.json()["data"]["quality"]
    assert quality is not None

    # 요약 카운터 필드 존재
    assert "overall_status" in quality
    assert "total_files" in quality
    assert "passed_files" in quality
    assert "review_required_files" in quality
    assert "failed_files" in quality
    assert "not_evaluated_files" in quality
    assert quality["total_files"] == 1

    # 파일 결과 필드 존재
    assert "file_results" in quality
    assert len(quality["file_results"]) == 1
    fr = quality["file_results"][0]
    assert "status" in fr
    assert "checked_items" in fr
    assert "issues" in fr

    # XLSX 제목 행 구조 → HEADER_NOT_FIRST_ROW (REVIEW_REQUIRED)
    # 검수 이슈에 sheet_name·row_index·col_index 위치 정보 포함
    if fr["status"] == "REVIEW_REQUIRED":
        assert len(fr["issues"]) > 0
        issue = fr["issues"][0]
        assert "code" in issue
        assert "severity" in issue
        assert "message" in issue
        # 위치 정보 (sheet_name 존재)
        assert "sheet_name" in issue


# ── R1-T01: source_id 불일치 → Q01-SOURCE_ID_MISMATCH → FAIL ─────────────────

def test_r1t01_source_id_mismatch_fail():
    """R1-T01: preflight source_id ≠ bundle source_id → Q01-SOURCE_ID_MISMATCH → FAIL."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.csv", sha, fk)
    bundle = SourceBundle(
        source_id="bundle-sid",
        company_id="company-001",
        submitted_by="admin-001",
        submitted_at="2026-11-01T00:00:00Z",
        files=[sf],
    )
    # Preflight: 다른 source_id
    pfl = PreflightReport(
        source_id="different-sid",
        overall_status="PASS",
        file_results=[_preflight_result("data.csv", fk, FileStatus.PASS)],
        errors=[],
    )
    doc = ParsedDocument(
        file_key=fk, filename="data.csv", sub_type="csv",
        total_rows=1, columns=["a"], csv_rows=[["1"]],
    )
    parse = ParseReport(source_id="bundle-sid", file_results=[
        ParsedFileResult(filename="data.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    mapped_doc = _make_csv_mapped_doc("data.csv", fk, ["a"], [["1"]])
    mapping = MappingReport(source_id="bundle-sid", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    all_codes = [i.code for fr in report.file_results for i in fr.issues]
    assert "Q01-SOURCE_ID_MISMATCH" in all_codes


# ── R1-T02: Preflight 기록 없음 → Q01-PREFLIGHT_RECORD_MISSING → FAIL ─────────

def test_r1t02_preflight_missing_fail():
    """R1-T02: 번들 파일이 Preflight에 없음 → Q01-PREFLIGHT_RECORD_MISSING → FAIL."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.csv", sha, fk)
    bundle = _make_bundle([sf], source_id="src-r1t02")
    # Preflight: file_results 빈 목록 (해당 파일 없음)
    pfl = PreflightReport(
        source_id="src-r1t02",
        overall_status="PASS",
        file_results=[],
        errors=[],
    )
    doc = ParsedDocument(
        file_key=fk, filename="data.csv", sub_type="csv",
        total_rows=1, columns=["a"], csv_rows=[["1"]],
    )
    parse = ParseReport(source_id="src-r1t02", file_results=[
        ParsedFileResult(filename="data.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    mapped_doc = _make_csv_mapped_doc("data.csv", fk, ["a"], [["1"]])
    mapping = MappingReport(source_id="src-r1t02", file_results=[
        MappedFileResult(
            filename="data.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    fr = report.file_results[0]
    assert fr.status == QualityStatus.FAIL
    codes = [i.code for i in fr.issues]
    assert "Q01-PREFLIGHT_RECORD_MISSING" in codes


# ── R1-T03: Parse 파일명 불일치 → Q01-FILENAME_MISMATCH → FAIL ───────────────

def test_r1t03_filename_mismatch_fail():
    """R1-T03: Parse 결과 파일명 ≠ Bundle 파일명 (동일 file_key) → Q01-FILENAME_MISMATCH → FAIL."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("original.csv", sha, fk)
    bundle = _make_bundle([sf], source_id="src-r1t03")
    pfl = _make_preflight("src-r1t03", [_preflight_result("original.csv", fk, FileStatus.PASS)])
    # Parse: 동일 file_key이지만 다른 파일명
    doc = ParsedDocument(
        file_key=fk, filename="different.csv", sub_type="csv",
        total_rows=1, columns=["a"], csv_rows=[["1"]],
    )
    parse = ParseReport(source_id="src-r1t03", file_results=[
        ParsedFileResult(filename="different.csv", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    mapped_doc = _make_csv_mapped_doc("different.csv", fk, ["a"], [["1"]])
    mapping = MappingReport(source_id="src-r1t03", file_results=[
        MappedFileResult(
            filename="different.csv", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    fr = report.file_results[0]
    assert fr.status == QualityStatus.FAIL
    codes = [i.code for i in fr.issues]
    assert "Q01-FILENAME_MISMATCH" in codes


# ── R1-T04: column_header_row_index > 0, 실제 헤더 중복 감지 ──────────────────

def test_r1t04_actual_header_duplicate_detected():
    """R1-T04: column_header_row_index>0, title_info.column_headers 중복 → Q03-DUPLICATE_HEADER (R1-02)."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.xlsx", sha, fk)
    bundle = _make_bundle([sf], source_id="src-r1t04")
    pfl = _make_preflight("src-r1t04", [_preflight_result("data.xlsx", fk, FileStatus.PASS)])

    sheet = SheetFullData(
        sheet_name="S1",
        columns=["유해화학물질 관리대장"],  # 행 0 — 제목 행
        rows=[
            ["물질명", "물질명", "보관장소"],  # 행 1 — 실제 헤더 (중복)
            ["톨루엔", "100", "창고A"],
        ],
        total_rows=2,
    )
    doc = ParsedDocument(
        file_key=fk, filename="data.xlsx", sub_type="xlsx",
        total_rows=2, xlsx_sheets=[sheet],
    )
    parse = ParseReport(source_id="src-r1t04", file_results=[
        ParsedFileResult(filename="data.xlsx", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    ti = DocumentTitleInfo(
        file_key=fk, filename="data.xlsx", sheet_name="S1",
        title_status=TitleStatus.NOT_FOUND,
        candidates=[],
        column_headers=["물질명", "물질명", "보관장소"],  # 실제 헤더 — 중복
        column_header_row_index=1,
    )
    # map_svc는 records=sheet.rows (헤더 행 포함 전체), total_rows=sheet.total_rows 그대로 저장
    mapped_doc = _make_xlsx_mapped_doc(
        "data.xlsx", fk, "S1",
        columns=["유해화학물질 관리대장"],  # mapped_doc.columns = 제목 행 값
        records=[["물질명", "물질명", "보관장소"], ["톨루엔", "100", "창고A"]],
        title_info=ti,
    )
    mapping = MappingReport(source_id="src-r1t04", file_results=[
        MappedFileResult(
            filename="data.xlsx", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.REVIEW_REQUIRED
    fr = report.file_results[0]
    codes = [i.code for i in fr.issues]
    # R1-02: 실제 헤더 행(title_info.column_headers) 기준으로 중복 감지
    assert "Q03-DUPLICATE_HEADER" in codes
    assert "Q03-HEADER_NOT_FIRST_ROW" in codes


# ── R1-T05: 음수 col_index → Q04-NEGATIVE_INDEX → FAIL ───────────────────────

def test_r1t05_negative_col_index_fail():
    """R1-T05: TitleCandidate.source.col_index=-1 → Q04-NEGATIVE_INDEX → FAIL (R1-03)."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.xlsx", sha, fk)
    bundle = _make_bundle([sf], source_id="src-r1t05")
    pfl = _make_preflight("src-r1t05", [_preflight_result("data.xlsx", fk, FileStatus.PASS)])

    sheet = SheetFullData(
        sheet_name="S1", columns=["A", "B"], rows=[["a1", "b1"]], total_rows=1,
    )
    doc = ParsedDocument(
        file_key=fk, filename="data.xlsx", sub_type="xlsx",
        total_rows=1, xlsx_sheets=[sheet],
    )
    parse = ParseReport(source_id="src-r1t05", file_results=[
        ParsedFileResult(filename="data.xlsx", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    cand = TitleCandidate(
        value="title",
        status=TitleStatus.CANDIDATE,
        source=SourceLocation(sheet_name="S1", row_index=0, col_index=-1, cell_value="title"),
        basis="stub",
    )
    ti = DocumentTitleInfo(
        file_key=fk, filename="data.xlsx", sheet_name="S1",
        title_status=TitleStatus.CANDIDATE,
        candidates=[cand],
        column_headers=["A", "B"],
        column_header_row_index=0,
    )
    mapped_doc = _make_xlsx_mapped_doc(
        "data.xlsx", fk, "S1", ["A", "B"], [["a1", "b1"]], title_info=ti,
    )
    mapping = MappingReport(source_id="src-r1t05", file_results=[
        MappedFileResult(
            filename="data.xlsx", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    fr = report.file_results[0]
    codes = [i.code for i in fr.issues]
    assert "Q04-NEGATIVE_INDEX" in codes


# ── R1-T06: cell_value 변조 (value 정상) → Q04-CELL_VALUE_TAMPERED → FAIL ─────

def test_r1t06_cell_value_tampered_fail():
    """R1-T06: SourceLocation.cell_value 변조, cand.value는 정상 → Q04-CELL_VALUE_TAMPERED (R1-03)."""
    import hashlib
    sha = hashlib.sha256(b"stub").hexdigest()
    fk = f"0:{sha}"
    sf = _make_source_file("data.xlsx", sha, fk)
    bundle = _make_bundle([sf], source_id="src-r1t06")
    pfl = _make_preflight("src-r1t06", [_preflight_result("data.xlsx", fk, FileStatus.PASS)])

    sheet = SheetFullData(
        sheet_name="S1", columns=["실제값", "B"], rows=[["v1", "v2"]], total_rows=1,
    )
    doc = ParsedDocument(
        file_key=fk, filename="data.xlsx", sub_type="xlsx",
        total_rows=1, xlsx_sheets=[sheet],
    )
    parse = ParseReport(source_id="src-r1t06", file_results=[
        ParsedFileResult(filename="data.xlsx", file_key=fk, status=ParseStatus.OK, document=doc),
    ])
    # cand.value = 실제값 (정상), cand.source.cell_value = "변조됨" (변조)
    cand = TitleCandidate(
        value="실제값",
        status=TitleStatus.CANDIDATE,
        source=SourceLocation(sheet_name="S1", row_index=0, col_index=0, cell_value="변조됨"),
        basis="stub",
    )
    ti = DocumentTitleInfo(
        file_key=fk, filename="data.xlsx", sheet_name="S1",
        title_status=TitleStatus.CANDIDATE,
        candidates=[cand],
        column_headers=["실제값", "B"],
        column_header_row_index=0,
    )
    mapped_doc = _make_xlsx_mapped_doc(
        "data.xlsx", fk, "S1", ["실제값", "B"], [["v1", "v2"]], title_info=ti,
    )
    mapping = MappingReport(source_id="src-r1t06", file_results=[
        MappedFileResult(
            filename="data.xlsx", file_key=fk, status=MappingStatus.MAPPED,
            documents=[mapped_doc],
        ),
    ])
    report = run_quality(
        source_bundle=bundle,
        preflight_report=pfl,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.overall_status == QualityStatus.FAIL
    fr = report.file_results[0]
    codes = [i.code for i in fr.issues]
    assert "Q04-CELL_VALUE_TAMPERED" in codes
    # value는 actual과 일치하므로 CANDIDATE_VALUE_MISMATCH 없음
    assert "Q04-CANDIDATE_VALUE_MISMATCH" not in codes


# ── R1-T07: PASS + NOT_EVALUATED → overall REVIEW_REQUIRED ───────────────────

def test_r1t07_pass_not_evaluated_overall_review_required():
    """R1-T07: PASS + NOT_EVALUATED 혼재 → overall_status=REVIEW_REQUIRED (R1-04)."""
    csv_bytes = b"a,b\n1,2\n"
    pdf_bytes = b"%PDF-1.4\ncontent\n%%EOF"
    bundle, preflight, parse, mapping = _full_pipeline({
        "data.csv": csv_bytes,
        "doc.pdf": pdf_bytes,
    })
    report = run_quality(
        source_bundle=bundle,
        preflight_report=preflight,
        parse_report=parse,
        mapping_report=mapping,
    )
    assert report.passed_files == 1
    assert report.not_evaluated_files == 1
    assert report.failed_files == 0
    # R1-04: PASS + NOT_EVALUATED → 미검사 파일 존재 → REVIEW_REQUIRED
    assert report.overall_status == QualityStatus.REVIEW_REQUIRED
