"""TAI 법령엔진 v3.0 — engine.stage_3_objectifier 단위 테스트.

실행: pytest tests/v3/test_stage_3_objectifier.py -v
"""

from __future__ import annotations

import pytest

from engine.stage_3_objectifier import (
    SKIP_MAPPING_SUBTYPES,
    Stage3Objectifier,
    StageObject,
)


@pytest.fixture
def objectifier() -> Stage3Objectifier:
    return Stage3Objectifier(supabase=None)


# ----- skip 대상 sub_type -----

class TestSkipSubtypes:
    @pytest.mark.parametrize("sub_type", sorted(SKIP_MAPPING_SUBTYPES))
    def test_skip_returns_none(self, objectifier: Stage3Objectifier, sub_type: str):
        """SKIP_MAPPING_SUBTYPES → 즉시 None."""
        result = objectifier.objectify(
            element_id="e1",
            sub_type=sub_type,
            element_fields={"executor": "사업주"},
        )
        assert result is None

    def test_skip_set_contains_expected(self):
        """SKIP 세트가 의도대로 구성됨."""
        assert "UNCLASSIFIED" in SKIP_MAPPING_SUBTYPES
        assert "DELETED" in SKIP_MAPPING_SUBTYPES
        assert "PARSE_FRAGMENT" in SKIP_MAPPING_SUBTYPES
        # 매핑 대상 sub_type은 들어있으면 안 됨
        assert "OBLIGATION_HEADER" not in SKIP_MAPPING_SUBTYPES
        assert "PENALTY_HEADER" not in SKIP_MAPPING_SUBTYPES


# ----- 룰 0개 fallback -----

class TestNoRulesFallback:
    def test_mappable_subtype_no_rules_returns_none(self, objectifier: Stage3Objectifier):
        """매핑 가능한 sub_type이지만 룰 0개 → None."""
        result = objectifier.objectify(
            element_id="e1",
            sub_type="OBLIGATION_HEADER",
            element_fields={"executor": "사업주"},
        )
        assert result is None

    def test_initial_rule_count_zero(self, objectifier: Stage3Objectifier):
        assert objectifier.rule_count == 0


# ----- batch -----

class TestObjectifyBatch:
    def test_batch_filters_none_results(self, objectifier: Stage3Objectifier):
        """매핑 불가 elements는 결과 리스트에서 제외."""
        elements = [
            {"id": "e1", "sub_type": "UNCLASSIFIED"},          # skip
            {"id": "e2", "sub_type": "OBLIGATION_HEADER"},     # 룰 없으니 None
            {"id": "e3", "sub_type": "DELETED"},               # skip
        ]
        objects = objectifier.objectify_batch(elements)
        assert objects == []

    def test_batch_skips_missing_id(self, objectifier: Stage3Objectifier):
        elements = [
            {"id": None, "sub_type": "OBLIGATION_HEADER"},
            {"id": "", "sub_type": "OBLIGATION_HEADER"},
        ]
        objects = objectifier.objectify_batch(elements)
        assert objects == []

    def test_batch_empty(self, objectifier: Stage3Objectifier):
        assert objectifier.objectify_batch([]) == []


# ----- 행 직렬화 -----

class TestObjectToRow:
    def test_row_complete(self):
        o = StageObject(
            element_id="e1",
            target_master_table="master_rule_v2",
            target_master_id="m1",
            field_values={"executor_text": "사업주"},
            mapping_rule_id="r1",
            mapping_status="MAPPED",
        )
        row = Stage3Objectifier._object_to_row(o)
        assert row["element_id"] == "e1"
        assert row["target_master_table"] == "master_rule_v2"
        assert row["target_master_id"] == "m1"
        assert row["field_values"] == {"executor_text": "사업주"}
        assert row["mapping_rule_id"] == "r1"
        assert row["mapping_status"] == "MAPPED"
        assert row["error_message"] is None

    def test_row_default(self):
        """기본값으로 생성된 StageObject 직렬화."""
        o = StageObject(element_id="e1", target_master_table="master_x")
        row = Stage3Objectifier._object_to_row(o)
        assert row["element_id"] == "e1"
        assert row["target_master_table"] == "master_x"
        assert row["target_master_id"] is None
        assert row["field_values"] == {}
        assert row["mapping_status"] == "PENDING"


# ----- DB 없을 때 안전성 -----

class TestNoSupabaseSafety:
    def test_load_rules_returns_zero(self, objectifier: Stage3Objectifier):
        assert objectifier.load_rules() == 0

    def test_insert_objects_returns_zero(self, objectifier: Stage3Objectifier):
        o = StageObject(element_id="e1", target_master_table="master_x")
        assert objectifier.insert_objects([o]) == 0

    def test_insert_empty_list(self, objectifier: Stage3Objectifier):
        assert objectifier.insert_objects([]) == 0
