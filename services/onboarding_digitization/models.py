"""OBJ01 Intake/Preflight/Triage/Parse/Map/Quality 모델 — WO-034/WO-035/WO-036/WO-037.

schema_version = "onboarding-preflight-v0-provisional"
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel


# ── WO-034: Intake + Preflight ────────────────────────────────────────────────

class FileStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED = "BLOCKED"


class CheckDetail(BaseModel):
    name: str
    passed: bool
    detail: str


class SourceFile(BaseModel):
    filename: str
    sha256: str
    byte_size: int
    declared_mime: str
    detected_mime: str
    magic_match: bool
    file_key: str = ""  # R1-01: "{index}:{sha256}" — 동일 파일명 구분


class SourceBundle(BaseModel):
    source_id: str
    company_id: str
    submitted_by: str
    submitted_at: str
    files: List[SourceFile]


class PreflightResult(BaseModel):
    filename: str
    status: FileStatus
    checks: List[CheckDetail]
    file_key: str = ""  # R1-01: 파이프라인 전체 추적용


class PreflightReport(BaseModel):
    source_id: str
    overall_status: str  # "PASS" | "FAIL" | "PARTIAL"
    file_results: List[PreflightResult]
    errors: List[str]


# ── WO-035: [3] Triage + [4] Parse ───────────────────────────────────────────

class TriageCategory(str, Enum):
    SPREADSHEET = "SPREADSHEET"
    PDF_DOCUMENT = "PDF_DOCUMENT"
    ARCHIVE = "ARCHIVE"
    UNKNOWN = "UNKNOWN"


class TriageFileResult(BaseModel):
    filename: str
    category: TriageCategory
    sub_type: str
    parse_eligible: bool
    ineligible_reason: Optional[str] = None
    file_key: str = ""  # R1-01


class TriageReport(BaseModel):
    source_id: str
    file_results: List[TriageFileResult]


class ParseStatus(str, Enum):
    OK = "OK"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class SheetPreview(BaseModel):
    """관리자 미리보기 전용 — max_preview_rows 적용 (R1-02)."""
    sheet_name: str
    columns: List[str]
    rows: List[List[str]]  # 최대 max_preview_rows 행
    total_rows: int  # 실제 전체 행 수


class SheetFullData(BaseModel):
    """XLSX 시트 전체 추출 데이터 — [5] Map 입력용 (R1-02)."""
    sheet_name: str
    columns: List[str]
    rows: List[List[str]]  # 전체 행 (처리 한도 이내)
    total_rows: int


class ParsedDocument(BaseModel):
    """[4] Parse 전체 추출 데이터 — [5] Map 입력용 (R1-02).

    SheetPreview는 관리자 화면 미리보기 전용.
    이 모델은 후속 Map 단계로 전달되는 전체 데이터.
    csv_rows는 헤더 제외 순수 데이터 행 — columns 필드에 헤더 보관 (WO-036 보정).
    """
    file_key: str = ""
    filename: str
    sub_type: str
    total_rows: int
    columns: List[str] = []                       # WO-036: 헤더 열명 (csv_rows는 헤더 제외)
    csv_rows: Optional[List[List[str]]] = None   # CSV 전체 행
    xlsx_sheets: Optional[List[SheetFullData]] = None  # XLSX 전체 시트


class ParsedFileResult(BaseModel):
    filename: str
    file_key: str = ""  # R1-01
    status: ParseStatus
    reason: Optional[str] = None
    sheets: Optional[List[SheetPreview]] = None   # XLSX 미리보기
    preview: Optional[SheetPreview] = None        # CSV 미리보기
    document: Optional[ParsedDocument] = None     # 전체 추출 데이터 (R1-02)


class ParseReport(BaseModel):
    source_id: str
    file_results: List[ParsedFileResult]


# ── WO-036: [5] Map ──────────────────────────────────────────────────────────

class MappingStatus(str, Enum):
    MAPPED = "MAPPED"    # 구조 변환 완료 (파일 처리 성공 — Canonical 연결 아님)
    BLOCKED = "BLOCKED"  # Parse BLOCKED → Map 진입 불가
    ERROR = "ERROR"      # Parse ERROR 또는 Map 자체 오류


# ── WO-036-R1-REVISED: 문서 제목·헤더 추출 ────────────────────────────────────

class TitleStatus(str, Enum):
    EXTRACTED = "EXTRACTED"  # 실제 제목 텍스트 추출됨, 출처 위치 확인
    CANDIDATE = "CANDIDATE"  # 제목일 가능성 있으나 확정 근거 부족
    NOT_FOUND = "NOT_FOUND"  # 추출 가능한 제목 없음
    BLOCKED = "BLOCKED"      # 파일 처리 자체 차단


class SourceLocation(BaseModel):
    """원본 파일 내 위치 — 제목 후보 추적용."""
    sheet_name: str = ""   # XLSX 시트명 (CSV: "")
    row_index: int         # 0-based 원본 파일 행 인덱스
    col_index: int = 0     # 0-based 열 인덱스
    cell_value: str        # 원본 셀 값


class TitleCandidate(BaseModel):
    value: str
    status: TitleStatus
    source: SourceLocation
    basis: str  # 어떤 근거로 후보 판단했는지 (AI 추론 아님 — 구조 규칙 설명)


class DocumentTitleInfo(BaseModel):
    """파일 또는 시트 단위 제목 추출 결과 — WO-036-R1-REVISED."""
    file_key: str = ""
    filename: str
    sheet_name: str = ""          # XLSX 시트별 / CSV: ""
    title_status: TitleStatus
    candidates: List[TitleCandidate]
    column_headers: List[str]     # 표의 열 제목 (parse에서 추출된 columns)
    column_header_row_index: int = 0  # 현재 구현: 항상 0 (parse 첫 행 = 헤더)


class MappedDocument(BaseModel):
    """[5] Map 결과 단위 — 컬럼명 확정 + 행 데이터 정렬.

    CSV: 1개 / XLSX: 시트당 1개.
    columns + records 조합이 Map 이후 단계([6] Normalize)의 입력.
    """
    file_key: str = ""
    filename: str
    sub_type: str
    sheet_name: str = ""  # CSV: "", XLSX: 시트명
    total_rows: int
    columns: List[str]
    records: List[List[str]]  # columns 순서대로 정렬된 행 데이터 (헤더 미포함)
    title_info: Optional[DocumentTitleInfo] = None  # WO-036-R1-REVISED


class MappedFileResult(BaseModel):
    filename: str
    file_key: str = ""
    status: MappingStatus
    reason: Optional[str] = None
    documents: Optional[List[MappedDocument]] = None  # OK시 파일당 1+개


class MappingReport(BaseModel):
    source_id: str
    file_results: List[MappedFileResult]


# ── WO-037: [7] Quality ──────────────────────────────────────────────────────

class QualityStatus(str, Enum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class QualityIssue(BaseModel):
    code: str
    severity: IssueSeverity
    file_key: str = ""
    filename: str
    sheet_name: str = ""
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    message: str


class QualityFileResult(BaseModel):
    file_key: str = ""
    filename: str
    status: QualityStatus
    checked_items: List[str]
    issues: List[QualityIssue]


class QualityReport(BaseModel):
    source_id: str
    overall_status: QualityStatus
    total_files: int
    passed_files: int
    review_required_files: int
    failed_files: int
    not_evaluated_files: int
    file_results: List[QualityFileResult]


# ── WO-038: [8] Package ──────────────────────────────────────────────────────

class PackageProcessingStatus(str, Enum):
    COMPLETE = "COMPLETE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class StageStatus(BaseModel):
    intake: str
    preflight: str
    triage: str
    parse: str
    structural_map: str
    normalize: str
    quality: str


class ExtractedSheet(BaseModel):
    sheet_name: str
    column_headers: List[str]
    column_header_row_index: int
    records: List[List[str]]
    total_rows: int


class ExtractedDocument(BaseModel):
    file_key: str
    filename: str
    sub_type: str
    status: str
    reason: Optional[str] = None
    sheets: Optional[List[ExtractedSheet]] = None


class TitleEvidence(BaseModel):
    file_key: str
    filename: str
    sheet_name: str
    title_status: str
    candidates: List[TitleCandidate]
    column_headers: List[str]
    column_header_row_index: int


class DeferredItem(BaseModel):
    file_key: str
    filename: str
    reason: str
    stage: str


class PackageIntegrity(BaseModel):
    source_id_consistent: bool
    file_count: int
    file_keys: List[str]
    sha256_map: Dict[str, str]
    content_hash: str


class CanonicalEvidencePackage(BaseModel):
    package_id: str
    schema_version: str
    source_id: str
    company_id: str
    created_at: str
    processing_status: PackageProcessingStatus
    stage_status: StageStatus
    source_manifest: SourceBundle
    extracted_documents: List[ExtractedDocument]
    title_and_header_evidence: List[TitleEvidence]
    quality_report: Optional[QualityReport] = None
    deferred_items: List[DeferredItem]
    integrity: PackageIntegrity


# ── 응답 래퍼 — 항상 마지막에 정의 ───────────────────────────────────────────────

class IntakePreflightResponse(BaseModel):
    schema_version: str
    bundle: SourceBundle
    preflight: PreflightReport
    triage: Optional[TriageReport] = None
    parsed: Optional[ParseReport] = None
    mapped: Optional[MappingReport] = None
    quality: Optional[QualityReport] = None  # WO-037
    package: Optional[CanonicalEvidencePackage] = None  # WO-038
