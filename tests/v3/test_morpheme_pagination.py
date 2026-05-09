"""TAI v3.0 — load_verified_dict_from_db 페이지네이션 회귀 테스트.

P0 (자동 로드 1,000건 미스터리) 회귀 fixture.
DB 실측 1,725건 통합 환경을 mock으로 재현.

핸드오프 §10 학습 #1: 단위 fixture가 통합 환경 재현해야 회귀 방지 효과 보장.
8개 어휘 fixture 통과 = 464개·1,725개 통합 통과 보장 X — 따라서 카운트를 실측에 맞춤.
"""

from __future__ import annotations

import logging

import pytest

from engine.morpheme import MorphemeEngine

from tests.v3.conftest import MockSupabase


def _make_dict_terms(
    n: int,
    prefix: str = "term",
    term_type: str = "GENERIC",
) -> list[dict]:
    """n건의 더미 dict_legal_terms 행 생성.

    공백 없는 단일어로 생성 (Kiwi add_user_word 경로 — add_re_word 회피).
    한글 prefix 사용해 Kiwi가 NNG로 받아들이게 함.
    """
    return [
        {
            "term": f"{prefix}어휘{i:05d}",
            "pos_tag": "NNG",
            "score": 0.0,
            "term_type": term_type,
        }
        for i in range(n)
    ]


class TestPagination:
    """페이지네이션 정확성 — P0 핵심 회귀 fixture."""

    def test_load_exact_1725(self):
        """DB 실측 1,725건 통합 환경 재현 — 1페이지(1000) + 2페이지(725) 정상 로드."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(1725),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb)
        assert added == 1725
        assert eng.user_dict_size == 1725

    def test_load_exactly_page_size(self):
        """카운트가 page_size와 동일 (1000) — 빈 다음 페이지로 종료."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(1000),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb)
        assert added == 1000

    def test_load_below_page_size(self):
        """카운트가 page_size 미만 (500) — 1페이지에서 종료."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(500),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb)
        assert added == 500

    def test_load_empty(self):
        """빈 결과 — 0 반환, 무한 루프 X."""
        sb = MockSupabase(table_data={"dict_legal_terms": []})
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb)
        assert added == 0

    def test_max_pages_safety(self):
        """max_pages 상한 — 5,000건이지만 max_pages=2 → 2,000만 로드."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(5000),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb, max_pages=2)
        assert added == 2000  # 두 페이지만 처리

    def test_max_pages_warning_logged(self, caplog):
        """max_pages 도달 + 마지막 페이지 풀 → warning 발생."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(2000),  # 정확히 max_pages*page_size
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        with caplog.at_level(logging.WARNING):
            added = eng.load_verified_dict_from_db(sb, max_pages=2)
        assert added == 2000
        assert any(
            "max_pages" in r.message and "도달" in r.message
            for r in caplog.records
        )

    def test_term_type_filter(self):
        """term_type 필터 + 페이지네이션 — DB 실측 LAW_NAME 423건 재현."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(423, term_type="LAW_NAME"),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb, term_type="LAW_NAME")
        assert added == 423

    def test_custom_page_size(self):
        """page_size 명시 변경 — 500 단위로 1,725건 = 4페이지(500+500+500+225)."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(1725),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        added = eng.load_verified_dict_from_db(sb, page_size=500)
        assert added == 1725


class TestAutoLoadIntegration:
    """__init__ 자동 로드 + 페이지네이션 통합 — P0 본질 회귀."""

    def test_auto_load_with_1725(self):
        """MorphemeEngine(supabase=sb) 자동 로드가 1,725건 정확 로드 (1000 X)."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(1725),
        })
        eng = MorphemeEngine(supabase=sb)  # auto_load_verified_dict=True 기본
        assert eng.user_dict_size == 1725, (
            f"P0 회귀: 1,725건 기대했으나 {eng.user_dict_size}건 로드됨. "
            "PostgREST max-rows 페이지네이션 회피 실패 가능성."
        )

    def test_auto_load_with_2500(self):
        """향후 dict 확장 시나리오 — 2,500건도 정확 로드."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(2500),
        })
        eng = MorphemeEngine(supabase=sb)
        assert eng.user_dict_size == 2500


class TestDeprecatedLimit:
    """기존 limit 인자 호환성 — deprecation warning."""

    def test_limit_arg_warns_but_works(self, caplog):
        """limit 인자가 들어와도 페이지네이션 동작 + warning 발생."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(1500),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        with caplog.at_level(logging.WARNING):
            added = eng.load_verified_dict_from_db(sb, limit=5000)
        assert added == 1500  # limit 무시하고 페이지네이션으로 전체 로드
        assert any(
            "deprecated" in r.message.lower()
            for r in caplog.records
        )

    def test_no_limit_no_warning(self, caplog):
        """limit 미지정 시 deprecation warning 발생 X."""
        sb = MockSupabase(table_data={
            "dict_legal_terms": _make_dict_terms(100),
        })
        eng = MorphemeEngine(supabase=sb, auto_load_verified_dict=False)
        with caplog.at_level(logging.WARNING):
            eng.load_verified_dict_from_db(sb)
        assert not any(
            "deprecated" in r.message.lower()
            for r in caplog.records
        )
