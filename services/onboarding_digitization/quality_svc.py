"""OBJ01 [7] Quality — 추출 결과 구조 검수 (WO-037).

목적: 파이프라인 전 단계 결과의 구조 일관성·원본 추적성 검사.
범위 외: 업무상 정확성, 법령 적합성, Canonical 매핑 적정성.
외부 API / DB / Storage / AI 호출 없음 — 순수 검사 함수.
"""
from __future__ import annotations

from .models import (
    FileStatus,
    IssueSeverity,
    MappedDocument,
    MappingReport,
    MappingStatus,
    ParseReport,
    ParseStatus,
    ParsedDocument,
    PreflightReport,
    QualityFileResult,
    QualityIssue,
    QualityReport,
    QualityStatus,
    SourceBundle,
)


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _issue(
    code: str,
    severity: IssueSeverity,
    file_key: str,
    filename: str,
    message: str,
    sheet_name: str = "",
    row_index: int | None = None,
    col_index: int | None = None,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity=severity,
        file_key=file_key,
        filename=filename,
        sheet_name=sheet_name,
        row_index=row_index,
        col_index=col_index,
        message=message,
    )


def _status_from_issues(issues: list[QualityIssue]) -> QualityStatus:
    if any(i.severity == IssueSeverity.ERROR for i in issues):
        return QualityStatus.FAIL
    if any(i.severity == IssueSeverity.WARNING for i in issues):
        return QualityStatus.REVIEW_REQUIRED
    return QualityStatus.PASS


def _overall_from_results(file_results: list[QualityFileResult]) -> QualityStatus:
    statuses = [r.status for r in file_results]
    if any(s == QualityStatus.FAIL for s in statuses):
        return QualityStatus.FAIL
    if any(s == QualityStatus.REVIEW_REQUIRED for s in statuses):
        return QualityStatus.REVIEW_REQUIRED
    if all(s == QualityStatus.NOT_EVALUATED for s in statuses):
        return QualityStatus.NOT_EVALUATED
    # R1-04: PASS + NOT_EVALUATED 혼재 → 미검사 파일 존재 → REVIEW_REQUIRED
    if any(s == QualityStatus.NOT_EVALUATED for s in statuses):
        return QualityStatus.REVIEW_REQUIRED
    return QualityStatus.PASS


# ── Q01: 파일 식별자 일치 ────────────────────────────────────────────────────

def _check_file_identity(
    source_bundle: SourceBundle,
    file_key: str,
    filename: str,
    parse_filename: str | None = None,
    map_filename: str | None = None,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if not file_key:
        return issues

    source_keys = {sf.file_key for sf in source_bundle.files}
    if file_key not in source_keys:
        issues.append(_issue(
            "Q01-FILEKEY_NOT_IN_BUNDLE",
            IssueSeverity.ERROR,
            file_key, filename,
            f"file_key '{file_key}'가 SourceBundle에 없음",
        ))
        return issues

    # "{index}:{sha256}" 형식이면 SHA256 연결 확인
    if ":" in file_key:
        _, key_sha = file_key.split(":", 1)
        for sf in source_bundle.files:
            if sf.file_key == file_key and sf.sha256 != key_sha:
                issues.append(_issue(
                    "Q01-SHA256_MISMATCH",
                    IssueSeverity.ERROR,
                    file_key, filename,
                    f"file_key SHA256 '{key_sha}' ≠ SourceBundle SHA256 '{sf.sha256}'",
                ))

    # R1-01c: Parse 단계 파일명 불일치 감지
    if parse_filename is not None and parse_filename != filename:
        issues.append(_issue(
            "Q01-FILENAME_MISMATCH",
            IssueSeverity.ERROR,
            file_key, filename,
            f"Parse 파일명 '{parse_filename}' ≠ Bundle 파일명 '{filename}'",
        ))

    # R1-01c: Map 단계 파일명 불일치 감지
    if map_filename is not None and map_filename != filename:
        issues.append(_issue(
            "Q01-FILENAME_MISMATCH",
            IssueSeverity.ERROR,
            file_key, filename,
            f"Map 파일명 '{map_filename}' ≠ Bundle 파일명 '{filename}'",
        ))

    return issues


# ── Q02: 행·열 수 일치 ───────────────────────────────────────────────────────

def _check_row_counts(
    mapped_doc: MappedDocument,
    parse_doc: ParsedDocument,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    fk = mapped_doc.file_key
    fn = mapped_doc.filename
    sn = mapped_doc.sheet_name

    actual_records = len(mapped_doc.records)

    # total_rows vs 실제 records 길이
    if mapped_doc.total_rows != actual_records:
        issues.append(_issue(
            "Q02-TOTAL_ROWS_MISMATCH",
            IssueSeverity.ERROR,
            fk, fn,
            f"total_rows={mapped_doc.total_rows} ≠ 실제 records 길이={actual_records}",
            sheet_name=sn,
        ))

    if mapped_doc.sub_type == "csv":
        # Parse total_rows vs Map total_rows
        if parse_doc.total_rows != mapped_doc.total_rows:
            issues.append(_issue(
                "Q02-PARSE_MAP_ROW_MISMATCH",
                IssueSeverity.ERROR,
                fk, fn,
                f"Parse total_rows={parse_doc.total_rows} ≠ Map total_rows={mapped_doc.total_rows}",
                sheet_name=sn,
            ))
        # 가변 길이 행 탐지
        expected_cols = len(mapped_doc.columns)
        if expected_cols > 0:
            for i, row in enumerate(mapped_doc.records):
                if len(row) != expected_cols:
                    issues.append(_issue(
                        "Q02-VARIABLE_ROW_LENGTH",
                        IssueSeverity.WARNING,
                        fk, fn,
                        f"행 {i}: 열 수={len(row)} ≠ 헤더 열 수={expected_cols}",
                        row_index=i,
                    ))

    elif mapped_doc.sub_type == "xlsx" and parse_doc.xlsx_sheets:
        for sheet in parse_doc.xlsx_sheets:
            if sheet.sheet_name == sn:
                if sheet.total_rows != mapped_doc.total_rows:
                    issues.append(_issue(
                        "Q02-PARSE_MAP_ROW_MISMATCH",
                        IssueSeverity.ERROR,
                        fk, fn,
                        f"Parse 시트 '{sn}' total_rows={sheet.total_rows} ≠ Map total_rows={mapped_doc.total_rows}",
                        sheet_name=sn,
                    ))
                # 가변 열 수 행 탐지
                expected_cols = len(sheet.columns)
                if expected_cols > 0:
                    for i, row in enumerate(sheet.rows):
                        if len(row) != expected_cols:
                            issues.append(_issue(
                                "Q02-VARIABLE_ROW_LENGTH",
                                IssueSeverity.WARNING,
                                fk, fn,
                                f"시트 '{sn}' 행 {i}: 열 수={len(row)} ≠ 헤더 열 수={expected_cols}",
                                sheet_name=sn,
                                row_index=i,
                            ))
                break

    return issues


# ── Q03: 헤더 구조 ────────────────────────────────────────────────────────────

def _check_header_structure(mapped_doc: MappedDocument) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    fk = mapped_doc.file_key
    fn = mapped_doc.filename
    sn = mapped_doc.sheet_name

    # R1-02: column_header_row_index > 0이면 title_info.column_headers가 실제 헤더
    headers = mapped_doc.columns
    if (
        mapped_doc.title_info
        and mapped_doc.title_info.column_header_row_index > 0
        and mapped_doc.title_info.column_headers
    ):
        headers = mapped_doc.title_info.column_headers

    if not headers:
        return issues

    # 빈 열 제목
    for i, h in enumerate(headers):
        if not h.strip():
            issues.append(_issue(
                "Q03-EMPTY_HEADER",
                IssueSeverity.WARNING,
                fk, fn,
                f"열 {i}: 빈 열 제목",
                sheet_name=sn,
                col_index=i,
            ))

    # 중복 열 제목
    seen: dict[str, int] = {}
    for i, h in enumerate(headers):
        stripped = h.strip()
        if not stripped:
            continue
        if stripped in seen:
            issues.append(_issue(
                "Q03-DUPLICATE_HEADER",
                IssueSeverity.WARNING,
                fk, fn,
                f"열 {i}: 열 제목 '{stripped}' 중복 (첫 출현: 열 {seen[stripped]})",
                sheet_name=sn,
                col_index=i,
            ))
        else:
            seen[stripped] = i

    # 헤더 행이 첫 행이 아닌 경우 (R2 title detection 결과)
    if mapped_doc.title_info and mapped_doc.title_info.column_header_row_index > 0:
        idx = mapped_doc.title_info.column_header_row_index
        issues.append(_issue(
            "Q03-HEADER_NOT_FIRST_ROW",
            IssueSeverity.WARNING,
            fk, fn,
            f"실제 열 제목이 행 0이 아닌 행 {idx}에 위치 — 행 0은 제목 후보",
            sheet_name=sn,
            row_index=idx,
        ))

    return issues


# ── Q04: 제목 후보 출처 ───────────────────────────────────────────────────────

def _check_title_source(
    mapped_doc: MappedDocument,
    parse_doc: ParsedDocument,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    fk = mapped_doc.file_key
    fn = mapped_doc.filename
    sn = mapped_doc.sheet_name

    if not mapped_doc.title_info or not mapped_doc.title_info.candidates:
        return issues

    for cand in mapped_doc.title_info.candidates:
        src = cand.source
        r = src.row_index
        c = src.col_index
        expected = cand.value.strip()

        if mapped_doc.sub_type == "csv":
            issues.append(_issue(
                "Q04-CSV_UNEXPECTED_CANDIDATE",
                IssueSeverity.ERROR,
                fk, fn,
                "CSV 파일에 제목 후보가 있음 — CSV는 제목 추출 대상 아님",
                sheet_name=sn,
            ))
            continue

        # R1-03: 음수 인덱스 감지
        if r < 0 or c < 0:
            issues.append(_issue(
                "Q04-NEGATIVE_INDEX",
                IssueSeverity.ERROR,
                fk, fn,
                f"제목 후보 위치 인덱스 음수: row_index={r}, col_index={c}",
                sheet_name=sn,
                row_index=r if r >= 0 else None,
                col_index=c if c >= 0 else None,
            ))
            continue

        # XLSX: 원본 시트 조회
        sheet_data = None
        if parse_doc.xlsx_sheets:
            for s in parse_doc.xlsx_sheets:
                if s.sheet_name == sn:
                    sheet_data = s
                    break

        if sheet_data is None:
            issues.append(_issue(
                "Q04-SHEET_NOT_FOUND",
                IssueSeverity.ERROR,
                fk, fn,
                f"제목 후보의 원본 시트 '{sn}'이 ParsedDocument에 없음",
                sheet_name=sn,
                row_index=r,
                col_index=c,
            ))
            continue

        # row_index=0: columns 배열
        # row_index>=1: rows[row_index-1]
        if r == 0:
            if c >= len(sheet_data.columns):
                issues.append(_issue(
                    "Q04-COL_INDEX_OUT_OF_RANGE",
                    IssueSeverity.ERROR,
                    fk, fn,
                    f"제목 후보 col_index={c}가 columns 범위 밖 (len={len(sheet_data.columns)})",
                    sheet_name=sn,
                    row_index=r,
                    col_index=c,
                ))
                continue
            actual = sheet_data.columns[c].strip()
        else:
            row_idx = r - 1
            if row_idx >= len(sheet_data.rows):
                issues.append(_issue(
                    "Q04-ROW_INDEX_OUT_OF_RANGE",
                    IssueSeverity.ERROR,
                    fk, fn,
                    f"제목 후보 row_index={r}가 rows 범위 밖 (rows 길이={len(sheet_data.rows)})",
                    sheet_name=sn,
                    row_index=r,
                    col_index=c,
                ))
                continue
            row_data = sheet_data.rows[row_idx]
            if c >= len(row_data):
                issues.append(_issue(
                    "Q04-COL_INDEX_OUT_OF_RANGE",
                    IssueSeverity.ERROR,
                    fk, fn,
                    f"제목 후보 col_index={c}가 행 {r} 범위 밖",
                    sheet_name=sn,
                    row_index=r,
                    col_index=c,
                ))
                continue
            actual = row_data[c].strip()

        # R1-03: cell_value 변조 감지 (SourceLocation.cell_value ≠ 실제 원본 값)
        if cand.source.cell_value.strip() != actual:
            issues.append(_issue(
                "Q04-CELL_VALUE_TAMPERED",
                IssueSeverity.ERROR,
                fk, fn,
                f"SourceLocation.cell_value '{cand.source.cell_value}' ≠ 원본 위치({r},{c}) 실제 값 '{actual}'",
                sheet_name=sn,
                row_index=r,
                col_index=c,
            ))

        if actual != expected:
            issues.append(_issue(
                "Q04-CANDIDATE_VALUE_MISMATCH",
                IssueSeverity.ERROR,
                fk, fn,
                f"제목 후보 값 '{expected}' ≠ 원본 위치({r},{c}) 실제 값 '{actual}'",
                sheet_name=sn,
                row_index=r,
                col_index=c,
            ))

    return issues


# ── Q06: 원본 보존 일관성 ────────────────────────────────────────────────────

def _check_data_preservation(
    mapped_doc: MappedDocument,
    parse_doc: ParsedDocument,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    fk = mapped_doc.file_key
    fn = mapped_doc.filename
    sn = mapped_doc.sheet_name

    if mapped_doc.sub_type == "csv":
        source_rows = parse_doc.csv_rows or []
        target_rows = mapped_doc.records
        if len(source_rows) != len(target_rows):
            issues.append(_issue(
                "Q06-ROW_COUNT_MISMATCH",
                IssueSeverity.ERROR,
                fk, fn,
                f"CSV Parse rows={len(source_rows)} ≠ Map records={len(target_rows)}",
            ))
            return issues
        for i, (src, tgt) in enumerate(zip(source_rows, target_rows)):
            if src != tgt:
                issues.append(_issue(
                    "Q06-ROW_DATA_CHANGED",
                    IssueSeverity.ERROR,
                    fk, fn,
                    f"행 {i}: Parse 원본과 Map 결과 불일치",
                    row_index=i,
                ))
                break  # 첫 불일치만 보고

    elif mapped_doc.sub_type == "xlsx":
        sheet_data = None
        if parse_doc.xlsx_sheets:
            for s in parse_doc.xlsx_sheets:
                if s.sheet_name == sn:
                    sheet_data = s
                    break
        if sheet_data is None:
            return issues
        source_rows = sheet_data.rows
        target_rows = mapped_doc.records
        if len(source_rows) != len(target_rows):
            issues.append(_issue(
                "Q06-ROW_COUNT_MISMATCH",
                IssueSeverity.ERROR,
                fk, fn,
                f"XLSX 시트 '{sn}' Parse rows={len(source_rows)} ≠ Map records={len(target_rows)}",
                sheet_name=sn,
            ))
            return issues
        for i, (src, tgt) in enumerate(zip(source_rows, target_rows)):
            if src != tgt:
                issues.append(_issue(
                    "Q06-ROW_DATA_CHANGED",
                    IssueSeverity.ERROR,
                    fk, fn,
                    f"시트 '{sn}' 행 {i}: Parse 원본과 Map 결과 불일치",
                    sheet_name=sn,
                    row_index=i,
                ))
                break

    return issues


# ── 파일별 평가 ───────────────────────────────────────────────────────────────

def _evaluate_file(
    source_bundle: SourceBundle,
    file_key: str,
    filename: str,
    preflight_status: str | None,
    parse_status: ParseStatus | None,
    parse_doc: ParsedDocument | None,
    map_status: MappingStatus | None,
    mapped_docs: list[MappedDocument] | None,
    parse_filename: str | None = None,
    map_filename: str | None = None,
) -> QualityFileResult:
    # R1-01b: Preflight 기록 없음 → FAIL
    if preflight_status is None:
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.FAIL,
            checked_items=["Q01"],
            issues=[_issue(
                "Q01-PREFLIGHT_RECORD_MISSING",
                IssueSeverity.ERROR,
                file_key, filename,
                "Preflight 기록 없음 — 이 파일이 Preflight에서 처리되지 않음",
            )],
        )

    # Q05: 처리 상태 전파
    if preflight_status in (
        FileStatus.FAIL, FileStatus.UNSUPPORTED, FileStatus.BLOCKED,
        "FAIL", "UNSUPPORTED", "BLOCKED",
    ):
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.NOT_EVALUATED,
            checked_items=["Q05"],
            issues=[],
        )

    if parse_status == ParseStatus.BLOCKED:
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.NOT_EVALUATED,
            checked_items=["Q05"],
            issues=[],
        )

    if parse_status == ParseStatus.ERROR:
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.FAIL,
            checked_items=["Q05"],
            issues=[_issue(
                "Q05-PARSE_ERROR",
                IssueSeverity.ERROR,
                file_key, filename,
                "Parse 단계 오류 — 정상 결과로 승격 불가",
            )],
        )

    if map_status == MappingStatus.BLOCKED:
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.NOT_EVALUATED,
            checked_items=["Q05"],
            issues=[],
        )

    if map_status == MappingStatus.ERROR:
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.FAIL,
            checked_items=["Q05"],
            issues=[_issue(
                "Q05-MAP_ERROR",
                IssueSeverity.ERROR,
                file_key, filename,
                "Map 단계 오류 — 정상 결과로 승격 불가",
            )],
        )

    if parse_doc is None or not mapped_docs:
        return QualityFileResult(
            file_key=file_key,
            filename=filename,
            status=QualityStatus.NOT_EVALUATED,
            checked_items=[],
            issues=[],
        )

    issues: list[QualityIssue] = []
    checked_items: list[str] = []

    # Q01
    checked_items.append("Q01")
    issues.extend(_check_file_identity(source_bundle, file_key, filename, parse_filename, map_filename))

    # 문서별 Q02/Q03/Q04/Q06
    for doc in mapped_docs:
        if "Q02" not in checked_items:
            checked_items.append("Q02")
        if "Q03" not in checked_items:
            checked_items.append("Q03")
        if "Q04" not in checked_items:
            checked_items.append("Q04")
        if "Q06" not in checked_items:
            checked_items.append("Q06")

        issues.extend(_check_row_counts(doc, parse_doc))
        issues.extend(_check_header_structure(doc))
        issues.extend(_check_title_source(doc, parse_doc))
        issues.extend(_check_data_preservation(doc, parse_doc))

    return QualityFileResult(
        file_key=file_key,
        filename=filename,
        status=_status_from_issues(issues),
        checked_items=checked_items,
        issues=issues,
    )


# ── 진입점 ───────────────────────────────────────────────────────────────────

def run_quality(
    source_bundle: SourceBundle,
    preflight_report: PreflightReport,
    parse_report: ParseReport,
    mapping_report: MappingReport,
) -> QualityReport:
    """[7] Quality — 파이프라인 결과 구조 검수."""
    # R1-01a: source_id 일치 확인 (4개 입력 간 교차 검증)
    expected_sid = source_bundle.source_id
    mismatched: dict[str, str] = {}
    if preflight_report.source_id != expected_sid:
        mismatched["preflight"] = preflight_report.source_id
    if parse_report.source_id != expected_sid:
        mismatched["parse"] = parse_report.source_id
    if mapping_report.source_id != expected_sid:
        mismatched["mapping"] = mapping_report.source_id
    if mismatched:
        pipeline_issue = _issue(
            "Q01-SOURCE_ID_MISMATCH",
            IssueSeverity.ERROR,
            "", "[pipeline]",
            f"파이프라인 단계 source_id 불일치: bundle='{expected_sid}', 불일치={mismatched}",
        )
        return QualityReport(
            source_id=expected_sid,
            overall_status=QualityStatus.FAIL,
            total_files=1,
            passed_files=0,
            review_required_files=0,
            failed_files=1,
            not_evaluated_files=0,
            file_results=[QualityFileResult(
                file_key="",
                filename="[pipeline]",
                status=QualityStatus.FAIL,
                checked_items=["Q01"],
                issues=[pipeline_issue],
            )],
        )

    # 조회 맵 구성 (R1-01c: filename 포함)
    preflight_map: dict[str, str] = {
        pr.file_key: pr.status.value
        for pr in preflight_report.file_results
    }
    parse_map: dict[str, tuple[ParseStatus, ParsedDocument | None, str]] = {
        pfr.file_key: (pfr.status, pfr.document, pfr.filename)
        for pfr in parse_report.file_results
    }
    map_file_map: dict[str, tuple[MappingStatus, list[MappedDocument] | None, str]] = {
        mfr.file_key: (mfr.status, mfr.documents, mfr.filename)
        for mfr in mapping_report.file_results
    }

    file_results: list[QualityFileResult] = []
    for sf in source_bundle.files:
        fk = sf.file_key
        fn = sf.filename

        pfl_status = preflight_map.get(fk)
        parse_status, parse_doc, parse_fn = parse_map.get(fk, (None, None, None))
        map_status, mapped_docs, map_fn = map_file_map.get(fk, (None, None, None))

        result = _evaluate_file(
            source_bundle=source_bundle,
            file_key=fk,
            filename=fn,
            preflight_status=pfl_status,
            parse_status=parse_status,
            parse_doc=parse_doc,
            map_status=map_status,
            mapped_docs=mapped_docs,
            parse_filename=parse_fn,
            map_filename=map_fn,
        )
        file_results.append(result)

    passed = sum(1 for r in file_results if r.status == QualityStatus.PASS)
    review = sum(1 for r in file_results if r.status == QualityStatus.REVIEW_REQUIRED)
    failed = sum(1 for r in file_results if r.status == QualityStatus.FAIL)
    not_eval = sum(1 for r in file_results if r.status == QualityStatus.NOT_EVALUATED)

    return QualityReport(
        source_id=parse_report.source_id,
        overall_status=_overall_from_results(file_results),
        total_files=len(file_results),
        passed_files=passed,
        review_required_files=review,
        failed_files=failed,
        not_evaluated_files=not_eval,
        file_results=file_results,
    )
