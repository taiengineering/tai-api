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
    assert any("non_safety:" in b for b in result.basis)


def test_S13_review_unrelated_event_no_non_safety_markers():
    """S-13: 반도체 품질관리 행사 — 비안전 목적 마커 없음 → REVIEW_REQUIRED. [REAL 유형: EVEN_069227]

    R1-02: 비안전 목적 마커 없이 안전 키워드 부재만으로는 OUT_OF_SCOPE 불가.
    """
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
    assert result.verdict == "REVIEW_REQUIRED"


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


# ---------------------------------------------------------------------------
# R1 regression tests (WO-TAI-BIZINFO-OBJ-003-SOURCE-IV-R1)
# ---------------------------------------------------------------------------


def test_S20_review_safety_signal_with_marketing_purpose():
    """S-20: 산업안전 키워드 + 해외 판로·수출 마케팅 목적 공존 → REVIEW_REQUIRED (R1-01).

    IN_SCOPE 자동 확정 금지: 안전 키워드가 있어도 비안전 목적 마커가 함께 있으면
    목적이 불확실하므로 REVIEW_REQUIRED로 하강한다.
    [SYNTHETIC]
    """
    rec = _record(
        title="산업안전 기술사업화 해외 판로 개척 지원",
        summary=(
            "산업안전 분야 기술을 보유한 기업의 해외 판로 개척 및 "
            "수출 마케팅을 지원합니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("purpose_conflict:" in b for b in result.basis)
    assert any("safety_signal:" in b for b in result.basis)


def test_S21_in_scope_r1_added_direct_keywords():
    """S-21: 끼임사고 예방·위험기계 방호덮개 — R1 추가 키워드 → IN_SCOPE (R1-02).

    키워드 누락만으로 OUT_OF_SCOPE 처리 금지: '끼임', '위험기계', '방호'는
    R1에서 _DIRECT_SAFETY에 추가된 키워드이며 안전 목적이 명확하다.
    [SYNTHETIC]
    """
    rec = _record(
        title="위험기계 방호덮개 설치 지원사업",
        summary=(
            "끼임사고를 예방하기 위해 위험기계에 방호덮개를 설치하는 "
            "비용을 지원합니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"


def test_S22_out_of_scope_explicit_non_safety_markers():
    """S-22: 명시적 비안전 목적 마커(농업인·농촌·운전자금) + 안전 키워드 없음 → OUT_OF_SCOPE.

    R1-02: 비안전 목적 마커가 존재하고 안전 신호가 전혀 없을 때만 OUT_OF_SCOPE.
    [SYNTHETIC]
    """
    rec = _record(
        title="[강원] 2026년 농업인 지원사업 모집",
        summary=(
            "농촌 지역 농업인의 경영 안정을 위한 운전자금 지원사업입니다. "
            "농업 경영체 등록 필수."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "OUT_OF_SCOPE"
    assert any("non_safety:" in b for b in result.basis)


def test_S23_in_scope_unaffected_by_r1():
    """S-23: 비안전 마커 없는 기존 IN_SCOPE 케이스는 R1 이후에도 유지. [SYNTHETIC]"""
    rec = _record(
        title="[부산] 중대재해 예방 안전보건 지원사업",
        summary="산업재해 예방 활동 및 위험성평가 컨설팅을 지원합니다.",
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"


# ---------------------------------------------------------------------------
# FINAL-FIX tests (WO-TAI-BIZINFO-OBJ-003-IV-FINAL-FIX)
# ---------------------------------------------------------------------------


def test_S24_review_safety_keyword_in_exclusion_context():
    """S-24: 제목·요약에 안전 키워드 있지만 요약에서 안전 설비 지원이 제외됨 → REVIEW_REQUIRED.

    FINAL-FIX: "안전설비 지원 제외" compact marker → IN_SCOPE 자동 확정 차단.
    [SYNTHETIC]
    """
    rec = _record(
        title="산업안전 지원사업 안내",
        summary=(
            "이 사업은 산업안전 설비 지원 제외. "
            "일반 제품 디자인 개선을 지원합니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("safety_negated:" in b for b in result.basis)


def test_S25_review_safety_product_exhibition_unrelated():
    """S-25: 산업안전 제품 전시·홍보, 본문에 "산업안전과 무관" 명시 → REVIEW_REQUIRED.

    FINAL-FIX: 전시·홍보 목적 공고에서 안전 관련성이 명시적으로 부정될 때
    IN_SCOPE 자동 확정 차단.
    [SYNTHETIC]
    """
    rec = _record(
        title="산업안전 제품 전시 및 홍보 지원사업",
        summary=(
            "산업안전 관련 제품의 전시 및 마케팅을 지원합니다. "
            "이 사업은 산업안전과 무관한 일반 제조업도 참여 가능합니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("safety_negated:" in b for b in result.basis)


def test_S26_in_scope_direct_safety_support_no_exclusion():
    """S-26: 산업재해 예방설비 설치비 지원 — 직접 목적 확인, 부정 표현 없음 → IN_SCOPE 유지.

    FINAL-FIX 이후에도 명확한 직접 지원 목적은 IN_SCOPE로 유지됨을 보장.
    [SYNTHETIC]
    """
    rec = _record(
        title="산업재해 예방설비 설치비 지원사업",
        summary=(
            "산업재해 예방을 위한 안전설비 설치 비용을 지원합니다. "
            "중소기업 대상."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"


# ---------------------------------------------------------------------------
# R2 regression tests (WO-TAI-BIZINFO-SAFETY-RELEVANCE-DB-001)
# ---------------------------------------------------------------------------


def test_S27_in_scope_compact_safety_management_personnel():
    """S-27: "안전관리 인력" (공백 포함) → compact 매칭 → IN_SCOPE.

    R2: 안전관리 인력은 산업안전보건법상 법정 의무 인력이다. 제목의 공백이
    keyword를 split하더라도 compact 형식으로 감지해야 한다.
    [REAL 유형: PBLN_000000000126712 — 자동차 부품업종 안전관리 인력 고용지원사업]
    """
    rec = _record(
        title="[울산] 2026년 자동차 부품업종 안전관리 인력 고용지원사업 참여기업 모집 공고",
        summary=(
            "울산지역 자동차 부품업종 안전관리 인력의 지역정착 및 "
            "안전관리자 장기근속 지원금, 안전관리자 선임 정착 지원."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    assert any("안전관리인력" in b or "안전관리자" in b for b in result.basis)


def test_S28_review_required_jungdae_simin_jaehae():
    """S-28: "중대시민재해" 교육 — 중대재해처벌법 준수 목적이지만 산업재해가 아닌
    소비자 제품 안전. "중대재해" 키워드가 "중대시민재해" 내부에 없으므로 직접 매칭
    안 됨 → REVIEW_REQUIRED 유지.

    R2: "중대재해" ⊄ "중대시민재해" (부분문자열 아님) — 오탐 없음 확인.
    [REAL 유형: EVEN_000000000069465 — 원료·제조물 분야 중대시민재해 교육]
    """
    rec = _record(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key="EVEN_TEST_SIMIN",
        title="[전국] 원료ㆍ제조물 분야 중대시민재해 교육 개최",
        summary=(
            "원료ㆍ제조물을 생산ㆍ제조ㆍ판매ㆍ유통하는 사업장을 대상으로 "
            "중대재해처벌법과 관계법령의 주요 내용, 안전ㆍ보건 의무사항 및 "
            "통합이행 안전ㆍ보건 체계 구축방법 안내."
        ),
    )
    result = review_relevance(rec)
    # 중대재해는 중대시민재해의 부분문자열이 아님 → 직접 안전 키워드 미매칭
    # 안전ㆍ보건(중간점)은 안전보건(연속)과 다름 → adjacent/no_evidence
    assert result.verdict == "REVIEW_REQUIRED"


def test_S29_out_of_scope_rural_accommodation_fire_safety():
    """S-29: 농어촌민박 소방안전시설 지원 — 소방(adjacent) + 농어촌민박(non_safety)
    → 인접 신호만 있고 비안전 목적 확인 → OUT_OF_SCOPE.

    R2: adjacent 신호만 있고 비안전 목적이 명확히 확인된 경우 OUT_OF_SCOPE.
    TAI Safe 고객군(산업현장)이 아닌 농촌 숙박시설 대상.
    [REAL 유형: PBLN_000000000127526 — 여수시 농어촌민박 소방안전시설 지원]
    """
    rec = _record(
        title="[전남광주] 여수시 2026년 농어촌민박 소방안전시설 지원 사업 모집 공고",
        summary=(
            "농어촌민박업소의 쾌적하고 안전한 여가 공간을 마련하여 방문객 편의 제공 및 "
            "농어촌관광 활성화를 도모하고자 소방안전시설 지원 사업에 참여할 "
            "농어촌민박업소를 모집합니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "OUT_OF_SCOPE"
    assert any("농어촌민박" in b for b in result.basis)
    assert any("adjacent_overridden" in b or "non_safety" in b for b in result.basis)


def test_S30_out_of_scope_personal_data_safety():
    """S-30: 개인정보 안전조치 모니터링 — '안전' 단어 포함이지만 데이터 보안 목적.
    '개인정보' 비안전 마커 → OUT_OF_SCOPE.

    R2: 개인정보보호는 산업안전과 무관한 별도 법적 의무 영역.
    [REAL 유형: PBLN_000000000122104 — 중소사업자 개인정보 안전조치 모니터링 지원]
    """
    rec = _record(
        title="2026년 중소사업자 개인정보 안전조치 모니터링 지원 사업 공고",
        summary=(
            "개인정보보호위원회에서 중소사업자를 대상으로 개인정보 안전조치 의무 "
            "이행 여부를 모니터링하고 개선을 지원하는 사업입니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "OUT_OF_SCOPE"
    assert any("개인정보" in b for b in result.basis)


def test_S31_in_scope_health_manager_selection_support():
    """S-31: 보건관리자 선임 지원 — R2 추가 키워드 → IN_SCOPE.

    보건관리자는 산업안전보건법상 안전관리자와 동급 법정 의무 인력이다.
    [SYNTHETIC]
    """
    rec = _record(
        title="[경기] 2026년 소규모사업장 보건관리자 선임 지원사업",
        summary=(
            "50인 미만 소규모사업장의 산업재해 예방을 위해 보건관리자 선임 비용을 "
            "지원합니다. 직업병 예방 및 건강검진 연계 포함."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    assert any("보건관리자" in b or "산업재해" in b for b in result.basis)


def test_S32_review_required_fire_safety_no_non_safety_marker():
    """S-32: 소방시설 지원이지만 비안전 목적 마커 없음 → REVIEW_REQUIRED 유지.

    R2: adjacent 신호만으로는 OUT_OF_SCOPE 불가. 비안전 목적이 명시적으로
    확인되지 않으면 REVIEW_REQUIRED로 유지.
    [SYNTHETIC]
    """
    rec = _record(
        title="[인천] 2026년 소규모 제조업체 소방시설 개선 지원사업",
        summary=(
            "소규모 제조업체의 화재 예방을 위한 소방시설 개선 비용을 지원합니다. "
            "50인 미만 제조업 사업장 대상."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("소방" in b for b in result.basis)


# ---------------------------------------------------------------------------
# DISCOVERY-001 — 기술형 안전 및 디지털전환 탐색 테스트
# ---------------------------------------------------------------------------


def test_S34_in_scope_smart_safety_solution_title_and_summary():
    """S-34: 스마트 안전솔루션 구축·도입 지원 — 제목+요약 모두 기술형 안전 직접 신호
    → IN_SCOPE.

    DISCOVERY-001: _DIRECT_SAFETY_COMPACT (B) 안전기술 확장.
    구미 국가산업단지 스마트 안전솔루션 지원사업 유형 (PBLN_000000000127340 실증).
    [REAL 유형: PBLN_000000000127340]
    """
    rec = _record(
        title="[경북] 2026년 구미 국가산업단지 스마트 안전솔루션 서비스 수혜기업 모집",
        summary=(
            "산업단지 안전관리 고도화를 위한 스마트 안전솔루션 구축 지원. "
            "안전 모니터링 시스템 설치 및 운영 지원금 포함."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    assert any("스마트안전" in b or "안전솔루션" in b or "안전모니터링" in b
               for b in result.basis)


def test_S35_review_required_smart_factory_tech_adoption():
    """S-35: 스마트공장 구축 지원 — 직접 안전 신호 없음, TECH_ADOPTION 신호 존재
    → REVIEW_REQUIRED (basis: tech_adoption:스마트공장).

    DISCOVERY-001: _TECH_ADOPTION 경로. 안전관리 활용 가능성은 있으나
    실제 지원 범위 미확인 단계. 일반 no_confirming_evidence와 구별.
    [SYNTHETIC — 스마트 제조혁신 지원사업 유형]
    """
    rec = _record(
        title="[전국] 2027년 스마트공장 구축 및 고도화 지원사업 통합 공고",
        summary=(
            "제조업 중소기업의 스마트공장 구축·고도화를 지원합니다. "
            "MES·ERP·로봇자동화·AI 품질검사 시스템 도입 비용 지원."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("tech_adoption" in b for b in result.basis)
    assert any("스마트공장" in b for b in result.basis)


def test_S36_review_required_smart_factory_startup_eligibility():
    """S-36: 창업기업 스마트공장 지원 — 창업기업 여부는 신청 자격 조건,
    비안전 목적의 근거가 아님 → REVIEW_REQUIRED (TECH_ADOPTION 경로).

    DISCOVERY-001-R1: "창업기업"은 _NON_SAFETY_PURPOSE에서 제외.
    스마트공장 도입 지원은 안전관리 소프트웨어 도입 가능성이 있으므로
    OUT_OF_SCOPE 자동 판정 금지.
    [SYNTHETIC — DISCOVERY-001-R1 창업기업 자격조건 수정]
    """
    rec = _record(
        title="[전국] 2026년 창업기업 스마트공장 도입 지원사업",
        summary=(
            "창업 3년 이내 초기 기업의 스마트공장 도입을 위한 바우처를 지원합니다. "
            "창업기업 전용 사업으로 기존 제조업 사업장은 대상 아님."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("tech_adoption" in b for b in result.basis)
    assert any("스마트공장" in b for b in result.basis)


def test_S37_in_scope_smart_factory_with_direct_safety_signal():
    """S-37: 스마트공장 + 직접 안전 신호(안전관리자) 공존 → IN_SCOPE.
    직접 안전 경로가 TECH_ADOPTION보다 우선하여 판정.

    [SYNTHETIC]
    """
    rec = _record(
        title="[경기] 2026년 중소 제조업 스마트공장 및 안전관리자 선임 통합 지원",
        summary=(
            "스마트공장 구축과 함께 안전관리자 선임 지원금을 함께 신청 가능합니다. "
            "50인 미만 제조업 사업장 대상."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    assert any("안전관리자" in b for b in result.basis)


def test_S38_review_required_jejo_ax_saas_tech_adoption():
    """S-38: 제조AX + SaaS 솔루션 매칭 사업 — 직접 안전 신호 없음,
    TECH_ADOPTION 신호(제조ax, saas) 존재 → REVIEW_REQUIRED.

    DISCOVERY-001-R1: _TECH_ADOPTION에 제조AX 추가 검증.
    성남시 제조AX 솔루션 매칭 지원사업 유형 (PBLN_000000000127610 실증).
    [REAL 유형: PBLN_000000000127610]
    """
    rec = _record(
        title="[경기] 2026년 성남시 제조AX 솔루션 매칭 지원사업",
        summary=(
            "제조업 중소기업의 AI 전환(AX)을 위해 SaaS 형태의 솔루션 도입을 지원합니다. "
            "AI 기반 품질검사, 공정최적화, 에너지 모니터링 솔루션 매칭."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("tech_adoption" in b for b in result.basis)
    assert any("제조ax" in b or "saas" in b for b in result.basis)


def test_S39_review_required_ai_platform_no_direct_safety():
    """S-39: 인공지능 플랫폼 도입 지원 — 직접 안전 신호 없음,
    TECH_ADOPTION 신호(인공지능) 존재 → REVIEW_REQUIRED.

    DISCOVERY-001-R1: _TECH_ADOPTION에 인공지능 추가 검증.
    AI 플랫폼 구축 지원이 안전관리 소프트웨어 도입으로 연결될 수 있는지
    인간 검토 필요.
    [SYNTHETIC]
    """
    rec = _record(
        title="[전국] 2026년 중소기업 인공지능 플랫폼 도입 지원사업",
        summary=(
            "제조·물류·서비스 중소기업의 인공지능 솔루션 도입을 지원합니다. "
            "AI 기반 수요예측, 공정최적화, IoT 센서 연동 플랫폼 구축 비용 지원."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "REVIEW_REQUIRED"
    assert any("tech_adoption" in b for b in result.basis)
    assert any("인공지능" in b or "iot" in b or "센서" in b for b in result.basis)


def test_S33_in_scope_safety_primary_privacy_boilerplate_incidental():
    """S-33: 산업안전 주 목적 사업에서 '개인정보 처리방침' 문구가 본문 하단에
    부수적으로 등장 → IN_SCOPE 유지. 개인정보가 제목에 없으면 충돌 마커로
    작동하지 않는다.

    R1-03: _INCIDENTAL_SAFE_MARKERS 경계 조건.
    - 개인정보가 제목에 있으면 → 충돌 마커 (purpose_conflict 발생 가능)
    - 개인정보가 요약에만 있으면 → 보조 문구로 간주, IN_SCOPE 유지
    [S-30(개인정보 주목적 → OUT_OF_SCOPE)과 구별]
    [SYNTHETIC]
    """
    rec = _record(
        title="[전국] 2026년 소규모사업장 산업안전 환경개선 지원사업",
        summary=(
            "50인 미만 소규모 사업장의 산업재해 예방을 위한 안전보건 환경개선을 "
            "지원합니다. 신청서 작성 시 수집되는 사업장 정보는 개인정보 처리방침에 "
            "따라 처리됩니다."
        ),
    )
    result = review_relevance(rec)
    assert result.verdict == "IN_SCOPE"
    # 개인정보는 제목에 없으므로 purpose_conflict로 보고되지 않아야 함
    assert not any("purpose_conflict:개인정보" in b for b in result.basis)
