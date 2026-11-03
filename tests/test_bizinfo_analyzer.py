"""OBJ-BZI-003 LLM Semantic Analyzer unit tests.

WO-TAI-BIZINFO-OBJ-003-LLM-ANALYZER-001.
No real OpenAI calls — all tests use injected mock llm_call_fn.

Test IDs:
  A-xx = analyzer (analyze_relevance) cases

Test categories:
  INCLUDE path       — A-01
  EXCLUDE path       — A-02
  HOLD paths         — A-03 to A-10 (error, hallucination, negation, low confidence …)
  Layer 1 contract   — A-11 to A-13 (IN_SCOPE pass-through, OUT_OF_SCOPE pass-through,
                                      layer1_verdict recorded but no bypass)
  Cross-cutting      — A-14 to A-17 (basis safety, immutability, literals, non-empty)
  R1 corrections     — A-18 to A-21 (exclude+safety, full-text exclusion,
                                      non-string field coercion, no skip_layer1_exclude)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.bizinfo.normalizer import NormalizedSourceRecord
from services.bizinfo.analyzer import AnalysisResult, analyze_relevance

_NOW = datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(**kwargs) -> NormalizedSourceRecord:
    """Minimal NormalizedSourceRecord for analyzer tests."""
    defaults = {
        "source_kind":  "PROGRAM",
        "source_id":    "BIZINFO_PROGRAM",
        "source_key":   "PBLN_TEST_A001",
        "title":        "테스트 지원사업",
        "source_org":   None,
        "origin_url":   None,
        "bizinfo_url":  None,
        "retrieved_at": _NOW,
    }
    defaults.update(kwargs)
    return NormalizedSourceRecord(**defaults)


def _mock_llm(
    verdict:        str,
    cited_evidence: str,
    confidence:     str = "high",
    purpose_summary: str = "테스트 목적",
):
    """Return a llm_call_fn that always yields a fixed JSON-like dict."""
    def _fn(system_msg: str, user_msg: str) -> dict:
        return {
            "verdict":         verdict,
            "purpose_summary": purpose_summary,
            "cited_evidence":  cited_evidence,
            "confidence":      confidence,
        }
    return _fn


def _mock_error():
    """Return a llm_call_fn that raises on call."""
    def _fn(system_msg: str, user_msg: str) -> dict:
        raise ConnectionError("simulated network error")
    return _fn


def _mock_non_dict():
    """Return a llm_call_fn that returns a non-dict value."""
    def _fn(system_msg: str, user_msg: str):
        return "not a dict"
    return _fn


# ---------------------------------------------------------------------------
# INCLUDE path
# ---------------------------------------------------------------------------


def test_A01_include_safety_purpose_verified():
    """A-01: 산업안전 목적 확인·인용 원문 존재·부정 맥락 없음 → INCLUDE. [SYNTHETIC]"""
    rec = _record(
        title="산업재해 예방설비 설치비 지원사업",
        summary="산업재해 예방을 위한 안전설비 설치 비용을 지원합니다. 중소기업 대상.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "산업재해 예방을 위한 안전설비 설치"),
    )
    assert result.verdict == "INCLUDE"
    assert any("cited_verified" in b for b in result.basis)


# ---------------------------------------------------------------------------
# EXCLUDE path
# ---------------------------------------------------------------------------


def test_A02_exclude_non_safety_purpose_verified():
    """A-02: 비안전 목적 확인·인용 원문 존재 → EXCLUDE. [SYNTHETIC]"""
    rec = _record(
        title="중소기업 수출마케팅 지원사업",
        summary="해외 판로 개척 및 수출 마케팅 비용을 지원합니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("EXCLUDE", "해외 판로 개척 및 수출 마케팅"),
    )
    assert result.verdict == "EXCLUDE"
    assert any("cited_verified" in b for b in result.basis)


# ---------------------------------------------------------------------------
# HOLD paths
# ---------------------------------------------------------------------------


def test_A03_hold_llm_call_raises():
    """A-03: LLM 호출 중 예외 발생 → HOLD (llm_call_error). [SYNTHETIC]"""
    rec = _record(title="안전보건 지원사업", summary="산업안전 관련 지원입니다.")
    result = analyze_relevance(rec, llm_call_fn=_mock_error())
    assert result.verdict == "HOLD"
    assert any("llm_call_error" in b for b in result.basis)


def test_A04_hold_cited_evidence_not_in_source():
    """A-04: 인용 문구가 원문에 없음 (환각) → HOLD (cited_not_in_source). [SYNTHETIC]"""
    rec = _record(
        title="안전보건 지원사업",
        summary="산업안전 관련 지원입니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "원문에 전혀 없는 가상의 문구"),
    )
    assert result.verdict == "HOLD"
    assert any("cited_not_in_source" in b for b in result.basis)


def test_A05_hold_cited_evidence_in_negation_context():
    """A-05: 인용이 부정 맥락("제외") 내에 위치 → HOLD (negation_context). [SYNTHETIC]

    "산업안전 설비 지원 제외" — 인용 문구는 원문에 존재하지만
    바로 뒤에 '제외'가 붙어 INCLUDE 판정을 뒷받침하지 않는다.
    """
    rec = _record(
        title="산업안전 지원사업 안내",
        summary="이 사업은 산업안전 설비 지원 제외. 일반 제품 디자인 개선을 지원합니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "산업안전 설비 지원"),
    )
    assert result.verdict == "HOLD"
    assert any("negation_context" in b for b in result.basis)


def test_A06_hold_low_confidence():
    """A-06: LLM confidence=low → HOLD (low_confidence). [SYNTHETIC]"""
    rec = _record(
        title="안전보건 지원사업",
        summary="산업안전 관련 지원입니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "산업안전 관련", confidence="low"),
    )
    assert result.verdict == "HOLD"
    assert any("low_confidence" in b for b in result.basis)


def test_A07_hold_non_dict_response():
    """A-07: LLM이 dict가 아닌 값 반환 → HOLD (invalid_response_type). [SYNTHETIC]"""
    rec = _record(title="테스트", summary="테스트 요약")
    result = analyze_relevance(rec, llm_call_fn=_mock_non_dict())
    assert result.verdict == "HOLD"
    assert any("invalid_response_type" in b for b in result.basis)


def test_A08_hold_missing_cited_evidence_field():
    """A-08: cited_evidence 필드 누락 → HOLD (missing_cited_evidence). [SYNTHETIC]"""
    rec = _record(title="안전보건 지원사업", summary="산업안전 관련 지원입니다.")

    def _fn(s, u):
        return {"verdict": "INCLUDE", "purpose_summary": "테스트", "confidence": "high"}

    result = analyze_relevance(rec, llm_call_fn=_fn)
    assert result.verdict == "HOLD"
    assert any("missing_cited_evidence" in b for b in result.basis)


def test_A09_hold_invalid_verdict_value():
    """A-09: verdict가 허용된 3값 외 반환 → HOLD (invalid_verdict). [SYNTHETIC]"""
    rec = _record(title="테스트", summary="테스트 요약")

    def _fn(s, u):
        return {"verdict": "MAYBE", "cited_evidence": "테스트", "confidence": "high"}

    result = analyze_relevance(rec, llm_call_fn=_fn)
    assert result.verdict == "HOLD"
    assert any("invalid_verdict" in b for b in result.basis)


def test_A10_hold_llm_returns_hold():
    """A-10: LLM 자체가 HOLD 반환 → HOLD (llm_hold). [SYNTHETIC]"""
    rec = _record(title="테스트", summary="불명확한 사업 내용")
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("HOLD", cited_evidence="", confidence="low"),
    )
    assert result.verdict == "HOLD"
    assert any("llm_hold" in b for b in result.basis)


# ---------------------------------------------------------------------------
# Layer 1 연동 계약
# ---------------------------------------------------------------------------


def test_A11_layer1_in_scope_passes_through_layer2():
    """A-11: Layer 1 IN_SCOPE도 Layer 2에서 LLM 판정 거침 — 즉시 확정 없음. [SYNTHETIC]

    layer1_verdict="IN_SCOPE"가 전달돼도 analyze_relevance는 LLM mock을
    그대로 호출하고 그 결과를 반영한다.
    """
    rec = _record(
        title="산업재해 예방설비 설치비 지원사업",
        summary="산업재해 예방을 위한 안전설비를 지원합니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "산업재해 예방을 위한 안전설비"),
        layer1_verdict="IN_SCOPE",
    )
    assert result.verdict == "INCLUDE"
    assert any("cited_verified" in b for b in result.basis)


def test_A12_layer1_out_of_scope_passes_through_layer2():
    """A-12: layer1_verdict=OUT_OF_SCOPE → Layer 2 LLM 판정을 그대로 거침. [SYNTHETIC]

    skip 경로가 없으므로 LLM mock 결과가 그대로 반영된다.
    """
    rec = _record(
        title="중소기업 수출지원사업",
        summary="해외 판로 개척 및 수출 마케팅을 지원합니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("EXCLUDE", "해외 판로 개척"),
        layer1_verdict="OUT_OF_SCOPE",
    )
    assert result.verdict == "EXCLUDE"
    assert any("cited_verified" in b for b in result.basis)


def test_A13_layer1_verdict_recorded_llm_always_called():
    """A-13: layer1_verdict 전달 여부와 무관하게 LLM은 항상 호출된다. [SYNTHETIC]

    skip_layer1_exclude 파라미터가 제거됐으므로 layer1_verdict="OUT_OF_SCOPE"여도
    LLM 호출이 반드시 발생해야 한다.
    """
    called: list[bool] = []

    def _tracking_fn(system_msg: str, user_msg: str) -> dict:
        called.append(True)
        return {"verdict": "EXCLUDE", "cited_evidence": "해외 판로", "confidence": "high"}

    rec = _record(title="수출지원", summary="해외 판로를 지원합니다.")
    analyze_relevance(
        rec,
        llm_call_fn=_tracking_fn,
        layer1_verdict="OUT_OF_SCOPE",
    )
    assert called, "LLM must always be called regardless of layer1_verdict"


# ---------------------------------------------------------------------------
# Cross-cutting / contract tests
# ---------------------------------------------------------------------------


def test_A14_basis_contains_no_sensitive_data():
    """A-14: basis에 HTML·개인정보·API 키·원문 전체 없음."""
    rec = _record(
        title="<script>xss</script>산업재해 예방설비",
        summary="<p>안전설비 설치를 지원합니다</p>",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "안전설비 설치를 지원합니다"),
    )
    for b in result.basis:
        assert "<" not in b
        assert ">" not in b
        assert "script" not in b
        assert len(b) < 100


def test_A15_record_not_modified():
    """A-15: analyze_relevance 호출 후 원본 레코드 불변."""
    rec = _record(
        title="산업재해 예방설비 설치비 지원",
        summary="안전설비 설치를 지원합니다.",
    )
    original_title   = rec.title
    original_summary = rec.summary

    analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "안전설비 설치를 지원합니다"),
    )

    assert rec.title   == original_title
    assert rec.summary == original_summary


def test_A16_verdict_is_valid_literal():
    """A-16: verdict는 항상 INCLUDE / EXCLUDE / HOLD 중 하나."""
    cases = [
        (
            _record(title="안전설비 지원", summary="안전설비 설치를 지원합니다."),
            _mock_llm("INCLUDE", "안전설비 설치를 지원합니다"),
        ),
        (
            _record(title="수출지원", summary="해외 판로 개척을 지원합니다."),
            _mock_llm("EXCLUDE", "해외 판로 개척"),
        ),
        (
            _record(title="테스트", summary="내용 없음"),
            _mock_error(),
        ),
    ]
    valid = {"INCLUDE", "EXCLUDE", "HOLD"}
    for rec, fn in cases:
        result = analyze_relevance(rec, llm_call_fn=fn)
        assert result.verdict in valid


def test_A17_basis_is_non_empty_tuple():
    """A-17: basis는 항상 비어 있지 않은 tuple."""
    rec = _record(title="테스트", summary=None)
    result = analyze_relevance(rec, llm_call_fn=_mock_error())
    assert isinstance(result.basis, tuple)
    assert len(result.basis) >= 1


# ---------------------------------------------------------------------------
# R1 corrections
# ---------------------------------------------------------------------------


def test_A18_hold_exclude_with_safety_keyword_in_source():
    """A-18: EXCLUDE 판정인데 원문에 직접 산업안전 키워드 존재 → HOLD (exclude_safety_signal_present).

    R1-01: 원문에 '산업재해'가 포함돼 있으면 LLM EXCLUDE를 자동 확정할 수 없다.
    [SYNTHETIC]
    """
    rec = _record(
        title="중소기업 지원사업",
        summary="해외 판로 개척을 지원합니다. 산업재해 예방 설비는 본 사업 범위에 포함됩니다.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("EXCLUDE", "해외 판로 개척을 지원합니다"),
    )
    assert result.verdict == "HOLD"
    assert any("exclude_safety_signal_present" in b for b in result.basis)


def test_A19_hold_include_full_text_exclusion_outside_window():
    """A-19: INCLUDE 판정인데 원문 전체에 제외 마커 존재 (인용 위치 ±50자 밖) → HOLD.

    R1-02: _cited_in_negation_context 창 밖에 있더라도 full_text_exclusion_conflict.
    안전설비지원제외 마커를 인용 구절에서 충분히 떨어뜨려 창 밖에 위치시킨다.
    [SYNTHETIC]
    """
    padding = "가" * 200
    rec = _record(
        title="안전보건 지원사업",
        summary=f"산업재해 예방을 위한 안전설비를 지원합니다. {padding} 안전설비 지원 제외.",
    )
    result = analyze_relevance(
        rec,
        llm_call_fn=_mock_llm("INCLUDE", "산업재해 예방을 위한 안전설비를 지원합니다"),
    )
    assert result.verdict == "HOLD"
    assert any("full_text_exclusion_conflict" in b for b in result.basis)


def test_A20_hold_non_string_verdict_field():
    """A-20: verdict 필드가 정수 등 비문자열 → 예외 없이 HOLD (invalid_verdict).

    R1-03: _safe_str() 적용으로 str() 변환 후 검증한다.
    42는 허용된 verdict 값이 아니므로 HOLD.
    [SYNTHETIC]
    """
    rec = _record(title="테스트", summary="테스트 요약")

    def _fn(s, u):
        return {"verdict": 42, "cited_evidence": "테스트", "confidence": "high"}

    result = analyze_relevance(rec, llm_call_fn=_fn)
    assert result.verdict == "HOLD"
    assert any("invalid_verdict" in b for b in result.basis)


def test_A21_no_skip_layer1_exclude_parameter():
    """A-21: analyze_relevance 시그니처에 skip_layer1_exclude 파라미터 없음.

    R1-04: 품질 평가 미완료 상태에서 bypass 경로 제거.
    [SYNTHETIC]
    """
    import inspect
    sig = inspect.signature(analyze_relevance)
    assert "skip_layer1_exclude" not in sig.parameters


def test_A22_hold_non_string_cited_evidence_despite_match_in_source():
    """A-22: cited_evidence=42 (비문자열) + 원문에 '42' 존재 → HOLD (invalid_cited_evidence_type).

    R1-03 보완: str()로 변환해 인용 근거로 수용하지 않는다.
    원문 "42개 중소기업"에 '42'가 존재하더라도 비문자열 인용은 차단된다.
    [SYNTHETIC]
    """
    rec = _record(
        title="안전보건 지원사업",
        summary="42개 중소기업을 대상으로 안전설비 설치를 지원합니다.",
    )

    def _fn(s, u):
        return {"verdict": "INCLUDE", "cited_evidence": 42, "confidence": "high"}

    result = analyze_relevance(rec, llm_call_fn=_fn)
    assert result.verdict == "HOLD"
    assert any("invalid_cited_evidence_type" in b for b in result.basis)
