"""OBJ-BZI-003 Safety Relevance Selector unit tests.

WO-TAI-BIZINFO-OBJ-003-CODE-001.
No DB / no network / no API calls.

Test IDs:
  S-xx = selector (review_relevance) cases

Fixtures marked [REAL] were derived from actual API samples observed during
OBJ-BZI-003-REAL-DATA-EVIDENCE-FIX-001 investigation.
Fixtures marked [SYNTHETIC] are purpose-built test cases.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.bizinfo.normalizer import NormalizedSourceRecord
from services.bizinfo.selector import RelevanceDecision, review_relevance

_NOW = datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(**kwargs) -> NormalizedSourceRecord:
    """Minimal NormalizedSourceRecord for selector tests."""
    defaults = {
        "source_kind":  "PROGRAM",
        "source_id":    "BIZINFO_PROGRAM",
        "source_key":   "PBLN_TEST001",
        "title":        "테스트 지원사업",
        "source_org":   None,
        "origin_url":   None,
        "bizinfo_url":  None,
        "retrieved_at": _NOW,
    }
    defaults.update(kwargs)
    return NormalizedSourceRecord(**defaults)


# ---------------------------------------------------------------------------
# IN_SCOPE tests
# ---------------------------------------------------------------------------


def test_S01_in_scope_direct_keyword_title_and_summary():
    """S-01: 제목 + 요약 모두 직접 안전 키워드 → IN_SCOPE. [REAL 유형: PBLN_127636]"""
    rec = _record(
        title="[부산] 고위험산업 사각지대 집중관리사업(안전보호구 지원)",
        summary=(
            "지역내 소규모 사업장의 중대재해 예방활동을 지원하고 "
            "사고위험의 격차를 해소하기 위한 안전보호구 지원 사업입니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    assert any("안전보호구" in b or "고위험산업" in b for b in result.basis)


def test_S02_in_scope_strong_summary_two_keywords():
    """S-02: 요약에 직접 안전 키워드 2개 이상 → IN_SCOPE (제목 키워드 없어도). [SYNTHETIC]"""
    rec = _record(
        title="2026년 하반기 소규모 사업장 지원사업",
        summary=(
            "산업재해 예방을 위한 방호장치 설치를 지원합니다. "
            "위험성평가 컨설팅 포함."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    assert len(result.basis) >= 2


def test_S03_in_scope_iso_title_and_safety_summary():
    """S-03: 제목 산업안전보건 + 요약 확인 → IN_SCOPE. [REAL 유형: PBLN_123904]"""
    rec = _record(
        title="[울산] 산업안전보건 국제표준 인증기업 지원사업",
        summary="ISO45001 인증 취득 지원. 산업안전보건 경영시스템 구축 컨설팅 포함.",
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"


def test_S04_in_scope_event_safety_education():
    """S-04: 행사 제목·요약 모두 산업안전 직접 언급 → IN_SCOPE. [REAL 유형: EVEN_069630]"""
    rec = _record(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key="EVEN_TEST001",
        title="[경기] 산업안전·탄소중립 교육 참여모집",
        summary="산업안전보건법 대응방안 및 ESG 실무 교육. 안전보건 관리체계 수립 지원.",
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"


# ---------------------------------------------------------------------------
# REVIEW_REQUIRED tests
# ---------------------------------------------------------------------------


def test_S05_review_title_keyword_no_summary():
    """S-05: 제목에 직접 안전 키워드 있지만 요약 없음 → REVIEW_REQUIRED. [SYNTHETIC]"""
    rec = _record(
        title="[경북] 중대재해 예방 사각지대 해소 지원사업",
        summary=None,
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("summary_missing" in b for b in result.basis)


def test_S06_review_single_keyword_summary_only():
    """S-06: 요약에 직접 키워드 1개만 → REVIEW_REQUIRED (확인 불충분). [SYNTHETIC]"""
    rec = _record(
        title="소규모 사업장 작업환경 개선 사업",
        summary="작업현장 개선을 통해 안전보건 환경을 조성합니다.",
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"


def test_S07_review_adjacent_keyword_sofa():
    """S-07: 소방 관련 → REVIEW_REQUIRED (인접 신호). [SYNTHETIC]"""
    rec = _record(
        title="소방시설 점검·유지관리 지원사업",
        summary="소방 시설 정기 점검 및 화재 예방을 위한 보수 지원입니다.",
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("소방" in b for b in result.basis)


def test_S08_review_no_content_no_keywords():
    """S-08: 요약 없음 + 키워드 없음 → REVIEW_REQUIRED. [SYNTHETIC]"""
    rec = _record(
        title="2026년 하반기 중소기업 지원사업",
        summary=None,
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("no_content_available" in b for b in result.basis)


def test_S09_review_iso_without_safety_confirmation():
    """S-09: ISO45001 태그만, 제목·요약에 직접 안전 미확인 → REVIEW_REQUIRED. [REAL 유형: PBLN_118467]"""
    rec = _record(
        title="[부산] 2026년 중소기업 ISO 인증 지원사업",
        summary=(
            "ISO 9001 품질경영시스템, ISO 14001 환경경영시스템, "
            "ISO 45001 안전보건경영시스템 인증 취득 지원."
        ),
        hashtags=["기술", "부산", "iso45001", "국제표준"],
    )
    result = review_relevance(rec)
    # iso45001이 summary에 있어 adjacent 신호 → REVIEW_REQUIRED
    assert result.verdict == "REVIEW_REQUIRED"


def test_S10_review_work_environment_improvement():
    """S-10: 작업환경 개선 - 안전 인접 신호, 직접 목적 불명확 → REVIEW_REQUIRED. [REAL 유형: PBLN_127424]"""
    rec = _record(
        title="[대구] 미래모빌리티 일자리고도화 수혜기업 모집",
        summary="일터 개선 및 작업환경 개선 지원. 모빌리티 산업 경쟁력 강화.",
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"


def test_S11_review_chemical_adjacent():
    """S-11: 화학물질 관련 → REVIEW_REQUIRED. [SYNTHETIC]"""
    rec = _record(
        title="2026년 화학물질 취급사업장 지원사업",
        summary="화학물질 보관·취급 시설 개선 지원. 환경안전 기준 준수.",
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("화학물질" in b or "환경안전" in b for b in result.basis)


# ---------------------------------------------------------------------------
# OUT_OF_SCOPE tests
# ---------------------------------------------------------------------------


def test_S12_out_of_scope_financial_export():
    """S-12: 금융·수출 사업, 안전 키워드 없음 → OUT_OF_SCOPE. [REAL 유형: 금융01 샘플]"""
    rec = _record(
        title="2026년 하반기 혁신스타트업 특례보증 지원",
        summary=(
            "서울경제진흥원·기술보증기금이 혁신 스타트업에 운전자금 보증을 제공합니다. "
            "코칭 및 경영 컨설팅 포함."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "OUT_OF_SCOPE"
    assert any("no_safety_signal" in b for b in result.basis)


def test_S13_out_of_scope_unrelated_event():
    """S-13: 반도체 품질관리 행사, 안전 무관 → OUT_OF_SCOPE. [REAL 유형: EVEN_069227]"""
    rec = _record(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key="EVEN_TEST002",
        title="[전국] 차세대반도체 불량분석 및 품질관리 전문인력양성 실습교육",
        summary=(
            "반도체 불량분석 기법 및 품질관리 실습 교육. "
            "측정 장비 운용 및 데이터 분석 과정."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "OUT_OF_SCOPE"


def test_S14_out_of_scope_fishing_subsidy():
    """S-14: 어업인 지원, 안전 무관 → OUT_OF_SCOPE. [REAL 유형: PROGRAM 경영 샘플]"""
    rec = _record(
        title="[강원] 강릉시 2026년 어업인수당 지원 대상자 모집",
        summary=(
            "어업과 어촌의 지속가능한 발전 및 어업활동을 통한 환경보전·어촌 유지 등 "
            "어촌 공익적 기능증진과 어업인 소득안정 도모를 위한 지원사업입니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# Cross-cutting / contract tests
# ---------------------------------------------------------------------------


def test_S15_basis_contains_no_html():
    """S-15: basis에 HTML 태그 없음."""
    rec = _record(
        title="<script>xss</script>산업안전 지원사업",
        summary="<p>중대재해 예방 및 안전보호구 지원</p>",
    )
    result = review_relevance(rec)
    for b in result.basis:
        assert "<" not in b
        assert ">" not in b
        assert "script" not in b


def test_S16_record_not_modified():
    """S-16: review_relevance 호출 후 원본 레코드 불변."""
    rec = _record(
        title="산업안전 지원사업",
        summary="안전보건 관련 지원 내용",
    )
    original_title   = rec.title
    original_summary = rec.summary

    review_relevance(rec)

    assert rec.title   == original_title
    assert rec.summary == original_summary


def test_S17_verdict_is_valid_literal():
    """S-17: verdict는 항상 3가지 중 하나."""
    cases = [
        _record(title="안전보호구 지원", summary="중대재해 예방사업"),
        _record(title="일반 수출 지원", summary="해외시장 개척 지원"),
        _record(title="소방 안전 교육", summary=None),
    ]
    valid = {"IN_SCOPE", "OUT_OF_SCOPE", "REVIEW_REQUIRED"}
    for rec in cases:
        result = review_relevance(rec)
        assert result.verdict in valid


def test_S18_basis_is_non_empty_tuple():
    """S-18: basis는 항상 비어 있지 않은 tuple."""
    rec = _record(title="테스트", summary=None)
    result = review_relevance(rec)
    assert isinstance(result.basis, tuple)
    assert len(result.basis) >= 1


def test_S19_review_no_summary_with_adjacent_keyword():
    """S-19: 요약 없고 제목에 인접 신호만 → REVIEW_REQUIRED."""
    rec = _record(
        title="법정의무교육 지원 사업",
        summary=None,
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
