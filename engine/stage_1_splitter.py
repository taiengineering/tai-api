"""TAI 법령엔진 v3.0 — Stage 1 의미절 분리 모듈 (골격).

law_article_part.part_text → 의미절 단위로 분리하여 stage_1_clauses에 저장.

설계 원칙 (MASTER_HANDOFF §2):
  - LLM 사용 X. rule_clause_split 테이블의 명시 룰만.
  - 법령 보전. source_text 원문 보존 + text_hash로 중복 검출.
  - 누락 0건. 룰 0개일 때 part_text 전체를 1개 의미절로 보전.
  - 100% link. 모든 SplitClause는 part_id 보유.

룰 타입 (rule_clause_split.pattern_type):
  - REGEX: 정규식 매칭 위치에서 분리
  - POS_SEQ: 형태소 POS 시퀀스 매칭
  - DELIMITER: 구분자 (마침표 등)
  - ENUMERATION: enumeration 부모-자식 분리

→ 현재는 골격. 실제 적용 로직은 Track E가 룰 데이터 채울 때 구현.

계층: Service (FastAPI import 금지).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from engine.morpheme import MorphemeEngine

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class SplitClause:
    """분리된 의미절 단위 결과.

    stage_1_clauses 테이블 INSERT에 그대로 사용.
    """
    part_id: str
    clause_position: int
    source_text: str
    text_hash: str
    text_normalized: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    split_rule_id: str | None = None
    tokenization_json: list[dict[str, Any]] | None = field(default=None)


class Stage1Splitter:
    """Stage 1 의미절 분리 엔진.

    Usage:
        engine = MorphemeEngine()
        splitter = Stage1Splitter(engine, supabase=sb)
        splitter.load_rules()
        clauses = splitter.split(part_id, part_text)
        splitter.insert_clauses(clauses)
    """

    def __init__(
        self,
        morpheme_engine: MorphemeEngine,
        supabase: SupabaseClient | None = None,
    ) -> None:
        self.morpheme = morpheme_engine
        self.supabase = supabase
        self._rules: list[dict[str, Any]] = []

    # ----- 룰 로드 -----

    def load_rules(self) -> int:
        """rule_clause_split 활성 룰을 우선순위 순 로드."""
        if self.supabase is None:
            logger.warning("Supabase client 미설정 — 룰 로드 스킵")
            return 0
        res = (
            self.supabase.table("rule_clause_split")
            .select("id, rule_name, pattern_type, pattern, split_at, priority")
            .eq("enabled", True)
            .order("priority", desc=False)
            .execute()
        )
        self._rules = res.data or []
        logger.info("Stage 1 룰 로드: %d개", len(self._rules))
        return len(self._rules)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ----- 분리 메인 -----

    def split(self, part_id: str, part_text: str) -> list[SplitClause]:
        """단일 part_text를 의미절로 분리.

        룰 0개 또는 매칭 안 됨 → fallback (part_text 전체를 1개 의미절로 보존).
        """
        if not part_text or not part_text.strip():
            return []

        # 룰 0개 fallback (누락 0건 원칙 준수)
        if not self._rules:
            return [self._make_clause(
                part_id=part_id,
                clause_position=0,
                source_text=part_text.strip(),
                char_start=0,
                char_end=len(part_text),
                split_rule_id=None,
            )]

        # TODO: REGEX / POS_SEQ / DELIMITER / ENUMERATION 룰 적용 로직
        # Track E 룰 데이터 채울 때 구현. 현재는 fallback 동일.
        return [self._make_clause(
            part_id=part_id,
            clause_position=0,
            source_text=part_text.strip(),
            char_start=0,
            char_end=len(part_text),
            split_rule_id=None,
        )]

    def split_batch(
        self,
        items: list[tuple[str, str]],
    ) -> list[SplitClause]:
        """일괄 분리. items: [(part_id, part_text), ...]

        한 번의 호출로 여러 part를 처리. 결과는 평면 list (clauses 합치기).
        """
        all_clauses: list[SplitClause] = []
        for part_id, part_text in items:
            all_clauses.extend(self.split(part_id, part_text))
        return all_clauses

    # ----- DB 쓰기 -----

    def insert_clauses(
        self,
        clauses: list[SplitClause],
        chunk_size: int = 100,
    ) -> int:
        """stage_1_clauses에 일괄 INSERT.

        chunk_size ≤ 100 (메모리 원칙: Supabase API 제한).
        """
        if self.supabase is None:
            logger.warning("Supabase client 미설정 — INSERT 스킵")
            return 0
        if not clauses:
            return 0
        rows = [self._clause_to_row(c) for c in clauses]
        inserted = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            try:
                res = self.supabase.table("stage_1_clauses").insert(chunk).execute()
                inserted += len(res.data or [])
            except Exception as e:  # noqa: BLE001
                logger.error("stage_1_clauses INSERT 실패 (chunk start=%d): %s", i, e)
        logger.info("stage_1_clauses INSERT 완료: %d/%d", inserted, len(rows))
        return inserted

    # ----- 내부 helper -----

    @staticmethod
    def hash_text(text: str) -> str:
        """sha256 hex digest — 중복 검출용."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _make_clause(
        self,
        *,
        part_id: str,
        clause_position: int,
        source_text: str,
        char_start: int | None = None,
        char_end: int | None = None,
        split_rule_id: str | None = None,
        text_normalized: str | None = None,
    ) -> SplitClause:
        # 토큰화 캐시 (Stage 2에서 재사용)
        tokens = self.morpheme.tokenize(source_text)
        tokenization_json = [
            {"form": t.form, "tag": t.tag, "start": t.start, "len": t.len}
            for t in tokens
        ]
        return SplitClause(
            part_id=part_id,
            clause_position=clause_position,
            source_text=source_text,
            text_hash=self.hash_text(source_text),
            text_normalized=text_normalized,
            char_start=char_start,
            char_end=char_end,
            split_rule_id=split_rule_id,
            tokenization_json=tokenization_json,
        )

    @staticmethod
    def _clause_to_row(c: SplitClause) -> dict[str, Any]:
        return {
            "part_id": c.part_id,
            "clause_position": c.clause_position,
            "source_text": c.source_text,
            "text_hash": c.text_hash,
            "text_normalized": c.text_normalized,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "split_rule_id": c.split_rule_id,
            "tokenization_json": c.tokenization_json,
        }
