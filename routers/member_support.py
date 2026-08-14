"""TAI 고객응대 — 실제 사용자 질문 진입점 결선.

설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md

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

처리 규칙:
  1) route() 호출
  2) ANSWER → explain(); 설명 ANSWER→반환 / 설명 INSUFFICIENT→Human handoff 저장 / 설명 ERROR→ERROR
  3) ASK   → 저장하지 않고 추가질문 상태 반환(already_asked=true 로 재요청 가능)
  4) HANDOFF → _save_member_inquiry 로 1건 저장(question+page_url+context+user/company 보존, Slack 통지) → HANDOFF
  5) 저장 실패 → ERROR (조회/LLM 실패와 구분되는 detail)
"""
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from routers.member_inquiries import (
    InquiryContextBody,
    _build_context,
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


def _default_route(question: str, ctx: Dict[str, Any], already_asked: bool) -> Dict[str, Any]:
    return support_routing_svc.route(question, ctx, already_asked)


def _default_explain(routing_result: Dict[str, Any], question: str) -> Dict[str, Any]:
    return support_answer_svc.explain(routing_result, question)


def _do_handoff(
    question: str,
    stored_ctx: Optional[Dict[str, Any]],
    identity: Dict[str, Any],
    reason: Optional[str],
    save_fn: Callable[..., Dict[str, Any]],
    supabase: Any,
) -> Dict[str, Any]:
    """공통 저장 함수로 문의 1건 저장. 실패 시 ERROR(저장 실패 구분)."""
    try:
        saved = save_fn(
            supabase,
            user_id=identity["user_id"],
            company_id=identity.get("company_id"),
            name=identity.get("name"),
            question=question,
            page_url=identity.get("page_url"),
            context=stored_ctx,
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
    route_fn: Callable[[str, Dict[str, Any], bool], Dict[str, Any]] = _default_route,
    explain_fn: Callable[[Dict[str, Any], str], Dict[str, Any]] = _default_explain,
    save_fn: Callable[..., Dict[str, Any]] = _save_member_inquiry,
    supabase: Any = None,
) -> Dict[str, Any]:
    """결선 순수 로직. 의존성 주입 가능(테스트: route/explain/save fake)."""
    routing_ctx = dict(stored_ctx or {})
    r = route_fn(question, routing_ctx, already_asked)
    status = r.get("status")

    if status == "ASK":
        # 저장하지 않음. 추가질문 상태 반환.
        return {"status": "ASK", "missing_field": r.get("missing_field"), "already_asked": True}

    if status == "ERROR":
        return {"status": "ERROR", "detail": r.get("detail") or "routing error"}

    if status == "HANDOFF":
        return _do_handoff(question, stored_ctx, identity, r.get("reason"), save_fn, supabase)

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
            return _do_handoff(question, stored_ctx, identity, "answer_insufficient", save_fn, supabase)
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

    stored_ctx = _build_context(body.context)
    identity = {
        "user_id": user_id,
        "company_id": current_user.get("company_id"),
        "name": current_user.get("name"),
        "page_url": (body.page_url or "").strip() or None,
    }
    return _handle_ask(body.question, stored_ctx, bool(body.already_asked), identity)
