"""[8] Package — Canonical Evidence Package 생성 (WO-038/R1).

OBJ01 파이프라인 전 단계 결과를 단일 불변 패키지로 묶는다.
- Normalize: DEFERRED (WO-039 이후)
- Canonical Mapping: OWNER_DEFERRED
- DB/Storage 쓰기 없음
- 20 MiB 직렬화 상한 (HTTPException 413)
- R1: content_hash 전체 내용 포함 + source_id 연결 검증
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from services.onboarding_digitization.models import (
    CanonicalEvidencePackage,
    DeferredItem,
    ExtractedDocument,
    ExtractedSheet,
    MappingReport,
    PackageIntegrity,
    PackageProcessingStatus,
    ParseReport,
    PreflightReport,
    QualityReport,
    QualityStatus,
    SourceBundle,
    StageStatus,
    TitleEvidence,
    TriageReport,
)

_PACKAGE_SCHEMA_VERSION = "digitization-package-v0-provisional"
_DEFAULT_MAX_BYTES = 20 * 1024 * 1024


# ── R1-02: 원본 연결 검증 ──────────────────────────────────────────────────────

def _validate_source_consistency(
    source_bundle: SourceBundle,
    preflight_report: PreflightReport,
    triage_report: TriageReport,
    parse_report: ParseReport,
    mapping_report: MappingReport,
    quality_report: Optional[QualityReport],
) -> list[str]:
    violations: list[str] = []
    expected_sid = source_bundle.source_id

    # 1. source_id 일치 검사
    for stage, sid in [
        ("preflight", preflight_report.source_id),
        ("triage", triage_report.source_id),
        ("parse", parse_report.source_id),
        ("mapping", mapping_report.source_id),
    ]:
        if sid != expected_sid:
            violations.append(
                f"{stage}.source_id={sid!r} ≠ bundle.source_id={expected_sid!r}"
            )
    if quality_report and quality_report.source_id != expected_sid:
        violations.append(
            f"quality.source_id={quality_report.source_id!r} ≠ {expected_sid!r}"
        )

    # 2. SourceBundle 자체 검증
    for sf in source_bundle.files:
        if not sf.file_key:
            violations.append(f"source_bundle empty file_key for {sf.filename!r}")
    seen_keys: set[str] = set()
    for sf in source_bundle.files:
        if sf.file_key:
            if sf.file_key in seen_keys:
                violations.append(f"source_bundle duplicate file_key={sf.file_key!r}")
            seen_keys.add(sf.file_key)
            # file_key 형식 검사: "{index}:{sha256}" — 콜론 구분자 + 양쪽 비어 있지 않아야 함
            parts = sf.file_key.split(":", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                violations.append(
                    f"source_bundle file_key format invalid for {sf.filename!r}: "
                    f"{sf.file_key!r} (expected {{index}}:{{sha256}})"
                )
            elif parts[1] != sf.sha256:
                violations.append(
                    f"source_bundle file_key SHA256 mismatch for {sf.filename!r}: "
                    f"key contains {parts[1]!r} but sha256={sf.sha256!r}"
                )

    # 3. 단계별 파일 키 인덱스
    valid_keys = {sf.file_key for sf in source_bundle.files if sf.file_key}
    key_to_filename = {sf.file_key: sf.filename for sf in source_bundle.files if sf.file_key}

    def _extract_stage(stage: str, file_results: list) -> list[tuple[str, str]]:
        """빈 키 플래그, 중복 키 플래그, 유효 (file_key, filename) 목록 반환."""
        valid: list[tuple[str, str]] = []
        for r in file_results:
            fk: str = r.file_key
            fn: str = r.filename
            if not fk:
                violations.append(f"{stage} result has empty file_key for {fn!r}")
            else:
                valid.append((fk, fn))
        counts: dict[str, int] = {}
        for fk, _ in valid:
            counts[fk] = counts.get(fk, 0) + 1
        for fk, cnt in counts.items():
            if cnt > 1:
                violations.append(
                    f"{stage} has {cnt} results for file_key={fk!r} (expected 1)"
                )
        return valid

    def _check_results(stage: str, results: list[tuple[str, str]]) -> None:
        for fk, fn in results:
            if fk not in valid_keys:
                violations.append(f"{stage}.file_key={fk!r} not in source_bundle")
            elif key_to_filename.get(fk) != fn:
                violations.append(
                    f"{stage} filename mismatch for file_key={fk!r}: "
                    f"{fn!r} ≠ {key_to_filename[fk]!r}"
                )

    def _check_coverage(stage: str, covered: set[str]) -> None:
        if not valid_keys:
            return
        for sf in source_bundle.files:
            if sf.file_key and sf.file_key not in covered:
                violations.append(
                    f"{stage} missing result for file_key={sf.file_key!r} ({sf.filename!r})"
                )

    # 4. 전체 단계 검사 (빈 키·중복·source_bundle 연결·커버리지)
    for _stage, _file_results in [
        ("preflight", preflight_report.file_results),
        ("triage", triage_report.file_results),
        ("parse", parse_report.file_results),
        ("mapping", mapping_report.file_results),
    ]:
        _extracted = _extract_stage(_stage, _file_results)
        _check_results(_stage, _extracted)
        _check_coverage(_stage, {k for k, _ in _extracted})

    if quality_report:
        _qr = _extract_stage("quality", quality_report.file_results)
        _check_results("quality", _qr)
        _check_coverage("quality", {k for k, _ in _qr})

    return violations


# ── R1-01: 전체 내용 해시 ──────────────────────────────────────────────────────

def _compute_full_content_hash(package: CanonicalEvidencePackage) -> str:
    """패키지 전체 내용(created_at·package_id·content_hash 제외)의 SHA256."""
    raw = package.model_dump(mode="json")
    raw.pop("package_id", None)
    raw.pop("created_at", None)
    raw.get("integrity", {}).pop("content_hash", None)
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


# ── 내부 빌더 ─────────────────────────────────────────────────────────────────

def _stage_status_from_reports(
    triage_report: TriageReport,
    parse_report: ParseReport,
    mapping_report: MappingReport,
    quality_report: Optional[QualityReport],
) -> StageStatus:
    def _summarize(statuses: list[str], ok_val: str, blocked_val: str) -> str:
        if all(s == ok_val for s in statuses):
            return ok_val
        if all(s == blocked_val for s in statuses):
            return blocked_val
        return "PARTIAL"

    return StageStatus(
        intake="COMPLETE",
        preflight="COMPLETE",
        triage="COMPLETE",
        parse=_summarize([r.status.value for r in parse_report.file_results], "OK", "BLOCKED"),
        structural_map=_summarize(
            [r.status.value for r in mapping_report.file_results], "MAPPED", "BLOCKED"
        ),
        normalize="DEFERRED",
        quality=quality_report.overall_status.value if quality_report else "NOT_RUN",
    )


def _processing_status_from_quality(
    quality_report: Optional[QualityReport],
    stage_status: StageStatus,
) -> PackageProcessingStatus:
    if quality_report is None:
        return PackageProcessingStatus.PARTIAL

    q = quality_report.overall_status
    if q == QualityStatus.FAIL:
        return PackageProcessingStatus.FAIL
    if q == QualityStatus.REVIEW_REQUIRED:
        return PackageProcessingStatus.REVIEW_REQUIRED
    if q == QualityStatus.NOT_EVALUATED:
        return PackageProcessingStatus.PARTIAL
    # PASS: normalize always DEFERRED → cannot claim COMPLETE yet
    return PackageProcessingStatus.REVIEW_REQUIRED


def _build_extracted_documents(mapping_report: MappingReport) -> list[ExtractedDocument]:
    docs = []
    for mfr in mapping_report.file_results:
        sheets = None
        sub_type = ""
        if mfr.documents:
            sub_type = mfr.documents[0].sub_type
            sheets = []
            for doc in mfr.documents:
                ti = doc.title_info
                col_header_row_idx = ti.column_header_row_index if ti else 0
                col_headers = ti.column_headers if ti else doc.columns
                sheets.append(ExtractedSheet(
                    sheet_name=doc.sheet_name,
                    column_headers=col_headers,
                    column_header_row_index=col_header_row_idx,
                    records=doc.records,
                    total_rows=doc.total_rows,
                ))
        docs.append(ExtractedDocument(
            file_key=mfr.file_key,
            filename=mfr.filename,
            sub_type=sub_type,
            status=mfr.status.value,
            reason=mfr.reason,
            sheets=sheets,
        ))
    return docs


def _build_title_evidence(mapping_report: MappingReport) -> list[TitleEvidence]:
    evidence = []
    for mfr in mapping_report.file_results:
        if not mfr.documents:
            continue
        for doc in mfr.documents:
            ti = doc.title_info
            if ti is None:
                continue
            evidence.append(TitleEvidence(
                file_key=mfr.file_key,
                filename=mfr.filename,
                sheet_name=doc.sheet_name,
                title_status=ti.title_status.value,
                candidates=ti.candidates,
                column_headers=ti.column_headers,
                column_header_row_index=ti.column_header_row_index,
            ))
    return evidence


def _build_deferred_items(
    source_bundle: SourceBundle,
    parse_report: ParseReport,
    mapping_report: MappingReport,
) -> list[DeferredItem]:
    items: list[DeferredItem] = []
    blocked_keys: set[str] = set()

    for pfr in parse_report.file_results:
        if pfr.status.value in ("BLOCKED", "ERROR"):
            blocked_keys.add(pfr.file_key)
            items.append(DeferredItem(
                file_key=pfr.file_key,
                filename=pfr.filename,
                reason=pfr.reason or pfr.status.value,
                stage="parse",
            ))

    for mfr in mapping_report.file_results:
        if mfr.status.value in ("BLOCKED", "ERROR") and mfr.file_key not in blocked_keys:
            blocked_keys.add(mfr.file_key)
            items.append(DeferredItem(
                file_key=mfr.file_key,
                filename=mfr.filename,
                reason=mfr.reason or mfr.status.value,
                stage="map",
            ))

    for mfr in mapping_report.file_results:
        if mfr.status.value == "MAPPED":
            items.append(DeferredItem(
                file_key=mfr.file_key,
                filename=mfr.filename,
                reason="DEFERRED — WO-039 이후",
                stage="normalize",
            ))

    for sf in source_bundle.files:
        items.append(DeferredItem(
            file_key=sf.file_key,
            filename=sf.filename,
            reason="OWNER_DEFERRED — 운영자 결정 후 적용",
            stage="canonical_mapping",
        ))

    return items


# ── 공개 엔트리포인트 ──────────────────────────────────────────────────────────

def run_package(
    source_bundle: SourceBundle,
    preflight_report: PreflightReport,
    triage_report: TriageReport,
    parse_report: ParseReport,
    mapping_report: MappingReport,
    quality_report: Optional[QualityReport] = None,
    max_serialized_bytes: int = _DEFAULT_MAX_BYTES,
) -> CanonicalEvidencePackage:
    # R1-02: 원본 연결 검증 — 불일치 시 422
    violations = _validate_source_consistency(
        source_bundle, preflight_report, triage_report,
        parse_report, mapping_report, quality_report,
    )
    if violations:
        raise HTTPException(
            status_code=422,
            detail={"message": "패키지 원본 연결 검증 실패", "violations": violations},
        )

    stage_status = _stage_status_from_reports(
        triage_report, parse_report, mapping_report, quality_report
    )
    processing_status = _processing_status_from_quality(quality_report, stage_status)

    extracted_documents = _build_extracted_documents(mapping_report)
    title_evidence = _build_title_evidence(mapping_report)
    deferred_items = _build_deferred_items(source_bundle, parse_report, mapping_report)

    sha256_map = {sf.file_key: sf.sha256 for sf in source_bundle.files}

    # R1-01: content_hash는 전체 내용 기반 — 임시 빈값으로 패키지 생성 후 교체
    package = CanonicalEvidencePackage(
        package_id=str(uuid.uuid4()),
        schema_version=_PACKAGE_SCHEMA_VERSION,
        source_id=source_bundle.source_id,
        company_id=source_bundle.company_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        processing_status=processing_status,
        stage_status=stage_status,
        source_manifest=source_bundle,
        extracted_documents=extracted_documents,
        title_and_header_evidence=title_evidence,
        quality_report=quality_report,
        deferred_items=deferred_items,
        integrity=PackageIntegrity(
            source_id_consistent=True,  # violations 검증 통과 후 설정
            file_count=len(source_bundle.files),
            file_keys=[sf.file_key for sf in source_bundle.files],
            sha256_map=sha256_map,
            content_hash="",  # 아래에서 실제 값으로 교체
        ),
    )

    package.integrity.content_hash = _compute_full_content_hash(package)

    serialized = package.model_dump_json()
    if len(serialized.encode()) > max_serialized_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"패키지 직렬화 크기 초과 — 최대 {max_serialized_bytes // (1024 * 1024)} MiB",
        )

    return package
