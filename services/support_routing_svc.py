# -*- coding: utf-8 -*-
"""TAI 고객응대 — Response Routing MVP (FAQ + Knowledge + diagnosis).

설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md
      + 라우팅 계약 / Auto-3 diagnosis 한정 규칙(Operator 확정).

이 서비스는 `question + context` 를 받아 다음 4상태 중 하나만 결정한다:
    ANSWER / ASK / HANDOFF / ERROR
(RESOLVED 는 만들지 않는다. 문의 저장/RESOLVED 처리는 이 서비스의 책임이 아니다.)

단계(고정 순서):
  1. FAQ            : safe_help_svc.search(types=["FAQ"]) 재사용. 항상 가장 먼저.
                      정규화 정확 일치만 ANSWER(source="FAQ") — canonical question 또는 등록된 alias(정확 표현).
                      유사하지만 불일치 → 다음 단계. 후보 2개 이상(모호) → 임의 선택 금지 → 다음 단계.
                      (임의 confidence 숫자 없음. 유사도/LLM/semantic match 없음.)
  2. 분기(intent classifier 아님 — object_type 값만 본다):
     2a. object_type == "diagnosis" → diagnosis Context 를 Knowledge 보다 '우선' 조회.
     2b. object_type 이 있으나 "diagnosis" 아님 → HANDOFF (이번 MVP 범위 밖).
     2c. object_type 없음 → Knowledge 단계로.
  3. Knowledge      : safe_help_svc.search(types=["PAGE_GUIDE","TASK_GUIDE"]) 재사용. hit → ANSWER.
  4. ASK / HANDOFF  : 부족정보가 명확할 때만 ASK, 최대 1회. 그 외 HANDOFF.

FAQ alias(동의 질문) 매칭:
  운영자가 FAQ 항목에 명시 등록한 alias(정확 표현) 목록을 캐논 질문과 동등하게 취급한다.
  매칭은 '정규화 후 exact' 만 사용한다(유사도 아님). alias 는 검색 hit item 의 "aliases": [str,...] 에서 읽는다.
  aliases 필드가 없으면 캐논만 본다(기존 동작과 동일 — 회귀 없음).

diagnosis 소유권 검증(보안, 필수):
  diagnosis Context 를 factory_id 로 조회하기 '이전'에, 인증 회사(company_id)가 해당 factory 를
  소유하는지 확인한다. company_id 부재/소유 불일치면 진단을 조회하지 않고 HANDOFF 한다(타사 진단 노출 차단).
  company_id 는 반드시 서버에서 파생된 값이어야 한다(member_support 가 인증 토큰에서 넣는다).
  화면 Context 빌더(_build_context)는 company_id 를 만들지 않으므로 클라이언트가 주입할 수 없다.

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


def _faq_item_matches(normalized_q: str, item: Dict[str, Any]) -> bool:
    """FAQ 한 건이 사용자 질문과 '정규화 후 exact' 로 일치하는지.

    canonical question 또는 등록된 alias(정확 표현) 중 하나라도 정규화 exact 일치면 True.
    alias 는 운영자가 명시 등록한 표현만 사용한다(유사도/LLM 판단 없음).
    aliases 필드가 없거나 형식이 아니면 canonical 만 본다(기존 동작과 동일 — 회귀 없음).
    """
    if _normalize(item.get("question")) == normalized_q:
        return True
    aliases = item.get("aliases")
    if isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, str) and _normalize(a) == normalized_q:
                return True
    return False


def _faq_match_candidates(normalized_q: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """정규화 exact(캐논/별칭) 일치 FAQ 후보들. doc_id 기준 중복 제거.

    한 FAQ 가 캐논·별칭 양쪽으로 맞아도 1건으로 센다. 반환 길이로 호출측이 0/1/다수를 판단한다.
    """
    matched: List[Dict[str, Any]] = []
    seen: set = set()
    for it in items:
        if _faq_item_matches(normalized_q, it):
            key = it.get("doc_id") or id(it)
            if key not in seen:
                seen.add(key)
                matched.append(it)
    return matched


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

    순서: FAQ exact(캐논/별칭) → (object_type=="diagnosis" 면 diagnosis Context 우선, 소유권 검증 후) → Knowledge.
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

    # ── 1. FAQ: 정규화 정확 일치만 ANSWER (캐논 또는 등록된 alias). 항상 최우선 ──
    try:
        faq = faq_search(q, ctx) or {}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": f"faq_search failed: {e}"}
    nq = _normalize(q)
    if nq:
        candidates = _faq_match_candidates(nq, faq.get("items") or [])
        if len(candidates) == 1:
            return {"status": "ANSWER", "source": "FAQ", "evidence": candidates[0]}
        # 0개: 유사하지만 미등록 → 다음 단계. 2개 이상: 모호 → 임의 선택 금지, FAQ ANSWER 금지 → 다음 단계.
        # (LLM/유사도 판단 없음. semantic match 미도입. canonical exact 는 기존 그대로 최우선.)

    # ── 2. 분기: object_type 값만 본다(intent classifier 아님) ──
    object_type = (ctx.get("object_type") or "").strip() or None
    company_id = (ctx.get("company_id") or "").strip() or None  # 서버 파생 인증 회사

    if object_type == "diagnosis":
        return _resolve_diagnosis(
            ctx, already_asked, latest_diagnosis, diagnosis_by_id, company_id, company_owns_factory,
        )

    if object_type:
        return {"status": "HANDOFF", "reason": f"unsupported object_type: {object_type}"}

    # ── 3. Knowledge: diagnosis 아닌 일반 질문에서만. 검색 hit = evidence ──
    try:
        kn = knowledge_search(q, ctx) or {}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": f"knowledge_search failed: {e}"}
    kn_items = kn.get("items") or []
    if kn_items:
        return {"status": "ANSWER", "source": "KNOWLEDGE", "evidence": kn_items}

    # ── 4. 근거 없음 → HANDOFF ──
    return {"status": "HANDOFF", "reason": "no evidence found"}
