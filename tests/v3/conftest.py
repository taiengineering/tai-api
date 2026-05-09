"""tests/v3/conftest.py — 공통 fixture (mock supabase 등).

mock supabase: load_rules / insert_* 등 DB 의존 코드의 단위 테스트용.
supabase-py 메서드 체이닝 패턴 (.table().select().eq().execute()) 재현.

Fixtures:
  mock_sb_empty       — 모든 테이블 빈 결과
  mock_sb_with_data   — 주요 테이블에 1~2건씩 주입
  mock_sb_failing     — 모든 메서드 RuntimeError (error path)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class MockResult:
    """supabase execute() 반환값 mock."""
    data: list[dict[str, Any]]
    count: int | None = None


class _Builder:
    """supabase-py 쿼리 빌더 mock.

    .select() / .eq() / .order() / .limit() / .like() 모두 self 반환.
    .execute() → MockResult.
    .insert() → _InsertBuilder.
    """

    def __init__(
        self,
        table: str,
        table_data: list[dict[str, Any]],
        record_inserts: dict[str, list[Any]],
    ):
        self._table = table
        self._data = table_data
        self._inserts = record_inserts
        self._count_requested = False

    def select(self, *_a, **kwargs) -> "_Builder":
        if kwargs.get("count") == "exact":
            self._count_requested = True
        return self

    def eq(self, *_a, **_kw) -> "_Builder": return self
    def neq(self, *_a, **_kw) -> "_Builder": return self
    def order(self, *_a, **_kw) -> "_Builder": return self
    def limit(self, *_a, **_kw) -> "_Builder": return self
    def like(self, *_a, **_kw) -> "_Builder": return self
    def in_(self, *_a, **_kw) -> "_Builder": return self
    def gte(self, *_a, **_kw) -> "_Builder": return self
    def lte(self, *_a, **_kw) -> "_Builder": return self

    def insert(self, rows: Any) -> "_InsertBuilder":
        rows_list = rows if isinstance(rows, list) else [rows]
        self._inserts.setdefault(self._table, []).extend(rows_list)
        return _InsertBuilder(rows_list)

    def execute(self) -> MockResult:
        return MockResult(
            data=list(self._data),
            count=len(self._data) if self._count_requested else None,
        )


class _InsertBuilder:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def execute(self) -> MockResult:
        return MockResult(data=self._rows, count=None)


class _FailingBuilder:
    """모든 메서드가 RuntimeError 발생 — error path 테스트용."""

    def __getattr__(self, name):
        def _raise(*_a, **_kw):
            raise RuntimeError(f"Mock failure: {name}")
        return _raise


@dataclass
class MockSupabase:
    """supabase Client mock.

    table_data: 테이블별 select 결과 데이터
    fail_tables: 해당 테이블 호출 시 RuntimeError 발생
    inserted: insert된 row 누적 (테스트 검증용)
    """

    table_data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    fail_tables: set[str] = field(default_factory=set)
    inserted: dict[str, list[Any]] = field(default_factory=dict)

    def table(self, name: str):
        if name in self.fail_tables:
            return _FailingBuilder()
        return _Builder(name, self.table_data.get(name, []), self.inserted)


# ----- 표준 fixture -----

@pytest.fixture
def mock_sb_empty() -> MockSupabase:
    """모든 테이블 빈 결과. load_* → 0 검증용."""
    return MockSupabase()


@pytest.fixture
def mock_sb_with_data() -> MockSupabase:
    """주요 테이블에 1~2건씩 데이터 주입."""
    return MockSupabase(table_data={
        "rule_classify_subtype": [{
            "id": "r1", "rule_name": "test_obligation",
            "sub_type": "OBLIGATION_HEADER", "match_strategy": "TAIL_MATCH",
            "pattern": "...", "pattern_position": "TAIL", "priority": 1,
        }],
        "rule_classify_if_pattern": [{
            "id": "i1", "rule_name": "test_event",
            "if_pattern": "CONDITIONAL_EVENT", "pattern_type": "KEYWORD",
            "pattern": "...", "priority": 1,
        }],
        "rule_pos_to_role": [{
            "id": "p1", "rule_name": "test_role",
            "pos_pattern": "...", "target_role": "executor", "priority": 1,
        }],
        "rule_objectify": [{
            "id": "o1", "rule_name": "test_obj",
            "source_sub_type": "OBLIGATION_HEADER",
            "target_master_table": "master_rule_v2",
            "field_mapping": {}, "priority": 1,
        }],
        "rule_clause_split": [{
            "id": "s1", "rule_name": "test_split",
            "split_strategy": "SENTENCE", "pattern": r"\.", "priority": 1,
        }],
        "dict_legal_terms": [
            {"term": "테스트법", "pos_tag": "NNP", "score": 0.0,
             "term_type": "LAW_NAME"},
            {"term": "다단어 테스트법", "pos_tag": "NNP", "score": 0.0,
             "term_type": "LAW_NAME"},
        ],
    })


@pytest.fixture
def mock_sb_failing() -> MockSupabase:
    """모든 INSERT/SELECT 실패. error path 검증용."""
    return MockSupabase(fail_tables={
        "rule_classify_subtype", "rule_classify_if_pattern",
        "rule_pos_to_role", "rule_objectify", "rule_clause_split",
        "dict_legal_terms", "stage_1_clauses", "stage_2_elements",
        "stage_3_objects", "verification_log",
    })
