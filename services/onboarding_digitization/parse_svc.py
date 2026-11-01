"""OBJ01 [4] Parse — 파일 내용 추출 (합성 데이터 전용, WO-035 / R1 보정).

R1 보정:
  R1-01: file_key 기반 조회 (tr.filename fallback) — 동일 파일명 혼용 해소
  R1-02: 미리보기(SheetPreview) vs 전체 데이터(ParsedDocument) 분리
  R1-03: data_only=False — XLSX 수식 손실 방지
  R1-04: XLSX 처리 한도 — 시트당 _MAX_XLSX_ROWS 초과 시 ERROR

PDF: 텍스트 파서 미탑재 → BLOCKED.
ZIP: Owner 결정 대기 → BLOCKED.
CSV: stdlib csv (UTF-8/EUC-KR/CP949).
XLSX: openpyxl (data_only=False, 수식 보존).
"""
from __future__ import annotations

import csv
import io
from typing import Dict, List

import openpyxl

from .models import (
    ParsedDocument,
    ParsedFileResult,
    ParseReport,
    ParseStatus,
    SheetFullData,
    SheetPreview,
    TriageReport,
)

_MAX_PREVIEW_ROWS = 100

# R1-04: XLSX 처리 한도 (보수적 — 운영용 최종 상한 Owner 결정 필요)
_MAX_XLSX_ROWS = 10_000  # 시트당 데이터 행 상한


def _parse_csv(
    filename: str,
    data: bytes,
    file_key: str = "",
    max_rows: int = _MAX_PREVIEW_ROWS,
) -> ParsedFileResult:
    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
        try:
            text = data.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        return ParsedFileResult(
            filename=filename,
            file_key=file_key,
            status=ParseStatus.ERROR,
            reason="인코딩 디코딩 실패 — 지원 인코딩 없음",
        )

    reader = csv.reader(io.StringIO(text))
    all_rows: list[list[str]] = [[str(c) for c in row] for row in reader]

    if not all_rows:
        return ParsedFileResult(
            filename=filename,
            file_key=file_key,
            status=ParseStatus.ERROR,
            reason="CSV 행 없음",
        )

    header = all_rows[0]
    data_rows = all_rows[1:]  # 헤더 제외 전체 행 (R1-02: 전체 보존)
    total_rows = len(data_rows)

    # R1-02: 미리보기 — max_rows 제한 적용
    preview = SheetPreview(
        sheet_name="",
        columns=header,
        rows=data_rows[:max_rows],
        total_rows=total_rows,
    )

    # R1-02: 전체 추출 데이터 — [5] Map 입력용
    # WO-036: columns 필드에 헤더 보관 (csv_rows는 헤더 제외 순수 데이터 행)
    document = ParsedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="csv",
        total_rows=total_rows,
        columns=header,
        csv_rows=data_rows,
    )

    return ParsedFileResult(
        filename=filename,
        file_key=file_key,
        status=ParseStatus.OK,
        preview=preview,
        document=document,
    )


def _parse_xlsx(
    filename: str,
    data: bytes,
    file_key: str = "",
    max_rows: int = _MAX_PREVIEW_ROWS,
) -> ParsedFileResult:
    try:
        # R1-03: data_only=False — 수식 셀 손실 방지 (True이면 캐시 없는 수식 → None → "")
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception as exc:
        return ParsedFileResult(
            filename=filename,
            file_key=file_key,
            status=ParseStatus.ERROR,
            reason=f"XLSX 파싱 실패: {exc}",
        )

    preview_sheets: list[SheetPreview] = []
    full_sheets: list[SheetFullData] = []

    for ws in wb.worksheets:
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if header_row is None:
            preview_sheets.append(SheetPreview(sheet_name=ws.title, columns=[], rows=[], total_rows=0))
            full_sheets.append(SheetFullData(sheet_name=ws.title, columns=[], rows=[], total_rows=0))
            continue

        header = [str(c) if c is not None else "" for c in header_row]
        all_data_rows: list[list[str]] = []
        total = 0

        for row in rows_iter:
            total += 1
            # R1-04: 처리 한도 초과 시 명시적 오류 (조용한 누락 금지)
            if total > _MAX_XLSX_ROWS:
                wb.close()
                return ParsedFileResult(
                    filename=filename,
                    file_key=file_key,
                    status=ParseStatus.ERROR,
                    reason=(
                        f"XLSX_ROW_LIMIT_EXCEEDED — 시트 '{ws.title}' "
                        f"행 수가 상한 {_MAX_XLSX_ROWS}를 초과합니다 "
                        f"(운영 상한 Owner 결정 필요)"
                    ),
                )
            cell_vals: list[str] = []
            for c in row:
                if c is None:
                    cell_vals.append("")
                else:
                    cell_vals.append(str(c))  # 수식 셀: "=SUM(A1:A3)" 형태 그대로
            all_data_rows.append(cell_vals)

        # R1-02: 미리보기 / 전체 분리
        preview_sheets.append(SheetPreview(
            sheet_name=ws.title,
            columns=header,
            rows=all_data_rows[:max_rows],
            total_rows=total,
        ))
        full_sheets.append(SheetFullData(
            sheet_name=ws.title,
            columns=header,
            rows=all_data_rows,
            total_rows=total,
        ))

    wb.close()

    total_all = sum(s.total_rows for s in full_sheets)
    document = ParsedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="xlsx",
        total_rows=total_all,
        xlsx_sheets=full_sheets,
    )

    return ParsedFileResult(
        filename=filename,
        file_key=file_key,
        status=ParseStatus.OK,
        sheets=preview_sheets,
        document=document,
    )


def run_parse(
    source_id: str,
    file_bytes_dict: Dict[str, bytes],
    triage_report: TriageReport,
    max_preview_rows: int = _MAX_PREVIEW_ROWS,
) -> ParseReport:
    """[4] Parse — 각 파일의 내용 추출."""
    file_results: list[ParsedFileResult] = []

    for tr in triage_report.file_results:
        if not tr.parse_eligible:
            file_results.append(ParsedFileResult(
                filename=tr.filename,
                file_key=tr.file_key,
                status=ParseStatus.BLOCKED,
                reason=tr.ineligible_reason,
            ))
            continue

        # R1-01: file_key 기반 조회; 기존 직접 호출 테스트 호환을 위해 filename fallback
        lookup_key = tr.file_key if tr.file_key else tr.filename
        data = file_bytes_dict.get(lookup_key)
        if data is None:
            file_results.append(ParsedFileResult(
                filename=tr.filename,
                file_key=tr.file_key,
                status=ParseStatus.ERROR,
                reason="파일 바이트 없음 — 파이프라인 오류",
            ))
            continue

        if tr.sub_type == "csv":
            file_results.append(
                _parse_csv(tr.filename, data, file_key=tr.file_key, max_rows=max_preview_rows)
            )
        elif tr.sub_type == "xlsx":
            file_results.append(
                _parse_xlsx(tr.filename, data, file_key=tr.file_key, max_rows=max_preview_rows)
            )
        else:
            file_results.append(ParsedFileResult(
                filename=tr.filename,
                file_key=tr.file_key,
                status=ParseStatus.BLOCKED,
                reason=f"PARSE_UNSUPPORTED — {tr.sub_type}",
            ))

    return ParseReport(source_id=source_id, file_results=file_results)
