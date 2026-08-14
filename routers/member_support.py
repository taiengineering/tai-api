"""TAI 고객응대 — 실제 사용자 질문 진입점 결선.

설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md
      + Enriched HANDOFF 최소 슬라이스(구현 1단계): HANDOFF 저장 시 '이번 요청에서
        이미 확보된' evidence 만 customer-safe FACT 로 projection 해 inquiries.context.support 에 남긴다.

POST /me/support/ask :
  로그인 회원의 질문 + Context 를 받아
    support_routing_svc.route()  (근거 탐색·경로 결정)
    → ANSWER 면 support_answer_svc.explain()  (evidence 설명)
  최종 상태를 4개 중 하나로 반환한다: ANSWER / ASK / HANDOFF / ERROR.

책임 분리:
  - 이 라우터는 결선(orchestration)만 한다. routing/answer 규칙을 바꾸지 않는다.
  - HANDOFF 저장은 member_inquiries._save_member_inquiry() 공통 함수를 재사용한다(복붙·신규 서비스 금지).
  - 신원(user_id/company_id)은 Bearer 토큰에서 서버가 파생한다(클라이언트 입력 금지).
  - AI 가 문의를 RESOLVED 로 자동 종료하지 않는다.

Enriched HANDOFF(구현 1단계 · 최소):
  - 신규 DB 조회/LLM/분류/원인추론 없음. route 결과에 '이미' 들어 있는 evidence 만 재사용한다.
  - 첫 슬라이스는 diagnosis(source=="CONTEXT") 의 대표 summary(verdict/risk_level/obligation_count)만
    FACT 로 남긴다. 전체 payload/obligations 원문/내부구조/raw 오류는 저장하지 않는다.
  - obligation_count 는 obligations 가 실제 list 일 때만 len() 으로. rule_count 를 obligation_count 로
    치환하지 않는다(의미가 다른 값). 대표값이 하나도 없으면 FACT 생략.
  - context.support.handoff_reason 은 raw routing reason 을 저장하지 않고 whitelist token 으로만 정규화한다
    (내부 구현 의미가 snapshot 에 새지 않도록). 단 기존 _save_member_inquiry(handoff_reason=) 흐름은 그대로 둔다.
  - FACT 가 하나도 없으면 support 를 첨부하지 않는다(기존 HANDOFF 저장과 완전히 동일).
  - projection 실패는 best-effort — support 만 생략하고 문의 저장은 계속한다.
  - _save_member_inquiry / routing / answer 서비스는 변경하지 않는다.

Context 분리(저장 vs 라우팅) — 서로 다른 계약이므로 별도로 만든다:
  - stored_ctx (_build_context): 저장(inquiries.context) 계약. object_type/object_id 는 '쌍'으로만.
      → 프론트가 object_id 없이 object_type="diagnosis" 만 보내면 저장 context 에서는 object_type 이 빠진다.
  - routing_ctx (_build_routing_context): routing 전용 최소 Context.
      factory_id + object_type="diagnosis"(단독, object_id 없이) 를 '보존'한다(diagnosis 분기 진입용).
      여기에 서버 파생 company_id 를 더해 factory 소유권 검증에 쓴다.
      company_id 는 저장 context 에 넣지 않는다(정규 컬럼 company_id 로 이미 저장, 중복 금지).
      company_id 를 서버(인증)에서만 넣으므로 클라이언트가 소유권 검증을 우회할 수 없다.

처리 규칙:
  1) route() 호출
  2) ANSWER → explain(); 설명 ANSWER→반환 / 설명 INSUFFICIENT→Human handoff 저장 / 설명 ERROR→ERROR
  3) ASK   → 저장하지 않고 추가질문 상태 반환(already_asked=true 로 재요청 가능)
  4) HANDOFF → _save_member_inquiry 로 1건 저장(question+page_url+context(+support)+user/company 보존, Slack 통지) → HANDOFF
  5) 저장 실패 → ERROR (조회/LLM 실패와 구분되는 detail)
"""
import logging
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from routers.member_inquiries import (
    InquiryContextBody,
    _build_context,
    _now_iso,
    _save_member_inquiry,
)
from services import support_routing_svc, support_answer_svc

logger = logging.getLogger("member_support")
router = APIRouter(prefix="/me/support", tags=["회원 고객응대"])


class SupportAskBody(BaseModel):
    question: str = Field(..., min_length=1)
    page_url: Optional[str] = None
    context: Optional[InquiryContextBody] = None
    already_asked: bool = False


# routing 에서 허용하는 object_type (MVP: diagnosis 하나). object_id 는 사용하지 않는다.
SUPPORT_ROUTING_OBJECT_TYPES = {"diagnosis"}


def _build_routing_context(ctx: Optional[InquiryContextBody]) -> Dict[str, Any]:
    """routing 전용 최소 Context.

    저장용 _build_context()(문의 저장 계약: object_type/object_id 쌍 필수)와 '분리'된 빌더.
    - factory_id: 있으면 포함
    - object_type: 허용목록(diagnosis)일 때만 포함. object_id 는 MVP 에서 사용하지 않으므로 전송/보존하지 않는다.
    → 프론트가 factory_id + object_type="diagnosis"(object_id 없음)만 보내도 routing 에서 diagnosis 분기로 들어간다.
    company_id(서버 파생)는 _handle_ask 에서 별도 주입한다.
    """
    if not ctx:
        return {}
    out: Dict[str, Any] = {}
    factory_id = (ctx.factory_id or "").strip() or None
    object_type = (ctx.object_type or "").strip() or None
    if factory_id:
        out["factory_id"] = factory_id
    if object_type in SUPPORT_ROUTING_OBJECT_TYPES:
        out["object_type"] = object_type
    return out


def _default_route(question: str, ctx: Dict[str, Any], already_asked: bool) -> Dict[str, Any]:
    return support_routing_svc.route(question, ctx, already_asked)


def _default_explain(routing_result: Dict[str, Any], question: str) -> Dict[str, Any]:
    return support_answer_svc.explain(routing_result, question)


# ── Enriched HANDOFF: customer-safe FACT projection (신규 조회 없음) ──

# raw routing reason → 저장용 whitelist token. raw 문자열(내부 구현 의미 포함 가능)을
# context.support 에 그대로 복사하지 않는다. 미매핑/비문자 → needs_review.
_SAFE_REASON_TOKENS = {
    "answer_insufficient": "answer_insufficient",
    "no evidence found": "no_evidence",
    "insufficient context after ask": "insufficient_context",
    "factory ownership unverifiable (no company)": "ownership_unverified",
    "factory not owned by company": "ownership_unverified",
    "no diagnosis for factory": "no_evidence",
    "diagnosis object_id not found": "no_evidence",
    "diagnosis object_id read path unavailable": "unsupported_context",
}
_UNSUPPORTED_REASON_PREFIX = "unsupported object_type"


def _safe_reason_token(reason: Any) -> str:
    """raw routing reason → whitelist token. 미매핑/비문자 → needs_review.

    raw 문자열은 절대 반환하지 않는다(내부 구현 의미가 snapshot 에 새지 않도록).
    """
    if not isinstance(reason, str):
        return "needs_review"
    key = reason.strip()
    if key in _SAFE_REASON_TOKENS:
        return _SAFE_REASON_TOKENS[key]
    if key.startswith(_UNSUPPORTED_REASON_PREFIX):
        return "unsupported_context"
    return "needs_review"


def _safe_str(v: Any, limit: int) -> Optional[str]:
    """이미 고객-safe 로 허용된 scalar(verdict/risk_level 등)의 길이 제한 전용. 아니면 None.

    raw routing reason 처리에는 사용하지 않는다(그건 _safe_reason_token 의 whitelist 가 먼저).
    """
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    return s[:limit]


def _project_diagnosis_summary(evidence: Any) -> Optional[Dict[str, Any]]:
    """진단 evidence → 대표 summary FACT(스칼라만). 구조 불명확/대표값 없으면 None.

    - 신규 조회 없음(route 단계에서 이미 조회된 evidence 재사용).
    - result_data 가 중첩이든 평면이든 허용. verdict/risk_level(짧은 문자열) + obligation_count(정수)만.
    - obligation_count 는 obligations 가 '실제 list' 일 때만 len(). rule_count 로 대체하지 않는다(의미 다름).
    - 전체 payload / obligations 원문 / input_data / rules / 내부구조 / rule_count 는 저장하지 않는다.
    """
    if not isinstance(evidence, dict):
        return None
    rd = evidence.get("result_data")
    if not isinstance(rd, dict):
        rd = evidence
    verdict = _safe_str(rd.get("verdict"), 60)
    risk_level = _safe_str(rd.get("risk_level"), 60)
    fact: Dict[str, Any] = {"fact_type": "diagnosis_summary"}
    if verdict is not None:
        fact["verdict"] = verdict
    if risk_level is not None:
        fact["risk_level"] = risk_level
    # obligation_count: obligations 가 실제 list 일 때만. rule_count fallback 금지(서로 다른 의미).
    obligations = rd.get("obligations")
    if isinstance(obligations, list):
        fact["obligation_count"] = len(obligations)
    # 대표 값이 하나도 없으면 FACT 로서 의미 없음 → 생략(추정 금지).
    if len(fact) == 1:
        return None
    return fact


def _safe_support_projection(route_result: Any, reason: Any) -> Optional[Dict[str, Any]]:
    """이미 확보된 route 결과만으로 customer-safe support package 생성(best-effort).

    신규 DB 조회·LLM·분류·원인추론 없음. 첫 슬라이스: diagnosis(CONTEXT) summary FACT 만.
    handoff_reason/unknown_gap 은 raw reason 이 아니라 whitelist token 으로만 저장한다.
    FACT 가 하나도 없으면 None 을 반환해 support 를 첨부하지 않는다(기존 HANDOFF 와 동일).
    예외는 삼켜서 support 만 생략한다(문의 저장 자체는 계속되어야 한다).
    """
    try:
        facts: List[Dict[str, Any]] = []
        if isinstance(route_result, dict) and route_result.get("source") == "CONTEXT":
            ds = _project_diagnosis_summary(route_result.get("evidence"))
            if ds:
                facts.append(ds)
        if not facts:
            return None
        token = _safe_reason_token(reason)  # raw 미저장 — whitelist token 만
        return {
            "handoff_reason": token,
            "verified_facts": facts,
            "unknown_gap": token,  # 첫 슬라이스: 동일 정규화 결과 재사용(중복 helper 금지)
            "checked_at": _now_iso(),
        }
    except Exception:  # noqa: BLE001
        logger.exception("support projection failed")
        return None


def _do_handoff(
    question: str,
    stored_ctx: Optional[Dict[str, Any]],
    identity: Dict[str, Any],
    reason: Optional[str],
    save_fn: Callable[..., Dict[str, Any]],
    supabase: Any,
    *,
    verified_support: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """공통 저장 함수로 문의 1건 저장. 실패 시 ERROR(저장 실패 구분).

    verified_support 가 있으면 screen context 와 '별도 키(support)'로 병합해 저장한다.
    verified_support 가 None 이면 기존과 완전히 동일하게 동작한다(하위호환).
    _do_handoff 는 조사/조회/분류/LLM 을 하지 않는다 — 이미 만들어진 package 를 받아 병합·저장만 한다.
    reason 은 기존대로 _save_member_inquiry(handoff_reason=)에 전달한다(Slack 내부통지 흐름 무변경).
    """
    context_eff = dict(stored_ctx) if stored_ctx else {}
    if verified_support:
        context_eff["support"] = verified_support
    context_to_save = context_eff or None  # 비면 None(기존 NULL 저장과 동일)
    try:
        saved = save_fn(
            supabase,
            user_id=identity["user_id"],
            company_id=identity.get("company_id"),
            name=identity.get("name"),
            question=question,
            page_url=identity.get("page_url"),
            context=context_to_save,
            handoff_reason=reason,
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": f"handoff save failed: {e!s}"}
    return {"status": "HANDOFF", "inquiry_no": saved.get("no")}


def _handle_ask(
    question: str,
    stored_ctx: Optional[Dict[str, Any]],
    already_asked: bool,
    identity: Dict[str, Any],
    *,
    routing_ctx: Optional[Dict[str, Any]] = None,
    route_fn: Callable[[str, Dict[str, Any], bool], Dict[str, Any]] = _default_route,
    explain_fn: Callable[[Dict[str, Any], str], Dict[str, Any]] = _default_explain,
    save_fn: Callable[..., Dict[str, Any]] = _save_member_inquiry,
    supabase: Any = None,
) -> Dict[str, Any]:
    """결선 순수 로직. 의존성 주입 가능(테스트: route/explain/save fake).

    routing_ctx 지정 시 그것을 routing 근거로 쓰고(미지정이면 stored_ctx — 하위호환),
    서버 파생 company_id 를 더해 route 한다. 저장(HANDOFF)에는 항상 stored_ctx 원본을 쓴다.
    HANDOFF 저장 시, route 결과에 이미 있는 evidence 만으로 customer-safe support 를 best-effort 로 붙인다.
    """
    # routing 용 Context: routing_ctx(지정 시) 또는 저장용 stored_ctx(하위호환) 를 복사한 뒤,
    # 서버 파생 company_id 를 넣는다. stored_ctx 원본은 그대로 저장에 사용한다(company_id 미포함).
    # company_id 는 반드시 서버 파생값이어야 소유권 검증이 안전하다(클라이언트 주입 불가).
    base_ctx = routing_ctx if routing_ctx is not None else (stored_ctx or {})
    routing_ctx_eff = dict(base_ctx)
    company_id = identity.get("company_id")
    if company_id:
        routing_ctx_eff["company_id"] = company_id
    r = route_fn(question, routing_ctx_eff, already_asked)
    status = r.get("status")

    if status == "ASK":
        # 저장하지 않음. 추가질문 상태 반환.
        return {"status": "ASK", "missing_field": r.get("missing_field"), "already_asked": True}

    if status == "ERROR":
        return {"status": "ERROR", "detail": r.get("detail") or "routing error"}

    if status == "HANDOFF":
        # route 자체 HANDOFF: 대개 evidence 없음(source 없음) → support 미첨부(기존과 동일).
        support_pkg = _safe_support_projection(r, r.get("reason"))
        return _do_handoff(
            question, stored_ctx, identity, r.get("reason"), save_fn, supabase,
            verified_support=support_pkg,
        )

    if status == "ANSWER":
        a = explain_fn(r, question)
        a_status = a.get("status")
        if a_status == "ANSWER":
            return {
                "status": "ANSWER",
                "answer": a.get("answer"),
                "source": a.get("source"),
                "citations": a.get("citations", []),
            }
        if a_status == "INSUFFICIENT":
            # AI 가 임의 답변하지 않음 → Human handoff 저장(사유 내부 보존).
            # route 결과(r)에 이미 있는 evidence(diagnosis 등)만 재사용해 support 첨부(신규 조회 없음).
            support_pkg = _safe_support_projection(r, "answer_insufficient")
            return _do_handoff(
                question, stored_ctx, identity, "answer_insufficient", save_fn, supabase,
                verified_support=support_pkg,
            )
        # 설명 ERROR
        return {"status": "ERROR", "detail": a.get("detail") or "answer error"}

    return {"status": "ERROR", "detail": f"unexpected routing status: {status}"}


@router.post("/ask")
def support_ask(
    body: SupportAskBody,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")

    stored_ctx = _build_context(body.context)          # 저장용(문의 저장 계약 유지)
    routing_ctx = _build_routing_context(body.context)  # routing 용(diagnosis object_type 단독 보존)
    identity = {
        "user_id": user_id,
        "company_id": current_user.get("company_id"),
        "name": current_user.get("name"),
        "page_url": (body.page_url or "").strip() or None,
    }
    return _handle_ask(
        body.question, stored_ctx, bool(body.already_asked), identity, routing_ctx=routing_ctx,
    )
