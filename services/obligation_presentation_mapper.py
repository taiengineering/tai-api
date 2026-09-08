"""Obligation Presentation Mappers (PURE) — Diagnosis / Operation.

WO-OBLIGATION-RESULT-CONTRACT-001 / STEP 1.

입력 = full_result.obligations_raw[] element (dict).
출력 = 표시용 공통 ViewModel (dict).

PURE MAPPING ONLY:
- 입력 obligation 을 mutate 하지 않는다.
- 동일 입력 → deterministic 동일 출력.
- 없는 값을 생성하지 않는다(임의 default/문자열 금지). absent = None 보존.
- action 문장 요약/LLM 재작성 없음 — what 을 그대로 사용.
- FREE/PAID 분기 없음(동일 mapper). 프로파일 차이는 다음 STEP.

경계(§6):
- Diagnosis Contract ≠ SaaS Operation State.
- who = 법령 수행주체(≠ assignee_user_id). when/inspection_cycle = 법령 결과값(≠ next_due_date).
- Operation mapper 는 assignee/next_due/status/completed/execution/attachment 등 운영값을 생성하지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _detail(ob: Dict[str, Any]) -> Dict[str, Any]:
    d = ob.get("obligation_detail") if isinstance(ob, dict) else None
    return d if isinstance(d, dict) else {}


def _enrichment(ob: Dict[str, Any]) -> Dict[str, Any]:
    e = ob.get("enrichment") if isinstance(ob, dict) else None
    return e if isinstance(e, dict) else {}


def _legal_basis(ob: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """law_name + law_article → legal_basis. 둘 다 없으면 None(생성 안 함)."""
    name = ob.get("law_name")
    article = ob.get("law_article")
    if name is None and article is None:
        return None
    return {"law_name": name, "law_article": article}


def map_diagnosis_presentation(ob: Any) -> Dict[str, Any]:
    """무료/유료 진단 화면 공통 ViewModel (PURE). where/how 는 있을 때만 detail 로 보존."""
    o = ob if isinstance(ob, dict) else {}
    d = _detail(o)
    e = _enrichment(o)

    vm: Dict[str, Any] = {
        "action": d.get("what"),                 # what 그대로 (요약/LLM 금지)
        "actor": d.get("who"),                   # 법령 수행주체
        "timing": d.get("when"),
        "cycle": e.get("inspection_cycle"),
        "condition": d.get("condition"),
        "reason": o.get("triggered_by"),         # 적용사유
        "legal_basis": _legal_basis(o),
        "recipient": d.get("recipient"),
        "evidence": o.get("evidence"),
        "status": o.get("check_result"),         # 법적 결과 상태(VERIFIED/NOT_APPLICABLE)
    }
    # where/how 는 원천 있을 때만 detail 용 값으로 보존(없으면 생성하지 않음, §4)
    if d.get("where") is not None:
        vm["where"] = d.get("where")
    if d.get("how") is not None:
        vm["how"] = d.get("how")
    return vm


def map_operation_presentation(ob: Any) -> Dict[str, Any]:
    """SaaS 운영 매칭용 법령 결과 ViewModel (PURE). 운영 상태값은 생성하지 않는다(§5/§6)."""
    o = ob if isinstance(ob, dict) else {}
    d = _detail(o)
    e = _enrichment(o)

    return {
        "action": d.get("what"),
        "legal_actor": d.get("who"),             # 법령 수행주체 (≠ SaaS assignee)
        "timing": d.get("when"),
        "cycle": e.get("inspection_cycle"),      # 법령 결과값 (≠ next_due_date)
        "condition": d.get("condition"),
        "method": d.get("how"),                  # 없으면 None (생성 안 함)
        "location": d.get("where"),              # 없으면 None (생성 안 함)
        "recipient": d.get("recipient"),
        "legal_basis": _legal_basis(o),
        "reason": o.get("triggered_by"),
        "identity": {
            "atom_id": o.get("atom_id"),
            "source_atom_ids": o.get("source_atom_ids"),
        },
        # assignee_user_id / next_due_date / status / completed_at / execution_record / attachment = 생성 안 함
    }
