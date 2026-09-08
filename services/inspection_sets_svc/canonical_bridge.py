"""services/inspection_sets_svc/canonical_bridge.py

WO-SAAS-OBLIGATION-IDENTITY-BRIDGE-001 / STEP 4B-1.

공식 LEG obligation(full_result.obligations_raw[] element) 과
SaaS inspection_sets 운영 row 사이의 **최소 exact-identity 경계**를 한 곳에 고정한다.

- 이 단계는 DB row 를 생성하지 않는다(pure preparation).
- exact identity = raw obligation.atom_id EXACT. legal_rule_id 변환/law+article/text/source_index/LLM/fuzzy = 0.
- operation presentation 은 기존 map_diagnosis mapper 계열의 map_operation_presentation() 만 재사용(신규 mapper 0).
- atom_id 부재 → identity 부재(fail-close). source_atom_ids 만으로 atom_id 합성 금지.

경계(§6): map_operation_presentation 은 assignee/next_due/status/execution 등 SaaS 운영값을 생성하지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.obligation_presentation_mapper import map_operation_presentation


def canonical_atom_id(raw_obligation: Any) -> Optional[str]:
    """raw obligation → exact atom_id (있고 non-empty 문자열일 때만). 없으면 None(합성 금지)."""
    if not isinstance(raw_obligation, dict):
        return None
    aid = raw_obligation.get("atom_id")
    if isinstance(aid, str) and aid.strip():
        return aid.strip()
    return None


def build_canonical_inspection_identity(raw_obligation: Any) -> Optional[Dict[str, Any]]:
    """공식 obligation 1건 → {legal_obligation_atom_id, operation_presentation}.

    atom_id 부재 → None (bridge identity 부재, fail-close).
    operation_presentation = map_operation_presentation(raw) 결과 그대로(재해석 0).
    입력 mutation 없음. 이 반환값을 그대로 inspection_sets 에 저장하라는 뜻이 아니며,
    legal_obligation_atom_id 만 운영 row 의 exact-identity carrier 로 쓴다(§5).
    """
    atom_id = canonical_atom_id(raw_obligation)
    if atom_id is None:
        return None
    return {
        "legal_obligation_atom_id": atom_id,
        "operation_presentation": map_operation_presentation(raw_obligation),
    }
