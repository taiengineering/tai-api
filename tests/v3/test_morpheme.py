"""TAI 법령엔진 v3.0 — engine.morpheme 단위 테스트.

실행: pytest tests/v3/test_morpheme.py -v

Day 1 발견 (10 sub_type baseline)을 그대로 테스트로 고정. 향후 Kiwi 업그레이드·사전 추가·룰 변경 시 회귀 검출.
"""

from __future__ import annotations

import pytest

from engine.morpheme import MorphemeEngine, TokenizationMeta


@pytest.fixture(scope="module")
def engine() -> MorphemeEngine:
    return MorphemeEngine()


# ----- 기본 토큰화 -----

class TestTokenize:
    def test_empty_string(self, engine: MorphemeEngine):
        assert engine.tokenize("") == []
        assert engine.tokenize("   ") == []

    def test_single_text(self, engine: MorphemeEngine):
        tokens = engine.tokenize("안전난간을 설치할 것")
        assert len(tokens) > 0
        forms = [t.form for t in tokens]
        assert "안전" in forms
        assert "난간" in forms

    def test_batch(self, engine: MorphemeEngine):
        texts = ["안전난간을 설치할 것", "검사를 할 수 있다."]
        results = engine.tokenize_batch(texts)
        assert len(results) == 2
        assert all(len(r) > 0 for r in results)

    def test_empty_batch(self, engine: MorphemeEngine):
        assert engine.tokenize_batch([]) == []


# ----- Day 1 발견 helper 검증 -----

class TestSignatures:
    def test_tail_signature_obligation(self, engine: MorphemeEngine):
        """OBLIGATION_HEADER — EF 종결 필수."""
        tokens = engine.tokenize("사업주는 안전대를 설치하여야 한다.")
        sig = MorphemeEngine.get_tail_signature(tokens, 3)
        assert "EF" in sig
        assert sig.endswith("./SF")

    def test_tail_signature_penalty(self, engine: MorphemeEngine):
        """PENALTY — 처하/VV + ᆫ다/EF 시그니처."""
        tokens = engine.tokenize("벌금에 처한다.")
        sig = MorphemeEngine.get_tail_signature(tokens, 3)
        assert "처하/VV" in sig
        assert "EF" in sig

    def test_head_signature_exception(self, engine: MorphemeEngine):
        """EXCEPTION_CLAUSE — head-1 = 다만/MAG."""
        tokens = engine.tokenize(
            "다만, 작업의 성질상 곤란한 경우에는 그러하지 아니하다."
        )
        head = MorphemeEngine.get_head_signature(tokens, 1)
        assert head == "다만/MAG"


# ----- HEADER vs ITEM 분별자 (Day 1 핵심 발견) -----

class TestHeaderVsItem:
    HEADER_SAMPLES = [
        "안전대를 설치하여야 한다.",                # OBLIGATION
        "거부할 수 없다.",                            # PROHIBITION
        "벌금에 처한다.",                              # PENALTY
        "검사를 할 수 있다.",                          # AUTHORITY
        "근로자를 말한다.",                            # DEFINITION
        "대통령령으로 정한다.",                      # DELEGATION
        "이 법을 적용하지 아니한다.",                # EXEMPTION
    ]
    ITEM_SAMPLES = [
        "안전난간을 설치할 것",                       # OBLIGATION_DETAIL_ITEM
        "안전조치를 하지 아니한 자",                  # PENALTY_VIOLATOR_ITEM
    ]

    @pytest.mark.parametrize("text", HEADER_SAMPLES)
    def test_header_has_ef(self, engine: MorphemeEngine, text: str):
        tokens = engine.tokenize(text)
        assert MorphemeEngine.has_ef_terminator(tokens) is True, f"HEADER인데 EF 부재: {text}"

    @pytest.mark.parametrize("text", ITEM_SAMPLES)
    def test_item_no_ef(self, engine: MorphemeEngine, text: str):
        tokens = engine.tokenize(text)
        assert MorphemeEngine.has_ef_terminator(tokens) is False, f"ITEM인데 EF 존재: {text}"


# ----- analyze (토큰화 + 메타) -----

class TestAnalyze:
    def test_combined(self, engine: MorphemeEngine):
        tokens, meta = engine.analyze("벌금에 처한다.")
        assert isinstance(meta, TokenizationMeta)
        assert meta.has_ef is True
        assert meta.token_count == len(tokens)
        assert "/" in meta.tail_3
        assert meta.last_tag == "EF"

    def test_empty(self, engine: MorphemeEngine):
        tokens, meta = engine.analyze("")
        assert tokens == []
        assert meta.token_count == 0
        assert meta.has_ef is False
        assert meta.tail_3 == ""


# ----- 사전 등록 -----

class TestUserDict:
    def test_add_user_word(self, engine: MorphemeEngine):
        initial = engine.user_dict_size
        ok = engine.add_user_word("산업안전보건법", "NNP", 0.0)
        assert ok is True
        assert engine.user_dict_size == initial + 1

    def test_add_user_word_empty_skipped(self, engine: MorphemeEngine):
        initial = engine.user_dict_size
        assert engine.add_user_word("", "NNG", 0.0) is False
        assert engine.user_dict_size == initial

    def test_load_dict_terms_skips_empty(self, engine: MorphemeEngine):
        initial = engine.user_dict_size
        terms = [
            {"term": "TAI안전테스트", "pos_tag": "NNP", "score": 0.0},
            {"term": "", "pos_tag": "NNG", "score": 0.0},      # skip
            {"term": None, "pos_tag": "NNG", "score": 0.0},    # skip
        ]
        added = engine.load_dict_terms(terms)
        assert added == 1
        assert engine.user_dict_size == initial + 1
