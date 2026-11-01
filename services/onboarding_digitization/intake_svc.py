"""OBJ01 Intake + Preflight 서비스 — WO-034.

파이프라인 [1] Intake Manifest + [2] Preflight Census.
합성 데이터 전용 — 실자료 처리 차단 (GR3-H05 미해소).
"""
from __future__ import annotations

import hashlib
import io
import os
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile

from .models import (
    CheckDetail,
    FileStatus,
    PreflightReport,
    PreflightResult,
    SourceBundle,
    SourceFile,
)

_MAX_BYTES: int = 52_428_800  # 50 MiB — GR3-H03 OWNER_APPROVED
_MAX_ZIP_ENTRIES: int = 10_000  # central directory scan 상한 — OOM 방어 (R1-04)
_SCHEMA_VERSION = "onboarding-preflight-v0-provisional"

_XLSX_MIMES = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",
})
_CSV_MIMES = frozenset({
    "text/csv",
    "text/plain",
    "application/csv",
    "application/octet-stream",
})
_PDF_MIMES = frozenset({
    "application/pdf",
    "application/octet-stream",
})
_ZIP_MIMES = frozenset({
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
})

_UNSUPPORTED_EXTENSIONS = frozenset({".hwp", ".hwpx"})


def _verify_company_exists(company_id: str, supabase) -> None:
    """companies 테이블 실존 확인 (C01: _ensure_own_company() 재사용 금지 — ALL 범위 우회 문제)."""
    try:
        res = (
            supabase.table("companies")
            .select("id")
            .eq("id", company_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"회사 확인 실패: {exc}") from exc
    if not res.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")


async def _read_with_size_limit(upload_file: UploadFile) -> bytes:
    """파일 읽기 + 크기 제한 (C02: Content-Length 헤더 단독 신뢰 금지).

    64KB 청크로 읽으며 누적 바이트가 _MAX_BYTES 초과 시 413.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload_file.read(65_536)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"파일 크기 초과 — 상한 {_MAX_BYTES:,} bytes (50 MiB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _detect_mime(header: bytes) -> str:
    """magic bytes 판별 (최초 8바이트)."""
    if header[:5] == b"%PDF-":
        return "application/pdf"
    if header[:4] == b"PK\x03\x04":
        return "application/zip"  # ZIP 또는 OOXML (XLSX 포함)
    return "application/octet-stream"


def _is_ooxml(data: bytes) -> bool:
    """어떤 OOXML 형식이든 감지 — [Content_Types].xml 존재 확인.

    zipfile.namelist()은 central directory만 읽음 — 압축 해제 없음 (C03).
    항목 수 > _MAX_ZIP_ENTRIES 시 False (R1-04 OOM 방어).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
        if len(names) > _MAX_ZIP_ENTRIES:
            return False
        return "[Content_Types].xml" in names
    except Exception:
        return False


def _is_xlsx_workbook(data: bytes) -> bool:
    """XLSX 고유 구조 확인: [Content_Types].xml + xl/workbook.xml.

    DOCX/PPTX는 [Content_Types].xml 있어도 xl/workbook.xml 없음 (R1-03).
    항목 수 > _MAX_ZIP_ENTRIES 시 False (R1-04).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
        if len(names) > _MAX_ZIP_ENTRIES:
            return False
        return "[Content_Types].xml" in names and "xl/workbook.xml" in names
    except Exception:
        return False


def _ext(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


# ── 파일별 Preflight ──────────────────────────────────────────────────────────

def _preflight_pdf(filename: str, data: bytes, declared_mime: str) -> PreflightResult:
    """PDF Preflight — 헤더·구조 검사. OCR/텍스트 레이어 판별은 [4] Parse 단계 (C04)."""
    checks: list[CheckDetail] = []
    header = data[:8]

    magic_ok = header[:5] == b"%PDF-"
    checks.append(CheckDetail(
        name="MAGIC_BYTES",
        passed=magic_ok,
        detail="PDF 헤더(%PDF-) 확인" if magic_ok else "PDF 헤더 불일치",
    ))
    if not magic_ok:
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    checks.append(CheckDetail(
        name="MIME_DECLARED",
        passed=declared_mime in _PDF_MIMES,
        detail=f"선언 MIME: {declared_mime}",
    ))

    eof_ok = b"%%EOF" in data[-1024:] or b"%EOF" in data[-1024:]
    checks.append(CheckDetail(
        name="PDF_STRUCTURE",
        passed=eof_ok,
        detail="PDF %%EOF 마커 확인" if eof_ok else "PDF %%EOF 마커 없음 (손상 의심)",
    ))

    # 텍스트 레이어 유무는 [4] Parse 단계 — Preflight에서 OCR 판정 금지 (C04)
    checks.append(CheckDetail(
        name="TEXT_LAYER_DEFERRED",
        passed=True,
        detail="텍스트 레이어 확인은 [4] Parse 단계에서 수행 — Preflight OCR 판정 보류",
    ))

    # TEXT_LAYER_DEFERRED는 항상 passed=True — 모든 검사 결과를 status에 반영 (R1-03)
    status = FileStatus.PASS if all(c.passed for c in checks) else FileStatus.FAIL
    return PreflightResult(filename=filename, status=status, checks=checks)


def _preflight_xlsx(filename: str, data: bytes, declared_mime: str) -> PreflightResult:
    """XLSX Preflight — OOXML 구조 확인 (C03: PK 헤더만으로 ZIP과 구분 불가)."""
    checks: list[CheckDetail] = []
    header = data[:8]

    zip_magic_ok = header[:4] == b"PK\x03\x04"
    checks.append(CheckDetail(
        name="MAGIC_BYTES",
        passed=zip_magic_ok,
        detail="ZIP/OOXML 헤더(PK) 확인" if zip_magic_ok else "ZIP/OOXML 헤더 불일치",
    ))
    if not zip_magic_ok:
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    # XLSX 고유 구조: [Content_Types].xml + xl/workbook.xml (R1-03: DOCX 위장 방지)
    xlsx_ok = _is_xlsx_workbook(data)
    checks.append(CheckDetail(
        name="OOXML_STRUCTURE",
        passed=xlsx_ok,
        detail="XLSX 구조 확인 ([Content_Types].xml + xl/workbook.xml)" if xlsx_ok
               else "XLSX 구조 불일치 — DOCX·PPTX·일반 ZIP일 수 있음 (R1-03)",
    ))
    if not xlsx_ok:
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    checks.append(CheckDetail(
        name="MIME_DECLARED",
        passed=declared_mime in _XLSX_MIMES,
        detail=f"선언 MIME: {declared_mime}",
    ))

    status = FileStatus.PASS if all(c.passed for c in checks) else FileStatus.FAIL
    return PreflightResult(filename=filename, status=status, checks=checks)


def _preflight_csv(filename: str, data: bytes, declared_mime: str) -> PreflightResult:
    """CSV Preflight — CSV는 magic bytes 없음, 인코딩·비어있음 검사 (C03)."""
    checks: list[CheckDetail] = []

    # CSV는 magic bytes 없음 — magic_match=False는 손상이 아닌 "확인 불가" (R1-03 P2)
    checks.append(CheckDetail(
        name="MAGIC_BYTES",
        passed=True,
        detail="CSV는 magic bytes 없음 — magic_match=False는 파일 손상 아닌 확인 불가 상태",
    ))

    checks.append(CheckDetail(
        name="MIME_DECLARED",
        passed=declared_mime in _CSV_MIMES,
        detail=f"선언 MIME: {declared_mime}",
    ))

    not_empty = len(data) > 0
    checks.append(CheckDetail(
        name="NOT_EMPTY",
        passed=not_empty,
        detail="내용 있음" if not_empty else "빈 파일",
    ))
    if not not_empty:
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    encoding_ok = False
    encoding_used = "unknown"
    for enc in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
        try:
            data.decode(enc)
            encoding_ok = True
            encoding_used = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    checks.append(CheckDetail(
        name="ENCODING",
        passed=encoding_ok,
        detail=f"인코딩: {encoding_used}" if encoding_ok else "지원 인코딩 디코딩 실패",
    ))

    # 모든 검사 결과를 status에 반영 (R1-03: MIME 불일치도 FAIL)
    status = FileStatus.PASS if all(c.passed for c in checks) else FileStatus.FAIL
    return PreflightResult(filename=filename, status=status, checks=checks)


def _preflight_zip(filename: str, data: bytes, declared_mime: str) -> PreflightResult:
    """ZIP Preflight — 수신·구조 안전 검사. 내부 처리 차단 (OWNER_DECISION_REQUIRED)."""
    checks: list[CheckDetail] = []
    header = data[:8]

    zip_magic_ok = header[:4] == b"PK\x03\x04"
    checks.append(CheckDetail(
        name="MAGIC_BYTES",
        passed=zip_magic_ok,
        detail="ZIP 헤더(PK) 확인" if zip_magic_ok else "ZIP 헤더 불일치",
    ))
    if not zip_magic_ok:
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    # OOXML이면 XLSX — 확장자 안내
    if _is_ooxml(data):
        checks.append(CheckDetail(
            name="FORMAT_IDENTITY",
            passed=False,
            detail="이 파일은 XLSX(OOXML) 형식입니다. 확장자를 .xlsx로 변경하세요.",
        ))
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    checks.append(CheckDetail(
        name="FORMAT_IDENTITY",
        passed=True,
        detail="ZIP 형식 확인 (OOXML 아님)",
    ))

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
        member_count = len(names)
        if member_count > _MAX_ZIP_ENTRIES:
            checks.append(CheckDetail(
                name="ZIP_STRUCTURE",
                passed=False,
                detail=f"ZIP 항목 수 초과 ({member_count} > {_MAX_ZIP_ENTRIES}) — R1-04 OOM 방어",
            ))
            return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)
        checks.append(CheckDetail(
            name="ZIP_STRUCTURE",
            passed=True,
            detail=f"ZIP 구조 정상 — 멤버 {member_count}개 확인",
        ))
    except zipfile.BadZipFile:
        checks.append(CheckDetail(
            name="ZIP_STRUCTURE",
            passed=False,
            detail="ZIP 구조 오류 (손상된 파일)",
        ))
        return PreflightResult(filename=filename, status=FileStatus.FAIL, checks=checks)

    # 내부 파일 처리 차단 — ZIP 내부 제한값 OWNER_DECISION_REQUIRED
    checks.append(CheckDetail(
        name="ZIP_CONTENT_PROCESSING",
        passed=False,
        detail="ZIP 내부 파일 처리 차단 — 내부 제한값(멤버수·비압축크기·압축비율) Owner 결정 대기",
    ))

    return PreflightResult(filename=filename, status=FileStatus.BLOCKED, checks=checks)


def _preflight_file(filename: str, data: bytes, declared_mime: str) -> PreflightResult:
    """단일 파일 Preflight 분기 진입점."""
    ext = _ext(filename)

    if ext in _UNSUPPORTED_EXTENSIONS:
        return PreflightResult(
            filename=filename,
            status=FileStatus.UNSUPPORTED,
            checks=[CheckDetail(
                name="FORMAT_SUPPORT",
                passed=False,
                detail=f"지원하지 않는 형식 ({ext})",
            )],
        )

    size_ok = len(data) <= _MAX_BYTES
    if not size_ok:
        return PreflightResult(
            filename=filename,
            status=FileStatus.FAIL,
            checks=[CheckDetail(
                name="SIZE_LIMIT",
                passed=False,
                detail=f"{len(data):,} bytes — 상한 {_MAX_BYTES:,} bytes 초과",
            )],
        )

    if ext == ".pdf":
        return _preflight_pdf(filename, data, declared_mime)
    if ext == ".xlsx":
        return _preflight_xlsx(filename, data, declared_mime)
    if ext == ".csv":
        return _preflight_csv(filename, data, declared_mime)
    if ext == ".zip":
        return _preflight_zip(filename, data, declared_mime)

    return PreflightResult(
        filename=filename,
        status=FileStatus.UNSUPPORTED,
        checks=[CheckDetail(
            name="FORMAT_SUPPORT",
            passed=False,
            detail=f"알 수 없는 파일 형식 ({ext or '확장자 없음'})",
        )],
    )


# ── 메인 실행 ──────────────────────────────────────────────────────────────────

async def run_intake_preflight(
    company_id: str,
    actor_id: str,
    upload_files: List[UploadFile],
    supabase,
    source_id: Optional[str] = None,
) -> Tuple[SourceBundle, PreflightReport, Dict[str, bytes]]:
    """[1] Intake Manifest + [2] Preflight Census 실행.

    source_id는 호출자가 사전 생성 가능 (R1-05: INTAKE_RECEIVED 감사와 동일 ID 추적).
    None 전달 시 내부 생성.
    """
    if source_id is None:
        source_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()

    source_files: list[SourceFile] = []
    preflight_results: list[PreflightResult] = []
    errors: list[str] = []
    file_bytes_dict: dict[str, bytes] = {}  # R1-01: key = "{index}:{sha256}"

    for i, upload_file in enumerate(upload_files):
        filename = upload_file.filename or "unknown"
        declared_mime = upload_file.content_type or "application/octet-stream"

        try:
            data = await _read_with_size_limit(upload_file)
        except HTTPException:
            raise  # 413 그대로 전파
        except Exception as exc:
            errors.append(f"{filename}: 읽기 실패 — {exc}")
            continue

        sha = _sha256(data)
        file_key = f"{i}:{sha}"  # R1-01: 동일 파일명이어도 고유 식별
        file_bytes_dict[file_key] = data
        detected_mime = _detect_mime(data[:8])
        magic_match = detected_mime != "application/octet-stream"

        source_files.append(SourceFile(
            filename=filename,
            sha256=sha,
            byte_size=len(data),
            declared_mime=declared_mime,
            detected_mime=detected_mime,
            magic_match=magic_match,
            file_key=file_key,
        ))

        pf = _preflight_file(filename, data, declared_mime)
        preflight_results.append(PreflightResult(
            filename=pf.filename,
            status=pf.status,
            checks=pf.checks,
            file_key=file_key,
        ))

    # overall_status 계산
    statuses = {r.status for r in preflight_results}
    if not preflight_results:
        overall = "FAIL"
    elif statuses == {FileStatus.PASS}:
        overall = "PASS"
    elif FileStatus.FAIL in statuses and FileStatus.PASS not in statuses and FileStatus.BLOCKED not in statuses:
        overall = "FAIL"
    else:
        overall = "PARTIAL"

    bundle = SourceBundle(
        source_id=source_id,
        company_id=company_id,
        submitted_by=actor_id,
        submitted_at=now,
        files=source_files,
    )
    report = PreflightReport(
        source_id=source_id,
        overall_status=overall,
        file_results=preflight_results,
        errors=errors,
    )

    return bundle, report, file_bytes_dict
