"""SaaS 회원 문의 저장 경로 — Question Context Contract 구현.

설계: docs(tai-www) 2026-08-14_TAI-고객응대-자동화_MVP-설계서.md §8-D, §15(1단계)

- POST /me/inquiries : 로그인 회원이 SaaS 안에서 문의를 접수한다.
- 신원(user_id/company_id)은 Bearer 토큰에서 서버가 파생한다(클라이언트 신뢰 금지).
  → routers.auth.get_current_user 재사용(토큰 검증 → users 행 반환).
- source 는 서버가 항상 "saas" 로 고정한다(이 경로는 SaaS 회원 전용). 클라이언트 입력을 받지 않는다.
- Question Context 보존(안 A · inquiries.context jsonb):
    정규 컬럼(user_id/company_id/page_url/source/content)에 있는 값은 context 에 중복 저장하지 않는다.
    context 에는 화면 Context 만 담는다 — factory_id, object_type, object_id.
    object_type/object_id 는 쌍으로만 저장한다(한쪽만 있으면 둘 다 버린다).
    없는 값은 넣지 않는다(추측 금지). context 가 비면 NULL 로 저장한다.
- 채번은 admin_inquiries._next_inquiry_no 재사용(TAI-INQ-YYYYMMDD-NNNN).
- 운영자 통지는 기존 services.slack_dispatcher.ops 재사용(베스트에포트 — 실패해도 저장 성공).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.admin_inquiries import _next_inquiry_no

logger = logging.getLogger("member_inquiries")
router = APIRouter(prefix="/me", tags=["회원 문의"])

# 이 경로는 SaaS 회원 전용이므로 source 는 서버가 고정한다(클라이언트 입력 금지).
INQUIRY_SOURCE = "saas"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InquiryContextBody(BaseModel):
    # 화면 Context 만. 정규 컬럼과 중복 금지.
    factory_id: Optional[str] = None
    object_type: Optional[str] = None
    object_id: Optional[str] = None


class MemberInquiryBody(BaseModel):
    question: str = Field(..., min_length=1)
    title: Optional[str] = None
    category: Optional[str] = None
    page_url: Optional[str] = None
    context: Optional[InquiryContextBody] = None


def _build_context(ctx: Optional[InquiryContextBody]) -> Optional[Dict[str, Any]]:
    """화면 Context 만 추려 jsonb 로 만든다. 비면 None(→ NULL)."""
    if not ctx:
        return None
    out: Dict[str, Any] = {}
    factory_id = (ctx.factory_id or "").strip() or None
    object_type = (ctx.object_type or "").strip() or None
    object_id = (ctx.object_id or "").strip() or None
    # object_type/object_id 는 쌍으로만 — 한쪽만 있으면 둘 다 버린다.
    if bool(object_type) != bool(object_id):
        object_type = None
        object_id = None
    if factory_id:
        out["factory_id"] = factory_id
    if object_type and object_id:
        out["object_type"] = object_type
        out["object_id"] = object_id
    return out or None


@router.post("/inquiries")
def create_member_inquiry(
    body: MemberInquiryBody,
    current_user: dict = Depends(get_current_user),
):
    """회원 문의 접수 → inquiries 저장(+ context) + Slack 통지(베스트에포트)."""
    supabase = get_supabase()

    # 신원은 토큰에서 서버가 파생한다(클라이언트 신뢰 금지).
    user_id = current_user.get("id")
    company_id = current_user.get("company_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")

    context = _build_context(body.context)

    row: Dict[str, Any] = {
        "no": _next_inquiry_no(supabase),
        "source": INQUIRY_SOURCE,  # 서버 고정 — 클라이언트 입력 안 받음
        "inquiry_type": "INQUIRY",
        "category": (body.category or "saas").strip() or "saas",
        "title": (body.title or "").strip() or None,
        "content": body.question.strip(),
        "name": current_user.get("name") or None,
        "is_member": True,
        "user_id": user_id,
        "company_id": company_id,
        "page_url": (body.page_url or "").strip() or None,
        "status": "RECEIVED",
        "priority": "NORMAL",
        "context": context,  # jsonb — None 이면 NULL
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    try:
        res = supabase.table("inquiries").insert(row).execute()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"저장 실패: {e!s}") from e
    if not res.data:
        raise HTTPException(status_code=500, detail="등록 후 데이터를 확인할 수 없습니다.")
    saved = res.data[0]

    # 운영자 통지(베스트에포트). 실패해도 저장 결과에 영향 없음.
    try:
        from services.slack_dispatcher import ops
        ctx_line = ""
        if context:
            parts = []
            if context.get("factory_id"):
                parts.append(f"factory={context['factory_id']}")
            if context.get("object_type"):
                parts.append(f"{context['object_type']}={context.get('object_id')}")
            if parts:
                ctx_line = "\nContext: " + ", ".join(parts)
        detail = (
            f"회원: {row['name'] or '-'} (user={user_id} / company={company_id or '-'})\n"
            f"화면: {row['page_url'] or '-'}{ctx_line}\n"
            f"내용: {row['content'][:800]}"
        )
        ops(f"새 SaaS 문의 · {row['name'] or '회원'}", detail)
    except Exception:  # noqa: BLE001
        logger.exception("member inquiry slack notify failed")

    return {"status": "success", "data": saved}
