# -*- coding: utf-8 -*-
"""TAI 고객응대 — Response Routing MVP (FAQ + Knowledge + diagnosis).

설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md
      + 라우팅 계약 / Auto-3 diagnosis 한정 규칙(Operator 확정).

이 서비스는 `question + context` 를 받아 다음 4상태 중 하나만 결정한다:
    ANSWER / ASK / HANDOFF / ERROR
(RESOLVED 는 만들지 않는다. 문의 저장/RESOLVED 처리는 이 서비스의 책임이 아니다.)

이번 단계 범위(고정):
- 근거를 찾고 올바른 경로를 결정하는 것까지만 구현한다. LLM 호출은 넣지 않는다.
- ANSWER 는 실제 evidence(FAQ 항목 / Knowledge 문서 / diagnosis 결과)를 그대로 반환한다.
  사람이 읽기 좋은 문장 생성(LLM/Projection)은 다음 작업에서 붙인다.

단계(고정 순서):
  1. FAQ       : safe_help_svc.search(types=["FAQ"]) 재사용.
                 단순 검색 hit 만으로 ANSWER 금지 — FAQ 의 실제 question 문구와
                 사용자 질문이 '정규화 후 명확히 일치'할 때만 ANSWER(source="FAQ").
                 유사하지만 불일치 → 다음 단계. (임의 confidence 숫자 없음)
  2. Knowledge : safe_help_svc.search(types=["PAGE_GUIDE","TASK_GUIDE"]) 재사용.
                 검색된 실제 문서를 evidence 로 반환. 근거 없으면 답 생성 없이 다음 단계.
  3. diagnosis : object_type == "diagnosis" 일 때만.
                 - object_id 없음 + factory_id 있음 → run_get_latest_diagnosis 사용.
                 - object_id 있음 + 정확 조회 경로 확인됨 → 해당 diagnosis 사용.
                 - object_id 있음 + 정확 조회 불가 → latest 대체 금지 → HANDOFF.
                 - 그 외 object_type → HANDOFF (이번 MVP 범위 밖).
  4. ASK       : 부족정보가 명확할 때만, 최대 1회. 이미 아는 Context 재질문 금지.
                 already_asked=True 인데도 근거 부족 → HANDOFF.
  5. HANDOFF   : 근거 부족/판단 필요/범위 밖. 실제 이관(POST /me/inquiries)은 호출측이 수행.

조회는 주입(injection) 가능하다(테스트/재사용). 미주입 시 기존 함수를 지연 import 한다.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

FAQ_TYPES: List[str] = ["FAQ"]
KNOWLEDGE_TYPES: List[str] = ["PAGE_GUIDE", "TASK_GUIDE"]


def _normalize(s: Optional[str]) -> str:
    """정규화: 소문자화 + 공백 제거 + 구두점/특수문자 제거(한글·영숫자만 남김)."""
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    return s


# ── 기본 조회 어댑터(미주입 시). 지연 import 로 순환/무거운 로딩 회피. ──

def _default_faq_search(question: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    from services import safe_help_svc
    return safe_help_svc.search(q=question, types=FAQ_TYPES, **_gating(ctx))


def _default_knowledge_search(question: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    from services import safe_help_svc
    return safe_help_svc.search(q=question, types=KNOWLEDGE_TYPES, **_gating(ctx))


def _default_latest_diagnosis(factory_id: str) -> Any:
    from db.supabase_client import get_supabase
    from services import legal_engine_svc
    return legal_engine_svc.run_get_latest_diagnosis(get_supabase(), factory_id)


def _gating(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """MVP: 게이팅 미적용(safe_help_svc.search 는 None 허용). 후속 확장 훅."""
    return {}


def route(
    question: str,
    context: Optional[Dict[str, Any]] = None,
    already_asked: bool = False,
    *,
    faq_search: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    knowledge_search: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    latest_diagnosis: Optional[Callable[[str], Any]] = None,
    diagnosis_by_id: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """question+context → {status: ANSWER|ASK|HANDOFF|ERROR, ...}.

    diagnosis_by_id 기본값 None = object_id 정확 조회 경로 '미확인'.
    (현재 확인된 진단 조회는 factory_id→latest 뿐이므로 object_id 있으면 HANDOFF.)
    """
    q = (question or "").strip()
    if not q:
        return {"status": "ERROR", "detail": "question is empty"}
    ctx = context or {}

    faq_search = faq_search or _default_faq_search
    knowledge_search = knowledge_search or _default_knowledge_search
    latest_diagnosis = latest_diagnosis or _default_latest_diagnosis

    # ── 1. FAQ: 정규화 정확 일치만 ANSWER ──
    try:
        faq = faq_search(q, ctx) or {}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": f"faq_search failed: {e}"}
    nq = _normalize(q)
    if nq:
        for item in (faq.get("items") or []):
            if _normalize(item.get("question")) == nq:
                return {"status": "ANSWER", "source": "FAQ", "evidence": item}
    # 유사하지만 정확 불일치 → 다음 단계 (FAQ ANSWER 금지)

    # ── 2. Knowledge: 검색 hit = evidence ──
    try:
        kn = knowledge_search(q, ctx) or {}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": f"knowledge_search failed: {e}"}
    kn_items = kn.get("items") or []
    if kn_items:
        return {"status": "ANSWER", "source": "KNOWLEDGE", "evidence": kn_items}

    # ── 3. diagnosis Context ──
    object_type = (ctx.get("object_type") or "").strip() or None
    object_id = (ctx.get("object_id") or "").strip() or None
    factory_id = (ctx.get("factory_id") or "").strip() or None

    if object_type and object_type != "diagnosis":
        return {"status": "HANDOFF", "reason": f"unsupported object_type: {object_type}"}

    if object_type == "diagnosis":
        if object_id:
            # object_id 있음 — 정확 조회 경로가 확인된 경우만 사용. 없으면 latest 대체 금지.
            if diagnosis_by_id is None:
                return {"status": "HANDOFF", "reason": "diagnosis object_id read path unavailable"}
            try:
                data = diagnosis_by_id(object_id)
            except LookupError:
                return {"status": "HANDOFF", "reason": "diagnosis object_id not found"}
            except Exception as e:  # noqa: BLE001
                return {"status": "ERROR", "detail": f"diagnosis_by_id failed: {e}"}
            if not data:
                return {"status": "HANDOFF", "reason": "diagnosis object_id not found"}
            return {"status": "ANSWER", "source": "CONTEXT", "evidence": data}

        if factory_id:
            try:
                data = latest_diagnosis(factory_id)
            except LookupError:
                return {"status": "HANDOFF", "reason": "no diagnosis for factory"}
            except Exception as e:  # noqa: BLE001
                return {"status": "ERROR", "detail": f"latest_diagnosis failed: {e}"}
            if not data:
                return {"status": "HANDOFF", "reason": "no diagnosis for factory"}
            return {"status": "ANSWER", "source": "CONTEXT", "evidence": data}

        # object_type=diagnosis 인데 factory_id·object_id 모두 없음 → 부족정보 특정 가능
        if not already_asked:
            return {"status": "ASK", "missing_field": "factory_id"}
        return {"status": "HANDOFF", "reason": "insufficient context after ask"}

    # ── 4/5. object_type 없음 & FAQ/KB 미해결 → 물어볼 것 특정 곤란 → HANDOFF ──
    return {"status": "HANDOFF", "reason": "no evidence found"}
