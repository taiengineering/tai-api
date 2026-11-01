"""OBJ01 [5] Map — ParsedDocument → MappedDocument (WO-036 / R1-REVISED).

구조 변환: ParseReport(csv_rows/xlsx_sheets) + 컬럼명 → MappedDocument(columns + records).
제목 추출: 문서 제목 후보, 시트명, 열 제목, 원본 위치 추출 (WO-036-R1-REVISED).
Canonical 연결: OWNER_DEFERRED — 실제 업체 문서 확보 이후 결정.
PDF/ZIP 등 BLOCKED 파일은 MappingStatus.BLOCKED 로 통과.
"""
from __future__ import annotations

from .models import (
    DocumentTitleInfo,
    MappedDocument,
    MappedFileResult,
    MappingReport,
    MappingStatus,
    ParseReport,
    ParseStatus,
    SourceLocation,
    TitleCandidate,
    TitleStatus,
)


def _single_nonempty(row: list[str]) -> tuple[str, int] | None:
    """행에서 비어있지 않은 셀이 정확히 1개인 경우 (값, 열인덱스) 반환."""
    hits = [(c.strip(), i) for i, c in enumerate(row) if c.strip()]
    return hits[0] if len(hits) == 1 else None


def _is_header_row(row: list[str]) -> bool:
    """행이 표 헤더로 볼 수 있을 만큼 충분한 비어있지 않은 셀이 있는지 (≥ 2).

    제목 후보(단독 셀) 발견 후 다음 행이 실제 열 제목인지 판단에 사용.
    """
    return sum(1 for c in row if c.strip()) >= 2


def _extract_title_info(
    file_key: str,
    filename: str,
    sheet_name: str,
    columns: list[str],
    first_data_rows: list[list[str]],
    sub_type: str,
) -> DocumentTitleInfo:
    """파일·시트 단위 제목 후보 추출.

    CSV: 문서 제목 추출 대상 아님 → NOT_FOUND.
    XLSX: 첫 두 행(행 0 = columns, 행 1 = first_data_rows[0])에서 단독 셀 스캔.
    AI 추론·제목 생성 없음 — 구조 규칙(단독 셀)만 적용.

    열 제목 결정 (WO-036-R2):
      행 0이 제목 후보(단독 셀) + 행 1이 복수 셀 → column_headers = 행 1, row_index = 1.
      그 외 → column_headers = 행 0 (columns 원본), row_index = 0.
    """
    if sub_type != "xlsx":
        return DocumentTitleInfo(
            file_key=file_key,
            filename=filename,
            sheet_name="",
            title_status=TitleStatus.NOT_FOUND,
            candidates=[],
            column_headers=columns,
            column_header_row_index=0,
        )

    candidates: list[TitleCandidate] = []

    # 행 0: parse가 첫 행을 헤더로 읽은 값 — 단독 셀이면 제목 후보
    hit0 = _single_nonempty(columns)
    if hit0:
        value0, col_idx0 = hit0
        candidates.append(TitleCandidate(
            value=value0,
            status=TitleStatus.CANDIDATE,
            source=SourceLocation(
                sheet_name=sheet_name,
                row_index=0,
                col_index=col_idx0,
                cell_value=value0,
            ),
            basis="단독 셀 — 행 0에 비어있지 않은 셀 1개 (표 헤더로 보기 어려움)",
        ))

    # 행 1: 파일의 두 번째 행 — 단독 셀이면 제목 후보
    if first_data_rows:
        hit1 = _single_nonempty(first_data_rows[0])
        if hit1:
            value1, col_idx1 = hit1
            candidates.append(TitleCandidate(
                value=value1,
                status=TitleStatus.CANDIDATE,
                source=SourceLocation(
                    sheet_name=sheet_name,
                    row_index=1,
                    col_index=col_idx1,
                    cell_value=value1,
                ),
                basis="단독 셀 — 행 1에 비어있지 않은 셀 1개",
            ))

    # 실제 열 제목 결정 (WO-036-R2):
    # 행 0이 제목 후보이고 행 1이 복수 셀(≥2) → 행 1이 실제 열 제목
    actual_column_headers = columns
    actual_header_row_index = 0
    if candidates and first_data_rows and _is_header_row(first_data_rows[0]):
        actual_column_headers = first_data_rows[0]
        actual_header_row_index = 1

    title_status = TitleStatus.CANDIDATE if candidates else TitleStatus.NOT_FOUND
    return DocumentTitleInfo(
        file_key=file_key,
        filename=filename,
        sheet_name=sheet_name,
        title_status=title_status,
        candidates=candidates,
        column_headers=actual_column_headers,
        column_header_row_index=actual_header_row_index,
    )


def run_map(
    source_id: str,
    parse_report: ParseReport,
) -> MappingReport:
    """[5] Map — ParsedDocument를 컬럼명 확정 MappedDocument로 변환 + 제목 추출."""
    file_results: list[MappedFileResult] = []

    for fr in parse_report.file_results:
        if fr.status == ParseStatus.BLOCKED:
            file_results.append(MappedFileResult(
                filename=fr.filename,
                file_key=fr.file_key,
                status=MappingStatus.BLOCKED,
                reason=fr.reason,
            ))
            continue

        if fr.status == ParseStatus.ERROR:
            file_results.append(MappedFileResult(
                filename=fr.filename,
                file_key=fr.file_key,
                status=MappingStatus.ERROR,
                reason=fr.reason,
            ))
            continue

        if fr.document is None:
            file_results.append(MappedFileResult(
                filename=fr.filename,
                file_key=fr.file_key,
                status=MappingStatus.ERROR,
                reason="MAP_NO_DOCUMENT — ParsedDocument 없음",
            ))
            continue

        doc = fr.document
        documents: list[MappedDocument] = []

        if doc.sub_type == "csv":
            title_info = _extract_title_info(
                file_key=doc.file_key,
                filename=doc.filename,
                sheet_name="",
                columns=doc.columns,
                first_data_rows=(doc.csv_rows or [])[:1],
                sub_type="csv",
            )
            documents.append(MappedDocument(
                file_key=doc.file_key,
                filename=doc.filename,
                sub_type="csv",
                sheet_name="",
                total_rows=doc.total_rows,
                columns=doc.columns,
                records=doc.csv_rows or [],
                title_info=title_info,
            ))

        elif doc.sub_type == "xlsx":
            for sheet in (doc.xlsx_sheets or []):
                title_info = _extract_title_info(
                    file_key=doc.file_key,
                    filename=doc.filename,
                    sheet_name=sheet.sheet_name,
                    columns=sheet.columns,
                    first_data_rows=sheet.rows[:1],
                    sub_type="xlsx",
                )
                documents.append(MappedDocument(
                    file_key=doc.file_key,
                    filename=doc.filename,
                    sub_type="xlsx",
                    sheet_name=sheet.sheet_name,
                    total_rows=sheet.total_rows,
                    columns=sheet.columns,
                    records=sheet.rows,
                    title_info=title_info,
                ))

        else:
            file_results.append(MappedFileResult(
                filename=fr.filename,
                file_key=fr.file_key,
                status=MappingStatus.ERROR,
                reason=f"MAP_UNSUPPORTED — {doc.sub_type}",
            ))
            continue

        file_results.append(MappedFileResult(
            filename=fr.filename,
            file_key=fr.file_key,
            status=MappingStatus.MAPPED,
            documents=documents,
        ))

    return MappingReport(source_id=source_id, file_results=file_results)
