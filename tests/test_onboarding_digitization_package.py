"""WO-038/R1 [8] Package — CanonicalEvidencePackage 생성 단위 테스트 P01~P13 + R1-T02~R1-T07."""
from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException

from services.onboarding_digitization.models import (
    CanonicalEvidencePackage,
    DocumentTitleInfo,
    MappedDocument,
    MappedFileResult,
    MappingReport,
    MappingStatus,
    PackageProcessingStatus,
    ParsedDocument,
    ParsedFileResult,
    ParseReport,
    ParseStatus,
    PreflightReport,
    PreflightResult,
    FileStatus,
    QualityReport,
    QualityStatus,
    QualityFileResult,
    SourceBundle,
    SourceFile,
    SourceLocation,
    TitleCandidate,
    TitleStatus,
    TriageCategory,
    TriageFileResult,
    TriageReport,
)
from services.onboarding_digitization.package_svc import (
    _PACKAGE_SCHEMA_VERSION,
    _compute_full_content_hash,
    run_package,
)


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────────

def _make_source_file(
    filename: str = "test.csv",
    sha256: str = "aabbcc",
    file_key: str = "0:aabbcc",
) -> SourceFile:
    return SourceFile(
        filename=filename,
        sha256=sha256,
        byte_size=100,
        declared_mime="text/csv",
        detected_mime="text/csv",
        magic_match=True,
        file_key=file_key,
    )


def _make_bundle(
    files: list[SourceFile] | None = None,
    source_id: str = "src-pkg",
    company_id: str = "cmp-001",
) -> SourceBundle:
    if files is None:
        files = [_make_source_file()]
    return SourceBundle(
        source_id=source_id,
        company_id=company_id,
        submitted_by="user-1",
        submitted_at="2026-01-01T00:00:00Z",
        files=files,
    )


def _make_preflight(source_id: str = "src-pkg") -> PreflightReport:
    return PreflightReport(
        source_id=source_id,
        overall_status="PASS",
        file_results=[
            PreflightResult(
                filename="test.csv",
                status=FileStatus.PASS,
                checks=[],
                file_key="0:aabbcc",
            )
        ],
        errors=[],
    )


def _make_triage(source_id: str = "src-pkg") -> TriageReport:
    return TriageReport(
        source_id=source_id,
        file_results=[
            TriageFileResult(
                filename="test.csv",
                category=TriageCategory.SPREADSHEET,
                sub_type="csv",
                parse_eligible=True,
                file_key="0:aabbcc",
            )
        ],
    )


def _make_parse(
    source_id: str = "src-pkg",
    status: ParseStatus = ParseStatus.OK,
    filename: str = "test.csv",
    file_key: str = "0:aabbcc",
) -> ParseReport:
    doc = ParsedDocument(
        file_key=file_key,
        filename=filename,
        sub_type="csv",
        total_rows=2,
        columns=["이름", "수량"],
        csv_rows=[["톨루엔", "100"], ["벤젠", "50"]],
    ) if status == ParseStatus.OK else None
    return ParseReport(
        source_id=source_id,
        file_results=[
            ParsedFileResult(
                filename=filename,
                file_key=file_key,
                status=status,
                reason="PDF 차단" if status == ParseStatus.BLOCKED else None,
                document=doc,
            )
        ],
    )


def _make_mapping(
    source_id: str = "src-pkg",
    status: MappingStatus = MappingStatus.MAPPED,
    filename: str = "test.csv",
    file_key: str = "0:aabbcc",
    with_title: bool = False,
) -> MappingReport:
    if status == MappingStatus.MAPPED:
        title_info = None
        if with_title:
            title_info = DocumentTitleInfo(
                file_key=file_key,
                filename=filename,
                sheet_name="",
                title_status=TitleStatus.EXTRACTED,
                candidates=[
                    TitleCandidate(
                        value="화학물질 현황",
                        status=TitleStatus.EXTRACTED,
                        source=SourceLocation(
                            sheet_name="",
                            row_index=0,
                            col_index=0,
                            cell_value="화학물질 현황",
                        ),
                        basis="첫 행 단일 셀 — 열 수 불일치",
                    )
                ],
                column_headers=["이름", "수량"],
                column_header_row_index=0,
            )
        docs = [
            MappedDocument(
                file_key=file_key,
                filename=filename,
                sub_type="csv",
                sheet_name="",
                total_rows=2,
                columns=["이름", "수량"],
                records=[["톨루엔", "100"], ["벤젠", "50"]],
                title_info=title_info,
            )
        ]
    else:
        docs = None

    return MappingReport(
        source_id=source_id,
        file_results=[
            MappedFileResult(
                filename=filename,
                file_key=file_key,
                status=status,
                reason="PDF 차단" if status == MappingStatus.BLOCKED else None,
                documents=docs,
            )
        ],
    )


def _make_quality(
    source_id: str = "src-pkg",
    overall: QualityStatus = QualityStatus.PASS,
) -> QualityReport:
    return QualityReport(
        source_id=source_id,
        overall_status=overall,
        total_files=1,
        passed_files=1 if overall == QualityStatus.PASS else 0,
        review_required_files=1 if overall == QualityStatus.REVIEW_REQUIRED else 0,
        failed_files=1 if overall == QualityStatus.FAIL else 0,
        not_evaluated_files=1 if overall == QualityStatus.NOT_EVALUATED else 0,
        file_results=[
            QualityFileResult(
                file_key="0:aabbcc",
                filename="test.csv",
                status=overall,
                checked_items=["Q01", "Q02", "Q03"],
                issues=[],
            )
        ],
    )


def _full_pipeline(
    source_id: str = "src-pkg",
    quality_overall: QualityStatus = QualityStatus.PASS,
    with_quality: bool = True,
):
    bundle = _make_bundle(source_id=source_id)
    preflight = _make_preflight(source_id)
    triage = _make_triage(source_id)
    parse = _make_parse(source_id)
    mapping = _make_mapping(source_id)
    quality = _make_quality(source_id, quality_overall) if with_quality else None
    return bundle, preflight, triage, parse, mapping, quality


# ── P01: run_package returns CanonicalEvidencePackage ────────────────────────

def test_p01_returns_canonical_evidence_package():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert isinstance(pkg, CanonicalEvidencePackage)


# ── P02: schema_version ───────────────────────────────────────────────────────

def test_p02_schema_version():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert pkg.schema_version == _PACKAGE_SCHEMA_VERSION
    assert pkg.schema_version == "digitization-package-v0-provisional"


# ── P03: normalize always DEFERRED ───────────────────────────────────────────

def test_p03_normalize_always_deferred():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert pkg.stage_status.normalize == "DEFERRED"


# ── P04: stage_status.quality reflects quality_report ─────────────────────────

def test_p04_stage_status_quality_from_report():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline(
        quality_overall=QualityStatus.REVIEW_REQUIRED
    )
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert pkg.stage_status.quality == "REVIEW_REQUIRED"


def test_p04b_stage_status_quality_not_run_when_no_quality():
    bundle, preflight, triage, parse, mapping, _ = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, None)
    assert pkg.stage_status.quality == "NOT_RUN"


# ── P05: PASS quality + DEFERRED normalize → REVIEW_REQUIRED ─────────────────

def test_p05_pass_quality_deferred_normalize_gives_review_required():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline(
        quality_overall=QualityStatus.PASS
    )
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert pkg.processing_status == PackageProcessingStatus.REVIEW_REQUIRED


# ── P06: FAIL quality → processing_status FAIL ───────────────────────────────

def test_p06_fail_quality_gives_fail():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline(
        quality_overall=QualityStatus.FAIL
    )
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert pkg.processing_status == PackageProcessingStatus.FAIL


# ── P07: REVIEW_REQUIRED quality → processing_status REVIEW_REQUIRED ─────────

def test_p07_review_required_quality_gives_review_required():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline(
        quality_overall=QualityStatus.REVIEW_REQUIRED
    )
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert pkg.processing_status == PackageProcessingStatus.REVIEW_REQUIRED


# ── P08: source SHA256 present in integrity.sha256_map ───────────────────────

def test_p08_sha256_in_integrity():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    assert "0:aabbcc" in pkg.integrity.sha256_map
    assert pkg.integrity.sha256_map["0:aabbcc"] == "aabbcc"
    assert pkg.integrity.file_count == 1
    assert pkg.integrity.source_id_consistent is True


# ── P09: content_hash is deterministic ───────────────────────────────────────

def test_p09_content_hash_deterministic():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg1 = run_package(bundle, preflight, triage, parse, mapping, quality)
    pkg2 = run_package(bundle, preflight, triage, parse, mapping, quality)
    # package_id and created_at differ — but content_hash must be identical
    assert pkg1.integrity.content_hash == pkg2.integrity.content_hash
    assert pkg1.package_id != pkg2.package_id


def test_p09b_content_hash_full_payload():
    """R1-01: content_hash는 전체 내용 기반 — _compute_full_content_hash와 일치."""
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)
    expected = _compute_full_content_hash(pkg)
    assert pkg.integrity.content_hash == expected


# ── P10: BLOCKED parse file → deferred_items stage="parse" ───────────────────

def test_p10_blocked_parse_file_in_deferred():
    sf = _make_source_file(filename="scan.pdf", sha256="ddeeff", file_key="0:ddeeff")
    bundle = _make_bundle(files=[sf], source_id="src-blk")
    # R1-02: preflight must cover the same file_key as source_bundle
    preflight = PreflightReport(
        source_id="src-blk",
        overall_status="PASS",
        file_results=[
            PreflightResult(
                filename="scan.pdf",
                status=FileStatus.PASS,
                checks=[],
                file_key="0:ddeeff",
            )
        ],
        errors=[],
    )
    triage = TriageReport(
        source_id="src-blk",
        file_results=[
            TriageFileResult(
                filename="scan.pdf",
                category=TriageCategory.PDF_DOCUMENT,
                sub_type="pdf",
                parse_eligible=False,
                ineligible_reason="PDF",
                file_key="0:ddeeff",
            )
        ],
    )
    parse = _make_parse("src-blk", status=ParseStatus.BLOCKED, filename="scan.pdf", file_key="0:ddeeff")
    mapping = MappingReport(
        source_id="src-blk",
        file_results=[
            MappedFileResult(
                filename="scan.pdf",
                file_key="0:ddeeff",
                status=MappingStatus.BLOCKED,
                reason="PDF 차단",
                documents=None,
            )
        ],
    )
    pkg = run_package(bundle, preflight, triage, parse, mapping, None)

    parse_deferred = [d for d in pkg.deferred_items if d.stage == "parse"]
    assert len(parse_deferred) == 1
    assert parse_deferred[0].file_key == "0:ddeeff"
    assert parse_deferred[0].filename == "scan.pdf"


# ── P11: MAPPED file → deferred_items includes stage="normalize" ──────────────

def test_p11_mapped_file_has_normalize_deferred():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)

    normalize_deferred = [d for d in pkg.deferred_items if d.stage == "normalize"]
    assert len(normalize_deferred) == 1
    assert normalize_deferred[0].file_key == "0:aabbcc"
    assert "DEFERRED" in normalize_deferred[0].reason


# ── P12: all files have canonical_mapping deferred item ───────────────────────

def test_p12_canonical_mapping_deferred_for_all_files():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    pkg = run_package(bundle, preflight, triage, parse, mapping, quality)

    cm_deferred = [d for d in pkg.deferred_items if d.stage == "canonical_mapping"]
    assert len(cm_deferred) == len(bundle.files)
    assert cm_deferred[0].file_key == "0:aabbcc"
    assert "OWNER_DEFERRED" in cm_deferred[0].reason


# ── P13: oversized package → HTTPException 413 ───────────────────────────────

def test_p13_size_limit_raises_413():
    bundle, preflight, triage, parse, mapping, quality = _full_pipeline()
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, quality, max_serialized_bytes=10)
    assert exc_info.value.status_code == 413


# ── R1-T02: 셀 값 변경 → 다른 해시 ──────────────────────────────────────────────

def test_r1t02_cell_mutation_changes_hash():
    bundle, preflight, triage, parse, mapping_a, quality = _full_pipeline()
    # 두 번째 mapping: 셀 값 하나 변경 (100 → 900)
    mapping_b = _make_mapping(source_id="src-pkg")
    mapping_b.file_results[0].documents[0].records[0][1] = "900"

    pkg_a = run_package(bundle, preflight, triage, parse, mapping_a, quality)
    pkg_b = run_package(bundle, preflight, triage, parse, mapping_b, quality)
    assert pkg_a.integrity.content_hash != pkg_b.integrity.content_hash


# ── R1-T03: Quality 상세 오류 추가 → 다른 해시 ────────────────────────────────────

def test_r1t03_quality_issue_mutation_changes_hash():
    from services.onboarding_digitization.models import IssueSeverity, QualityIssue

    bundle, preflight, triage, parse, mapping, quality_a = _full_pipeline()
    # quality_b: 동일하지만 오류 1건 추가
    quality_b = _make_quality(source_id="src-pkg", overall=QualityStatus.REVIEW_REQUIRED)
    quality_b.file_results[0].issues.append(
        QualityIssue(
            code="Q03-DUPLICATE_HEADER",
            severity=IssueSeverity.WARNING,
            file_key="0:aabbcc",
            filename="test.csv",
            sheet_name="",
            message="중복 열 제목",
        )
    )

    pkg_a = run_package(bundle, preflight, triage, parse, mapping, quality_a)
    pkg_b = run_package(bundle, preflight, triage, parse, mapping, quality_b)
    assert pkg_a.integrity.content_hash != pkg_b.integrity.content_hash


# ── R1-T04: 제목 후보 변경 → 다른 해시 ───────────────────────────────────────────

def test_r1t04_title_candidate_mutation_changes_hash():
    bundle, preflight, triage, parse, _, quality = _full_pipeline()
    mapping_a = _make_mapping(source_id="src-pkg", with_title=True)
    mapping_b = _make_mapping(source_id="src-pkg", with_title=True)
    # 제목 후보 값 변경
    mapping_b.file_results[0].documents[0].title_info.candidates[0].value = "변경된 제목"

    pkg_a = run_package(bundle, preflight, triage, parse, mapping_a, quality)
    pkg_b = run_package(bundle, preflight, triage, parse, mapping_b, quality)
    assert pkg_a.integrity.content_hash != pkg_b.integrity.content_hash


# ── R1-T05: source_id 불일치 → HTTPException 422 ──────────────────────────────

def test_r1t05_source_id_mismatch_raises_422():
    bundle = _make_bundle(source_id="bundle-sid")
    preflight = _make_preflight("bundle-sid")
    triage = _make_triage("bundle-sid")
    parse = _make_parse("bundle-sid")
    # mapping에 다른 source_id
    mapping = _make_mapping("DIFFERENT-SID")

    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert "violations" in detail
    assert any("mapping.source_id" in v for v in detail["violations"])


# ── R1-T06: 존재하지 않는 file_key → HTTPException 422 ────────────────────────

def test_r1t06_unknown_file_key_raises_422():
    bundle = _make_bundle(source_id="src-fk")
    preflight = _make_preflight("src-fk")
    triage = _make_triage("src-fk")
    parse = _make_parse("src-fk")
    # mapping에 source_bundle에 없는 file_key
    from services.onboarding_digitization.models import MappedDocument, MappedFileResult
    mapping = MappingReport(
        source_id="src-fk",
        file_results=[
            MappedFileResult(
                filename="test.csv",
                file_key="99:UNKNOWN",  # source_bundle에 없음
                status="MAPPED",
                documents=[
                    MappedDocument(
                        file_key="99:UNKNOWN",
                        filename="test.csv",
                        sub_type="csv",
                        sheet_name="",
                        total_rows=1,
                        columns=["이름"],
                        records=[["벤젠"]],
                    )
                ],
            )
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert any("99:UNKNOWN" in v for v in detail["violations"])


# ── R1-T07: Preflight 필수 결과 누락 → HTTPException 422 ─────────────────────

def test_r1t07_missing_preflight_result_raises_422():
    sf_a = _make_source_file(filename="a.csv", sha256="aa", file_key="0:aa")
    sf_b = _make_source_file(filename="b.csv", sha256="bb", file_key="1:bb")
    bundle = _make_bundle(files=[sf_a, sf_b], source_id="src-miss")

    # Preflight에 b.csv 결과 없음
    preflight = PreflightReport(
        source_id="src-miss",
        overall_status="PASS",
        file_results=[
            PreflightResult(filename="a.csv", status=FileStatus.PASS, checks=[], file_key="0:aa")
            # b.csv 누락
        ],
        errors=[],
    )
    # triage/parse/map은 두 파일 모두 포함 — preflight 누락만 테스트
    triage = TriageReport(
        source_id="src-miss",
        file_results=[
            TriageFileResult(filename="a.csv", category=TriageCategory.SPREADSHEET,
                             sub_type="csv", parse_eligible=True, file_key="0:aa"),
            TriageFileResult(filename="b.csv", category=TriageCategory.SPREADSHEET,
                             sub_type="csv", parse_eligible=True, file_key="1:bb"),
        ],
    )
    parse = ParseReport(
        source_id="src-miss",
        file_results=[
            ParsedFileResult(filename="a.csv", file_key="0:aa", status=ParseStatus.OK),
            ParsedFileResult(filename="b.csv", file_key="1:bb", status=ParseStatus.OK),
        ],
    )
    mapping = MappingReport(
        source_id="src-miss",
        file_results=[
            MappedFileResult(filename="a.csv", file_key="0:aa", status="MAPPED"),
            MappedFileResult(filename="b.csv", file_key="1:bb", status="MAPPED"),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert any("1:bb" in v and "preflight" in v for v in detail["violations"])


# ── R1F-T01: Triage 알 수 없는 file_key → 422 ────────────────────────────────

def test_r1ft01_triage_unknown_file_key_raises_422():
    bundle, preflight, _, parse, mapping, _ = _full_pipeline(source_id="src-tr")
    triage = TriageReport(
        source_id="src-tr",
        file_results=[
            TriageFileResult(
                filename="test.csv",
                file_key="99:UNKNOWN_TRIAGE",  # source_bundle에 없음
                category=TriageCategory.SPREADSHEET,
                sub_type="csv",
                parse_eligible=True,
            )
        ],
    )
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    assert any("99:UNKNOWN_TRIAGE" in v for v in exc_info.value.detail["violations"])


# ── R1F-T02: Quality 알 수 없는 file_key → 422 ────────────────────────────────

def test_r1ft02_quality_unknown_file_key_raises_422():
    bundle, preflight, triage, parse, mapping, _ = _full_pipeline(source_id="src-qk")
    quality = QualityReport(
        source_id="src-qk",
        overall_status=QualityStatus.PASS,
        total_files=1,
        passed_files=1,
        review_required_files=0,
        failed_files=0,
        not_evaluated_files=0,
        file_results=[
            QualityFileResult(
                file_key="99:UNKNOWN_QUALITY",  # source_bundle에 없음
                filename="test.csv",
                status=QualityStatus.PASS,
                checked_items=["Q01"],
                issues=[],
            )
        ],
    )
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, quality)
    assert exc_info.value.status_code == 422
    assert any("99:UNKNOWN_QUALITY" in v for v in exc_info.value.detail["violations"])


# ── R1F-T03: Parse 필수 파일 결과 누락 → 422 ─────────────────────────────────

def test_r1ft03_parse_missing_result_raises_422():
    bundle, preflight, triage, _, mapping, _ = _full_pipeline(source_id="src-pm")
    # parse 결과 없음 (빈 list)
    parse = ParseReport(source_id="src-pm", file_results=[])
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    assert any("parse" in v and "0:aabbcc" in v for v in exc_info.value.detail["violations"])


# ── R1F-T04: Map 필수 파일 결과 누락 → 422 ───────────────────────────────────

def test_r1ft04_map_missing_result_raises_422():
    bundle, preflight, triage, parse, _, _ = _full_pipeline(source_id="src-mm")
    # mapping 결과 없음 (빈 list)
    mapping = MappingReport(source_id="src-mm", file_results=[])
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    assert any("mapping" in v and "0:aabbcc" in v for v in exc_info.value.detail["violations"])


# ── R1F-T05: file_key 내 SHA256 불일치 → 422 ─────────────────────────────────

def test_r1ft05_file_key_sha256_mismatch_raises_422():
    # sha256="actual_sha" 이지만 file_key에는 "different_sha" 포함
    sf = SourceFile(
        filename="test.csv",
        sha256="actual_sha",
        byte_size=100,
        declared_mime="text/csv",
        detected_mime="text/csv",
        magic_match=True,
        file_key="0:different_sha",  # 불일치
    )
    bundle = _make_bundle(files=[sf], source_id="src-sha")
    preflight = _make_preflight("src-sha")
    preflight.file_results[0].file_key = "0:different_sha"
    triage = _make_triage("src-sha")
    triage.file_results[0].file_key = "0:different_sha"
    parse = _make_parse("src-sha", file_key="0:different_sha")
    mapping = _make_mapping("src-sha", file_key="0:different_sha")

    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    violations = exc_info.value.detail["violations"]
    assert any("SHA256 mismatch" in v for v in violations)


# ── R1F-T06: 정상 복수 파일 패키지 생성 성공 ────────────────────────────────────

def test_r1ft06_multi_file_success():
    sf_a = _make_source_file(filename="a.csv", sha256="aaaa", file_key="0:aaaa")
    sf_b = _make_source_file(filename="b.csv", sha256="bbbb", file_key="1:bbbb")
    bundle = _make_bundle(files=[sf_a, sf_b], source_id="src-multi")

    preflight = PreflightReport(
        source_id="src-multi",
        overall_status="PASS",
        file_results=[
            PreflightResult(filename="a.csv", status=FileStatus.PASS, checks=[], file_key="0:aaaa"),
            PreflightResult(filename="b.csv", status=FileStatus.PASS, checks=[], file_key="1:bbbb"),
        ],
        errors=[],
    )
    triage = TriageReport(
        source_id="src-multi",
        file_results=[
            TriageFileResult(filename="a.csv", category=TriageCategory.SPREADSHEET,
                             sub_type="csv", parse_eligible=True, file_key="0:aaaa"),
            TriageFileResult(filename="b.csv", category=TriageCategory.SPREADSHEET,
                             sub_type="csv", parse_eligible=True, file_key="1:bbbb"),
        ],
    )
    parse = ParseReport(
        source_id="src-multi",
        file_results=[
            ParsedFileResult(filename="a.csv", file_key="0:aaaa", status=ParseStatus.OK),
            ParsedFileResult(filename="b.csv", file_key="1:bbbb", status=ParseStatus.OK),
        ],
    )
    mapping = MappingReport(
        source_id="src-multi",
        file_results=[
            MappedFileResult(
                filename="a.csv", file_key="0:aaaa", status="MAPPED",
                documents=[MappedDocument(
                    file_key="0:aaaa", filename="a.csv", sub_type="csv",
                    sheet_name="", total_rows=1, columns=["항목"], records=[["값A"]],
                )],
            ),
            MappedFileResult(
                filename="b.csv", file_key="1:bbbb", status="MAPPED",
                documents=[MappedDocument(
                    file_key="1:bbbb", filename="b.csv", sub_type="csv",
                    sheet_name="", total_rows=1, columns=["항목"], records=[["값B"]],
                )],
            ),
        ],
    )

    pkg = run_package(bundle, preflight, triage, parse, mapping, None)
    assert pkg.integrity.file_count == 2
    assert "0:aaaa" in pkg.integrity.sha256_map
    assert "1:bbbb" in pkg.integrity.sha256_map
    assert pkg.integrity.source_id_consistent is True
    assert len(pkg.extracted_documents) == 2


# ── R1FC-T01: 동일 단계 중복 file_key → 422 ──────────────────────────────────

def test_r1fct01_duplicate_stage_result_raises_422():
    bundle, preflight, triage, parse, _, quality = _full_pipeline(source_id="src-dup")
    # mapping에 동일 file_key 결과 2건
    mapping = MappingReport(
        source_id="src-dup",
        file_results=[
            MappedFileResult(filename="test.csv", file_key="0:aabbcc", status="MAPPED",
                             documents=[MappedDocument(file_key="0:aabbcc", filename="test.csv",
                                                       sub_type="csv", sheet_name="",
                                                       total_rows=1, columns=["c"], records=[["v"]])]),
            MappedFileResult(filename="test.csv", file_key="0:aabbcc", status="MAPPED",
                             documents=[MappedDocument(file_key="0:aabbcc", filename="test.csv",
                                                       sub_type="csv", sheet_name="",
                                                       total_rows=1, columns=["c"], records=[["v2"]])]),
        ],
    )
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, quality)
    assert exc_info.value.status_code == 422
    assert any("mapping has 2 results" in v for v in exc_info.value.detail["violations"])


# ── R1FC-T02: 빈 file_key 결과 → 422 ─────────────────────────────────────────

def test_r1fct02_empty_stage_file_key_raises_422():
    bundle, preflight, _, parse, mapping, quality = _full_pipeline(source_id="src-empty")
    # triage 결과에 빈 file_key
    triage = TriageReport(
        source_id="src-empty",
        file_results=[
            TriageFileResult(
                filename="test.csv",
                category=TriageCategory.SPREADSHEET,
                sub_type="csv",
                parse_eligible=True,
                file_key="",  # 빈 키
            )
        ],
    )
    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, quality)
    assert exc_info.value.status_code == 422
    assert any("empty file_key" in v and "triage" in v for v in exc_info.value.detail["violations"])


# ── R1FC-T03: 잘못된 원본 file_key 형식 → 422 ────────────────────────────────

def test_r1fct03_invalid_source_file_key_format_raises_422():
    sf = SourceFile(
        filename="test.csv",
        sha256="aabbcc",
        byte_size=100,
        declared_mime="text/csv",
        detected_mime="text/csv",
        magic_match=True,
        file_key="NOCOLON",  # 콜론 구분자 없음 → 형식 위반
    )
    bundle = _make_bundle(files=[sf], source_id="src-fmt")
    # 모든 단계에 동일 file_key 사용 (형식 위반 외 다른 오류 방지)
    preflight = PreflightReport(
        source_id="src-fmt",
        overall_status="PASS",
        file_results=[
            PreflightResult(filename="test.csv", status=FileStatus.PASS,
                            checks=[], file_key="NOCOLON")
        ],
        errors=[],
    )
    triage = TriageReport(
        source_id="src-fmt",
        file_results=[
            TriageFileResult(filename="test.csv", category=TriageCategory.SPREADSHEET,
                             sub_type="csv", parse_eligible=True, file_key="NOCOLON"),
        ],
    )
    parse = ParseReport(
        source_id="src-fmt",
        file_results=[
            ParsedFileResult(filename="test.csv", file_key="NOCOLON", status=ParseStatus.OK),
        ],
    )
    mapping = _make_mapping("src-fmt", file_key="NOCOLON")

    with pytest.raises(HTTPException) as exc_info:
        run_package(bundle, preflight, triage, parse, mapping, None)
    assert exc_info.value.status_code == 422
    assert any("format invalid" in v for v in exc_info.value.detail["violations"])
