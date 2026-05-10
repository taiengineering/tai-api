"""sample_accuracy.py 단위 테스트 — Ground Truth 카테고리화 (Phase 2.2-Patch)."""

from __future__ import annotations

import pytest

from engine.sample_accuracy import (
    CATEGORY_VERIFICATION_PATTERNS,
    compute_stage2_sample_accuracy,
    _verify_row,
)


class TestVerifyRow:
    """_verify_row 카테고리화 검증."""

    def test_obligation_header_tp(self) -> None:
        assert _verify_row("OBLIGATION_HEADER", "관계 서류를 제출하여야 한다.") == "TP"
        assert _verify_row("OBLIGATION_HEADER", "준수해야 한다.") == "TP"
        assert _verify_row("OBLIGATION_HEADER", "의무가 있다.") == "TP"

    def test_authority_header_tp(self) -> None:
        assert _verify_row("AUTHORITY_HEADER", "명할 수 있다.") == "TP"
        assert _verify_row("AUTHORITY_HEADER", "폐지할 수 있다.") == "TP"

    def test_as_bonda_tail3_tp(self) -> None:
        assert _verify_row("AS_본다", "제출한 것으로 본다.") == "TP"

    def test_as_bonda_wa_gatda_fp(self) -> None:
        assert _verify_row("AS_본다", "다음 각 호와 같다.") == "FP"
        assert _verify_row("AS_본다", "별표 1과 같다.") == "FP"

    def test_obligation_detail_gwan_sahang_fp(self) -> None:
        assert _verify_row("OBLIGATION_DETAIL_ITEM", "관한 사항") == "FP"

    def test_enumeration_list_intro_tp(self) -> None:
        assert _verify_row("ENUMERATION_LIST_INTRO", "다음 각 호와 같다.") == "TP"
        assert _verify_row("ENUMERATION_LIST_INTRO", "다음과 같다.") == "TP"

    def test_reference_to_attachment_tp(self) -> None:
        assert _verify_row("REFERENCE_TO_ATTACHMENT", "별표 1과 같다.") == "TP"
        assert (
            _verify_row("REFERENCE_TO_ATTACHMENT", "별지 제3호 서식에 따른다.") == "TP"
        )

    def test_reference_invocation_tp(self) -> None:
        assert (
            _verify_row("REFERENCE_INVOCATION", "제5조의 규정을 준용한다.") == "TP"
        )

    def test_uc_returns_uc(self) -> None:
        assert _verify_row("UNCLASSIFIED", "아무 텍스트") == "UC"

    def test_weak_returns_weak(self) -> None:
        assert _verify_row("WEAK_한다단순", "제출한다.") == "WEAK"
        assert _verify_row("WEAK_있다단순", "있다.") == "WEAK"

    def test_phase1_tp(self) -> None:
        assert _verify_row("DEFINITION_INTRO", "아무 텍스트") == "PHASE1_TP"
        assert _verify_row("TITLE_HEADER", "제1장 총칙") == "PHASE1_TP"

    def test_deleted_tp(self) -> None:
        assert _verify_row("DELETED", "삭제 <2020. 1. 1.>") == "TP"

    def test_exception_clause_tp(self) -> None:
        assert (
            _verify_row("EXCEPTION_CLAUSE", "다만, 부득이한 경우는 제외한다.") == "TP"
        )

    def test_patterns_dict_consistency(self) -> None:
        assert "AS_본다" in CATEGORY_VERIFICATION_PATTERNS
        assert "ENUMERATION_LIST_INTRO" in CATEGORY_VERIFICATION_PATTERNS


class TestComputeStage2SampleAccuracy:
    def test_offline_stub(self) -> None:
        acc, n = compute_stage2_sample_accuracy(supabase=None, sample_size=100)
        assert acc == 0.95
        assert n == 100

    def test_pm_diagnosis_reproduction_via_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PM 진단 89.74% 근사 — 고정 분포 mock."""

        def _fake_fetch(
            _sb: object,
            *,
            sample_articles: int,
            law_id: int | str | None = None,
            law_batch: list[int | str] | None = None,
            exclude_isolated: bool = False,
        ) -> list[dict]:
            _ = sample_articles
            _ = law_id
            _ = law_batch
            _ = exclude_isolated
            rows: list[dict] = []
            rows.extend(
                [{"sub_type": "OBLIGATION_HEADER", "source_text": "준수해야 한다."}]
                * 315
            )
            rows.extend(
                [{"sub_type": "AS_본다", "source_text": "다음 각 호와 같다."}] * 24
            )
            rows.extend([{"sub_type": "WEAK_X", "source_text": "x"}] * 12)
            return rows

        monkeypatch.setattr(
            "engine.sample_accuracy._fetch_sample_rows",
            _fake_fetch,
        )
        acc, classified = compute_stage2_sample_accuracy(
            object(),
            sample_size=351,
        )
        assert classified == 351
        expected = 315 / 351  # ≈ 0.8974358974358975
        assert abs(acc - expected) < 1e-9
