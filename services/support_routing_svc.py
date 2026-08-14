# -*- coding: utf-8 -*-
"""TAI 고객응대 — Response Routing MVP (FAQ + Knowledge + diagnosis).

설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md
      + 라우팅 계약 / Auto-3 diagnosis 한정 규칙(Operator 확정).

이 서비스는 `question + context` 를 받아 다음 4상태 중 하나만 결정한다:
    ANSWER / ASK / HANDOFF / ERROR
(RESOLVED 는 만들지 않는다. 문의 저장/RESOLVED 처리는 이 서비스의 책임이 아니다.)

단계(고정 순서):
  1. FAQ            : safe_help_svc.search(types=["FAQ"]) 재사용. 항상 가장 먼저.
                      단순 검색 hit 만으로 ANSWER 금지 — FAQ 의 실제 question 문구와
                      사용자 질문이 '정규화 후 명확히 일치'할 때만 ANSWER(source="FAQ").
                      유사하지만 불일치 → 다음 단계. (임의 confidence 숫자 없음)
  2. 분기(intent classifier 아님 — object_type 값만 본다):
     2a. object_type == "diagnosis" → diagnosis Context 를 Knowledge 보다 '우선' 조회.
         - object_id 없음 + factory_id 있음 → (소유권 검증 후) run_get_latest_diagnosis 사용.
         - object_id 있음 + 정확 조회 경로 확인됨 → 해당 diagnosis 사용.
         - object_id 있음 + 정확 조회 불가 → latest 대체 금지 → HANDOFF.
         - factory_id·object_id 모두 없음 → ASK(1회) / already_asked → HANDOFF.
         (diagnosis 분기는 여기서 ANSWER/ASK/HANDOFF/ERROR 로 종결. Knowledge 로 내려가지 않는다.)
     2b. object_type 이 있으나 "diagnosis" 아님 → HANDOFF (이번 MVP 범위 밖).
     2c. object_type 없음(=diagnosis 아닌 일반 질문) → Knowledge 단계로.
  3. Knowledge      : safe_help_svc.search(types=["PAGE_GUIDE","TASK_GUIDE"]) 재사용.
                      검색된 실제 문서를 evidence 로 반환. 근거 없으면 답 생성 없이 HANDOFF.
  4. ASK / HANDOFF  : 부족정보가 명확할 때만 ASK, 최대 1회. 그 외 HANDOFF.

diagnosis 소유권 검증(보안, 필수):
  diagnosis Context 를 factory_id 로 조회하기 '이전'에, 인증 회사(company_id)가 해당 factory 를
  소유하는지 확인한다(factories.id == factory_id AND company_id == 인증회사).
  company_id 부재/소유 불일치면 진단을 조회하지 않고 HANDOFF 한다(타사 진단 노출 차단).
  company_id 는 반드시 서버 파생값이어야 한다 — 호출측 member_support 가 인증 토큰에서
  context["company_id"] 로 넣는다. 화면 Context 빌더(_build_context)는 company_id 를 만들지 않으므로
  클라이언트가 주입할 수 없다.

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


def _default_company_owns_factory(company_id: str, factory_id: str) -> bool:
    """인증 회사가 factory 를 소유하는지 확인. factories.id == factory_id AND company_id == 인증회사."""
    from db.supabase_client import get_supabase
    sb = get_supabase()
    res = (
        sb.table("factories")
        .select("id")
        .eq("id", factory_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return bool(getattr(res, "data", None))


def _gating(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """MVP: 게이팅 미적용(safe_help_svc.search 는 None 허용). 후속 확장 훅."""
    return {}


def _resolve_diagnosis(
    ctx: Dict[str, Any],
    already_asked: bool,
    latest_diagnosis: Callable[[str], Any],
    diagnosis_by_id: Optional[Callable[[str], Any]],
    company_id: Optional[str],
    company_owns_factory: Callable[[str, str], bool],
) -> Dict[str, Any]:
    """object_type=="diagnosis" 전용 처리. ANSWER/ASK/HANDOFF/ERROR 로 종결.

    factory_id 로 진단을 조회하기 전에 소유권을 검증한다(company_id 필수).
    """
    object_id = (ctx.get("object_id") or "").strip() or None
    factory_id = (ctx.get("factory_id") or "").strip() or None

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
        # ── 소유권 검증(진단 조회 이전) ──
        # company_id 는 서버 파생값이어야 한다. 없으면 검증 불가 → 조회하지 않고 HANDOFF.
        if not company_id:
            return {"status": "HANDOFF", "reason": "factory ownership unverifiable (no company)"}
        try:
            owns = company_owns_factory(company_id, factory_id)
        except Exception as e:  # noqa: BLE001
            return {"status": "ERROR", "detail": f"ownership check failed: {e}"}
        if not owns:
            # 인증 회사가 소유하지 않는 factory → 진단을 조회하지 않는다(타사 노출 차단).
            return {"status": "HANDOFF", "reason": "factory not owned by company"}

        # 소유 확인됨 → 최신 진단 조회
        try:
            data = latest_diagnosis(factory_id)
        except LookupError:
            return {"status": "HANDOFF", "reason": "no diagnosis for factory"}
        except Exception as e:  # noqa: BLE001
            return {"status": "ERROR", "detail": f"latest_diagnosis failed: {e}"}
        if not data:
            return {"status": "HANDOFF", "reason": "no diagnosis for factory"}
        return {"status": "ANSWER", "source": "CONTEXT", "evidence": data}

    # factory_id·object_id 모두 없음 → 부족정보 특정 가능 → ASK(1회)
    if not already_asked:
        return {"status": "ASK", "missing_field": "factory_id"}
    return {"status": "HANDOFF", "reason": "insufficient context after ask"}


def route(
    question: str,
    context: Optional[Dict[str, Any]] = None,
    already_asked: bool = False,
    *,
    faq_search: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    knowledge_search: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    latest_diagnosis: Optional[Callable[[str], Any]] = None,
    diagnosis_by_id: Optional[Callable[[str], Any]] = None,
    company_owns_factory: Optional[Callable[[str, str], bool]] = None,
) -> Dict[str, Any]:
    """question+context → {status: ANSWER|ASK|HANDOFF|ERROR, ...}.

    순서: FAQ exact → (object_type=="diagnosis" 면 diagnosis Context 우선, 소유권 검증 후) → Knowledge.
    context["company_id"] 는 서버 파생 인증 회사(호출측 member_support 가 넣음). 소유권 검증에 사용한다.
    diagnosis_by_id 기본값 None = object_id 정확 조회 경로 '미확인' → object_id 있으면 HANDOFF.
    """
    q = (question or "").strip()
    if not q:
        return {"status": "ERROR", "detail": "question is empty"}
    ctx = context or {}

    faq_search = faq_search or _default_faq_search
    knowledge_search = knowledge_search or _default_knowledge_search
    latest_diagnosis = latest_diagnosis or _default_latest_diagnosis
    company_owns_factory = company_owns_factory or _default_company_owns_factory

    # ── 1. FAQ: 정규화 정확 일치만 ANSWER (항상 최우선) ──
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

    # ── 2. 분기: object_type 값만 본다(intent classifier 아님) ──
    object_type = (ctx.get("object_type") or "").strip() or None
    company_id = (ctx.get("company_id") or "").strip() or None  # 서버 파생 인증 회사

    if object_type == "diagnosis":
        # diagnosis Context 를 Knowledge 보다 우선 조회. 여기서 종결(Knowledge 로 안 내려감).
        return _resolve_diagnosis(
            ctx, already_asked, latest_diagnosis, diagnosis_by_id, company_id, company_owns_factory,
        )

    if object_type:
        # diagnosis 가 아닌 object_type → 이번 MVP 범위 밖
        return {"status": "HANDOFF", "reason": f"unsupported object_type: {object_type}"}

    # ── 3. Knowledge: diagnosis 아닌 일반 질문에서만. 검색 hit = evidence ──
    try:
        kn = knowledge_search(q, ctx) or {}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": f"knowledge_search failed: {e}"}
    kn_items = kn.get("items") or []
    if kn_items:
        return {"status": "ANSWER", "source": "KNOWLEDGE", "evidence": kn_items}

    # ── 4. 근거 없음 & 물어볼 것 특정 곤란 → HANDOFF ──
    return {"status": "HANDOFF", "reason": "no evidence found"}
