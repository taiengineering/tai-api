"""TAI 법령엔진 v3.0 — Stage 3 객체화 모듈 (골격).

stage_2_elements → 마스터 객체 (master_rule_v2 등) 매핑 → stage_3_objects INSERT.

설계 원칙 (MASTER_HANDOFF §2):
  - LLM 사용 X. rule_objectify 명시 룰만.
  - UNCLASSIFIED / DELETED / PARSE_FRAGMENT 는 즉시 skip (매핑 대상 X).
  - 룰 0개 또는 매칭 실패 → None return + stage_3 row 안 만듦.
  - 100% 매핑 추적은 verification_log 어디는 차원 이용 예정.

매핑 흐름:
  1. UNCLASSIFIED 등 SKIP_MAPPING_SUBTYPES → 즉시 None
  2. 룰 0개 → None (시도 X)
  3. source_sub_type 매칭 룰 priority 순 검색
  4. field_mapping(jsonb) 적용 → target_master_table INSERT → ID 획득
  5. StageObject (mapping_status='MAPPED') 반환

→ 현재는 골격 (1·2만 구현). 3-5는 Track E에서 수행.

계층: Service (FastAPI import 금지).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


# ----- 매핑 skip 대상 sub_type -----
# 의미적으로 매핑 대상 아닌 sub_type. 사용자 직접 검토 영역.
SKIP_MAPPING_SUBTYPES: frozenset[str] = frozenset({
    "UNCLASSIFIED",
    "DELETED",
    "PARSE_FRAGMENT",
})


@dataclass
class StageObject:
    """stage_3_objects 매핑 결과."""
    element_id: str
    target_master_table: str
    target_master_id: str | None = None
    field_values: dict[str, Any] = field(default_factory=dict)
    mapping_rule_id: str | None = None
    mapping_status: str = "PENDING"  # PENDING / MAPPED / FAILED / SKIPPED
    error_message: str | None = None


class Stage3Objectifier:
    """Stage 3 객체화 엔진.

    Usage:
        objectifier = Stage3Objectifier(supabase=sb)
        objectifier.load_rules()
        objects = objectifier.objectify_batch(stage_2_rows)
        objectifier.insert_objects(objects)
    """

    def __init__(self, supabase: SupabaseClient | None = None) -> None:
        self.supabase = supabase
        self._rules: list[dict[str, Any]] = []

    # ----- 룰 로드 -----

    def load_rules(self) -> int:
        """rule_objectify 활성 룰 priority 순 로드."""
        if self.supabase is None:
            logger.warning("Supabase client 미설정 — 룰 로드 스킵")
            return 0
        res = (
            self.supabase.table("rule_objectify")
            .select("id, rule_name, source_sub_type, target_master_table, field_mapping, priority")
            .eq("enabled", True)
            .order("priority", desc=False)
            .execute()
        )
        self._rules = res.data or []
        logger.info("Stage 3 룰 로드: %d개", len(self._rules))
        return len(self._rules)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ----- 객체화 메인 -----

    def objectify(
        self,
        element_id: str,
        sub_type: str,
        element_fields: dict[str, Any] | None = None,
    ) -> StageObject | None:
        """단일 element 객체화. 매핑 불가 시 None.

        Args:
            element_id: stage_2_elements.id
            sub_type: stage_2_elements.sub_type
            element_fields: stage_2 전체 row (8 역할 + condition + exception 등)

        Returns:
            매핑 결과 StageObject 또는 대상 X면 None.
        """
        # 1. 매핑 skip 대상
        if sub_type in SKIP_MAPPING_SUBTYPES:
            return None

        # 2. 룰 0개 → 시도 X
        if not self._rules:
            return None

        # TODO: 3-5단계 구현 (Track E)
        # 3. source_sub_type 매칭 룰 priority 순 검색
        # 4. field_mapping(jsonb) 적용 → target_master_table INSERT
        # 5. StageObject (mapping_status='MAPPED') 반환
        return None

    def objectify_batch(
        self,
        elements: list[dict[str, Any]],
    ) -> list[StageObject]:
        """일괄 객체화. None은 필터링."""
        objects: list[StageObject] = []
        for row in elements:
            eid = row.get("id")
            sub = row.get("sub_type", "")
            if not eid:
                logger.warning("element id 누락: %r", row)
                continue
            obj = self.objectify(
                element_id=eid,
                sub_type=sub,
                element_fields=row,
            )
            if obj is not None:
                objects.append(obj)
        return objects

    # ----- DB 쓰기 -----

    def insert_objects(
        self,
        objects: list[StageObject],
        chunk_size: int = 100,
    ) -> int:
        """stage_3_objects에 일괄 INSERT."""
        if self.supabase is None:
            logger.warning("Supabase client 미설정 — INSERT 스킵")
            return 0
        if not objects:
            return 0
        rows = [self._object_to_row(o) for o in objects]
        inserted = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            try:
                res = self.supabase.table("stage_3_objects").insert(chunk).execute()
                inserted += len(res.data or [])
            except Exception as e:  # noqa: BLE001
                logger.error("stage_3_objects INSERT 실패 (chunk start=%d): %s", i, e)
        logger.info("stage_3_objects INSERT 완료: %d/%d", inserted, len(rows))
        return inserted

    @staticmethod
    def _object_to_row(o: StageObject) -> dict[str, Any]:
        return {
            "element_id": o.element_id,
            "target_master_table": o.target_master_table,
            "target_master_id": o.target_master_id,
            "field_values": o.field_values,
            "mapping_rule_id": o.mapping_rule_id,
            "mapping_status": o.mapping_status,
            "error_message": o.error_message,
        }
