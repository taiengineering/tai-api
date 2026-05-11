"""TAI 법령엔진 v3.0 — engine.stage_1_splitter 단위 테스트.

실행: pytest tests/v3/test_stage_1_splitter.py -v

DB 의존성 X 검증 (supabase=None으로 fallback 테스트). DB 통합 테스트는
integration 단계에서 별도 구성 예정.
"""

from __future__ import annotations

import pytest

from engine.morpheme import MorphemeEngine
from engine.stage_1_splitter import SplitClause, Stage1Splitter


@pytest.fixture(scope="module")
def morpheme() -> MorphemeEngine:
    return MorphemeEngine()


@pytest.fixture
def splitter(morpheme: MorphemeEngine) -> Stage1Splitter:
    """DB 없는 splitter (fallback 동작 검증용)."""
    return Stage1Splitter(morpheme_engine=morpheme, supabase=None)


# ----- 기본 분리 동작 -----

class TestSplitBasic:
    def test_empty_text_returns_empty(self, splitter: Stage1Splitter):
        assert splitter.split("part-id-1", "") == []
        assert splitter.split("part-id-1", "   ") == []

    def test_no_rules_fallback_preserves_text(self, splitter: Stage1Splitter):
        """룰 0개 → part_text 전체를 1개 의미절로 보존 (누락 0건 원칙)."""
        text = "사업주는 근로자에게 안전대를 제공하여야 한다."
        clauses = splitter.split("part-id-1", text)
        assert len(clauses) == 1
        c = clauses[0]
        assert c.source_text == text
        assert c.part_id == "part-id-1"
        assert c.clause_position == 0
        assert c.char_start == 0
        assert c.char_end == len(text)
        assert c.split_rule_id is None  # fallback 이므로 룰 ID 없음

    def test_text_strip_applied(self, splitter: Stage1Splitter):
        text = "   조문 내용   "
        clauses = splitter.split("p1", text)
        assert clauses[0].source_text == "조문 내용"

    def test_rule_count_initially_zero(self, splitter: Stage1Splitter):
        assert splitter.rule_count == 0


# ----- text_hash (중복 검출) -----

class TestTextHash:
    def test_hash_deterministic(self, splitter: Stage1Splitter):
        """동일 텍스트 → 동일 hash."""
        text = "동일한 텍스트"
        c1 = splitter.split("p1", text)[0]
        c2 = splitter.split("p2", text)[0]
        assert c1.text_hash == c2.text_hash

    def test_hash_different_for_different_text(self, splitter: Stage1Splitter):
        c1 = splitter.split("p1", "텍스트 A")[0]
        c2 = splitter.split("p1", "텍스트 B")[0]
        assert c1.text_hash != c2.text_hash

    def test_hash_is_sha256_hex(self, splitter: Stage1Splitter):
        h = Stage1Splitter.hash_text("테스트")
        assert len(h) == 64  # sha256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in h)


# ----- tokenization_json 캐시 -----

class TestTokenizationCache:
    def test_tokens_attached(self, splitter: Stage1Splitter):
        """_make_clause가 tokenization_json을 추가하는지."""
        text = "사업주는 설치하여야 한다."
        clause = splitter.split("p1", text)[0]
        assert clause.tokenization_json is not None
        assert len(clause.tokenization_json) > 0

    def test_token_structure(self, splitter: Stage1Splitter):
        text = "처한다."
        clause = splitter.split("p1", text)[0]
        assert clause.tokenization_json is not None
        first = clause.tokenization_json[0]
        assert set(first.keys()) >= {"form", "tag", "start", "len"}


# ----- batch -----

class TestSplitBatch:
    def test_split_batch_multiple_parts(self, splitter: Stage1Splitter):
        items = [
            ("p1", "첫 번째 조문."),
            ("p2", "두 번째 조문."),
            ("p3", "세 번째 조문."),
        ]
        clauses = splitter.split_batch(items)
        assert len(clauses) == 3
        # 각 part_id 보존 확인
        assert {c.part_id for c in clauses} == {"p1", "p2", "p3"}

    def test_split_batch_empty(self, splitter: Stage1Splitter):
        assert splitter.split_batch([]) == []


# ----- 행 직렬화 (DB INSERT 용) -----

class TestClauseToRow:
    def test_row_contains_all_fields(self):
        c = SplitClause(
            part_id="p1",
            clause_position=0,
            source_text="텍스트",
            text_hash="abc",
            char_start=0,
            char_end=3,
            tokenization_json=[{"form": "x", "tag": "NNG", "start": 0, "len": 1}],
        )
        row = Stage1Splitter._clause_to_row(c)
        assert row["part_id"] == "p1"
        assert row["clause_position"] == 0
        assert row["source_text"] == "텍스트"
        assert row["text_hash"] == "abc"
        assert row["char_start"] == 0
        assert row["char_end"] == 3
        assert row["split_rule_id"] is None
        assert row["tokenization_json"] is not None


# ----- DB 없을 때 안전성 -----

class TestNoSupabaseSafety:
    def test_load_rules_returns_zero(self, splitter: Stage1Splitter):
        """supabase=None이면 load_rules는 0 반환, 예외 X."""
        assert splitter.load_rules() == 0

    def test_insert_clauses_returns_zero(self, splitter: Stage1Splitter):
        """supabase=None이면 insert는 0 반환, 예외 X."""
        clauses = splitter.split("p1", "텍스트.")
        assert splitter.insert_clauses(clauses) == 0

    def test_insert_empty_list(self, splitter: Stage1Splitter):
        assert splitter.insert_clauses([]) == 0
