from __future__ import annotations

from typing import Any, Dict, Optional

from clients.leg_runtime_client import _LEG_INPUT_FIELDS   # 103 direct vocabulary = 단일 SoT (second list 금지)
from schemas.legal_engine import DiagnoseStep1Body


def build_unified_leg_input(
    *,
    sector: str,
    source_facts: Dict[str, Any],
    factory_id: Optional[str] = None,
) -> DiagnoseStep1Body:
    """이미 획득된 source_facts → LEG 103 vocabulary exact-key만 lossless 수용한 DiagnoseStep1Body.

    계약(FREEZE):
      - allowlist = _LEG_INPUT_FIELDS (exact-name). vocabulary와 정확히 같은 이름 값만 보존.
      - None / blank string / whitespace-only = ABSENT (키 미포함).
      - False / 0 / [] / {} = 보존(truthy filter 금지).
      - 값 변환/추정/파생/기본값 생성 금지. 400 / 1.0 / "건축" 등 synthetic 슬롯 미설정.
      - alias(has_chemical→has_chemical_substance) / derived(has_building_elevator) 는 이 코어 책임 아님.
        기존 build_facility 가 그대로 처리한다(무변경).
      - input 에만 싣는다(top-level 미복제 → build_facility 가 input 사용 → shadow 불가).
      - sector projection(BUILDING N1 gate 등)은 build_facility 담당. 여기서 자르지 않는다.
    """
    facts = source_facts if isinstance(source_facts, dict) else {}
    unified: Dict[str, Any] = {}
    for code in _LEG_INPUT_FIELDS:
        if code not in facts:
            continue
        val = facts[code]
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        unified[code] = val
    return DiagnoseStep1Body(sector=sector, input=unified, factory_id=factory_id)
