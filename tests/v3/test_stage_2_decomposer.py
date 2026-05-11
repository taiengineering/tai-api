"""TAI 법령엔진 v3.0 — engine.stage_2_decomposer 단위 테스트.

실행: pytest tests/v3/test_stage_2_decomposer.py -v
"""

from __future__ import annotations

import pytest

from engine.morpheme import MorphemeEngine
from engine.stage_2_decomposer import (
    DEFAULT_IF_PATTERN,
    DEFAULT_SUB_TYPE,
    Stage2Decomposer,
    StageElement,
)


@pytest.fixture(scope="module")
def morpheme() -> MorphemeEngine:
    return MorphemeEngine()


@pytest.fixture
def decomposer(morpheme: MorphemeEngine) -> Stage2Decomposer:
    return Stage2Decomposer(morpheme_engine=morpheme, supabase=None)


# ----- 기본 분해 -----

class TestDecomposeBasic:
    def test_no_rules_fallback_unclassified(self, decomposer: Stage2Decomposer):
        """룰 0개 → UNCLASSIFIED + UNCONDITIONAL 보전 (누락 0건)."""
        e = decomposer.decompose("c1", "사업주는 안전대를 설치하여야 한다.")
        assert e.clause_id == "c1"
        assert e.sub_type == DEFAULT_SUB_TYPE
        assert e.if_pattern == DEFAULT_IF_PATTERN
        assert e.confidence_score == 0.0

    def test_8_roles_default_none(self, decomposer: Stage2Decomposer):
        """룰 없는 상태에서 8 역할은 모두 None."""
        e = decomposer.decompose("c1", "테스트.")
        for role in ["executor", "recipient", "what",
                     "when_value", "where_value", "how",
                     "condition", "exception"]:
            assert getattr(e, role) is None, f"{role} 기본값이 None이 아님"

    def test_applied_rules_empty_list(self, decomposer: Stage2Decomposer):
        e = decomposer.decompose("c1", "테스트.")
        assert e.applied_rules == []

    def test_default_constants(self):
        """기본값 상수가 마스터 §5·6 spec과 일치."""
        assert DEFAULT_SUB_TYPE == "UNCLASSIFIED"
        assert DEFAULT_IF_PATTERN == "UNCONDITIONAL"


# ----- batch -----

class TestDecomposeBatch:
    def test_batch_multiple(self, decomposer: Stage2Decomposer):
        clauses = [
            {"id": "c1", "source_text": "첫 번째 의미절."},
            {"id": "c2", "source_text": "두 번째 의미절."},
            {"id": "c3", "source_text": "세 번째 의미절."},
        ]
        elements = decomposer.decompose_batch(clauses)
        assert len(elements) == 3
        assert {e.clause_id for e in elements} == {"c1", "c2", "c3"}

    def test_batch_empty(self, decomposer: Stage2Decomposer):
        assert decomposer.decompose_batch([]) == []

    def test_batch_skips_missing_fields(self, decomposer: Stage2Decomposer):
        """id 또는 source_text 누락 row는 skip."""
        clauses = [
            {"id": "c1", "source_text": "정상."},
            {"id": None, "source_text": "id 누락."},
            {"id": "c3", "source_text": None},
            {"id": "c4", "source_text": "정상2."},
        ]
        elements = decomposer.decompose_batch(clauses)
        assert len(elements) == 2
        assert {e.clause_id for e in elements} == {"c1", "c4"}


# ----- 룰 카운트 -----

class TestRuleCount:
    def test_initial_zero_all(self, decomposer: Stage2Decomposer):
        assert decomposer.subtype_rule_count == 0
        assert decomposer.if_rule_count == 0
        assert decomposer.role_rule_count == 0


# ----- 행 직렬화 (DB INSERT 용) -----

class TestElementToRow:
    def test_row_complete_fields(self):
        e = StageElement(
            clause_id="c1",
            sub_type="OBLIGATION_HEADER",
            if_pattern="CONDITIONAL_EVENT",
            executor="사업주",
            what="안전대 설치",
            confidence_score=0.85,
        )
        row = Stage2Decomposer._element_to_row(e)
        assert row["clause_id"] == "c1"
        assert row["sub_type"] == "OBLIGATION_HEADER"
        assert row["if_pattern"] == "CONDITIONAL_EVENT"
        assert row["executor"] == "사업주"
        assert row["what"] == "안전대 설치"
        assert row["confidence_score"] == 0.85
        # 미설정 역할은 None
        assert row["recipient"] is None
        assert row["when_value"] is None

    def test_row_default_element(self):
        """기본값으로 생성된 StageElement 직렬화."""
        e = StageElement(clause_id="c1")
        row = Stage2Decomposer._element_to_row(e)
        assert row["clause_id"] == "c1"
        assert row["sub_type"] == DEFAULT_SUB_TYPE
        assert row["if_pattern"] == DEFAULT_IF_PATTERN
        assert row["applied_rules"] == []
        assert row["confidence_score"] == 1.0


# ----- DB 없을 때 안전성 -----

class TestNoSupabaseSafety:
    def test_load_rules_returns_zeros(self, decomposer: Stage2Decomposer):
        """supabase=None → 0 반환, 예외 X."""
        counts = decomposer.load_rules()
        assert counts == {"subtype": 0, "if_pattern": 0, "role": 0}

    def test_insert_elements_returns_zero(self, decomposer: Stage2Decomposer):
        e = StageElement(clause_id="c1")
        assert decomposer.insert_elements([e]) == 0

    def test_insert_empty_list(self, decomposer: Stage2Decomposer):
        assert decomposer.insert_elements([]) == 0
