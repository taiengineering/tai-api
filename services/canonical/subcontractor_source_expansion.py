"""services/canonical/subcontractor_source_expansion.py

WO-E2E-OBJ-SEM-001-IMPLEMENT-REV1 (+ PATCH1) — subcontractor_work_types → LEG domain boolean expansion.

subcontractor_work_types (multi_select array) 를 build_unified_leg_input 진입 전 source_facts 에서
deterministic expansion 하여 LEG domain fact 2개를 만든다.

계약 (PATCH1 강화):
  expansion 은 다음이 **모두** 참일 때만 수행한다:
    - has_subcontractor is True (parent 조건 — stale child 값 서버 경계 차단)
    - subcontractor_work_types key 존재
    - value 가 list/tuple
    - len(value) >= 1 (non-empty)
    - 모든 항목이 VALID enum
  하나라도 실패 → has_fire_facility_subcontract / has_ict_subcontract 둘 다 생성 금지(ABSENT).
    즉 빈 배열 / unknown token / malformed / has_subcontractor≠true 를 "해당 없음"(false)으로 확정하지 않는다.

  정상 배열:
    FIRE_FACILITY 포함 → has_fire_facility_subcontract = True, 아니면 False
    ICT 포함           → has_ict_subcontract = True, 아니면 False
    (GENERAL_CONSTRUCTION/OTHER 는 LEG domain fact 로 확장하지 않는다 — 도메인 무관)

  기존 source_facts 를 mutate 하지 않는다(새 dict 반환). 다른 값 무변경.
"""
from __future__ import annotations
from typing import Any, Dict

_KEY = "subcontractor_work_types"
_FIRE = "FIRE_FACILITY"
_ICT = "ICT"
VALID = {"GENERAL_CONSTRUCTION", "FIRE_FACILITY", "ICT", "OTHER"}


def expand_subcontractor_work_types(source_facts: Dict[str, Any]) -> Dict[str, Any]:
    """source_facts + subcontractor_work_types → domain boolean 추가된 새 dict.
    검증 실패(absent/empty/unknown/malformed/parent false) → 확장 없음(두 boolean 미생성)."""
    facts = dict(source_facts) if isinstance(source_facts, dict) else {}

    # parent 조건: has_subcontractor 가 명시적 True 일 때만 (stale child 차단)
    if facts.get("has_subcontractor") is not True:
        return facts
    # key 존재
    if _KEY not in facts:
        return facts
    val = facts[_KEY]
    # list/tuple + non-empty
    if not isinstance(val, (list, tuple)) or len(val) < 1:
        return facts
    # 모든 항목이 VALID enum (unknown token 하나라도 있으면 ABSENT)
    items = [str(x) for x in val]
    if not all(x in VALID for x in items):
        return facts

    selected = set(items)
    facts["has_fire_facility_subcontract"] = (_FIRE in selected)
    facts["has_ict_subcontract"] = (_ICT in selected)
    return facts
