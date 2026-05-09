"""tests/v3/test_morpheme_collision.py — 부분문자열 충돌 회귀 테스트.

Track C v1.1 패치 (2026-05-09):
  '수도법'(단일어) + '하수도법 시행규칙'(다단어) 동시 등록 시
  다단어가 짧은 분해에 밀리는 케이스 검증.

→ MULTIWORD_SCORE_BOOST=10.0 적용으로 다단어 우선 결정.

실행: pytest tests/v3/test_morpheme_collision.py -v
"""

from __future__ import annotations

import pytest

from engine.morpheme import MULTIWORD_SCORE_BOOST, MorphemeEngine


# ----- 임계값 상수 결정 -----

class TestScoreBoostConstant:
    def test_boost_is_positive(self):
        """score boost가 양수여야 Kiwi 내부 우선순위 가중치 작동."""
        assert MULTIWORD_SCORE_BOOST > 0

    def test_boost_strong_enough(self):
        """일반 score(0.0) vs boost 간 충분한 격차 보장 (경험치 ≥ 5.0)."""
        assert MULTIWORD_SCORE_BOOST >= 5.0


# ----- 부분문자열 충돌 감지 -----

class TestSubstringCollision:
    """동일 어근이 단일어와 다단어에 동시 등록된 경우의 회귀."""

    @pytest.fixture
    def engine(self) -> MorphemeEngine:
        """수도법(단일어) + 하수도법(단일어) + 다단어 조합을 동시 등록한 엔진."""
        eng = MorphemeEngine()
        # Track C v1.1에서 실제 관찰된 충돌 패턴
        eng.add_user_word("수도법", "NNP")
        eng.add_user_word("하수도법", "NNP")
        eng.add_user_word("수도법 시행규칙", "NNP")
        eng.add_user_word("하수도법 시행규칙", "NNP")
        eng.add_user_word("수도법 시행령", "NNP")
        eng.add_user_word("하수도법 시행령", "NNP")
        return eng

    def test_long_multiword_wins_over_short_decomposition(
        self, engine: MorphemeEngine,
    ):
        """'하수도법 시행규칙'이 '하_IC + 수도법 시행규칙' 보다 우선."""
        tokens, _ = engine.analyze("하수도법 시행규칙")
        # 단일 토큰으로 묶여야 성공
        assert len(tokens) == 1, (
            f"예상 1토큰, 실제 {len(tokens)}토큰: "
            f"{[(t.form, t.tag) for t in tokens]}"
        )
        assert tokens[0].form == "하수도법 시행규칙"
        assert tokens[0].tag == "NNP"

    def test_decree_variant_also_wins(self, engine: MorphemeEngine):
        """시행령 변형에서도 다단어 우선."""
        tokens, _ = engine.analyze("하수도법 시행령")
        assert len(tokens) == 1
        assert tokens[0].form == "하수도법 시행령"
        assert tokens[0].tag == "NNP"

    def test_short_form_alone_still_works(self, engine: MorphemeEngine):
        """단독 '수도법' 입력 시에는 단일어 매칭 정상."""
        tokens, _ = engine.analyze("수도법")
        # '수도법'이 단일 NNP로 매칭
        assert len(tokens) >= 1
        assert tokens[0].form == "수도법"
        assert tokens[0].tag == "NNP"

    def test_full_law_text_with_collision(self, engine: MorphemeEngine):
        """실제 문장 맥락에서 '하수도법 시행규칙' 다단어 매칭."""
        tokens, _ = engine.analyze("하수도법 시행규칙 제5조에 따른다.")
        # 첫 토큰이 다단어 자체여야 함
        assert tokens[0].form == "하수도법 시행규칙"
        assert tokens[0].tag == "NNP"


# ----- 동일 구조 실제 실패 케이스 (Track C v1.1 관찰 단어) -----

class TestObservedFailures:
    """Track C v1.1 실행에서 실제 관찰된 3건 회귀.

    Cursor 2026-05-09 실행 결과:
        '하수도법 시행규칙' → 하_IC + 수도법 시행규칙_NNP (2토큰, 실패)
        '하수도법 시행령' → 해제 필요
        '체외진단의료기기법 시행령' → 3토큰, 해제 필요
    """

    @pytest.fixture
    def engine(self) -> MorphemeEngine:
        eng = MorphemeEngine()
        # 패치 이후 v1.1 실제 등록 재현: 어근 단일어 + 다단어 동시 등록
        for term in [
            "수도법", "하수도법",
            "수도법 시행규칙", "하수도법 시행규칙",
            "수도법 시행령", "하수도법 시행령",
            "체외진단의료기기법", "체외진단의료기기법 시행령",
        ]:
            eng.add_user_word(term, "NNP")
        return eng

    @pytest.mark.parametrize("term", [
        "하수도법 시행규칙",
        "하수도법 시행령",
        "체외진단의료기기법 시행령",
    ])
    def test_observed_failures_now_pass(self, engine: MorphemeEngine, term: str):
        """v1.1 실제 실패 단어 3건 회귀 검증."""
        tokens, _ = engine.analyze(term)
        assert len(tokens) == 1, (
            f"{term!r} → 예상 1토큰, 실제 {len(tokens)}토큰: "
            f"{[(t.form, t.tag) for t in tokens]}"
        )
        assert tokens[0].form == term
        assert tokens[0].tag == "NNP"
