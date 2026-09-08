"""services/canonical/subcontractor_source_expansion.py

WO-E2E-OBJ-SEM-001-IMPLEMENT-REV1 — subcontractor_work_types → LEG domain boolean expansion.

subcontractor_work_types (multi_select array) 를 build_unified_leg_input 진입 전 source_facts 에서
deterministic expansion 하여 LEG domain fact 2개를 만든다.

계약:
  - array 존재(사용자 정상 응답) → 미선택 = 해당 유형 아님 (false).
      FIRE_FACILITY 포함 → has_fire_facility_subcontract = True, 아니면 False.
      ICT 포함           → has_ict_subcontract = True, 아니면 False.
  - subcontractor_work_types key 자체 ABSENT → 두 boolean 모두 ABSENT (키 미생성).
      "미응답 → false" 금지.
  - 기존 source_facts 를 mutate 하지 않는다(새 dict 반환). 다른 값 무변경.
  - alias/derive/파생 없음. GENERAL_CONSTRUCTION/OTHER 는 LEG fact 로 확장하지 않는다(도메인 무관).
"""
from __future__ import annotations
from typing import Any, Dict

_KEY = "subcontractor_work_types"
_FIRE = "FIRE_FACILITY"
_ICT = "ICT"


def expand_subcontractor_work_types(source_facts: Dict[str, Any]) -> Dict[str, Any]:
    """source_facts + subcontractor_work_types → domain boolean 추가된 새 dict.
    key ABSENT → 확장 없음(두 boolean 미생성)."""
    facts = dict(source_facts) if isinstance(source_facts, dict) else {}
    if _KEY not in facts:
        return facts  # ABSENT → 확장 없음 (미응답→false 금지)
    val = facts[_KEY]
    if not isinstance(val, (list, tuple)):
        # array 아님 → 확장하지 않음 (억지 변환 금지)
        return facts
    selected = set(str(x) for x in val)
    facts["has_fire_facility_subcontract"] = (_FIRE in selected)
    facts["has_ict_subcontract"] = (_ICT in selected)
    return facts
