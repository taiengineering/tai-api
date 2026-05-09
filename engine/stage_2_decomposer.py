"""TAI 법령엔진 v3.0 — Stage 2 역할별 분해 모듈 (골격).

stage_1_clauses → 8 역할 분해 + 25 sub_type 분류 + 7 IF 패턴 분류 → stage_2_elements INSERT.

설계 원칙 (MASTER_HANDOFF §2):
  - LLM 사용 X. rule_classify_subtype / rule_classify_if_pattern / rule_pos_to_role 명시 룰만.
  - 법령 보전. source_text 의미해석 X.
  - 누락 0건. 룰 0개 또는 미매칭 → sub_type='UNCLASSIFIED', if_pattern='UNCONDITIONAL'으로 보전.
  - 100% link. 모든 StageElement는 clause_id 보유.

Day 1 baseline 직결 (MorphemeEngine 헬퍼 사용):
  - has_ef_terminator(tokens) → HEADER vs ITEM 1차 분기
  - get_tail_signature(tokens, 3) → sub_type 룰 매칭
  - get_head_signature(tokens, 1) → 다만/MAG → EXCEPTION 즉시 검출

→ 현재는 골격. 실제 메칭 로직은 Track E 룰 데이터 채울 때 구현.

계층: Service (FastAPI import 금지).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from engine.morpheme import MorphemeEngine

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


# ----- 기본값 상수 -----
DEFAULT_SUB_TYPE = "UNCLASSIFIED"
DEFAULT_IF_PATTERN = "UNCONDITIONAL"


@dataclass
class StageElement:
    """역할별 분해 결과. stage_2_elements 테이블 INSERT에 그대로 사용.

    8 역할 (마스터 §4.1):
      executor / recipient / what / when_value / where_value / how / condition / exception
    """
    clause_id: str
    sub_type: str = DEFAULT_SUB_TYPE
    if_pattern: str = DEFAULT_IF_PATTERN
    executor: str | None = None
    recipient: str | None = None
    what: str | None = None
    when_value: str | None = None
    where_value: str | None = None
    how: str | None = None
    condition: str | None = None
    exception: str | None = None
    applied_rules: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 1.0


class Stage2Decomposer:
    """Stage 2 역할별 분해 엔진.

    Usage:
        morpheme = MorphemeEngine(supabase=sb)
        decomposer = Stage2Decomposer(morpheme, supabase=sb)
        decomposer.load_rules()
        elements = decomposer.decompose_batch(stage_1_rows)
        decomposer.insert_elements(elements)
    """

    def __init__(
        self,
        morpheme_engine: MorphemeEngine,
        supabase: SupabaseClient | None = None,
    ) -> None:
        self.morpheme = morpheme_engine
        self.supabase = supabase
        self._subtype_rules: list[dict[str, Any]] = []
        self._if_rules: list[dict[str, Any]] = []
        self._role_rules: list[dict[str, Any]] = []

    # ----- 룰 로드 -----

    def load_rules(self) -> dict[str, int]:
        """3개 룰 테이블을 한 번에 로드.

        Returns:
            {"subtype": N, "if_pattern": M, "role": K}
        """
        if self.supabase is None:
            logger.warning("Supabase client 미설정 — 룰 로드 스킵")
            return {"subtype": 0, "if_pattern": 0, "role": 0}

        r1 = (
            self.supabase.table("rule_classify_subtype")
            .select("id, rule_name, sub_type, match_strategy, pattern, pattern_position, priority")
            .eq("enabled", True)
            .order("priority", desc=False)
            .execute()
        )
        self._subtype_rules = r1.data or []

        r2 = (
            self.supabase.table("rule_classify_if_pattern")
            .select("id, rule_name, if_pattern, pattern_type, pattern, priority")
            .eq("enabled", True)
            .order("priority", desc=False)
            .execute()
        )
        self._if_rules = r2.data or []

        r3 = (
            self.supabase.table("rule_pos_to_role")
            .select("id, rule_name, pos_pattern, target_role, priority")
            .eq("enabled", True)
            .order("priority", desc=False)
            .execute()
        )
        self._role_rules = r3.data or []

        counts = {
            "subtype": len(self._subtype_rules),
            "if_pattern": len(self._if_rules),
            "role": len(self._role_rules),
        }
        logger.info("Stage 2 룰 로드: %s", counts)
        return counts

    @property
    def subtype_rule_count(self) -> int:
        return len(self._subtype_rules)

    @property
    def if_rule_count(self) -> int:
        return len(self._if_rules)

    @property
    def role_rule_count(self) -> int:
        return len(self._role_rules)

    # ----- 분해 메인 -----

    def decompose(
        self,
        clause_id: str,
        source_text: str,
        tokenization_json: list[dict[str, Any]] | None = None,
    ) -> StageElement:
        """단일 의미절 분해.

        Args:
            clause_id: stage_1_clauses.id
            source_text: 의미절 원문
            tokenization_json: stage_1에서 캐시된 토큰화 결과 (현재는 미사용 — TODO)
        """
        # 현재는 단순 재토큰화. TODO: tokenization_json 재사용 최적화.
        _tokens, _meta = self.morpheme.analyze(source_text)

        # 룰 0개 fallback (누락 0건 원칙 준수)
        if not self._subtype_rules and not self._if_rules:
            return StageElement(
                clause_id=clause_id,
                sub_type=DEFAULT_SUB_TYPE,
                if_pattern=DEFAULT_IF_PATTERN,
                applied_rules=[],
                confidence_score=0.0,  # 룰 없으니 신뢰도 0
            )

        # TODO: 실제 룰 적용 로직
        # 1. sub_type 분류 (rule_classify_subtype: priority 순, has_ef + tail/head 매칭)
        # 2. if_pattern 분류 (rule_classify_if_pattern: KEYWORD/POS_SEQ/REGEX)
        # 3. 8 역할 분해 (rule_pos_to_role: POS 시퀀스 → 역할)
        # Track E 룰 데이터 채울 때 구현. 현재는 fallback 동일.
        return StageElement(
            clause_id=clause_id,
            sub_type=DEFAULT_SUB_TYPE,
            if_pattern=DEFAULT_IF_PATTERN,
            applied_rules=[],
            confidence_score=0.0,
        )

    def decompose_batch(
        self,
        clauses: list[dict[str, Any]],
    ) -> list[StageElement]:
        """일괄 분해. clauses: stage_1_clauses 행들 (dict 리스트).

        각 row 최소 'id', 'source_text' 보유 가정. 둘 중 하나라도 누락 시 skip + warning.
        """
        elements: list[StageElement] = []
        for row in clauses:
            cid = row.get("id")
            text = row.get("source_text")
            if not cid or not text:
                logger.warning("clause id 또는 source_text 누락: %r", row)
                continue
            elements.append(self.decompose(
                clause_id=cid,
                source_text=text,
                tokenization_json=row.get("tokenization_json"),
            ))
        return elements

    # ----- DB 쓰기 -----

    def insert_elements(
        self,
        elements: list[StageElement],
        chunk_size: int = 100,
    ) -> int:
        """stage_2_elements에 일괄 INSERT.

        chunk_size ≤ 100 (메모리 원칙).
        """
        if self.supabase is None:
            logger.warning("Supabase client 미설정 — INSERT 스킵")
            return 0
        if not elements:
            return 0
        rows = [self._element_to_row(e) for e in elements]
        inserted = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            try:
                res = self.supabase.table("stage_2_elements").insert(chunk).execute()
                inserted += len(res.data or [])
            except Exception as e:  # noqa: BLE001
                logger.error("stage_2_elements INSERT 실패 (chunk start=%d): %s", i, e)
        logger.info("stage_2_elements INSERT 완료: %d/%d", inserted, len(rows))
        return inserted

    @staticmethod
    def _element_to_row(e: StageElement) -> dict[str, Any]:
        return {
            "clause_id": e.clause_id,
            "sub_type": e.sub_type,
            "if_pattern": e.if_pattern,
            "executor": e.executor,
            "recipient": e.recipient,
            "what": e.what,
            "when_value": e.when_value,
            "where_value": e.where_value,
            "how": e.how,
            "condition": e.condition,
            "exception": e.exception,
            "applied_rules": e.applied_rules,
            "confidence_score": e.confidence_score,
        }
