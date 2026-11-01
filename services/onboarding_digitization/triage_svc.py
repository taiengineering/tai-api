"""OBJ01 [3] Triage — 파일 분류 및 파서 적격성 판정 (WO-035)."""
from __future__ import annotations

import os
from typing import List

from .models import (
    FileStatus,
    PreflightResult,
    TriageCategory,
    TriageFileResult,
    TriageReport,
)

_EXT_CATEGORY: dict[str, tuple[TriageCategory, str]] = {
    ".xlsx": (TriageCategory.SPREADSHEET, "xlsx"),
    ".csv":  (TriageCategory.SPREADSHEET, "csv"),
    ".pdf":  (TriageCategory.PDF_DOCUMENT, "pdf"),
    ".zip":  (TriageCategory.ARCHIVE,      "zip"),
}

_PARSE_ELIGIBLE_EXTS = frozenset({".xlsx", ".csv"})

_BLOCKED_REASON: dict[str, str] = {
    ".pdf": "PDF_PARSE_BLOCKED — 텍스트 파서 미탑재 (의존성 없음, [4] Parse 이연)",
    ".zip": "ZIP_PARSE_BLOCKED — 내부 파일 처리 Owner 결정 대기",
}


def run_triage(
    source_id: str,
    preflight_results: List[PreflightResult],
) -> TriageReport:
    """[3] Triage Census — 각 파일의 범주·파서 적격성 판정."""
    file_results: list[TriageFileResult] = []

    for pf in preflight_results:
        ext = os.path.splitext(pf.filename.lower())[1]
        category, sub_type = _EXT_CATEGORY.get(
            ext, (TriageCategory.UNKNOWN, ext.lstrip(".") or "unknown")
        )

        if pf.status != FileStatus.PASS:
            file_results.append(TriageFileResult(
                filename=pf.filename,
                category=category,
                sub_type=sub_type,
                parse_eligible=False,
                ineligible_reason=f"PREFLIGHT_{pf.status.value} — Parse 진입 불가",
                file_key=pf.file_key,
            ))
            continue

        parse_eligible = ext in _PARSE_ELIGIBLE_EXTS
        ineligible_reason: str | None = None
        if not parse_eligible:
            ineligible_reason = _BLOCKED_REASON.get(
                ext, f"PARSE_UNSUPPORTED — 알 수 없는 형식 ({ext or '확장자 없음'})"
            )

        file_results.append(TriageFileResult(
            filename=pf.filename,
            category=category,
            sub_type=sub_type,
            parse_eligible=parse_eligible,
            ineligible_reason=ineligible_reason,
            file_key=pf.file_key,
        ))

    return TriageReport(source_id=source_id, file_results=file_results)
