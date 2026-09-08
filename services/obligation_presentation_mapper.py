"""Obligation Presentation Mappers (PURE) — Diagnosis / Operation.

WO-OBLIGATION-RESULT-CONTRACT-001 / STEP 1 + PATCH-1(P2).

입력 = full_result.obligations_raw[] element (dict). 출력 = 표시용 공통 ViewModel (dict).

PURE MAPPING ONLY:
- 입력 mutate 없음 · deterministic.
- ABSENT ≠ NULL 보존(P2): 원천 key 가 **없으면 presentation key 도 만들지 않는다**.
  원천 key 가 있고 값이 None 이면 그 의미(key + None)를 유지한다.
- 임의 default/"미확인"/"" 생성 0. action 요약/LLM 재작성 0(what 그대로).
- FREE/PAID 분기 없음(동일 mapper).

경계(§6): Diagnosis Contract ≠ SaaS Operation State.
  who=법령 수행주체(≠assignee_user_id) · when/inspection_cycle=법령 결과값(≠next_due_date).
  Operation mapper 는 assignee/next_due/status/completed/execution/attachment 등 운영값을 생성하지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _detail(ob: Dict[str, Any]) -> Dict[str, Any]:
    d = ob.get("obligation_detail") if isinstance(ob, dict) else None
    return d if isinstance(d, dict) else {}


def _enrichment(ob: Dict[str, Any]) -> Dict[str, Any]:
    e = ob.get("enrichment") if isinstance(ob, dict) else None
    return e if isinstance(e, dict) else {}


def _legal_basis(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """law_name/law_article 중 존재하는 것만 담는다. 둘 다 없으면 None(키 미생성)."""
    has_n = "law_name" in o
    has_a = "law_article" in o
    if not has_n and not has_a:
        return None
    lb: Dict[str, Any] = {}
    if has_n:
        lb["law_name"] = o["law_name"]
    if has_a:
        lb["law_article"] = o["law_article"]
    return lb


def map_diagnosis_presentation(ob: Any) -> Dict[str, Any]:
    """무료/유료 진단 화면 공통 ViewModel (PURE). 원천 없는 key 는 생성하지 않음."""
    o = ob if isinstance(ob, dict) else {}
    d = _detail(o)
    e = _enrichment(o)
    vm: Dict[str, Any] = {}
    if "what" in d:
        vm["action"] = d["what"]          # what 그대로 (요약/LLM 금지)
    if "who" in d:
        vm["actor"] = d["who"]            # 법령 수행주체
    if "when" in d:
        vm["timing"] = d["when"]
    if "inspection_cycle" in e:
        vm["cycle"] = e["inspection_cycle"]
    if "condition" in d:
        vm["condition"] = d["condition"]
    if "triggered_by" in o:
        vm["reason"] = o["triggered_by"]  # 적용사유
    lb = _legal_basis(o)
    if lb is not None:
        vm["legal_basis"] = lb
    if "recipient" in d:
        vm["recipient"] = d["recipient"]
    if "evidence" in o:
        vm["evidence"] = o["evidence"]
    if "check_result" in o:
        vm["status"] = o["check_result"]  # 법적 결과 상태
    if "where" in d:
        vm["where"] = d["where"]
    if "how" in d:
        vm["how"] = d["how"]
    return vm


def map_operation_presentation(ob: Any) -> Dict[str, Any]:
    """SaaS 운영 매칭용 법령 결과 ViewModel (PURE). 원천 없는 key/빈 identity 생성 안 함. 운영 상태값 생성 0."""
    o = ob if isinstance(ob, dict) else {}
    d = _detail(o)
    e = _enrichment(o)
    vm: Dict[str, Any] = {}
    if "what" in d:
        vm["action"] = d["what"]
    if "who" in d:
        vm["legal_actor"] = d["who"]      # 법령 수행주체 (≠ SaaS assignee)
    if "when" in d:
        vm["timing"] = d["when"]
    if "inspection_cycle" in e:
        vm["cycle"] = e["inspection_cycle"]  # 법령 결과값 (≠ next_due_date)
    if "condition" in d:
        vm["condition"] = d["condition"]
    if "how" in d:
        vm["method"] = d["how"]
    if "where" in d:
        vm["location"] = d["where"]
    if "recipient" in d:
        vm["recipient"] = d["recipient"]
    lb = _legal_basis(o)
    if lb is not None:
        vm["legal_basis"] = lb
    if "triggered_by" in o:
        vm["reason"] = o["triggered_by"]
    ident: Dict[str, Any] = {}
    if "atom_id" in o:
        ident["atom_id"] = o["atom_id"]
    if "source_atom_ids" in o:
        ident["source_atom_ids"] = o["source_atom_ids"]
    if ident:
        vm["identity"] = ident            # 둘 다 없으면 빈 identity 미생성
    # assignee_user_id / next_due_date / status / completed_at / execution_record / attachment = 생성 안 함
    return vm
