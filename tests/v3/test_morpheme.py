"""TAI 법령엔진 v3.0 — engine.morpheme 단위 테스트.

실행: pytest tests/v3/test_morpheme.py -v

Day 1 발견 (10 sub_type baseline)을 테스트로 고정. Track C 권고 반영
(다단어 사전 + 자동 로드 옵션) 테스트 포함.
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
        tokens = engine.tokenize("사업주는 안전대를 설치하여야 한다.")
        sig = MorphemeEngine.get_tail_signature(tokens, 3)
        assert "EF" in sig
        assert sig.endswith("./SF")

    def test_tail_signature_penalty(self, engine: MorphemeEngine):
        tokens = engine.tokenize("벌금에 처한다.")
        sig = MorphemeEngine.get_tail_signature(tokens, 3)
        assert "처하/VV" in sig
        assert "EF" in sig

    def test_head_signature_exception(self, engine: MorphemeEngine):
        tokens = engine.tokenize(
            "다만, 작업의 성질상 곤란한 경우에는 그러하지 아니하다."
        )
        head = MorphemeEngine.get_head_signature(tokens, 1)
        assert head == "다만/MAG"


# ----- HEADER vs ITEM 분별자 (Day 1 핵심 발견) -----

class TestHeaderVsItem:
    HEADER_SAMPLES = [
        "안전대를 설치하여야 한다.",
        "거부할 수 없다.",
        "벌금에 처한다.",
        "검사를 할 수 있다.",
        "근로자를 말한다.",
        "대통령령으로 정한다.",
        "이 법을 적용하지 아니한다.",
    ]
    ITEM_SAMPLES = [
        "안전난간을 설치할 것",
        "안전조치를 하지 아니한 자",
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


# ----- 사전 등록 기본 -----

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
            {"term": "", "pos_tag": "NNG", "score": 0.0},
            {"term": None, "pos_tag": "NNG", "score": 0.0},
        ]
        added = engine.load_dict_terms(terms)
        assert added == 1
        assert engine.user_dict_size == initial + 1


# ----- 다단어 처리 (Track C 권고, 2026-05-09) -----

class TestMultiWordTerm:
    """공백 포함 어휘 사전 등록 — add_re_word 경로."""

    def test_multiword_law_name_registered(self):
        """다단어 법령명 등록 성공 — add_re_word 경로."""
        eng = MorphemeEngine()
        initial = eng.user_dict_size
        ok = eng.add_user_word("건축물의 분양에 관한 법률", "NNP", 0.0)
        assert ok is True
        assert eng.user_dict_size == initial + 1

    def test_multiword_with_special_chars(self):
        """정규식 메타문자 포함 — escape 처리되어 안전."""
        eng = MorphemeEngine()
        # 괄호 등 정규식 메타문자
        ok = eng.add_user_word("(주) 테스트회사", "NNP", 0.0)
        assert ok is True

    def test_load_dict_mixed_single_multi(self):
        """단일어 + 다단어 혼합 일괄 등록."""
        eng = MorphemeEngine()
        initial = eng.user_dict_size
        terms = [
            {"term": "산업안전상계법", "pos_tag": "NNP", "score": 0.0},
            {"term": "고압가스 안전관리법", "pos_tag": "NNP", "score": 0.0},
            {"term": "기후에너지환경부", "pos_tag": "NNP", "score": 0.0},
        ]
        added = eng.load_dict_terms(terms)
        assert added == 3
        assert eng.user_dict_size == initial + 3


# ----- 자동 사전 로드 옵션 (Track C 권고) -----

class TestAutoLoad:
    """__init__의 supabase + auto_load_verified_dict 옵션 검증."""

    def test_no_supabase_no_auto_load(self):
        """supabase=None → 자동 로드 X, 정상 초기화."""
        eng = MorphemeEngine(supabase=None)
        assert eng.user_dict_size == 0
        # 토큰화는 정상 동작
        tokens = eng.tokenize("테스트 텍스트.")
        assert len(tokens) > 0

    def test_auto_load_explicitly_disabled(self):
        """auto_load_verified_dict=False → supabase 주입되도 로드 X."""
        # mock supabase·설령 mock이 있어도 호출 자체가 안 되어야 함
        called = {"flag": False}

        class _MockSb:
            def table(self, *_a, **_kw):
                called["flag"] = True
                return self

        eng = MorphemeEngine(
            supabase=_MockSb(),  # type: ignore[arg-type]
            auto_load_verified_dict=False,
        )
        assert called["flag"] is False
        assert eng.user_dict_size == 0

    def test_auto_load_failure_safe(self):
        """자동 로드 실패 시 warning 후 계속 진행 (예외 X)."""

        class _BadSb:
            def table(self, *_a, **_kw):
                raise RuntimeError("DB 연결 실패 simulation")

        # 예외 터지지 않고 engine 생성 완료되어야 함
        eng = MorphemeEngine(
            supabase=_BadSb(),  # type: ignore[arg-type]
            auto_load_verified_dict=True,
        )
        assert eng.user_dict_size == 0
        # 토큰화는 정상 동작 (degraded)
        assert len(eng.tokenize("테스트")) > 0
